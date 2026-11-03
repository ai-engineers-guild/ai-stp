//! Read-only adoption of exact terminal external-provider ownership.
//! Historical state, archives and ASFW records are preserved, never migrated.

use super::{CONTROLS, invalid, native};
use crate::{
    error::Result,
    files::physical::DirectoryIdentity,
    installation::{
        custody::Ownership, forward, identity, lock::TargetLock, sqlite, target::Target,
    },
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Evidence {
    root: DirectoryIdentity,
    control: DirectoryIdentity,
    state_path: String,
    state: forward::Observation,
    fields_path: String,
    fields: forward::Observation,
    database: Option<forward::Observation>,
    rights: BTreeMap<String, Ownership>,
}
#[cfg(test)]
mod tests;
pub(crate) struct Adoption {
    evidence: Evidence,
    root: [u8; 25],
    _lock: TargetLock,
}
fn names(harness: &str) -> Result<(&'static str, &'static str)> {
    Ok(match harness {
        "codex" => (".codex-setup-system", "NDDEV-CODEX-PROVIDER.json"),
        "claude-code" => (".claude-setup-system", "NDDEV-CLAUDE-PROVIDER.json"),
        "cursor" => (".cursor-setup-system", "NDDEV-CURSOR-PROVIDER.json"),
        "grok-build" => (".grok-setup-system", "NDDEV-GROK-PROVIDER.json"),
        "pi" => (".pi-setup-system", "NDDEV-PI-PROVIDER.json"),
        "opencode" => (".opencode-setup-system", "NDDEV-OPENCODE-PROVIDER.json"),
        "antigravity" => (
            ".antigravity-setup-system",
            "NDDEV-ANTIGRAVITY-PROVIDER.json",
        ),
        _ => return Err(invalid()),
    })
}
fn terminal(control: &cap_std::fs::Dir) -> Result<()> {
    let directory =
        match crate::installation::target::child(control, std::ffi::OsStr::new("forward")) {
            Ok(directory) => directory,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(_) => return Err(invalid()),
        };
    let scope = sqlite::Scope::open(control, "forward", directory, false).map_err(|_| invalid())?;
    let db = rusqlite::Connection::open_with_flags_and_vfs(
        scope.path(),
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_NO_MUTEX,
        sqlite::NAME,
    )
    .map_err(|_| invalid())?;
    db.set_db_config(
        rusqlite::config::DbConfig::SQLITE_DBCONFIG_TRUSTED_SCHEMA,
        false,
    )
    .map_err(|_| invalid())?;
    db.pragma_update(None, "query_only", true)
        .map_err(|_| invalid())?;
    let application: i64 = db
        .pragma_query_value(None, "application_id", |row| row.get(0))
        .map_err(|_| invalid())?;
    let version: u32 = db
        .pragma_query_value(None, "user_version", |row| row.get(0))
        .map_err(|_| invalid())?;
    let active: i64 = db
        .query_row(
            "SELECT count(*) FROM operations WHERE active IS NOT NULL OR phase!='completed'",
            [],
            |row| row.get(0),
        )
        .map_err(|_| invalid())?;
    let payloads: i64 = db
        .query_row("SELECT count(*) FROM changes", [], |row| row.get(0))
        .map_err(|_| invalid())?;
    if application != 0x4153_4657 || ![1, 2].contains(&version) || active != 0 || payloads != 0 {
        return Err(invalid());
    }
    scope.validate().map_err(|_| invalid())
}
impl Adoption {
    pub(crate) fn capture(
        target: &Target,
        harness: &str,
        setup: &Value,
        rights: BTreeMap<String, Ownership>,
    ) -> Result<Self> {
        Self::capture_inner(target, harness, setup, rights, None)
    }
    fn capture_inner(
        target: &Target,
        harness: &str,
        setup: &Value,
        rights: BTreeMap<String, Ownership>,
        marker: Option<&[u8]>,
    ) -> Result<Self> {
        let (name, state_path) = names(harness)?;
        let root = native(target.directory())?;
        let control = crate::installation::target::child(&root, std::ffi::OsStr::new(name))
            .map_err(|_| invalid())?;
        for other in CONTROLS {
            if other == name {
                continue;
            }
            match crate::installation::target::child(&root, std::ffi::OsStr::new(other)) {
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
                Ok(directory) if marker.is_some() => {
                    let journal =
                        native(forward::observe(target, &format!("{other}/journal.json")))?
                            .1
                            .ok_or_else(invalid)?;
                    if Some(journal.bytes.as_slice()) != marker {
                        return Err(invalid());
                    }
                    for entry in directory.entries().map_err(|_| invalid())? {
                        let name = entry.map_err(|_| invalid())?.file_name();
                        if !matches!(name.to_str(), Some("journal.json" | "target.lock")) {
                            return Err(invalid());
                        }
                    }
                }
                _ => return Err(invalid()),
            }
        }
        // Existing legacy mutation locks are used unchanged; never create a
        // substitute lock to reinterpret an unrecognized external directory.
        if native(forward::observe(target, &format!("{name}/target.lock")))?
            .1
            .is_none()
        {
            return Err(invalid());
        }
        let lock = native(TargetLock::acquire_at(&control, &target.root().join(name)))?;
        if let Some(journal) = native(forward::observe(target, &format!("{name}/journal.json")))?.1
            && Some(journal.bytes.as_slice()) != marker
        {
            return Err(invalid());
        }
        terminal(&control).map_err(|_| {
            crate::error::Failure::precondition(
                "legacy forward history is unfinished or has an unsupported layout",
            )
        })?;
        let (state, body) = native(forward::observe(target, state_path))?;
        let body = crate::wire::parse(&body.ok_or_else(invalid)?.bytes)?;
        if body["state_schema"] != 4
            || body["protocol_version"] != 3
            || body["harness_id"] != harness
            || body["provider_version"] != "0.0.95"
            || body["provider_id"] != name.trim_start_matches('.')
            || body["setup_stable_id"] != setup["stable_id"]
            || body["setup_version"] != setup["version"]
            || body["setup_version_passport_digest"] != setup["passport_digest"]
            || body["drift_state"] != "clean"
        {
            return Err(crate::error::Failure::precondition(
                "legacy state does not identify this exact supported setup and harness",
            ));
        }
        let path = Path::new(body["canonical_target"].as_str().ok_or_else(invalid)?);
        let claimed = native(Target::resolve(path, ".ai-stp-native"))?;
        if DirectoryIdentity::capture(&native(claimed.directory())?)?
            != DirectoryIdentity::capture(&root)?
        {
            return Err(invalid());
        }
        let paths = body["written_paths"].as_array().ok_or_else(invalid)?;
        let written = paths
            .iter()
            .map(|path| path.as_str().ok_or_else(invalid))
            .collect::<Result<BTreeSet<_>>>()?;
        if paths.len() != written.len()
            || written != rights.keys().map(String::as_str).collect()
            || rights.is_empty()
            || rights.len() > 2000
        {
            return Err(crate::error::Failure::precondition(
                "legacy written paths do not exactly match the reviewed setup",
            ));
        }
        let fields_path = format!("{name}/written-fields.json");
        let (fields, ledger) = native(forward::observe(target, &fields_path))?;
        let ledger: BTreeMap<String, Vec<String>> = ledger
            .map(|content| {
                serde_json::from_value(crate::wire::parse(&content.bytes)?).map_err(|_| invalid())
            })
            .transpose()?
            .unwrap_or_default();
        for (path, ownership) in &rights {
            match ownership {
                Ownership::Whole if ledger.contains_key(path) => return Err(invalid()),
                Ownership::Contribution { key, .. }
                    if ledger.get(path) != Some(&vec![key.clone()]) =>
                {
                    return Err(invalid());
                }
                _ => (),
            }
        }
        if ledger.keys().any(|path| !rights.contains_key(path)) {
            return Err(invalid());
        }
        let database_path = format!("{name}/forward/{}", sqlite::DATABASE);
        let (database, content) = native(forward::observe(target, &database_path))?;
        let evidence = Evidence {
            root: DirectoryIdentity::capture(&root)?,
            control: DirectoryIdentity::capture(&control)?,
            state_path: state_path.into(),
            state,
            fields_path,
            fields,
            database: content.map(|_| database),
            rights,
        };
        Ok(Self {
            evidence,
            root: identity::directory(&root).map_err(|_| invalid())?,
            _lock: lock,
        })
    }
    pub(crate) fn permits_root(&self, target: &Target) -> bool {
        target
            .directory()
            .ok()
            .and_then(|dir| identity::directory(&dir).ok())
            == Some(self.root)
    }
    pub(crate) fn permits(&self, root: [u8; 25], path: &str, ownership: &Ownership) -> bool {
        root == self.root && self.evidence.rights.get(path) == Some(ownership)
    }
    pub(crate) fn control(&self) -> &str {
        self.evidence.fields_path.split('/').next().unwrap_or("")
    }
    pub(crate) fn evidence(&self) -> Result<Value> {
        serde_json::to_value(&self.evidence).map_err(|_| invalid())
    }
    pub(crate) fn reopen(
        target: &Target,
        harness: &str,
        setup: &Value,
        custody: &crate::installation::custody::Custody,
        value: &Value,
    ) -> Result<Self> {
        let expected = parse(value)?;
        let marker = super::marker(target, custody)?;
        let actual = Self::capture_inner(
            target,
            harness,
            setup,
            expected.rights.clone(),
            Some(&marker),
        )?;
        if actual.evidence()? != *value {
            return Err(invalid());
        }
        Ok(actual)
    }
    pub(crate) fn revalidate(
        &self,
        target: &Target,
        custody: &crate::installation::custody::Custody,
    ) -> Result<()> {
        self._lock.revalidate().map_err(|_| invalid())?;
        let root = native(target.directory())?;
        if DirectoryIdentity::capture(&root)? != self.evidence.root {
            return Err(invalid());
        }
        for (path, expected) in [
            (&self.evidence.state_path, &self.evidence.state),
            (&self.evidence.fields_path, &self.evidence.fields),
        ] {
            if native(forward::observe(target, path))?.0 != *expected {
                return Err(invalid());
            }
        }
        let name = self.control();
        let control = crate::installation::target::child(&root, std::ffi::OsStr::new(name))
            .map_err(|_| invalid())?;
        if DirectoryIdentity::capture(&control)? != self.evidence.control {
            return Err(invalid());
        }
        terminal(&control)?;
        let (database, content) = native(forward::observe(
            target,
            &format!("{name}/forward/{}", sqlite::DATABASE),
        ))?;
        if content.map(|_| database) != self.evidence.database {
            return Err(invalid());
        }
        if let Some(journal) = native(forward::observe(target, &format!("{name}/journal.json")))?.1
            && journal.bytes != super::marker(target, custody)?
        {
            return Err(invalid());
        }
        Ok(())
    }
}

fn parse(value: &Value) -> Result<Evidence> {
    let evidence: Evidence = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    evidence.root.validate()?;
    evidence.control.validate()?;
    if evidence.rights.is_empty()
        || evidence.rights.len() > 2000
        || serde_json::to_value(&evidence).map_err(|_| invalid())? != *value
    {
        return Err(invalid());
    }
    for (path, right) in &evidence.rights {
        if !crate::archive::safe_path(path) {
            return Err(invalid());
        }
        if let Ownership::Contribution { parser_id, key } = right
            && (!matches!(parser_id.as_str(), "toml/1" | "json/1")
                || key.is_empty()
                || key.len() > 255)
        {
            return Err(invalid());
        }
    }
    Ok(evidence)
}
pub(crate) fn validate(value: &Value) -> Result<()> {
    parse(value).map(|_| ())
}
