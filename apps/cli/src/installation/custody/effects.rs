//! Materialize only the reviewed ownership effects for the qualified writer.

use super::{
    Ownership, Review, invalid,
    model::{Root, Value as OwnedValue},
    native,
};
use crate::{
    authoring::contribution::{self, Format},
    error::Result,
    installation::{forward, target::Target},
};
use std::collections::BTreeMap;

impl Review {
    /// Build complete desired file bytes from the exact current host and the
    /// reviewed owned values. Incoming unowned fields never become write rights.
    /// This creates no transaction and grants no execution authority.
    pub fn configuration_changes(
        &self,
        target: &Target,
        desired: &BTreeMap<String, forward::Content>,
    ) -> Result<Vec<forward::Change>> {
        self.digest()?;
        let root = Root::capture(target)?;
        let mut groups = BTreeMap::<_, Vec<_>>::new();
        for effect in &self.effects {
            if effect.locator.root == root {
                groups
                    .entry(effect.locator.path.as_str())
                    .or_default()
                    .push(effect);
            }
        }
        if desired
            .keys()
            .any(|path| !groups.contains_key(path.as_str()))
        {
            return Err(invalid());
        }
        let mut changes = Vec::new();
        for (path, effects) in groups {
            let (before, current) = native(forward::observe(target, path))?;
            for effect in &effects {
                let observed = effect.locator.observe()?;
                if observed.before != effect.observation
                    || observed.value != effect.before
                    || before != effect.observation
                {
                    return Err(invalid());
                }
            }
            let incoming = desired.get(path);
            let after = match &effects[0].locator.ownership {
                Ownership::Whole => {
                    if effects.len() != 1 {
                        return Err(invalid());
                    }
                    let effect = effects[0];
                    if effect.after.is_none() {
                        if incoming.is_some() {
                            return Err(invalid());
                        }
                        None
                    } else {
                        Some(incoming.or(current.as_ref()).ok_or_else(invalid)?.clone())
                    }
                }
                ownership @ Ownership::Contribution { .. } => {
                    let format = ownership.format(path)?;
                    if incoming
                        .zip(current.as_ref())
                        .is_some_and(|(a, b)| a.mode != b.mode)
                    {
                        return Err(invalid());
                    }
                    let mode = current.as_ref().or(incoming).ok_or_else(invalid)?.mode;
                    let mut host = current
                        .as_ref()
                        .map(|v| v.bytes.clone())
                        .unwrap_or_else(|| {
                            if format == Format::Toml {
                                Vec::new()
                            } else {
                                b"{}\n".to_vec()
                            }
                        });
                    for effect in &effects {
                        let kind = &effect.locator.ownership;
                        let Ownership::Contribution { key, .. } = kind else {
                            return Err(invalid());
                        };
                        if kind.format(path)? != format {
                            return Err(invalid());
                        }
                        if effect.after.is_none() {
                            host = contribution::reconcile(
                                format,
                                &host,
                                std::slice::from_ref(key),
                                None,
                            )?;
                        } else if let Some(incoming) = incoming {
                            host = contribution::reconcile(
                                format,
                                &host,
                                &[],
                                Some((key, &incoming.bytes)),
                            )?;
                        } else if effect.before != effect.after {
                            return Err(invalid());
                        }
                    }
                    Some(native(forward::Content::new(host, mode))?)
                }
            };
            for effect in &effects {
                let actual = after
                    .as_ref()
                    .map(|content| {
                        OwnedValue::of(
                            &effect.locator.ownership,
                            path,
                            &content.bytes,
                            content.mode,
                        )
                    })
                    .transpose();
                let actual = match actual {
                    Ok(value) => value,
                    Err(error) if matches!(error.kind, crate::error::ErrorKind::NotFound) => None,
                    Err(error) => return Err(error),
                };
                if actual != effect.after {
                    return Err(invalid());
                }
            }
            let same = match (&current, &after) {
                (None, None) => true,
                (Some(a), Some(b)) => a.bytes == b.bytes && a.mode == b.mode,
                _ => false,
            };
            if !same {
                changes.push(forward::Change {
                    path: path.into(),
                    before,
                    after,
                });
            }
        }
        native(forward::validate_changes(&changes))?;
        Ok(changes)
    }
}
