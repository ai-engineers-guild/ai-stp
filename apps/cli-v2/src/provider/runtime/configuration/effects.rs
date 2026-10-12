//! Expected public file effects derived from the bundle and recorded ownership.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{bundle::Bundle, instructions, invalid};
use crate::{
    authoring::contribution::{self, Format},
    digest,
    error::Result,
    provider::runtime::target::{Target, content::Content},
};

pub(super) fn valid_path(path: &str) -> bool {
    crate::archive::safe_path(path) && path.split('/').count() <= 32
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Fingerprint {
    pub digest: String,
    pub byte_length: usize,
    pub mode: u32,
}

impl Fingerprint {
    fn of(content: &Content) -> Self {
        Self {
            digest: digest::sha256(&content.bytes),
            byte_length: content.bytes.len(),
            mode: content.mode,
        }
    }
    pub fn validate(&self) -> Result<()> {
        if !crate::provider::plan::hash(&self.digest)
            || self.byte_length > 4 * 1024 * 1024
            || self.mode & !0o777 != 0
            || self.mode & 0o400 == 0
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Effect {
    pub path: String,
    pub parents: Vec<[String; 2]>,
    pub before_identity: Option<[String; 2]>,
    pub before: Option<Fingerprint>,
    pub after: Option<Fingerprint>,
}

pub(super) fn expected(
    target: &Target,
    ownership: &Value,
    bundle: Option<&Bundle>,
    attachment: Option<&str>,
) -> Result<Vec<Effect>> {
    let recorded: BTreeMap<&str, &Value> = ownership
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(|row| Ok((row["path"].as_str().ok_or_else(invalid)?, row)))
        .collect::<Result<_>>()?;
    let paths: BTreeSet<&str> = recorded
        .keys()
        .copied()
        .chain(
            bundle
                .into_iter()
                .flat_map(|bundle| bundle.files.keys().map(String::as_str)),
        )
        .collect();
    if paths.len() > 8192 {
        return Err(invalid());
    }
    let mut result = Vec::new();
    let (mut read_bytes, mut desired_bytes) = (0usize, 0usize);
    for path in paths {
        if !valid_path(path) {
            return Err(invalid());
        }
        let observed = target.observe(path)?;
        let current = observed.content;
        read_bytes += current.as_ref().map_or(0, |content| content.bytes.len());
        if read_bytes > 64 * 1024 * 1024 {
            return Err(invalid());
        }
        let row = recorded.get(path);
        let keys = row
            .filter(|row| row["ownership"] == "contribution")
            .map(|row| {
                row["ownership_keys"]
                    .as_array()
                    .ok_or_else(invalid)?
                    .iter()
                    .map(|value| value.as_str().map(str::to_owned).ok_or_else(invalid))
                    .collect::<Result<Vec<_>>>()
            })
            .transpose()?;
        let incoming = bundle.and_then(|bundle| bundle.files.get(path));
        let after = if let Some(claim) = incoming.and_then(|file| file.contribution.as_ref()) {
            let incoming = incoming.ok_or_else(invalid)?;
            let format = Format::for_path(path)?;
            let parser = if format == Format::Toml {
                "toml/1"
            } else {
                "json/1"
            };
            let observed = current
                .as_ref()
                .map_or(Value::Null, |content| digest::sha256(&content.bytes).into());
            if claim["parser_id"] != parser
                || claim["host_digest"] != observed
                || row.is_some() && keys.is_none()
            {
                return Err(invalid());
            }
            let name = claim["ownership_key"].as_str().ok_or_else(invalid)?;
            let empty: &[u8] = if format == Format::Toml { b"" } else { b"{}" };
            Some(Content {
                bytes: contribution::reconcile(
                    format,
                    current.as_ref().map_or(empty, |content| &content.bytes),
                    keys.as_deref().unwrap_or_default(),
                    Some((name, &incoming.bytes)),
                )?,
                mode: current
                    .as_ref()
                    .map_or(incoming.mode, |content| content.mode & incoming.mode),
            })
        } else if let Some(keys) = keys {
            if incoming.is_some() {
                return Err(invalid());
            }
            current
                .as_ref()
                .map(|content| {
                    Ok(Content {
                        bytes: contribution::reconcile(
                            Format::for_path(path)?,
                            &content.bytes,
                            &keys,
                            None,
                        )?,
                        mode: content.mode,
                    })
                })
                .transpose()?
        } else if attachment == Some(path) {
            instructions::desired(
                current.as_ref().map(|content| content.bytes.as_slice()),
                incoming.map(|file| file.bytes.as_slice()),
                row.is_some(),
            )?
            .map(|bytes| Content {
                bytes,
                mode: match (current.as_ref(), incoming) {
                    (Some(content), Some(file)) => content.mode & file.mode,
                    (Some(content), None) => content.mode,
                    (None, Some(file)) => file.mode,
                    (None, None) => 0o600,
                },
            })
        } else {
            if row.is_none()
                && let (Some(current), Some(incoming)) = (&current, incoming)
                && current.bytes != incoming.bytes
            {
                return Err(invalid());
            }
            incoming.map(|file| Content {
                bytes: file.bytes.clone(),
                mode: file.mode,
            })
        };
        desired_bytes += after.as_ref().map_or(0, |content| content.bytes.len());
        if desired_bytes > 64 * 1024 * 1024 {
            return Err(invalid());
        }
        result.push(Effect {
            path: path.into(),
            parents: observed.parents,
            before_identity: observed.identity,
            before: current.as_ref().map(Fingerprint::of),
            after: after.as_ref().map(Fingerprint::of),
        });
    }
    validate(&result)?;
    Ok(result)
}

pub(super) fn validate(effects: &[Effect]) -> Result<()> {
    if effects.len() > 8192 || effects.windows(2).any(|pair| pair[0].path >= pair[1].path) {
        return Err(invalid());
    }
    for effect in effects {
        if !valid_path(&effect.path)
            || effect.parents.is_empty()
            || effect.parents.len() > effect.path.split('/').count()
            || effect.before.is_some() != effect.before_identity.is_some()
            || effect
                .parents
                .iter()
                .chain(effect.before_identity.iter())
                .flatten()
                .any(|part| {
                    !part
                        .parse::<u64>()
                        .is_ok_and(|number| number.to_string() == *part)
                })
        {
            return Err(invalid());
        }
        for value in [&effect.before, &effect.after].into_iter().flatten() {
            value.validate()?;
        }
    }
    Ok(())
}

pub(super) fn verify(target: &Target, effects: &[Effect], final_state: bool) -> Result<()> {
    validate(effects)?;
    for effect in effects {
        let expected = if final_state {
            &effect.after
        } else {
            &effect.before
        };
        let observed = target.observe(&effect.path)?;
        if &observed.content.as_ref().map(Fingerprint::of) != expected
            || !observed.parents.starts_with(&effect.parents)
            || !final_state
                && (observed.parents != effect.parents
                    || observed.identity != effect.before_identity)
        {
            return Err(invalid());
        }
    }
    target.revalidate()
}
