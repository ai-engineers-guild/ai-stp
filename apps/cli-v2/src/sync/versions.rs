//! Immutable version closure carried as metadata, never as artifact availability.

use std::collections::BTreeMap;

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
    store::{
        database,
        revisions::{self, Write},
    },
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

fn collision() -> Failure {
    Failure::new(
        ErrorKind::Conflict,
        "a sync version number already names different immutable content",
    )
}

/// Preserve exact historical coordinates; only complete native passports are
/// materializable. A generic legacy envelope remains metadata, not an artifact.
pub(super) fn receive(
    t: &Transaction<'_>,
    scope: &super::ledger::Scope,
    id: &str,
    kind: &str,
    event_id: &str,
    device_id: &str,
    item: &Binding,
) -> Result<()> {
    // Page admission already checked the scope and bindings in this transaction;
    // reconciliation validates retained bindings before calling this writer.
    let (major, minor) = item.coordinates()?;
    for (sql, arguments) in [
        (
            "SELECT passport_digest,revision_id FROM object_version WHERE stable_id=? AND version=?",
            vec![id, item.version.as_str()],
        ),
        (
            "SELECT passport_digest,revision_id FROM sync_pending_version WHERE account_id=? AND stable_id=? AND version=?",
            vec![scope.account(), id, item.version.as_str()],
        ),
    ] {
        let held: Option<(String, String)> = t
            .query_row(sql, rusqlite::params_from_iter(arguments), |r| {
                Ok((r.get(0)?, r.get(1)?))
            })
            .optional()
            .map_err(database)?;
        if held.is_some_and(|(hash, revision)| {
            hash != item.passport_digest || revision != item.revision_id
        }) {
            return Err(collision());
        }
    }
    if let Some(snapshot) = &item.snapshot {
        revisions::commit(
            t,
            snapshot,
            device_id,
            None,
            Write::ReceivedSnapshot {
                account_id: scope.account(),
            },
        )?;
    }
    let present: bool = t
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM revision WHERE revision_id=?)",
            [&item.revision_id],
            |r| r.get(0),
        )
        .map_err(database)?;
    if !present {
        t.execute("INSERT INTO sync_pending_version(account_id,stable_id,version,passport_digest,revision_id,created_at,event_id) VALUES (?,?,?,?,?,?,?) ON CONFLICT(account_id,stable_id,version) DO NOTHING",
            params![scope.account(),id,item.version,item.passport_digest,item.revision_id,item.created_at,event_id]).map_err(database)?;
        return Ok(());
    }
    let document = Objects { connection: t }.revision(&item.revision_id)?;
    if document["stable_id"] != id
        || document["kind"] != kind
        || document.get("version").is_some_and(|v| v != &item.version)
        || digest::canonical("ai-stp:passport:v1", &document)? != item.passport_digest
    {
        return Err(invalid());
    }
    t.execute("INSERT INTO object_version(stable_id,version,major,minor,passport_digest,revision_id,created_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(stable_id,version) DO NOTHING",
        params![id,item.version,major,minor,item.passport_digest,item.revision_id,item.created_at]).map_err(database)?;
    // This also checks numeric coordinates already retained by an idempotent insert.
    Objects { connection: t }.version_metadata(id, &item.version, Some(&item.passport_digest))?;
    t.execute(
        "DELETE FROM sync_pending_version WHERE account_id=? AND stable_id=? AND version=?",
        params![scope.account(), id, item.version],
    )
    .map_err(database)?;
    Ok(())
}

pub(super) fn reconcile(t: &Transaction<'_>, scope: &super::ledger::Scope) -> Result<()> {
    let mut statement = t.prepare("SELECT p.stable_id,e.kind,p.version,p.passport_digest,p.revision_id,p.created_at,p.event_id FROM sync_pending_version p JOIN revision r ON r.revision_id=p.revision_id JOIN entity e ON e.stable_id=p.stable_id WHERE p.account_id=? LIMIT 16385").map_err(database)?;
    let rows = statement
        .query_map([scope.account()], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                Binding {
                    version: r.get(2)?,
                    passport_digest: r.get(3)?,
                    revision_id: r.get(4)?,
                    created_at: r.get(5)?,
                    snapshot: None,
                },
                r.get::<_, String>(6)?,
            ))
        })
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if rows.len() > 16384 {
        return Err(Failure::precondition(
            "pending sync version reconciliation exceeds its bound",
        ));
    }
    for (id, kind, binding, event) in rows {
        Binding::read(
            &serde_json::to_value(&binding).map_err(|_| invalid())?,
            &id,
            &kind,
        )?;
        receive(t, scope, &id, &kind, &event, "", &binding)?;
    }
    Ok(())
}

pub fn outgoing(connection: &Connection, id: &str, kind: &str) -> Result<Vec<Binding>> {
    let mut query = connection.prepare("SELECT version,passport_digest,revision_id,created_at FROM object_version WHERE stable_id=? ORDER BY major,minor LIMIT 129").map_err(database)?;
    let items = query
        .query_map([id], |r| {
            Ok(Binding {
                version: r.get(0)?,
                passport_digest: r.get(1)?,
                revision_id: r.get(2)?,
                created_at: r.get(3)?,
                snapshot: None,
            })
        })
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if items.len() > MAX_VERSIONS {
        return Err(invalid());
    }
    items
        .into_iter()
        .map(|mut item| {
            let document = Objects { connection }.version_metadata(
                id,
                &item.version,
                Some(&item.passport_digest),
            )?;
            if document["revision_id"] != item.revision_id {
                return Err(invalid());
            }
            if document["parent_revision_ids"]
                .as_array()
                .is_some_and(Vec::is_empty)
            {
                item.snapshot = Some(document);
            }
            Binding::read(
                &serde_json::to_value(&item).map_err(|_| invalid())?,
                id,
                kind,
            )
        })
        .collect()
}
