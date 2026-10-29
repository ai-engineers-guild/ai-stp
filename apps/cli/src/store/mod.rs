//! Confined native state with explicitly enabled profiles and enrollment recovery.
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
pub(crate) const PROFILE_SCHEMA: u32 = 55;
pub(crate) const ENROLLMENT_RECOVERY_SCHEMA: u32 = 56;
pub(crate) const CHECKOUT_LINK_SCHEMA: u32 = 57;
pub(crate) const CHECKOUT_RETIREMENT_SCHEMA: u32 = 58;
// The SQL layout stays at 58; the new durable unlink journal encoding needs an
// explicit epoch so earlier clients cannot write alongside unknown operations.
pub(crate) const CHECKOUT_UNLINK_SCHEMA: u32 = 59;
pub(crate) const BINDING_RETIREMENT_SCHEMA: u32 = 60;
pub(crate) const CHECKOUT_LOCATION_SCHEMA: u32 = 61;
const BOOTSTRAP: &str = include_str!("schema.sql");
const PROFILES: &str = include_str!("profiles.sql");
const ENROLLMENT_RECOVERY: &str = include_str!("enrollment_recovery.sql");
const CHECKOUT_LINKS: &str = include_str!("checkout_links.sql");
const CHECKOUT_RETIREMENT: &str = include_str!("checkout_retirement.sql");
const BINDING_RETIREMENT: &str = include_str!("binding_retirement.sql");
const CHECKOUT_LOCATION: &str = include_str!("checkout_location.sql");
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

fn expected_profile_schema() -> Result<&'static Schema> {
    static EXPECTED: OnceLock<Result<Schema>> = OnceLock::new();
    EXPECTED
        .get_or_init(|| {
            let connection = Connection::open_in_memory().map_err(database)?;
            connection.execute_batch(BOOTSTRAP).map_err(database)?;
            connection.execute_batch(PROFILES).map_err(database)?;
            schema(&connection)
        })
        .as_ref()
        .map_err(|_| {
            Failure::new(
                ErrorKind::Internal,
                "the embedded profile registry schema is invalid",
            )
        })
}

fn expected_recovery_schema() -> Result<&'static Schema> {
    static EXPECTED: OnceLock<Result<Schema>> = OnceLock::new();
    EXPECTED
        .get_or_init(|| {
            let connection = Connection::open_in_memory().map_err(database)?;
            connection.execute_batch(BOOTSTRAP).map_err(database)?;
            connection.execute_batch(PROFILES).map_err(database)?;
            connection
                .execute_batch(ENROLLMENT_RECOVERY)
                .map_err(database)?;
            schema(&connection)
        })
        .as_ref()
        .map_err(|_| {
            Failure::new(
                ErrorKind::Internal,
                "the embedded enrollment recovery registry schema is invalid",
            )
        })
}

fn expected_checkout_schema() -> Result<&'static Schema> {
    static EXPECTED: OnceLock<Result<Schema>> = OnceLock::new();
    EXPECTED
        .get_or_init(|| {
            let connection = Connection::open_in_memory().map_err(database)?;
            connection.execute_batch(BOOTSTRAP).map_err(database)?;
            connection.execute_batch(PROFILES).map_err(database)?;
            connection
                .execute_batch(ENROLLMENT_RECOVERY)
                .map_err(database)?;
            connection.execute_batch(CHECKOUT_LINKS).map_err(database)?;
            schema(&connection)
        })
        .as_ref()
        .map_err(|_| {
            Failure::new(
                ErrorKind::Internal,
                "the embedded checkout registry schema is invalid",
            )
        })
}

fn expected_retirement_schema() -> Result<&'static Schema> {
    static EXPECTED: OnceLock<Result<Schema>> = OnceLock::new();
    EXPECTED
        .get_or_init(|| {
            let connection = Connection::open_in_memory().map_err(database)?;
            for source in [
                BOOTSTRAP,
                PROFILES,
                ENROLLMENT_RECOVERY,
                CHECKOUT_LINKS,
                CHECKOUT_RETIREMENT,
            ] {
                connection.execute_batch(source).map_err(database)?;
            }
            schema(&connection)
        })
        .as_ref()
        .map_err(|_| {
            Failure::new(
                ErrorKind::Internal,
                "the embedded checkout retirement registry schema is invalid",
            )
        })
}

