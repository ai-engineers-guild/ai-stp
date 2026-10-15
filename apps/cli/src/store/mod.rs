//! Confined native state: isolated schema 53 or explicitly transferred schema 54.
//! Production transfer preserves its original registry file and data model.

pub(crate) mod journal;
pub(crate) mod migration;
pub mod revisions;
pub mod versions;
mod vfs;

use std::{path::Path, sync::OnceLock, time::Duration};

use cap_std::fs::Dir;
use rusqlite::{Connection, OpenFlags, Transaction, TransactionBehavior, config::DbConfig};

use crate::{
    error::{ErrorKind, Failure, Result},
    files::{OwnedDirectory, private_options},
    snapshot::SCHEMA_VERSION,
};

const NAMESPACE: &str = "ai-stp-v2-state";
const OWNER: &[u8] = b"ai-stp-cli-v2 local registry v1\n";
const ATTACHED_OWNER: &[u8] = b"ai-stp-cli-v2 local registry v2\n";
const RECOVERED_OWNER: &[u8] = b"ai-stp-cli-v2 local registry v3\n";
const PRODUCTION_OWNER: &[u8] = b"ai-stp native production registry v1\n";
const TRANSFER_OWNER: &[u8] = b"ai-stp native production transfer v1\n";
pub(crate) const PRODUCTION_SCHEMA: u32 = 54;
const BOOTSTRAP: &str = include_str!("schema.sql");
type Schema = Vec<(String, String, String, String)>;

pub struct Store {
    // Drop SQLite before releasing the process lock and directory handle.
    pub(crate) connection: Connection,
    scope: Option<std::sync::Arc<vfs::Scope>>,
    planning: bool,
}

pub(crate) fn database(error: rusqlite::Error) -> Failure {
    let kind = match error.sqlite_error_code() {
        Some(rusqlite::ErrorCode::DatabaseBusy | rusqlite::ErrorCode::DatabaseLocked) => {
            ErrorKind::Unavailable
        }
        Some(rusqlite::ErrorCode::ConstraintViolation) => ErrorKind::Conflict,
        _ => ErrorKind::Precondition,
    };
    let failure = Failure::new(
        kind,
        "the local registry transaction could not be completed",
    );
    match error {
        rusqlite::Error::SqliteFailure(code, _) => {
            failure.with_details([("sqlite_code".into(), code.extended_code.into())])
        }
        _ => failure,
    }
}

fn schema(connection: &Connection) -> Result<Schema> {
    let mut query = connection.prepare(
        "SELECT type, name, tbl_name, coalesce(sql, '') FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name",
    ).map_err(database)?;
    query
        .query_map([], |row| {
            Ok((
                row.get(0)?,
                row.get(1)?,
                row.get(2)?,
                schema_sql(&row.get::<_, String>(3)?),
            ))
        })
        .map_err(database)?
        .collect::<std::result::Result<_, _>>()
        .map_err(database)
}

// Historical migrations and the native bootstrap retain different indentation.
// Ignore only whitespace outside quoted literals/identifiers, without rewriting
// the user's schema. Constraints, defaults and token boundaries stay exact.
fn schema_sql(sql: &str) -> String {
    let mut normalized = String::with_capacity(sql.len());
    let mut quote = None;
    let mut space = false;
    for character in sql.chars() {
        if let Some(end) = quote {
            normalized.push(character);
            if character == end {
                quote = None;
            }
        } else if character.is_ascii_whitespace() {
            space = true;
        } else {
            if space && !normalized.is_empty() {
                normalized.push(' ');
            }
            space = false;
            normalized.push(character);
            quote = match character {
                '\'' | '"' | '`' => Some(character),
                '[' => Some(']'),
                _ => None,
            };
        }
    }
    normalized
}

fn expected_schema() -> Result<&'static Schema> {
    static EXPECTED: OnceLock<Result<Schema>> = OnceLock::new();
    EXPECTED
        .get_or_init(|| {
            let connection = Connection::open_in_memory().map_err(database)?;
            connection.execute_batch(BOOTSTRAP).map_err(database)?;
            schema(&connection)
        })
        .as_ref()
        .map_err(|_| {
            Failure::new(
                ErrorKind::Internal,
                "the embedded registry schema is invalid",
            )
        })
}

impl Store {
    pub fn open(parent: &Path, create: bool) -> Result<Self> {
        let parent = Self::parent(parent)?;
        Self::open_at(&parent, create)
    }

