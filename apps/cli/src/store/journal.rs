//! Operation receipts bind the operation identity, kind and exact planned effect.

use rusqlite::{Connection, OptionalExtension, Transaction};

use super::database;
use crate::error::{ErrorKind, Failure, Result};

pub(crate) fn checkout_unlink_epoch(connection: &Connection) -> Result<bool> {
    let version: u32 = connection
        .pragma_query_value(None, "user_version", |row| row.get(0))
        .map_err(database)?;
    let enabled = super::has_checkout_unlinks(version);
    if !enabled
        && connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM operation WHERE kind='corporate.project_unlink')",
                [],
                |row| row.get::<_, bool>(0),
            )
            .map_err(database)?
    {
        return Err(Failure::precondition(
            "native unlink records require their explicit registry epoch",
        ));
    }
    Ok(enabled)
}

/// Keep every admitted remote intent within the device-replacement receipt's
/// existing bound. Check only new admissions: retained work can still settle.
pub(crate) fn recovery_capacity(t: &Transaction<'_>, additional: i64) -> Result<()> {
    let unlink = checkout_unlink_epoch(t)?;
    let pending: i64 = t.query_row(
        "SELECT count(*) FROM operation WHERE (kind IN ('sync.run','publication.run','publication.set','corporate.project_link') OR (kind='corporate.project_unlink' AND ?)) AND finished_at IS NULL",
        [unlink], |r| r.get(0)).map_err(database)?;
    if !(1..=2).contains(&additional) || pending > 128 - additional {
        return Err(Failure::precondition(
            "finish an outstanding operation before admitting another recoverable remote intent",
        ));
    }
    Ok(())
}

/// Admission to historical, query-only replay. Each domain still validates its
/// exact digest or retained plan in its own receipt format before returning.
pub(crate) fn finished(connection: &Connection, id: &str, kind: &str) -> Result<bool> {
    connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM operation WHERE operation_id=? AND kind=? AND state IN ('verified','completed') AND finished_at IS NOT NULL)",
        [id, kind], |row| row.get(0)).map_err(database)
}

pub(crate) fn state(
    connection: &Connection,
    id: &str,
    kind: &str,
    expected: &str,
) -> Result<Option<String>> {
    let known: Option<(String, String, String)> = connection
        .query_row(
            "SELECT kind,state,coalesce(detail,'') FROM operation WHERE operation_id=?",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .map_err(database)?;
    match known {
        Some((held_kind, state, binding)) if held_kind == kind && binding == expected => {
            Ok(Some(state))
        }
        Some(_) => Err(Failure::new(
            ErrorKind::Conflict,
            "the operation identity is bound to another planned effect",
        )),
        None => Ok(None),
    }
}