fn expected_binding_retirement_schema() -> Result<&'static Schema> {
    static EXPECTED: OnceLock<Result<Schema>> = OnceLock::new();
    EXPECTED
        .get_or_init(|| {
            let connection = Connection::open_in_memory().map_err(database)?;
            for source in [
                BOOTSTRAP,
                PROFILES,
                ENROLLMENT_RECOVERY,
                CHECKOUT_LINKS,
                CHECKOUT_RETIREMENT,
                BINDING_RETIREMENT,
            ] {
                connection.execute_batch(source).map_err(database)?;
            }
            schema(&connection)
        })
        .as_ref()
        .map_err(|_| {
            Failure::new(
                ErrorKind::Internal,
                "the embedded binding retirement schema is invalid",
            )
        })
}

fn expected_location_schema() -> Result<&'static Schema> {
    static EXPECTED: OnceLock<Result<Schema>> = OnceLock::new();
    EXPECTED
        .get_or_init(|| {
            let connection = Connection::open_in_memory().map_err(database)?;
            for source in [
                BOOTSTRAP,
                PROFILES,
                ENROLLMENT_RECOVERY,
                CHECKOUT_LINKS,
                CHECKOUT_RETIREMENT,
                BINDING_RETIREMENT,
                CHECKOUT_LOCATION,
            ] {
                connection.execute_batch(source).map_err(database)?;
            }
            schema(&connection)
        })
        .as_ref()
        .map_err(|_| {
            Failure::new(
                ErrorKind::Internal,
                "the embedded checkout location schema is invalid",
            )
        })
}

pub(crate) fn profile_schema_after(before: u32) -> Result<u32> {
    match before {
        53 | PRODUCTION_SCHEMA | PROFILE_SCHEMA => Ok(PROFILE_SCHEMA),
        ENROLLMENT_RECOVERY_SCHEMA => Ok(ENROLLMENT_RECOVERY_SCHEMA),
        CHECKOUT_LINK_SCHEMA => Ok(CHECKOUT_LINK_SCHEMA),
        CHECKOUT_RETIREMENT_SCHEMA => Ok(CHECKOUT_RETIREMENT_SCHEMA),
        CHECKOUT_UNLINK_SCHEMA => Ok(CHECKOUT_UNLINK_SCHEMA),
        BINDING_RETIREMENT_SCHEMA => Ok(BINDING_RETIREMENT_SCHEMA),
        CHECKOUT_LOCATION_SCHEMA => Ok(CHECKOUT_LOCATION_SCHEMA),
        _ => Err(Failure::precondition("the profile registry schema changed")),
    }
}

pub(crate) fn has_enrollment_recovery(version: u32) -> bool {
    [
        ENROLLMENT_RECOVERY_SCHEMA,
        CHECKOUT_LINK_SCHEMA,
        CHECKOUT_RETIREMENT_SCHEMA,
        CHECKOUT_UNLINK_SCHEMA,
        BINDING_RETIREMENT_SCHEMA,
        CHECKOUT_LOCATION_SCHEMA,
    ]
    .contains(&version)
}

pub(crate) fn has_checkout_links(version: u32) -> bool {
    [
        CHECKOUT_LINK_SCHEMA,
        CHECKOUT_RETIREMENT_SCHEMA,
        CHECKOUT_UNLINK_SCHEMA,
        BINDING_RETIREMENT_SCHEMA,
        CHECKOUT_LOCATION_SCHEMA,
    ]
    .contains(&version)
}

pub(crate) fn has_checkout_retirement(version: u32) -> bool {
    [
        CHECKOUT_RETIREMENT_SCHEMA,
        CHECKOUT_UNLINK_SCHEMA,
        BINDING_RETIREMENT_SCHEMA,
        CHECKOUT_LOCATION_SCHEMA,
    ]
    .contains(&version)
}

pub(crate) fn has_checkout_unlinks(version: u32) -> bool {
    [
        CHECKOUT_UNLINK_SCHEMA,
        BINDING_RETIREMENT_SCHEMA,
        CHECKOUT_LOCATION_SCHEMA,
    ]
    .contains(&version)
}

pub(crate) fn has_binding_retirement(version: u32) -> bool {
    [BINDING_RETIREMENT_SCHEMA, CHECKOUT_LOCATION_SCHEMA].contains(&version)
}

pub(crate) fn has_checkout_locations(version: u32) -> bool {
    version == CHECKOUT_LOCATION_SCHEMA
}

