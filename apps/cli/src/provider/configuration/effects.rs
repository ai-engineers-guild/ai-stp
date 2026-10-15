//! Portable expected file effects; observation belongs to the platform runtime.

use super::invalid;
use crate::error::Result;
use serde::{Deserialize, Serialize};

pub(crate) fn valid_path(path: &str) -> bool {
    crate::archive::safe_path(path) && path.split('/').count() <= 32
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Fingerprint {
    pub digest: String,
    pub byte_length: usize,
    pub mode: u32,
}

impl Fingerprint {
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
pub(crate) struct Effect {
    pub path: String,
    pub parents: Vec<[String; 2]>,
    pub before_identity: Option<[String; 2]>,
    pub before: Option<Fingerprint>,
    pub after: Option<Fingerprint>,
}

pub(crate) fn validate(effects: &[Effect]) -> Result<()> {
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
