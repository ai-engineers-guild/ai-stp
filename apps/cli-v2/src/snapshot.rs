//! Inspect an explicitly supplied backup; never open a user's live registry.

use std::{fs::File, io::Read, path::Path};

use rusqlite::{Connection, MAIN_DB, config::DbConfig};
use serde_json::{Value, json};

use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
};

pub const SCHEMA_VERSION: u32 = 53;
const MAX_BYTES: u64 = 128 * 1024 * 1024;

pub fn inspect(path: &Path, expected_digest: &str) -> Result<Value> {
    let metadata = path
        .symlink_metadata()
        .map_err(|_| Failure::new(ErrorKind::NotFound, "snapshot is not accessible"))?;
    if !metadata.is_file() {
        return Err(Failure::input("snapshot must be a regular file"));
    }
    let mut bytes = Vec::new();
    File::open(path)
        .and_then(|file| file.take(MAX_BYTES + 1).read_to_end(&mut bytes))
        .map_err(|_| Failure::input("snapshot cannot be read"))?;
    inspect_bytes(&bytes, expected_digest)
}

/// SQLite receives the same owned bytes that passed the digest check. Reading
/// in memory avoids path replacement races and creation of WAL/SHM sidecars.
pub fn inspect_bytes(bytes: &[u8], expected_digest: &str) -> Result<Value> {
    if bytes.len() as u64 > MAX_BYTES || bytes.len() < 100 {
        return Err(Failure::input("snapshot must contain 100 bytes to 128 MiB"));
    }
    let digest = digest::sha256(bytes);
    if digest != expected_digest {
        return Err(Failure::precondition("snapshot digest does not match"));
    }
    // A backup must be closed in DELETE mode. Raw WAL database copies do not
    // contain every committed page and cannot be accepted as standalone state.
    if &bytes[..16] != b"SQLite format 3\0" || bytes[18..20] != [1, 1] {
        return Err(Failure::precondition(
            "snapshot must be a standalone SQLite backup in DELETE journal mode",
        ));
    }
    let invalid = |_| Failure::precondition("snapshot is not a readable, intact SQLite registry");
    let mut connection = Connection::open_in_memory().map_err(invalid)?;
    connection
        .deserialize_read_exact(MAIN_DB, bytes, bytes.len(), true)
        .map_err(invalid)?;
    connection
        .set_db_config(DbConfig::SQLITE_DBCONFIG_TRUSTED_SCHEMA, false)
        .map_err(invalid)?;
    connection
        .set_db_config(DbConfig::SQLITE_DBCONFIG_DEFENSIVE, true)
        .map_err(invalid)?;
    connection
        .pragma_update(None, "query_only", true)
        .map_err(invalid)?;
    // Bound malformed database work independently of its byte size.
    let mut steps = 0;
    connection
        .progress_handler(
            1000,
            Some(move || {
                steps += 1;
                steps > 100_000
            }),
        )
        .map_err(invalid)?;
    let schema: u32 = connection
        .query_row("PRAGMA user_version", [], |row| row.get(0))
        .map_err(invalid)?;
    if schema != SCHEMA_VERSION {
        return Err(Failure::precondition(format!(
            "snapshot schema {schema} is unsupported; expected {SCHEMA_VERSION}"
        )));
    }
    let integrity: String = connection
        .query_row("PRAGMA integrity_check", [], |row| row.get(0))
        .map_err(invalid)?;
    if integrity != "ok" {
        return Err(Failure::precondition("snapshot integrity check failed"));
    }
    let mut statement = connection.prepare("SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name").map_err(invalid)?;
    let tables = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(invalid)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(invalid)?;
    let mut counts = serde_json::Map::new();
    for name in &tables {
        let quoted = name.replace('"', "\"\"");
        let count: i64 = connection
            .query_row(&format!("SELECT count(*) FROM \"{quoted}\""), [], |row| {
                row.get(0)
            })
            .map_err(invalid)?;
        counts.insert(name.clone(), count.into());
    }
    if !["entity", "revision", "head", "operation"]
        .iter()
        .all(|name| counts.contains_key(*name))
    {
        return Err(Failure::precondition("snapshot lacks registry tables"));
    }
    Ok(json!({
        "schema_version": 1, "local_schema_version": schema,
        "snapshot_digest": digest, "sqlite_version": rusqlite::version(),
        "read_only": true, "table_count": tables.len(), "row_counts": counts
    }))
}
