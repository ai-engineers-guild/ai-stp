//! Transfer the existing registry in place; the schema stamp fences old writers.

use std::{collections::BTreeMap, path::Path, time::Duration};

use cap_fs_ext::MetadataExt;
use cap_std::fs::Dir;
use rusqlite::{Connection, OpenFlags, params, types::ValueRef};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use super::{PRODUCTION_SCHEMA, Store, database, expected_schema, schema};
use crate::{
    canonical,
    error::{Failure, Result},
    files, passport,
};

const KIND: &str = "state.migrate";
const MAX_BYTES: u64 = 128 * 1024 * 1024;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Inventory {
    pub database_identity: [String; 2],
    pub generation: String,
    pub rows: BTreeMap<String, u64>,
}

fn invalid() -> Failure {
    Failure::precondition(
        "the production registry changed or has unfinished work; finish legacy operations before migration",
    )
}

fn db_identity(parent: &Dir) -> Result<[String; 2]> {
    #[cfg(unix)]
    if cap_std::fs::MetadataExt::mode(&parent.dir_metadata().map_err(|_| invalid())?) & 0o077 != 0 {
        return Err(invalid());
    }
    let file = files::open_regular(parent, Path::new("registry.sqlite")).map_err(|_| invalid())?;
    let metadata = file.metadata().map_err(|_| invalid())?;
    if metadata.nlink() != 1 || metadata.len() > MAX_BYTES {
        return Err(invalid());
    }
    #[cfg(unix)]
    if cap_std::fs::MetadataExt::mode(&metadata) & 0o077 != 0 {
        return Err(invalid());
    }
    Ok([metadata.dev().to_string(), metadata.ino().to_string()])
}

fn quiescent(connection: &Connection, excluded: Option<&str>) -> Result<()> {
    if connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM operation WHERE finished_at IS NULL AND (?1 IS NULL OR operation_id<>?1))",
        [excluded], |row| row.get::<_,bool>(0)).map_err(database)? {return Err(invalid());}
    for query in [
        "SELECT EXISTS(SELECT 1 FROM agent_task WHERE state NOT IN ('completed','failed','cancelled'))",
        "SELECT EXISTS(SELECT 1 FROM installation_transaction WHERE state NOT IN ('verified','rolled_back','cancelled'))",
        "SELECT EXISTS(SELECT 1 FROM project_sync_plan WHERE state NOT IN ('applied','failed'))",
        "SELECT EXISTS(SELECT 1 FROM selected_version WHERE state='pending')",
    ] {
        if connection
            .query_row(query, [], |row| row.get::<_, bool>(0))
            .map_err(database)?
        {
            return Err(invalid());
        }
    }
    Ok(())
}

fn inventory(
    connection: &Connection,
    identity: [String; 2],
    excluded: Option<&str>,
) -> Result<Inventory> {
    if connection
        .query_row("PRAGMA user_version", [], |row| row.get::<_, u32>(0))
        .map_err(database)?
        != if excluded.is_some() {
            PRODUCTION_SCHEMA
        } else {
            super::SCHEMA_VERSION
        }
        || &schema(connection)? != expected_schema()?
    {
        return Err(invalid());
    }
    quiescent(connection, excluded)?;
    let integrity: String = connection
        .query_row("PRAGMA quick_check", [], |row| row.get(0))
        .map_err(database)?;
    let foreign: bool = connection
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM pragma_foreign_key_check)",
            [],
            |row| row.get(0),
        )
        .map_err(database)?;
    if integrity != "ok" || foreign {
        return Err(invalid());
    }
    let mut rows = BTreeMap::new();
    let mut hash = Sha256::new();
    hash.update(b"ai-stp:registry-generation:v1\0");
    let mut size = 0u64;
    let mut total = 0u64;
    for (_, name, _, _) in expected_schema()?.iter().filter(|entry| entry.0 == "table") {
        if !name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
        {
            return Err(invalid());
        }
        hash.update((name.len() as u64).to_be_bytes());
        hash.update(name.as_bytes());
        let condition = if matches!(name.as_str(), "operation" | "operation_event") {
            "operation_id<>?1"
        } else {
            "1"
        };
        let mut statement = connection
            .prepare(&format!(
                "SELECT * FROM \"{name}\" WHERE (?1 IS NULL OR {condition}) ORDER BY rowid"
            ))
            .map_err(database)?;
        let columns = statement.column_count();
        let mut records = statement.query([excluded]).map_err(database)?;
        let mut count = 0u64;
        while let Some(row) = records.next().map_err(database)? {
            count += 1;
            total += 1;
            if total > 100_000 {
                return Err(invalid());
            }
            hash.update([0xff]);
            for index in 0..columns {
                match row.get_ref(index).map_err(database)? {
                    ValueRef::Null => hash.update([0]),
                    ValueRef::Integer(value) => {
                        hash.update([1]);
                        hash.update(value.to_be_bytes());
                    }
                    ValueRef::Real(value) => {
                        hash.update([2]);
                        hash.update(value.to_bits().to_be_bytes());
                    }
                    ValueRef::Text(value) | ValueRef::Blob(value) => {
                        let tag =
                            if matches!(row.get_ref(index).map_err(database)?, ValueRef::Text(_)) {
                                3
                            } else {
                                4
                            };
                        size = size.checked_add(value.len() as u64).ok_or_else(invalid)?;
                        if size > MAX_BYTES {
                            return Err(invalid());
                        }
                        hash.update([tag]);
                        hash.update((value.len() as u64).to_be_bytes());
                        hash.update(value);
                    }
                }
            }
        }
        hash.update(count.to_be_bytes());
        rows.insert(name.clone(), count);
    }
    Ok(Inventory {
        database_identity: identity,
        generation: format!(
            "sha256:{}",
            hash.finalize()
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>()
        ),
        rows,
    })
}

