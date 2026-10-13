//! Namespace admission fencing and durable reservations for unfinished roots.

use cap_std::fs::Dir;
use rusqlite::Connection;
use std::path::Path;

use super::{identity, invalid, plan::Plan};
use crate::{
    digest,
    error::Result,
    files::OwnedDirectory,
    provider::{configuration::record::Record, runtime::target::Target},
    store::{Store, database},
};

const NAMESPACE: &str = "configuration-operations";
const PREVIOUS_OWNER: &[u8] = b"ai-stp-cli-v2:configuration-operations/v1\n";
const OWNER: &[u8] = b"ai-stp-cli-v2:configuration-operations/v2\n";

pub(super) fn target_key(plan: &Plan) -> String {
    digest::sha256(format!("{}:{}", plan.target_identity[0], plan.target_identity[1]).as_bytes())
}

pub(super) fn target_owner(key: &str) -> Vec<u8> {
    format!("ai-stp:configuration-target/v1\n{key}\n").into_bytes()
}

pub(super) fn namespace(parent: &Dir, migrate: bool) -> Result<OwnedDirectory> {
    let namespace =
        OwnedDirectory::open_compatible(parent, NAMESPACE, OWNER, &[PREVIOUS_OWNER], true)?
            .ok_or_else(invalid)?;
    namespace.validate_lock()?;
    if migrate && namespace.read_file("owner", 256)?.as_deref() == Some(PREVIOUS_OWNER) {
        // An older writer releases this namespace before SQLite admission but
        // retains its target lock until its final effect/receipt. Drain those
        // locks while excluding new old admissions, then fence that executable.
        // There is no interval where a SQLite-only idle check grants authority.
        for entry in namespace.directory.entries().map_err(|_| invalid())? {
            let entry = entry.map_err(|_| invalid())?;
            let name = entry.file_name();
            let name = name.to_str().ok_or_else(invalid)?;
            if let Some(suffix) = name.strip_prefix("target-") {
                let key = format!("sha256:{suffix}");
                if !crate::provider::plan::hash(&key) {
                    return Err(invalid());
                }
                let lock = OwnedDirectory::open_at(
                    &namespace.directory,
                    name,
                    &target_owner(&key),
                    false,
                )?;
                if let Some(lock) = lock {
                    lock.validate_lock()?;
                }
            } else if !matches!(name, "owner" | "lock")
                && !crate::passport::stable_id(name, "operation")
                && !name
                    .strip_prefix(".tmp-")
                    .is_some_and(|suffix| suffix.parse::<ulid::Ulid>().is_ok())
            {
                return Err(invalid());
            }
        }
        // A legacy namespace may already contain overlapping unfinished work.
        // Fencing its writers before that work is reconciled would strand both
        // operations. Leave the previous marker intact on this refusal.
        let store = Store::planning_at(parent)?;
        let mut query = store
            .connection
            .prepare(
                "SELECT kind,state,coalesce(detail,'') FROM operation WHERE state='applying' \
             AND kind IN ('configuration.install','configuration.replace','configuration.remove')",
            )
            .map_err(database)?;
        let mut rows = query.query([]).map_err(database)?;
        while let Some(row) = rows.next().map_err(database)? {
            let kind: String = row.get(0).map_err(database)?;
            let state: String = row.get(1).map_err(database)?;
            let detail: String = row.get(2).map_err(database)?;
            let (_, plan) = Record::parse(&detail, &kind, &state)?;
            available(&store.connection, &plan)?;
        }
        namespace.atomic("owner", OWNER)?;
    }
    Ok(namespace)
}

pub(super) fn available(connection: &Connection, plan: &Plan) -> Result<()> {
    let mut query = connection
        .prepare(
            "SELECT kind,state,coalesce(detail,'') FROM operation WHERE state='applying' \
         AND kind IN ('configuration.install','configuration.replace','configuration.remove') \
         AND operation_id<>? ORDER BY operation_id",
        )
        .map_err(database)?;
    let mut rows = query.query([&plan.operation_id]).map_err(database)?;
    let mut target = None;
    while let Some(row) = rows.next().map_err(database)? {
        let kind: String = row.get(0).map_err(database)?;
        let state: String = row.get(1).map_err(database)?;
        let detail: String = row.get(2).map_err(database)?;
        let (_, held) = Record::parse(&detail, &kind, &state)?;
        if held.state_parent != plan.state_parent || held.state_identity != plan.state_identity {
            return Err(invalid());
        }
        if plan.target_identity == held.target_identity
            || Path::new(&plan.target_path).starts_with(&held.target_path)
            || Path::new(&held.target_path).starts_with(&plan.target_path)
        {
            return Err(invalid());
        }
        if target.is_none() {
            let opened = Target::open(Path::new(&plan.target_path))?;
            if identity(&opened)? != plan.target_identity {
                return Err(invalid());
            }
            target = Some(opened);
        }
        // Textually different paths may still alias through bind mounts. If an
        // unfinished target disappeared or was substituted, its reservation
        // cannot be silently forgotten or declared physically disjoint.
        let other = Target::open(Path::new(&held.target_path))?;
        if identity(&other)? != held.target_identity {
            return Err(invalid());
        }
        target
            .as_ref()
            .ok_or_else(invalid)?
            .disjoint(&other.directory()?)?;
        other.revalidate()?;
    }
    Ok(())
}
