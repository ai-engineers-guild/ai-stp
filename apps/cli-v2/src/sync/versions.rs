//! Immutable version closure carried as metadata, never as artifact availability.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    passport,
};

pub const MAX_VERSIONS: usize = 128;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
pub struct Binding {
    pub version: String,
    pub passport_digest: String,
    pub revision_id: String,
    pub created_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub snapshot: Option<Value>,
}

fn invalid() -> Failure {
    Failure::input("a private sync version does not match its immutable coordinates")
}

impl Binding {
    pub fn coordinates(&self) -> Result<(i64, i64)> {
        if !passport::version_number(&self.version) {
            return Err(invalid());
        }
        let (major, minor) = self.version.split_once('.').ok_or_else(invalid)?;
        Ok((
            major.parse().map_err(|_| invalid())?,
            minor.parse().map_err(|_| invalid())?,
        ))
    }

    fn read(value: &Value, id: &str, kind: &str) -> Result<Self> {
        let mut item: Self = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
        // A present null snapshot is malformed, not a legacy omitted snapshot.
        item.snapshot = value.get("snapshot").cloned();
        item.coordinates()?;
        let hex = |value: &str, prefix: &str| {
            value.strip_prefix(prefix).is_some_and(|v| {
                v.len() == 64
                    && v.bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            })
        };
        if !passport::timestamp(&item.created_at)
            || !hex(&item.passport_digest, "sha256:")
            || !hex(&item.revision_id, "revision_")
        {
            return Err(invalid());
        }
        if let Some(snapshot) = &item.snapshot {
            passport::validate(snapshot)?;
            if snapshot["stable_id"] != id
                || snapshot["kind"] != kind
                || snapshot["revision_id"] != item.revision_id
                || !snapshot["parent_revision_ids"]
                    .as_array()
                    .is_some_and(Vec::is_empty)
                || snapshot.get("version").is_some_and(|v| v != &item.version)
                || digest::canonical("ai-stp:passport:v1", snapshot)? != item.passport_digest
            {
                return Err(invalid());
            }
        }
        Ok(item)
    }
}

pub fn bindings(payload: &Value, id: &str, kind: &str) -> Result<Vec<Binding>> {
    let Some(raw) = payload.get("sync_released_versions") else {
        return Ok(Vec::new());
    };
    let raw = raw
        .as_array()
        .filter(|v| v.len() <= MAX_VERSIONS)
        .ok_or_else(invalid)?;
    if !raw.is_empty() && !matches!(kind, "component" | "setup") {
        return Err(invalid());
    }
    let mut seen = BTreeMap::new();
    let mut result = Vec::with_capacity(raw.len());
    for raw in raw {
        let item = Binding::read(raw, id, kind)?;
        let coordinates = (item.passport_digest.clone(), item.revision_id.clone());
        if seen
            .insert(item.version.clone(), coordinates.clone())
            .is_some_and(|previous| previous != coordinates)
        {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "one sync payload binds a version number to different content",
            ));
        }
        result.push(item);
    }
    Ok(result)
}
