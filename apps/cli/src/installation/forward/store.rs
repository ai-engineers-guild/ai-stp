//! One bounded transaction database; completed records contain no file payloads.

use std::sync::Arc;

use cap_fs_ext::DirExt;
use cap_std::fs::Dir;
use rusqlite::{Connection, OpenFlags, OptionalExtension, config::DbConfig, limits::Limit, params};
use serde::{Deserialize, Serialize};

use super::{Admission, Change, Content, Result, files, invalid};
use crate::installation::sqlite as vfs;

const OWNER: &str = "CREATE TABLE owner (singleton INTEGER PRIMARY KEY CHECK(singleton=1), identity BLOB NOT NULL) STRICT";
const OPERATIONS: &str = "CREATE TABLE operations (id TEXT PRIMARY KEY, digest TEXT NOT NULL, admission BLOB NOT NULL, context BLOB NOT NULL, stage BLOB, phase TEXT NOT NULL CHECK(phase IN ('applying','finishing','completed')), active INTEGER CHECK(active=1), outcome BLOB, CHECK((active IS NULL)=(phase='completed'))) STRICT, WITHOUT ROWID";
const PREPARED_OPERATIONS: &str = r#"CREATE TABLE "operations" (id TEXT PRIMARY KEY, digest TEXT NOT NULL, admission BLOB NOT NULL, context BLOB NOT NULL, stage BLOB, phase TEXT NOT NULL CHECK(phase IN ('prepared','applying','finishing','completed')), active INTEGER CHECK(active=1), outcome BLOB, CHECK((active IS NULL)=(phase='completed'))) STRICT, WITHOUT ROWID"#;
const ACTIVE: &str =
    "CREATE UNIQUE INDEX one_active ON operations(active) WHERE active IS NOT NULL";
const CHANGES: &str = "CREATE TABLE changes (operation TEXT NOT NULL, sequence INTEGER NOT NULL, metadata BLOB NOT NULL, payload BLOB, PRIMARY KEY(operation,sequence)) STRICT, WITHOUT ROWID";
const APPLICATION: i64 = 0x4153_4657;
const CONTROL: &str = "forward";
const META_LIMIT: usize = 8 * 1024 * 1024;
// Reserve space above the 64 MiB effect bound for final provenance metadata.
const PAYLOAD_LIMIT: usize = 96 * 1024 * 1024;
pub(super) const CHANGE_LIMIT: usize = 8192;

fn sql<T>(value: rusqlite::Result<T>) -> Result<T> {
    value.map_err(|error| invalid().with_source(error))
}

fn encode<T: Serialize>(value: &T) -> Result<Vec<u8>> {
    let bytes = serde_json::to_vec(value).map_err(|_| invalid())?;
    if bytes.len() > META_LIMIT {
        return Err(invalid());
    }
    Ok(bytes)
}

