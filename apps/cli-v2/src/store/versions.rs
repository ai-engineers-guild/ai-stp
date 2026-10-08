//! Exact immutable coordinates. Number allocation and recording share the writer.

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{
    database,
    revisions::{self, Write},
};
use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
};

#[derive(Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Increment {
    Minor,
    Major,
}

fn coordinates(version: &str) -> Result<(i64, i64)> {
    if !passport::version_number(version) {
        return Err(Failure::input("a version must be an exact X.Y number"));
    }
    let (major, minor) = version
        .split_once('.')
        .ok_or_else(|| Failure::input("a version must be X.Y"))?;
    Ok((
        major
            .parse()
            .map_err(|_| Failure::input("the version major exceeds the registry range"))?,
        minor
            .parse()
            .map_err(|_| Failure::input("the version minor exceeds the registry range"))?,
    ))
}

pub fn next(connection: &Connection, id: &str, increment: Increment) -> Result<String> {
    if !passport::stable_id(id, "component") && !passport::stable_id(id, "setup") {
        return Err(Failure::input(
            "only a component or setup has immutable versions",
        ));
    }
    let latest: Option<String> = connection.query_row(
        "SELECT version FROM object_version WHERE stable_id=? ORDER BY major DESC,minor DESC LIMIT 1",
        [id],|row|row.get(0)).optional().map_err(database)?;
    let Some(latest) = latest else {
        return Ok("1.0".into());
    };
    Objects { connection }.exact_version(id, &latest, None)?;
    let (major, minor) = coordinates(&latest)?;
    let overflow = || Failure::precondition("the version sequence is exhausted");
    let (major, minor) = match increment {
        Increment::Minor => (major, minor.checked_add(1).ok_or_else(overflow)?),
        Increment::Major => (major.checked_add(1).ok_or_else(overflow)?, 0),
    };
    Ok(format!("{major}.{minor}"))
}

pub fn record(
    transaction: &Transaction<'_>,
    document: &Value,
    device_id: &str,
    operation_id: Option<&str>,
    at: &str,
) -> Result<Value> {
    if !passport::timestamp(at) || !passport::stable_id(device_id, "device") {
        return Err(Failure::input(
            "the version observation time or device identity is invalid",
        ));
    }
    let document = revisions::seal(document)?;
    passport::versions::validate_document(&document)?;
    let id = document["stable_id"]
        .as_str()
        .ok_or_else(|| Failure::input("the version identity is absent"))?;
    let version = document["version"]
        .as_str()
        .ok_or_else(|| Failure::input("the version number is absent"))?;
    let (major, minor) = coordinates(version)?;
    let address = digest::canonical("ai-stp:passport:v1", &document)?;
    let existing: Option<String> = transaction
        .query_row(
            "SELECT created_at FROM object_version WHERE stable_id=? AND version=?",
            [id, version],
            |row| row.get(0),
        )
        .optional()
        .map_err(database)?;
    if let Some(created) = existing {
        if !passport::timestamp(&created) {
            return Err(Failure::precondition(
                "the recorded version time is invalid",
            ));
        }
        let held = Objects {
            connection: transaction,
        }
        .exact_version(id, version, Some(&address))?;
        if held != document {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "the immutable number already names another passport",
            ));
        }
        return Ok(held);
    }
    let stored = revisions::commit(
        transaction,
        &document,
        device_id,
        operation_id,
        Write::Immutable,
    )?;
    transaction.execute("INSERT INTO object_version(stable_id,version,major,minor,passport_digest,revision_id,created_at) VALUES (?,?,?,?,?,?,?)",
        params![id,version,major,minor,address,stored["revision_id"].as_str(),at]).map_err(database)?;
    Ok(stored)
}
