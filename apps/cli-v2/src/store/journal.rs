//! Operation receipts bind the operation identity, kind and exact planned effect.

use rusqlite::{Connection, OptionalExtension};

use super::database;
use crate::error::{ErrorKind, Failure, Result};

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
