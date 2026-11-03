//! Exact full-file effect fingerprints, including native compatibility guards.

use super::{Review, invalid, model::Root, native};
use crate::{
    digest,
    error::Result,
    installation::{forward, target::Target},
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Content {
    digest: String,
    byte_length: usize,
    mode: u32,
}
#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Publication {
    root: Root,
    path: String,
    sequence: usize,
    before: forward::Observation,
    after: Option<Content>,
}
fn capture(target: &Target, changes: &[forward::Change]) -> Result<Vec<Publication>> {
    native(forward::validate_changes(changes))?;
    let root = Root::capture(target)?;
    changes
        .iter()
        .enumerate()
        .map(|(sequence, change)| {
            if target.is_internal(&change.path) {
                return Err(invalid());
            }
            Ok(Publication {
                root: root.clone(),
                path: change.path.clone(),
                sequence,
                before: change.before.clone(),
                after: change.after.as_ref().map(|content| Content {
                    digest: digest::sha256(&content.bytes),
                    byte_length: content.bytes.len(),
                    mode: content.mode,
                }),
            })
        })
        .collect()
}
pub(super) fn validate(publications: &[Publication]) -> Result<()> {
    if publications.len() > 8192 {
        return Err(invalid());
    }
    let mut paths = BTreeSet::new();
    let mut total = 0_usize;
    for item in publications {
        if !item.root.path.is_absolute()
            || !matches!(item.root.identity[0], 1 | 2)
            || !crate::archive::safe_path(&item.path)
            || item.path.split('/').count() > 32
            || !paths.insert((
                item.root.identity,
                unicase::UniCase::new(item.path.as_str()),
            ))
        {
            return Err(invalid());
        }
        if let Some(content) = &item.after {
            total = total.checked_add(content.byte_length).ok_or_else(invalid)?;
            if !crate::provider::plan::hash(&content.digest)
                || content.byte_length > 4 * 1024 * 1024
                || content.mode & !0o777 != 0
                || content.mode & 0o400 == 0
            {
                return Err(invalid());
            }
        }
    }
    if total > 64 * 1024 * 1024 {
        return Err(invalid());
    }
    Ok(())
}
impl Review {
    /// Number of actual configuration changes, excluding fixed legacy guards.
    pub fn configuration_effect_count(&self) -> Result<usize> {
        self.digest()?;
        Ok(self
            .publications
            .as_ref()
            .ok_or_else(invalid)?
            .iter()
            .filter(|p| !crate::installation::legacy::is_guard(&p.path))
            .count())
    }
    /// Freeze every complete file effect, including compatibility metadata.
    /// The retained document contains fingerprints rather than host payloads.
    pub fn bind_publications(mut self, roots: &[(&Target, &[forward::Change])]) -> Result<Self> {
        if self.publications.is_some() {
            return Err(invalid());
        }
        let mut publications = Vec::new();
        for (target, changes) in roots {
            publications.extend(capture(target, changes)?);
        }
        publications.sort_by_key(|a| (a.root.identity, a.sequence));
        validate(&publications)?;
        self.publications = Some(publications);
        self.digest()?;
        Ok(self)
    }
    /// Refuse a changed desired host, mode, observation or root before admission.
    pub fn verify_publications(&self, target: &Target, changes: &[forward::Change]) -> Result<()> {
        self.digest()?;
        let root = Root::capture(target)?;
        let expected = self.publications.as_ref().ok_or_else(invalid)?;
        let expected: Vec<_> = expected
            .iter()
            .filter(|p| p.root == root)
            .cloned()
            .collect();
        let mut actual = capture(target, changes)?;
        actual.sort_by_key(|a| a.sequence);
        if actual != expected {
            return Err(invalid());
        }
        Ok(())
    }
}