/// A transaction reads committed WAL state. This is not an immutable-file read
/// or a snapshot copy; neither the database nor a credential is exported.
pub(crate) fn inspect(parent: &Path) -> Result<Inventory> {
    let directory =
        Dir::open_ambient_dir(parent, cap_std::ambient_authority()).map_err(|_| invalid())?;
    let before = db_identity(&directory)?;
    let mut connection = Connection::open_with_flags(
        parent.join("registry.sqlite"),
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(database)?;
    connection
        .busy_timeout(Duration::from_secs(2))
        .map_err(database)?;
    connection
        .execute_batch("PRAGMA temp_store=MEMORY; PRAGMA trusted_schema=OFF; PRAGMA query_only=ON;")
        .map_err(database)?;
    let transaction = connection.transaction().map_err(database)?;
    let value = inventory(&transaction, before.clone(), None)?;
    transaction.commit().map_err(database)?;
    if db_identity(&directory)? != before {
        return Err(invalid());
    }
    Ok(value)
}

pub(crate) fn open(parent: &Dir) -> Result<Store> {
    Store::open_mode(
        parent.try_clone().map_err(|_| invalid())?,
        true,
        false,
        true,
    )
}

pub(crate) fn verify(store: &Store, expected: &Inventory, operation: Option<&str>) -> Result<()> {
    if inventory(
        &store.connection,
        store
            .scope
            .as_ref()
            .ok_or_else(invalid)?
            .database_identity()?,
        operation,
    )? != *expected
    {
        return Err(invalid());
    }
    Ok(())
}

pub(crate) fn receipt(store: &Store, operation: &str, digest: &str) -> Result<Option<Value>> {
    match super::journal::state(&store.connection, operation, KIND, digest)? {
        Some(state) if state == "verified" => {
            let body: String = store
                .connection
                .query_row(
                    "SELECT evidence FROM operation_event WHERE operation_id=? AND sequence=2",
                    [operation],
                    |row| row.get(0),
                )
                .map_err(database)?;
            if body.len() > 128 * 1024 {
                return Err(invalid());
            }
            canonical::parse(body.as_bytes()).map(Some)
        }
        Some(state) if state == "applying" => Ok(None),
        Some(_) => Err(invalid()),
        None => Ok(None),
    }
}

/// Existing rows and bytes stay in place. The receipt and version transition
/// commit together while the VFS owns SQLite's exclusive interoperable lock.
pub(crate) fn commit(
    store: &mut Store,
    operation: &str,
    digest: &str,
    evidence: &Value,
    at: &str,
) -> Result<()> {
    if !passport::stable_id(operation, "operation") || !passport::timestamp(at) {
        return Err(invalid());
    }
    let body = String::from_utf8(canonical::bytes(evidence)?).map_err(|_| invalid())?;
    if body.len() > 128 * 1024 {
        return Err(invalid());
    }
    store.transaction(|transaction| {
        let changed=transaction.execute("UPDATE operation SET state='verified',finished_at=? WHERE operation_id=? AND kind=? AND state='applying' AND detail=?", params![at,operation,KIND,digest]).map_err(database)?;
        if changed!=1 {return Err(invalid());}
        transaction.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,2,?,'applying','verified','production_writer_transferred',?)", params![operation,at,body]).map_err(database)?;
        Ok(())
    })
}

pub(crate) fn publish(store: &Store) -> Result<()> {
    store
        .scope
        .as_ref()
        .ok_or_else(invalid)?
        .publish_production()
}

pub(crate) fn ensure_ready(parent: &Dir) -> Result<()> {
    use cap_fs_ext::DirExt;
    use std::io::Read;
    let namespace = match parent.open_dir_nofollow(super::NAMESPACE) {
        Ok(directory) => directory,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(_) => return Err(invalid()),
    };
    let file = files::open_regular(&namespace, Path::new("owner")).map_err(|_| invalid())?;
    let mut marker = Vec::new();
    file.take(257)
        .read_to_end(&mut marker)
        .map_err(|_| invalid())?;
    if ![
        super::OWNER,
        super::ATTACHED_OWNER,
        super::RECOVERED_OWNER,
        super::PRODUCTION_OWNER,
    ]
    .contains(&marker.as_slice())
    {
        return Err(invalid());
    }
    Ok(())
}

pub(crate) fn phase(store: &Store, operation: &str, digest: &str) -> Result<Option<String>> {
    super::journal::state(&store.connection, operation, KIND, digest)
}

pub(crate) fn admit(store: &mut Store, operation: &str, digest: &str, at: &str) -> Result<()> {
    store.transaction(|transaction| {
        transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'applying',?,NULL,?)",params![operation,KIND,at,digest]).map_err(database)?;
        transaction.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,1,?,'planned','applying','legacy_writer_fenced','{}')",params![operation,at]).map_err(database)?;
        transaction.pragma_update(None,"user_version",PRODUCTION_SCHEMA).map_err(database)?;
        Ok(())
    })
}