fn decode<T: serde::de::DeserializeOwned>(bytes: &[u8]) -> Result<T> {
    if bytes.len() > META_LIMIT {
        return Err(invalid());
    }
    serde_json::from_slice(bytes).map_err(|_| invalid())
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Metadata {
    path: String,
    before: files::Observation,
    after: Option<(String, usize, u32)>,
}

pub(super) struct Record {
    pub(super) admission: Admission,
    pub(super) context: serde_json::Value,
    pub(super) stage: Option<files::Identity>,
    pub(super) phase: String,
    pub(super) outcome: Option<serde_json::Value>,
}

pub(super) struct Store {
    // SQLite must close its handles before the held VFS scope is released.
    db: Connection,
    scope: Arc<vfs::Scope>,
}

impl Store {
    pub(super) fn open(control: &Dir, owner: files::Identity) -> Result<Self> {
        match control.create_dir(CONTROL) {
            Ok(()) => files::sync(control)?,
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(invalid().with_source(error)),
        }
        let directory = files::io(control.open_dir_nofollow(CONTROL))?;
        for entry in files::io(directory.entries())? {
            let entry = files::io(entry)?;
            let name = entry.file_name();
            let name = name.to_str().ok_or_else(invalid)?;
            if !matches!(name, vfs::DATABASE | vfs::JOURNAL | vfs::LOCK) {
                return Err(invalid());
            }
            files::io(vfs::inspect(&directory, name))?.ok_or_else(invalid)?;
        }
        let scope = vfs::Scope::open(control, CONTROL, directory, true)?;
        let db = sql(Connection::open_with_flags_and_vfs(
            scope.path(),
            OpenFlags::SQLITE_OPEN_READ_WRITE
                | OpenFlags::SQLITE_OPEN_CREATE
                | OpenFlags::SQLITE_OPEN_NO_MUTEX,
            vfs::NAME,
        ))?;
        sql(db.set_db_config(DbConfig::SQLITE_DBCONFIG_TRUSTED_SCHEMA, false))?;
        sql(db.set_db_config(DbConfig::SQLITE_DBCONFIG_DEFENSIVE, true))?;
        for (kind, limit) in [
            (Limit::SQLITE_LIMIT_LENGTH, 33 * 1024 * 1024),
            (Limit::SQLITE_LIMIT_SQL_LENGTH, 64 * 1024),
            (Limit::SQLITE_LIMIT_COLUMN, 16),
            (Limit::SQLITE_LIMIT_EXPR_DEPTH, 100),
            (Limit::SQLITE_LIMIT_ATTACHED, 0),
            (Limit::SQLITE_LIMIT_TRIGGER_DEPTH, 0),
            (Limit::SQLITE_LIMIT_WORKER_THREADS, 0),
        ] {
            sql(db.set_limit(kind, limit))?;
        }
        sql(db.execute_batch(
            "PRAGMA mmap_size=0; PRAGMA temp_store=MEMORY; PRAGMA cache_size=-2048;",
        ))?;
        let store = Self { db, scope };
        store.schema(owner)?;
        Ok(store)
    }

    fn schema(&self, owner: files::Identity) -> Result<()> {
        let application: i64 = sql(self.db.query_row("PRAGMA application_id", [], |r| r.get(0)))?;
        let version: i64 = sql(self.db.query_row("PRAGMA user_version", [], |r| r.get(0)))?;
        let mut statement = sql(self
            .db
            .prepare("SELECT sql FROM sqlite_schema ORDER BY name"))?;
        let schemas = sql(sql(statement.query_map([], |r| r.get::<_, String>(0)))?
            .collect::<rusqlite::Result<Vec<_>>>())?;
        let empty = application == 0 && version == 0 && schemas.is_empty();
        if !empty
            && (application != APPLICATION
                || !matches!(version, 1 | 2)
                || schemas
                    != [
                        CHANGES,
                        ACTIVE,
                        if version == 1 {
                            OPERATIONS
                        } else {
                            PREPARED_OPERATIONS
                        },
                        OWNER,
                    ])
        {
            return Err(invalid());
        }
        if !empty {
            let recorded: Vec<u8> =
                sql(self
                    .db
                    .query_row("SELECT identity FROM owner WHERE singleton=1", [], |r| {
                        r.get(0)
                    }))?;
            if decode::<files::Identity>(&recorded)? != owner {
                return Err(invalid());
            }
        }
        let journal: String = sql(self
            .db
            .query_row("PRAGMA journal_mode=DELETE", [], |r| r.get(0)))?;
        if journal != "delete" {
            return Err(invalid());
        }
        sql(self.db.execute_batch(
            "PRAGMA synchronous=EXTRA; PRAGMA max_page_count=65536; PRAGMA secure_delete=ON;",
        ))?;
        if empty {
            sql(self.db.execute_batch("BEGIN IMMEDIATE"))?;
            for schema in [OWNER, OPERATIONS, ACTIVE, CHANGES] {
                sql(self.db.execute_batch(schema))?;
            }
            sql(self
                .db
                .execute("INSERT INTO owner VALUES (1,?1)", [encode(&owner)?]))?;
            sql(self.db.pragma_update(None, "application_id", APPLICATION))?;
            sql(self.db.pragma_update(None, "user_version", 1))?;
            sql(self.db.execute_batch("COMMIT"))?;
        }
        self.scope.validate()
    }

    pub(super) fn record(&self, admission: &Admission) -> Result<Option<Record>> {
        self.scope.validate()?;
        let row = sql(self
            .db
            .query_row(
                "SELECT digest,admission,context,stage,phase,outcome FROM operations WHERE id=?1",
                [&admission.operation_id],
                |r| {
                    Ok((
                        r.get::<_, String>(0)?,
                        r.get::<_, Vec<u8>>(1)?,
                        r.get::<_, Vec<u8>>(2)?,
                        r.get::<_, Option<Vec<u8>>>(3)?,
                        r.get::<_, String>(4)?,
                        r.get::<_, Option<Vec<u8>>>(5)?,
                    ))
                },
            )
            .optional())?;
        row.map(|(digest, bytes, context, stage, phase, outcome)| {
            if digest != admission.plan_digest || decode::<Admission>(&bytes)? != *admission {
                return Err(invalid());
            }
            let outcome = outcome.map(|v| decode(&v)).transpose()?;
            if phase == "completed" && outcome.is_none() {
                return Err(invalid());
            }
            Ok(Record {
                admission: admission.clone(),
                context: decode(&context)?,
                stage: stage.map(|v| decode(&v)).transpose()?,
                phase,
                outcome,
            })
        })
        .transpose()
    }

    pub(super) fn idle(&self) -> Result<()> {
        let count: i64 =
            sql(self
                .db
                .query_row("SELECT count(*) FROM operations WHERE active=1", [], |r| {
                    r.get(0)
                }))?;
        if count != 0 {
            return Err(invalid());
        }
        Ok(())
    }

    fn insert_changes(&self, id: &str, start: usize, changes: &[Change]) -> Result<()> {
        if changes.len() + start > CHANGE_LIMIT {
            return Err(invalid());
        }
        let mut total = 0_usize;
        let mut paths = std::collections::BTreeSet::new();
        for (index, change) in changes.iter().enumerate() {
            if !files::valid_path(&change.path) || !paths.insert(&change.path) {
                return Err(invalid());
            }
            let after = change.after.as_ref().map(|content| {
                (
                    crate::digest::sha256(&content.bytes),
                    content.bytes.len(),
                    content.mode,
                )
            });
            if let Some(content) = &change.after {
                total = total.checked_add(content.bytes.len()).ok_or_else(invalid)?;
                content.validate()?;
            }
            if total > PAYLOAD_LIMIT {
                return Err(invalid());
            }
            let metadata = Metadata {
                path: change.path.clone(),
                before: change.before.clone(),
                after,
            };
            sql(self.db.execute(
                "INSERT INTO changes VALUES (?1,?2,?3,?4)",
                params![
                    id,
                    i64::try_from(index + start).map_err(|_| invalid())?,
                    encode(&metadata)?,
                    change.after.as_ref().map(|c| &c.bytes)
                ],
            ))?;
        }
        Ok(())
    }

    pub(super) fn admit(
        &mut self,
        admission: &Admission,
        context: &serde_json::Value,
        changes: &[Change],
        prepared: bool,
    ) -> Result<()> {
        self.idle()?;
        if prepared {
            self.enable_preparation()?;
        }
        self.scope.validate()?;
        sql(self.db.execute_batch("BEGIN IMMEDIATE"))?;
        let result = (|| {
            sql(self.db.execute(
                "INSERT INTO operations VALUES (?1,?2,?3,?4,NULL,?5,1,NULL)",
                params![
                    admission.operation_id,
                    admission.plan_digest,
                    encode(admission)?,
                    encode(context)?,
                    if prepared { "prepared" } else { "applying" },
                ],
            ))?;
            self.insert_changes(&admission.operation_id, 0, changes)
        })();
        self.end(result)
    }

    // Only explicit preparation upgrades an idle v1 store. Old in-flight
    // operations and ordinary single-root calls keep their original format.
    // Schema and user_version jointly fence readers that cannot distinguish
    // preparation from publication. Historical receipt bytes are copied intact
    // inside one SQLite transaction; no before-image payload is introduced.
    fn enable_preparation(&mut self) -> Result<()> {
        self.scope.validate()?;
        let version: i64 = sql(self.db.query_row("PRAGMA user_version", [], |r| r.get(0)))?;
        if version == 2 {
            return Ok(());
        }
        if version != 1 {
            return Err(invalid());
        }
        self.idle()?;
        sql(self.db.execute_batch("BEGIN IMMEDIATE"))?;
        let result = (|| {
            sql(self.db.execute_batch(&PREPARED_OPERATIONS.replacen(
                "\"operations\"",
                "migrating_operations",
                1,
            )))?;
            sql(self.db.execute_batch("INSERT INTO migrating_operations SELECT * FROM operations; DROP TABLE operations; ALTER TABLE migrating_operations RENAME TO operations;"))?;
            sql(self.db.execute_batch(ACTIVE))?;
            sql(self.db.pragma_update(None, "user_version", 2))?;
            Ok(())
        })();
        self.end(result)
    }

    pub(super) fn start(&self, id: &str) -> Result<()> {
        self.scope.validate()?;
        if sql(self.db.execute("UPDATE operations SET phase='applying' WHERE id=?1 AND phase='prepared' AND stage IS NOT NULL AND active=1", [id]))? != 1 {
            return Err(invalid());
        }
        Ok(())
    }

    pub(super) fn has_active(&self) -> Result<bool> {
        sql(self.db.query_row(
            "SELECT EXISTS(SELECT 1 FROM operations WHERE active=1)",
            [],
            |row| row.get(0),
        ))
    }

    pub(super) fn cancel(
        &mut self,
        admission: &Admission,
        outcome: &serde_json::Value,
        admitted: bool,
    ) -> Result<()> {
        self.scope.validate()?;
        sql(self.db.execute_batch("BEGIN IMMEDIATE"))?;
        let result = (|| {
            if admitted {
                if sql(self.db.execute(
                    "UPDATE operations SET phase='completed',active=NULL,context=x'7b7d',outcome=?1 WHERE id=?2 AND digest=?3 AND (phase='prepared' OR (phase='applying' AND stage IS NULL)) AND active=1",
                    params![encode(outcome)?, admission.operation_id, admission.plan_digest],
                ))? != 1 {
                    return Err(invalid());
                }
                sql(self.db.execute(
                    "DELETE FROM changes WHERE operation=?1",
                    [&admission.operation_id],
                ))?;
            } else {
                sql(self.db.execute(
                    "INSERT INTO operations VALUES (?1,?2,?3,x'7b7d',NULL,'completed',NULL,?4)",
                    params![
                        admission.operation_id,
                        admission.plan_digest,
                        encode(admission)?,
                        encode(outcome)?
                    ],
                ))?;
            }
            Ok(())
        })();
        self.end(result)
    }

    fn end(&self, result: Result<()>) -> Result<()> {
        match result {
            Ok(()) => {
                sql(self.db.execute_batch("COMMIT"))?;
                self.scope.validate()
            }
            Err(error) => {
                let _ = self.db.execute_batch("ROLLBACK");
                Err(error)
            }
        }
    }

    pub(super) fn set_stage(&self, id: &str, identity: files::Identity) -> Result<()> {
        self.scope.validate()?;
        if sql(self.db.execute(
            "UPDATE operations SET stage=?1 WHERE id=?2 AND stage IS NULL AND phase IN ('prepared','applying')",
            params![encode(&identity)?, id],
        ))? != 1
        {
            return Err(invalid());
        }
        Ok(())
    }

    pub(super) fn changes(&self, id: &str) -> Result<Vec<Change>> {
        self.scope.validate()?;
        let mut statement = sql(self.db.prepare("SELECT sequence,metadata,payload FROM changes WHERE operation=?1 ORDER BY sequence LIMIT 8193"))?;
        let mut rows = sql(statement.query([id]))?;
        let mut changes = Vec::new();
        let mut total = 0_usize;
        while let Some(row) = sql(rows.next())? {
            let sequence = usize::try_from(sql(row.get::<_, i64>(0))?).map_err(|_| invalid())?;
            if sequence != changes.len() || sequence >= CHANGE_LIMIT {
                return Err(invalid());
            }
            let metadata: Metadata = decode(&sql(row.get::<_, Vec<u8>>(1))?)?;
            let payload: Option<Vec<u8>> = sql(row.get(2))?;
            let after = match (metadata.after, payload) {
                (Some((hash, length, mode)), Some(bytes))
                    if bytes.len() == length && crate::digest::sha256(&bytes) == hash =>
                {
                    total = total.checked_add(bytes.len()).ok_or_else(invalid)?;
                    let content = Content { bytes, mode };
                    content.validate()?;
                    Some(content)
                }
                (None, None) => None,
                _ => return Err(invalid()),
            };
            if total > PAYLOAD_LIMIT {
                return Err(invalid());
            }
            changes.push(Change {
                path: metadata.path,
                before: metadata.before,
                after,
            });
        }
        Ok(changes)
    }

    pub(super) fn finish(
        &mut self,
        id: &str,
        changes: &[Change],
        outcome: &serde_json::Value,
    ) -> Result<()> {
        let count: i64 = sql(self.db.query_row(
            "SELECT count(*) FROM changes WHERE operation=?1",
            [id],
            |r| r.get(0),
        ))?;
        sql(self.db.execute_batch("BEGIN IMMEDIATE"))?;
        let result = (|| {
            self.insert_changes(id, usize::try_from(count).map_err(|_| invalid())?, changes)?;
            if sql(self.db.execute("UPDATE operations SET phase='finishing',outcome=?1 WHERE id=?2 AND phase='applying'", params![encode(outcome)?, id]))? != 1 { return Err(invalid()); }
            Ok(())
        })();
        self.end(result)
    }

    pub(super) fn complete(&mut self, id: &str) -> Result<()> {
        sql(self.db.execute_batch("BEGIN IMMEDIATE"))?;
        let result = (|| {
            sql(self
                .db
                .execute("DELETE FROM changes WHERE operation=?1", [id]))?;
            if sql(self.db.execute("UPDATE operations SET phase='completed',active=NULL,context=x'7b7d' WHERE id=?1 AND phase='finishing' AND outcome IS NOT NULL", [id]))? != 1 { return Err(invalid()); }
            Ok(())
        })();
        self.end(result)
    }
}
