//! Authenticated Sigstore trust refresh with mandatory persistent rollback floors.

mod metadata;
mod storage;
#[cfg(test)]
mod tests;
mod transport;

use std::path::Path;

use cap_std::fs::Dir;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256, Sha512};
use sigstore_tuf::{Root, Targets, metadata::Role};
use sigstore_verify::trust_root::TrustedRoot;

use crate::{
    digest,
    error::{Failure, Result},
};

const MAX_METADATA: usize = 1024 * 1024;
const BOOTSTRAP: &[u8] = include_bytes!("trust/bootstrap.json");
const TARGET: &str = "trusted_root.json";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct State {
    schema_version: u8,
    roots: Vec<String>,
    timestamp: Option<Evidence>,
    snapshot: Option<Evidence>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Evidence {
    root_index: usize,
    bytes: String,
}

impl Default for State {
    fn default() -> Self {
        Self {
            schema_version: 1,
            roots: Vec::new(),
            timestamp: None,
            snapshot: None,
        }
    }
}

/// Only authenticated refresh constructs this material; it cannot be deserialized.
pub struct Material {
    root: TrustedRoot,
    report: Value,
    expires: jiff::Timestamp,
}

impl Material {
    pub fn root(&self) -> Result<&TrustedRoot> {
        if jiff::Timestamp::now() >= self.expires {
            return Err(invalid());
        }
        Ok(&self.root)
    }
    pub fn report(&self) -> &Value {
        &self.report
    }
}

fn invalid() -> Failure {
    Failure::precondition(
        "Sigstore trust metadata, freshness, durable state or rollback protection was refused",
    )
}

trait Repository {
    fn get(&mut self, name: &str, target: bool, limit: usize) -> Result<Option<Vec<u8>>>;
}

/// The supplied parent must already exist. Only its private trust state is written.
pub fn refresh(parent: &Path) -> Result<Material> {
    let parent =
        Dir::open_ambient_dir(parent, cap_std::ambient_authority()).map_err(|_| invalid())?;
    refresh_at(&parent)
}

pub(crate) fn refresh_at(parent: &Dir) -> Result<Material> {
    run_at(
        parent,
        BOOTSTRAP,
        &mut transport::Http::new(),
        jiff::Timestamp::now(),
    )
}

fn required(repo: &mut impl Repository, name: &str, target: bool, limit: usize) -> Result<Vec<u8>> {
    repo.get(name, target, limit)?
        .filter(|bytes| !bytes.is_empty() && bytes.len() <= limit)
        .ok_or_else(invalid)
}

#[cfg(test)]
fn run(
    parent: &Path,
    bootstrap: &[u8],
    repo: &mut impl Repository,
    now: jiff::Timestamp,
) -> Result<Material> {
    let parent =
        Dir::open_ambient_dir(parent, cap_std::ambient_authority()).map_err(|_| invalid())?;
    run_at(&parent, bootstrap, repo, now)
}

fn run_at(
    parent: &Dir,
    bootstrap: &[u8],
    repo: &mut impl Repository,
    now: jiff::Timestamp,
) -> Result<Material> {
    let (storage, mut state) = storage::Storage::open(parent)?;
    let (mut trusted, mut floors) = metadata::restore(&state, bootstrap)?;
    // Publish initialization only after all retained evidence has been reverified.
    storage.save(&state)?;
    for attempt in 0..=32 {
        let next = trusted.root().version.checked_add(1).ok_or_else(invalid)?;
        let Some(bytes) = repo.get(&format!("{next}.root.json"), false, 64 * 1024)? else {
            break;
        };
        if attempt == 32 || bytes.len() > 64 * 1024 || state.roots.len() >= 256 {
            return Err(invalid());
        }
        let new = metadata::parse::<Root>(&bytes)?;
        let reset = metadata::online_keys_changed(trusted.root(), new.signed())?;
        trusted.update_root(&bytes).map_err(|_| invalid())?;
        if reset {
            state.timestamp = None;
            state.snapshot = None;
            floors = metadata::Floors::default();
        }
        state
            .roots
            .push(String::from_utf8(bytes).map_err(|_| invalid())?);
        // Root revocation progress survives a later network or metadata failure.
        storage.save(&state)?;
    }
    metadata::fresh(trusted.root(), now)?;
    let timestamp = required(repo, "timestamp.json", false, MAX_METADATA)?;
    state.timestamp = Some(Evidence {
        root_index: state.roots.len(),
        bytes: metadata::timestamp(&mut trusted, &floors, &timestamp, now)?,
    });
    storage.save(&state)?;
    let version = trusted
        .timestamp()
        .and_then(|ts| ts.snapshot_meta())
        .ok_or_else(invalid)?
        .version;
    let snapshot_name = if trusted.root().consistent_snapshot {
        format!("{version}.snapshot.json")
    } else {
        "snapshot.json".into()
    };
    let snapshot = required(repo, &snapshot_name, false, MAX_METADATA)?;
    state.snapshot = Some(Evidence {
        root_index: state.roots.len(),
        bytes: metadata::snapshot(&mut trusted, &floors, &snapshot, now)?,
    });
    storage.save(&state)?;
    let version = trusted
        .snapshot()
        .and_then(|snapshot| snapshot.meta.get("targets.json"))
        .ok_or_else(invalid)?
        .version;
    let targets_name = if trusted.root().consistent_snapshot {
        format!("{version}.targets.json")
    } else {
        "targets.json".into()
    };
    let targets = required(repo, &targets_name, false, MAX_METADATA)?;
    let parsed = metadata::parse::<Targets>(&targets)?;
    metadata::fresh(parsed.signed(), now)?;
    let targets = trusted
        .update_targets(&targets, now)
        .map_err(|_| invalid())?;
    // Only Sigstore's top-level trust target is needed; delegation is not inferred.
    let target = targets.target(TARGET).ok_or_else(invalid)?.clone();
    if target.length == 0 || target.length > MAX_METADATA as u64 {
        return Err(invalid());
    }
    let hash = target.hashes.get("sha256").ok_or_else(invalid)?;
    if hash.len() != 64
        || !hash
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    {
        return Err(invalid());
    }
    let name = if trusted.root().consistent_snapshot {
        format!("{hash}.{TARGET}")
    } else {
        TARGET.into()
    };
    let bytes = required(repo, &name, true, target.length as usize)?;
    if bytes.len() as u64 != target.length {
        return Err(invalid());
    }
    for (algorithm, expected) in &target.hashes {
        let actual = match algorithm.as_str() {
            "sha256" => Sha256::digest(&bytes)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>(),
            "sha512" => Sha512::digest(&bytes)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>(),
            _ => continue,
        };
        if !actual.eq_ignore_ascii_case(expected) {
            return Err(invalid());
        }
    }
    let text = std::str::from_utf8(&bytes).map_err(|_| invalid())?;
    crate::wire::parse(&bytes)?;
    let root = TrustedRoot::from_json(text).map_err(|_| invalid())?;
    let expires = [
        trusted.root().expires_at(),
        trusted.timestamp().ok_or_else(invalid)?.expires_at(),
        trusted.snapshot().ok_or_else(invalid)?.expires_at(),
        parsed.signed().expires_at(),
    ]
    .into_iter()
    .collect::<std::result::Result<Vec<_>, _>>()
    .map_err(|_| invalid())?
    .into_iter()
    .min()
    .ok_or_else(invalid)?;
    Ok(Material {
        root,
        expires,
        report: json!({"bootstrap_digest":digest::sha256(bootstrap), "root_version":trusted.root().version,
        "observed_at":now.to_string(),"expires_at":expires.to_string(),
        "timestamp_version":trusted.timestamp().ok_or_else(invalid)?.version,"snapshot_version":trusted.snapshot().ok_or_else(invalid)?.version,
        "targets_version":parsed.signed().version,"target_digest":digest::sha256(&bytes),"target_bytes":bytes.len()}),
    })
}