pub(crate) fn unlink_schema_after(before: u32) -> Result<u32> {
    match before {
        CHECKOUT_LINK_SCHEMA | CHECKOUT_RETIREMENT_SCHEMA | CHECKOUT_UNLINK_SCHEMA => {
            Ok(CHECKOUT_UNLINK_SCHEMA)
        }
        BINDING_RETIREMENT_SCHEMA => Ok(BINDING_RETIREMENT_SCHEMA),
        CHECKOUT_LOCATION_SCHEMA => Ok(CHECKOUT_LOCATION_SCHEMA),
        _ => Err(Failure::precondition(
            "the native unlink registry schema changed",
        )),
    }
}

pub(crate) fn checkout_schema_after(before: u32) -> Result<u32> {
    match before {
        PROFILE_SCHEMA | ENROLLMENT_RECOVERY_SCHEMA | CHECKOUT_LINK_SCHEMA => {
            Ok(CHECKOUT_LINK_SCHEMA)
        }
        CHECKOUT_RETIREMENT_SCHEMA => Ok(CHECKOUT_RETIREMENT_SCHEMA),
        CHECKOUT_UNLINK_SCHEMA => Ok(CHECKOUT_UNLINK_SCHEMA),
        BINDING_RETIREMENT_SCHEMA => Ok(BINDING_RETIREMENT_SCHEMA),
        CHECKOUT_LOCATION_SCHEMA => Ok(CHECKOUT_LOCATION_SCHEMA),
        _ => Err(Failure::precondition(
            "the corporate checkout registry schema changed",
        )),
    }
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
            version != PRODUCTION_SCHEMA
                && version != PROFILE_SCHEMA
                && version != ENROLLMENT_RECOVERY_SCHEMA
                && version != CHECKOUT_LINK_SCHEMA
                && version != CHECKOUT_RETIREMENT_SCHEMA
                && version != CHECKOUT_UNLINK_SCHEMA
                && version != BINDING_RETIREMENT_SCHEMA
                && version != CHECKOUT_LOCATION_SCHEMA
                && !(transfer && version == SCHEMA_VERSION)
        } else {
            version != SCHEMA_VERSION
                && version != PROFILE_SCHEMA
                && version != ENROLLMENT_RECOVERY_SCHEMA
                && version != CHECKOUT_LINK_SCHEMA
                && version != CHECKOUT_RETIREMENT_SCHEMA
                && version != CHECKOUT_UNLINK_SCHEMA
                && version != BINDING_RETIREMENT_SCHEMA
                && version != CHECKOUT_LOCATION_SCHEMA
        } {
            return Err(Failure::precondition(
                "the local registry schema is unsupported",
            ));
        }
        if &schema(&connection)?
            != if has_checkout_locations(version) {
                expected_location_schema()?
            } else if version == BINDING_RETIREMENT_SCHEMA {
                expected_binding_retirement_schema()?
            } else if has_checkout_retirement(version) {
                expected_retirement_schema()?
            } else if version == CHECKOUT_LINK_SCHEMA {
                expected_checkout_schema()?
            } else if version == ENROLLMENT_RECOVERY_SCHEMA {
                expected_recovery_schema()?
            } else if version == PROFILE_SCHEMA {
                expected_profile_schema()?
            } else {
                expected_schema()?
            }
        {
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

    /// Upgrade and the first profile admission share one SQLite commit. No
    /// existing rows or unfinished operations are rewritten or discarded.
    pub(crate) fn profile_transaction<T>(
        &mut self,
        operation: impl FnOnce(&Transaction<'_>) -> Result<T>,
    ) -> Result<T> {
        self.transaction(|transaction| {
            let version: u32 = transaction
                .query_row("PRAGMA user_version", [], |row| row.get(0))
                .map_err(database)?;
            if ![
                PROFILE_SCHEMA,
                ENROLLMENT_RECOVERY_SCHEMA,
                CHECKOUT_LINK_SCHEMA,
                CHECKOUT_RETIREMENT_SCHEMA,
                CHECKOUT_UNLINK_SCHEMA,
                BINDING_RETIREMENT_SCHEMA,
                CHECKOUT_LOCATION_SCHEMA,
            ]
            .contains(&version)
            {
                if ![SCHEMA_VERSION, PRODUCTION_SCHEMA].contains(&version) {
                    return Err(Failure::precondition("the profile registry schema changed"));
                }
                transaction.execute_batch(PROFILES).map_err(database)?;
                transaction
                    .pragma_update(None, "user_version", PROFILE_SCHEMA)
                    .map_err(database)?;
            }
            operation(transaction)
        })
    }

    pub(crate) fn profiles_enabled(&self) -> Result<bool> {
        Ok([
            PROFILE_SCHEMA,
            ENROLLMENT_RECOVERY_SCHEMA,
            CHECKOUT_LINK_SCHEMA,
            CHECKOUT_RETIREMENT_SCHEMA,
            CHECKOUT_UNLINK_SCHEMA,
            BINDING_RETIREMENT_SCHEMA,
            CHECKOUT_LOCATION_SCHEMA,
        ]
        .contains(&self.version()?))
    }

    pub(crate) fn version(&self) -> Result<u32> {
        self.connection
            .query_row("PRAGMA user_version", [], |row| row.get(0))
            .map_err(database)
    }

    /// The epoch fence, parent recovery and child enrollment are admitted in
    /// one commit. The caller holds the original account and credential locks.
    pub(crate) fn enrollment_recovery_transaction<T>(
        &mut self,
        operation: impl FnOnce(&Transaction<'_>) -> Result<T>,
    ) -> Result<T> {
        self.transaction(|transaction| {
            let version: u32 = transaction
                .query_row("PRAGMA user_version", [], |row| row.get(0))
                .map_err(database)?;
            if version == PROFILE_SCHEMA {
                transaction
                    .execute_batch(ENROLLMENT_RECOVERY)
                    .map_err(database)?;
                transaction
                    .pragma_update(None, "user_version", ENROLLMENT_RECOVERY_SCHEMA)
                    .map_err(database)?;
            } else if !has_enrollment_recovery(version) {
                return Err(Failure::precondition(
                    "retained profiles are required before enrollment recovery",
                ));
            }
            operation(transaction)
        })
    }

    /// Admission and its physical reservation share the explicit format upgrade.
    /// No admitted profile or recovery plan is rewritten into the newer format.
    pub(crate) fn checkout_transaction<T>(
        &mut self,
        operation: impl FnOnce(&Transaction<'_>) -> Result<T>,
    ) -> Result<T> {
        self.transaction(|transaction| {
            let version: u32 = transaction
                .pragma_query_value(None, "user_version", |row| row.get(0))
                .map_err(database)?;
            if !has_checkout_links(version) {
                if ![PROFILE_SCHEMA, ENROLLMENT_RECOVERY_SCHEMA].contains(&version) {
                    return Err(Failure::precondition(
                        "retained profiles are required before corporate checkout admission",
                    ));
                }
                if version == PROFILE_SCHEMA {
                    transaction
                        .execute_batch(ENROLLMENT_RECOVERY)
                        .map_err(database)?;
                }
                transaction
                    .execute_batch(CHECKOUT_LINKS)
                    .map_err(database)?;
                transaction
                    .pragma_update(None, "user_version", CHECKOUT_LINK_SCHEMA)
                    .map_err(database)?;
            }
            operation(transaction)
        })
    }

    /// Fence old writers and retain the exact retirement receipt in the same
    /// commit as the original journal transition and reservation release.
    pub(crate) fn checkout_retirement_transaction<T>(
        &mut self,
        operation: impl FnOnce(&Transaction<'_>) -> Result<T>,
    ) -> Result<T> {
        self.transaction(|transaction| {
            let version: u32 = transaction
                .pragma_query_value(None, "user_version", |row| row.get(0))
                .map_err(database)?;
            if version == CHECKOUT_LINK_SCHEMA {
                transaction
                    .execute_batch(CHECKOUT_RETIREMENT)
                    .map_err(database)?;
                transaction
                    .pragma_update(None, "user_version", CHECKOUT_RETIREMENT_SCHEMA)
                    .map_err(database)?;
            } else if !has_checkout_retirement(version) {
                return Err(Failure::precondition(
                    "an admitted checkout intent is required before retirement",
                ));
            }
            operation(transaction)
        })
    }

    /// Fence old writers and admit the original unlink intent in one commit.
    /// No binding or physical reservation is released by unlink admission.
    pub(crate) fn checkout_unlink_transaction<T>(
        &mut self,
        operation: impl FnOnce(&Transaction<'_>) -> Result<T>,
    ) -> Result<T> {
        self.transaction(|transaction| {
            let version: u32 = transaction
                .pragma_query_value(None, "user_version", |row| row.get(0))
                .map_err(database)?;
            if version == CHECKOUT_LINK_SCHEMA {
                transaction
                    .execute_batch(CHECKOUT_RETIREMENT)
                    .map_err(database)?;
            } else if !has_checkout_retirement(version) {
                return Err(Failure::precondition(
                    "an active native checkout binding is required before unlink",
                ));
            }
            if !has_checkout_unlinks(version) {
                transaction
                    .pragma_update(None, "user_version", CHECKOUT_UNLINK_SCHEMA)
                    .map_err(database)?;
            }
            operation(transaction)
        })
    }

    /// Publish the terminal marker, receipt and exact reservation release in
    /// one commit. Read-only opening never upgrades an existing registry.
    pub(crate) fn binding_retirement_transaction<T>(
        &mut self,
        operation: impl FnOnce(&Transaction<'_>) -> Result<T>,
    ) -> Result<T> {
        self.transaction(|transaction| {
            let version: u32 = transaction
                .pragma_query_value(None, "user_version", |row| row.get(0))
                .map_err(database)?;
            if !has_checkout_links(version) {
                return Err(Failure::precondition(
                    "an original active checkout binding is required",
                ));
            }
            if version == CHECKOUT_LINK_SCHEMA {
                transaction
                    .execute_batch(CHECKOUT_RETIREMENT)
                    .map_err(database)?;
            }
            if !has_binding_retirement(version) {
                transaction
                    .execute_batch(BINDING_RETIREMENT)
                    .map_err(database)?;
                transaction
                    .pragma_update(None, "user_version", BINDING_RETIREMENT_SCHEMA)
                    .map_err(database)?;
            }
            operation(transaction)
        })
    }

    /// A reviewed terminal location receipt and the new writer fence commit
    /// together. No marker, user file or original journal is rewritten.
    pub(crate) fn checkout_location_transaction<T>(
        &mut self,
        operation: impl FnOnce(&Transaction<'_>) -> Result<T>,
    ) -> Result<T> {
        self.binding_retirement_transaction(|transaction| {
            let version: u32 = transaction
                .pragma_query_value(None, "user_version", |row| row.get(0))
                .map_err(database)?;
            if !has_checkout_locations(version) {
                if version != BINDING_RETIREMENT_SCHEMA {
                    return Err(Failure::precondition(
                        "the checkout location registry epoch changed",
                    ));
                }
                transaction
                    .execute_batch(CHECKOUT_LOCATION)
                    .map_err(database)?;
                transaction
                    .pragma_update(None, "user_version", CHECKOUT_LOCATION_SCHEMA)
                    .map_err(database)?;
            }
            operation(transaction)
        })
    }
}

#[cfg(test)]
mod checkout_epoch_tests {
    use super::*;

    #[test]
    fn location_epoch_is_atomic_preserves_receipts_and_does_not_downgrade()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        for before in [
            CHECKOUT_LINK_SCHEMA,
            CHECKOUT_RETIREMENT_SCHEMA,
            CHECKOUT_UNLINK_SCHEMA,
            BINDING_RETIREMENT_SCHEMA,
        ] {
            let parent = tempfile::tempdir()?;
            let mut store = Store::open(parent.path(), true)?;
            store.profile_transaction(|_| Ok(()))?;
            store.checkout_transaction(|_| Ok(()))?;
            match before {
                CHECKOUT_RETIREMENT_SCHEMA => store.checkout_retirement_transaction(|_| Ok(()))?,
                CHECKOUT_UNLINK_SCHEMA => store.checkout_unlink_transaction(|_| Ok(()))?,
                BINDING_RETIREMENT_SCHEMA => store.binding_retirement_transaction(|_| Ok(()))?,
                _ => (),
            }
            store.connection.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES ('retained','test.original','verified','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','immutable original receipt')", [])?;
            let bytes = store.connection.serialize("main")?.to_vec();
            let failed: Result<()> = store.checkout_location_transaction(|t| {
                t.execute("INSERT INTO native_checkout_location(binding_operation_id,location_operation_id) VALUES ('absent-binding','absent-location')", []).map_err(database)?;
                Ok(())
            });
            assert!(failed.is_err());
            assert_eq!(store.version()?, before);
            assert_eq!(store.connection.serialize("main")?.to_vec(), bytes);
            store.checkout_location_transaction(|_| Ok(()))?;
            assert_eq!(store.version()?, CHECKOUT_LOCATION_SCHEMA);
            store.profile_transaction(|_| Ok(()))?;
            store.enrollment_recovery_transaction(|_| Ok(()))?;
            store.checkout_transaction(|_| Ok(()))?;
            store.checkout_retirement_transaction(|_| Ok(()))?;
            store.checkout_unlink_transaction(|_| Ok(()))?;
            store.binding_retirement_transaction(|_| Ok(()))?;
            store.checkout_location_transaction(|_| Ok(()))?;
            assert_eq!(store.version()?, CHECKOUT_LOCATION_SCHEMA);
            drop(store);
            let store = Store::open(parent.path(), false)?;
            assert_eq!(store.version()?, CHECKOUT_LOCATION_SCHEMA);
            assert_eq!(
                store.connection.query_row(
                    "SELECT detail FROM operation WHERE operation_id='retained'",
                    [],
                    |r| r.get::<_, String>(0)
                )?,
                "immutable original receipt"
            );
            assert!(has_checkout_locations(CHECKOUT_LOCATION_SCHEMA));
            assert!(has_binding_retirement(CHECKOUT_LOCATION_SCHEMA));
            assert_eq!(
                profile_schema_after(CHECKOUT_LOCATION_SCHEMA)?,
                CHECKOUT_LOCATION_SCHEMA
            );
            assert_eq!(
                checkout_schema_after(CHECKOUT_LOCATION_SCHEMA)?,
                CHECKOUT_LOCATION_SCHEMA
            );
            assert_eq!(
                unlink_schema_after(CHECKOUT_LOCATION_SCHEMA)?,
                CHECKOUT_LOCATION_SCHEMA
            );
            store
                .connection
                .pragma_update(None, "user_version", CHECKOUT_LOCATION_SCHEMA + 1)?;
            drop(store);
            assert!(Store::open(parent.path(), false).is_err());
            assert!(!has_checkout_locations(CHECKOUT_LOCATION_SCHEMA + 1));
        }
        Ok(())
    }

    #[test]
    fn binding_retirement_is_atomic_preserves_older_journals_and_refuses_future_epochs()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        for before in [
            CHECKOUT_LINK_SCHEMA,
            CHECKOUT_RETIREMENT_SCHEMA,
            CHECKOUT_UNLINK_SCHEMA,
        ] {
            let parent = tempfile::tempdir()?;
            let mut store = Store::open(parent.path(), true)?;
            store.profile_transaction(|_| Ok(()))?;
            store.checkout_transaction(|_| Ok(()))?;
            if before == CHECKOUT_RETIREMENT_SCHEMA {
                store.checkout_retirement_transaction(|_| Ok(()))?;
            } else if before == CHECKOUT_UNLINK_SCHEMA {
                store.checkout_unlink_transaction(|_| Ok(()))?;
            }
            store.connection.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES ('preserved','test.original','verified','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','original immutable receipt')", [])?;
            let original_schema = schema(&store.connection)?;
            let failed: Result<()> = store.binding_retirement_transaction(|transaction| {
                assert!(journal::checkout_unlink_epoch(transaction)?);
                transaction.execute("INSERT INTO native_binding_retirement(binding_operation_id,request_operation_id,retirement_operation_id) VALUES ('missing-binding','missing-request','missing-receipt')", []).map_err(database)?;
                Ok(())
            });
            assert!(failed.is_err());
            assert_eq!(store.version()?, before);
            assert_eq!(schema(&store.connection)?, original_schema);
            store.binding_retirement_transaction(|transaction| {
                assert_eq!(
                    transaction
                        .query_row("SELECT count(*) FROM native_binding_retirement", [], |r| {
                            r.get::<_, i64>(0)
                        })
                        .map_err(database)?,
                    0
                );
                Ok(())
            })?;
            assert_eq!(store.version()?, BINDING_RETIREMENT_SCHEMA);
            let detail: String = store.connection.query_row(
                "SELECT detail FROM operation WHERE operation_id='preserved'",
                [],
                |r| r.get(0),
            )?;
            assert_eq!(detail, "original immutable receipt");
            store.profile_transaction(|_| Ok(()))?;
            store.enrollment_recovery_transaction(|_| Ok(()))?;
            store.checkout_transaction(|_| Ok(()))?;
            store.checkout_retirement_transaction(|_| Ok(()))?;
            store.checkout_unlink_transaction(|_| Ok(()))?;
            assert_eq!(store.version()?, BINDING_RETIREMENT_SCHEMA);
            drop(store);
            let store = Store::open(parent.path(), false)?;
            assert_eq!(store.version()?, BINDING_RETIREMENT_SCHEMA);
            assert!(journal::checkout_unlink_epoch(&store.connection)?);
            store
                .connection
                .pragma_update(None, "user_version", CHECKOUT_LOCATION_SCHEMA + 1)?;
            drop(store);
            assert!(Store::open(parent.path(), false).is_err());
            assert!(!has_checkout_unlinks(CHECKOUT_LOCATION_SCHEMA + 1));
            assert!(profile_schema_after(CHECKOUT_LOCATION_SCHEMA + 1).is_err());
            assert!(checkout_schema_after(CHECKOUT_LOCATION_SCHEMA + 1).is_err());
            assert!(unlink_schema_after(CHECKOUT_LOCATION_SCHEMA + 1).is_err());
        }
        Ok(())
    }

    fn schema(connection: &Connection) -> rusqlite::Result<Vec<(String, String)>> {
        let mut query = connection.prepare(
            "SELECT name,coalesce(sql,'') FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY name",
        )?;
        query
            .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))?
            .collect()
    }

    #[test]
    fn unlink_epoch_rolls_back_original_data_and_never_downgrades()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        for before in [CHECKOUT_LINK_SCHEMA, CHECKOUT_RETIREMENT_SCHEMA] {
            let parent = tempfile::tempdir()?;
            let mut store = Store::open(parent.path(), true)?;
            store.profile_transaction(|_| Ok(()))?;
            store.checkout_transaction(|_| Ok(()))?;
            if before == CHECKOUT_RETIREMENT_SCHEMA {
                store.checkout_retirement_transaction(|_| Ok(()))?;
            }
            store.connection.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES ('retained','fixture','verified','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','original-bytes')", [])?;
            let original_schema = schema(&store.connection)?;
            let failed: Result<()> = store.checkout_unlink_transaction(|transaction| {
                assert!(journal::checkout_unlink_epoch(transaction)?);
                transaction
                    .execute(
                        "UPDATE operation SET detail='uncommitted' WHERE operation_id='retained'",
                        [],
                    )
                    .map_err(database)?;
                Err(Failure::precondition(
                    "unlink admission failed after its format fence",
                ))
            });
            assert!(failed.is_err());
            assert_eq!(store.version()?, before);
            assert_eq!(schema(&store.connection)?, original_schema);
            drop(store);
            let mut store = Store::open(parent.path(), false)?;
            let retained: String = store.connection.query_row(
                "SELECT detail FROM operation WHERE operation_id='retained'",
                [],
                |row| row.get(0),
            )?;
            assert_eq!(retained, "original-bytes");
            store.checkout_unlink_transaction(|_| Ok(()))?;
            assert_eq!(store.version()?, CHECKOUT_UNLINK_SCHEMA);
            store.profile_transaction(|_| Ok(()))?;
            store.enrollment_recovery_transaction(|_| Ok(()))?;
            store.checkout_transaction(|_| Ok(()))?;
            store.checkout_retirement_transaction(|_| Ok(()))?;
            assert_eq!(store.version()?, CHECKOUT_UNLINK_SCHEMA);
            drop(store);
            let store = Store::open(parent.path(), false)?;
            assert_eq!(store.version()?, CHECKOUT_UNLINK_SCHEMA);
            assert!(journal::checkout_unlink_epoch(&store.connection)?);
        }
        Ok(())
    }

    #[test]
    fn unlink_records_require_their_epoch_and_share_recovery_capacity()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let parent = tempfile::tempdir()?;
        let mut store = Store::open(parent.path(), true)?;
        store.profile_transaction(|_| Ok(()))?;
        store.checkout_transaction(|_| Ok(()))?;
        store.checkout_retirement_transaction(|_| Ok(()))?;
        store.connection.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at) VALUES ('malformed-old-unlink','corporate.project_unlink','completed','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')", [])?;
        assert!(journal::checkout_unlink_epoch(&store.connection).is_err());
        assert!(
            store
                .transaction(|t| journal::recovery_capacity(t, 1))
                .is_err()
        );
        assert_eq!(store.version()?, CHECKOUT_RETIREMENT_SCHEMA);
        store.connection.execute(
            "DELETE FROM operation WHERE operation_id='malformed-old-unlink'",
            [],
        )?;
        store.checkout_unlink_transaction(|transaction| {
            for index in 0..126 {
                transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at) VALUES (?,'sync.run','applying','2026-01-01T00:00:00Z')", [format!("pending_{index}")]).map_err(database)?;
            }
            transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at) VALUES ('pending_unlink','corporate.project_unlink','applying','2026-01-01T00:00:00Z')", []).map_err(database)?;
            journal::recovery_capacity(transaction, 1)?;
            assert!(journal::recovery_capacity(transaction, 2).is_err());
            transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at) VALUES ('pending_set','publication.set','applying','2026-01-01T00:00:00Z')", []).map_err(database)?;
            assert!(journal::recovery_capacity(transaction, 1).is_err());
            Ok(())
        })?;
        Ok(())
    }

    #[test]
    fn checkout_epoch_admission_rolls_back_ddl_version_and_previous_journal_together()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        for before in [PROFILE_SCHEMA, ENROLLMENT_RECOVERY_SCHEMA] {
            let parent = tempfile::tempdir()?;
            let mut store = Store::open(parent.path(), true)?;
            store.profile_transaction(|_| Ok(()))?;
            if before == ENROLLMENT_RECOVERY_SCHEMA {
                store.enrollment_recovery_transaction(|_| Ok(()))?;
            }
            store.connection.execute(
                "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES ('original-receipt','fixture','verified','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','original-bytes')",
                [],
            )?;
            let original_schema = schema(&store.connection)?;
            let failed: Result<()> = store.checkout_transaction(|transaction| {
                transaction.execute(
                    "UPDATE operation SET detail='uncommitted-change' WHERE operation_id='original-receipt'",
                    [],
                ).map_err(database)?;
                Err(Failure::precondition("fixture admission failed after the format upgrade"))
            });
            assert!(failed.is_err());
            assert_eq!(store.version()?, before);
            assert_eq!(schema(&store.connection)?, original_schema);
            let receipt: String = store.connection.query_row(
                "SELECT detail FROM operation WHERE operation_id='original-receipt'",
                [],
                |row| row.get(0),
            )?;
            assert_eq!(receipt, "original-bytes");
            drop(store);
            // Reopen through the real layout validator, rather than trusting
            // only PRAGMA or an in-memory transaction result.
            let mut store = Store::open(parent.path(), false)?;
            assert_eq!(store.version()?, before);
            store.checkout_transaction(|_| Ok(()))?;
            assert_eq!(store.version()?, CHECKOUT_LINK_SCHEMA);
            store.profile_transaction(|_| Ok(()))?;
            store.enrollment_recovery_transaction(|_| Ok(()))?;
            assert_eq!(store.version()?, CHECKOUT_LINK_SCHEMA);
            drop(store);
            let store = Store::open(parent.path(), false)?;
            assert_eq!(store.version()?, CHECKOUT_LINK_SCHEMA);
            assert!(store.connection.query_row(
                "SELECT EXISTS(SELECT 1 FROM sqlite_schema WHERE type='table' AND name='native_checkout_reservation')",
                [], |row| row.get::<_, bool>(0),
            )?);
            let receipt: String = store.connection.query_row(
                "SELECT detail FROM operation WHERE operation_id='original-receipt'",
                [],
                |row| row.get(0),
            )?;
            assert_eq!(receipt, "original-bytes");
        }
        Ok(())
    }

    #[test]
    fn checkout_retirement_epoch_rolls_back_and_never_downgrades()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let parent = tempfile::tempdir()?;
        let mut store = Store::open(parent.path(), true)?;
        store.profile_transaction(|_| Ok(()))?;
        store.checkout_transaction(|_| Ok(()))?;
        store.connection.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES ('retained','fixture','verified','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','exact-original')", [])?;
        let before = schema(&store.connection)?;
        let failed: Result<()> = store.checkout_retirement_transaction(|t| {
            t.execute(
                "UPDATE operation SET detail='uncommitted' WHERE operation_id='retained'",
                [],
            )
            .map_err(database)?;
            Err(Failure::precondition(
                "retirement failed after its format fence",
            ))
        });
        assert!(failed.is_err());
        assert_eq!(store.version()?, CHECKOUT_LINK_SCHEMA);
        assert_eq!(schema(&store.connection)?, before);
        drop(store);
        let mut store = Store::open(parent.path(), false)?;
        store.checkout_retirement_transaction(|_| Ok(()))?;
        assert_eq!(store.version()?, CHECKOUT_RETIREMENT_SCHEMA);
        store.profile_transaction(|_| Ok(()))?;
        store.enrollment_recovery_transaction(|_| Ok(()))?;
        store.checkout_transaction(|_| Ok(()))?;
        assert_eq!(store.version()?, CHECKOUT_RETIREMENT_SCHEMA);
        drop(store);
        let store = Store::open(parent.path(), false)?;
        assert_eq!(store.version()?, CHECKOUT_RETIREMENT_SCHEMA);
        let retained: String = store.connection.query_row(
            "SELECT detail FROM operation WHERE operation_id='retained'",
            [],
            |r| r.get(0),
        )?;
        assert_eq!(retained, "exact-original");
        Ok(())
    }
}