    pub(crate) fn open_at(parent: &Dir, create: bool) -> Result<Self> {
        Self::open_existing(
            parent
                .try_clone()
                .map_err(|_| Failure::precondition("the registry parent cannot be retained"))?,
            create,
            false,
        )
    }

    /// A missing registry is represented in memory. Existing state is query-only:
    /// planning cannot bootstrap a directory or commit domain records.
    pub fn planning(parent: &Path) -> Result<Self> {
        let parent = Self::parent(parent)?;
        Self::planning_at(&parent)
    }

    pub(crate) fn planning_at(parent: &Dir) -> Result<Self> {
        match Self::open_existing(
            parent
                .try_clone()
                .map_err(|_| Failure::precondition("the registry parent cannot be retained"))?,
            false,
            true,
        ) {
            Ok(store) => Ok(store),
            Err(error) if matches!(error.kind, ErrorKind::NotFound) => {
                let connection = Connection::open_in_memory().map_err(database)?;
                connection.execute_batch(BOOTSTRAP).map_err(database)?;
                connection
                    .pragma_update(None, "user_version", SCHEMA_VERSION)
                    .map_err(database)?;
                connection
                    .pragma_update(None, "query_only", true)
                    .map_err(database)?;
                Ok(Self {
                    connection,
                    scope: None,
                    planning: true,
                })
            }
            Err(error) => Err(error),
        }
    }

    fn parent(parent: &Path) -> Result<Dir> {
        Dir::open_ambient_dir(parent, cap_std::ambient_authority())
            .map_err(|_| Failure::precondition("the registry parent cannot be opened"))
    }

    fn open_existing(parent: Dir, create: bool, planning: bool) -> Result<Self> {
        Self::open_mode(parent, create, planning, false)
    }

    fn open_mode(parent: Dir, create: bool, planning: bool, transfer: bool) -> Result<Self> {
        let directory = OwnedDirectory::open_compatible(
            &parent,
            NAMESPACE,
            if transfer { TRANSFER_OWNER } else { OWNER },
            &[
                ATTACHED_OWNER,
                RECOVERED_OWNER,
                TRANSFER_OWNER,
                PRODUCTION_OWNER,
            ],
            create,
        )?
        .ok_or_else(|| {
            Failure::new(
                ErrorKind::NotFound,
                "the explicit preview registry does not exist",
            )
        })?;
        let marker = directory
            .read_file("owner", 256)?
            .ok_or_else(|| Failure::precondition("the registry owner is absent"))?;
        let production = marker == PRODUCTION_OWNER || marker == TRANSFER_OWNER;
        if marker == TRANSFER_OWNER && !transfer || transfer && !production {
            return Err(Failure::precondition(
                "resume the admitted production state transfer before opening this registry",
            ));
        }
        let data = if production {
            &parent
        } else {
            &directory.directory
        };
        let database_name = if production {
            "registry.sqlite"
        } else {
            "registry.sqlite3"
        };
        if let Err(error) = data.symlink_metadata(database_name) {
            if error.kind() != std::io::ErrorKind::NotFound
                || directory
                    .directory
                    .entries()
                    .map_err(|_| Failure::precondition("the registry cannot be inspected"))?
                    .any(|entry| {
                        entry.map_or(true, |entry| {
                            !matches!(entry.file_name().to_str(), Some("owner" | "lock"))
                        })
                    })
            {
                return Err(Failure::precondition(
                    "the missing registry has unexpected companion files",
                ));
            }
            if !create {
                return Err(Failure::new(
                    ErrorKind::NotFound,
                    "the owned registry initialization is incomplete",
                ));
            }
        }
        if create && !production {
            match data.open_with(database_name, private_options().create_new(true)) {
                Ok(file) => {
                    file.sync_all().map_err(|_| {
                        Failure::precondition("the registry file could not be persisted")
                    })?;
                    directory.sync()?;
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(_) => {
                    return Err(Failure::precondition(
                        "the registry file could not be created",
                    ));
                }
            }
        }
        let scope = vfs::Scope::open(parent, directory, production)?;
        let mut connection = Connection::open_with_flags_and_vfs(
            scope.path(),
            OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NO_MUTEX,
            vfs::NAME,
        )
        .map_err(database)?;
        // The owned namespace and database lock exclude other processes for the
        // whole connection. SQLite can keep its WAL index in memory; no shared
        // memory or ambient temporary file is needed. Set this before any read.
        connection
            .execute_batch(
                "PRAGMA locking_mode=EXCLUSIVE; PRAGMA temp_store=MEMORY; PRAGMA mmap_size=0;",
            )
            .map_err(database)?;
        connection
            .busy_timeout(Duration::from_secs(2))
            .map_err(database)?;
        connection
            .set_db_config(DbConfig::SQLITE_DBCONFIG_TRUSTED_SCHEMA, false)
            .map_err(database)?;
        connection
            .set_db_config(DbConfig::SQLITE_DBCONFIG_DEFENSIVE, true)
            .map_err(database)?;
        connection
            .pragma_update(None, "foreign_keys", true)
            .map_err(database)?;
        // Bootstrap uses rollback journaling until WAL can be enabled. EXTRA
        // includes the directory sync that makes its initial commit durable.
        connection
            .pragma_update(None, "synchronous", "EXTRA")
            .map_err(database)?;
        let version: u32 = connection
            .query_row("PRAGMA user_version", [], |row| row.get(0))
            .map_err(database)?;
        if !production && version == 0 && schema(&connection)?.is_empty() {
            if !create {
                return Err(Failure::new(
                    ErrorKind::NotFound,
                    "the owned registry initialization is incomplete",
                ));
            }
            let transaction = connection
                .transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(database)?;
            transaction.execute_batch(BOOTSTRAP).map_err(database)?;
            transaction
                .pragma_update(None, "user_version", SCHEMA_VERSION)
                .map_err(database)?;
            transaction.commit().map_err(database)?;
        } else if if production {
            version != PRODUCTION_SCHEMA && !(transfer && version == SCHEMA_VERSION)
        } else {
            version != SCHEMA_VERSION
        } {
            return Err(Failure::precondition(
                "the local registry schema is unsupported",
            ));
        }
        if &schema(&connection)? != expected_schema()? {
            return Err(Failure::precondition(
                "the local registry schema differs from its declared format",
            ));
        }
        let mode: String = connection
            .query_row(
                if planning {
                    "PRAGMA journal_mode"
                } else {
                    "PRAGMA journal_mode=WAL"
                },
                [],
                |row| row.get(0),
            )
            .map_err(database)?;
        // A complete bootstrap can survive before WAL activation. Query-only
        // planning may read it; the next writer finishes activation in place.
        if mode != "wal" && !(planning && mode == "delete") {
            return Err(Failure::precondition(
                "the local registry requires write-ahead logging",
            ));
        }
        connection
            .pragma_update(None, "synchronous", "FULL")
            .map_err(database)?;
        if planning {
            connection
                .pragma_update(None, "query_only", true)
                .map_err(database)?;
        }
        Ok(Self {
            connection,
            scope: Some(scope),
            planning,
        })
    }

    /// Fence older preview writers before committing ownership. An interruption
    /// here leaves an ordinary, readable registry with its original owner.
    pub(crate) fn fence_legacy_writers(&self) -> Result<()> {
        let scope = self
            .scope
            .as_ref()
            .ok_or_else(|| Failure::precondition("attachment requires a persistent registry"))?;
        scope.fence_unless(ATTACHED_OWNER, RECOVERED_OWNER)
    }

    pub(crate) fn fence_retired_devices(&self) -> Result<()> {
        self.scope
            .as_ref()
            .ok_or_else(|| Failure::precondition("recovery requires a persistent registry"))?
            .fence(RECOVERED_OWNER)
    }

    pub fn transaction<T>(
        &mut self,
        operation: impl FnOnce(&Transaction<'_>) -> Result<T>,
    ) -> Result<T> {
        if let Some(scope) = &self.scope {
            scope
                .validate()
                .map_err(|_| Failure::precondition("the registry binding changed"))?;
        }
        let transaction = self
            .connection
            .transaction_with_behavior(if self.planning {
                TransactionBehavior::Deferred
            } else {
                TransactionBehavior::Immediate
            })
            .map_err(database)?;
        let result = operation(&transaction)?;
        transaction.commit().map_err(database)?;
        if let Some(scope) = &self.scope {
            scope
                .validate()
                .map_err(|_| Failure::precondition("the registry binding changed"))?;
        }
        Ok(result)
    }
}
