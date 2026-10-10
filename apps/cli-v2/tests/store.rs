use std::{error::Error, fs};

use ai_stp_cli_v2::{
    digest,
    error::Failure,
    snapshot::Snapshot,
    store::{
        Store,
        revisions::{self, Write},
        versions::{self, Increment},
    },
};
use serde_json::{Value, json};

#[test]
fn durable_revision_history_replay_conflict_and_atomic_rollback() -> Result<(), Box<dyn Error>> {
    if let Ok(mode) = std::env::var("AI_STP_STORE_TEST_MODE") {
        return sqlite_child(&mode);
    }
    confined_registry_and_wal_recovery()?;
    interrupted_bootstrap_remains_readable_and_resumable()?;
    let root = tempfile::tempdir()?;
    assert!(Store::open(root.path(), false).is_err());
    assert_eq!(fs::read_dir(root.path())?.count(), 0);
    let device = "device_01ARZ3NDEKTSV4RRFFQ69G5FAV";
    let id = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV";
    let at = "2026-10-08T00:00:00.000Z";
    let document = json!({"kind": "component", "stable_id": id,
        "owner_id": "account_01ARZ3NDEKTSV4RRFFQ69G5FAV", "created_at": at,
        "facts": {"name": {"value": "Native", "origin": "declared", "confirmation": "none"}}});
    let mut planning = Store::planning(root.path())?;
    assert!(
        planning
            .transaction(|t| revisions::commit(
                t,
                &document,
                device,
                None,
                Write::Advance {
                    expected_heads: &[]
                }
            ))
            .is_err()
    );
    assert!(
        planning
            .transaction(|t| revisions::heads(t, id))?
            .is_empty()
    );
    drop(planning);
    assert_eq!(fs::read_dir(root.path())?.count(), 0);
    // A crash during initial ownership must be resumable only as the exact
    // public prefix in an otherwise empty namespace. Planning never repairs it.
    let namespace = root.path().join("ai-stp-v2-state");
    fs::create_dir(&namespace)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&namespace, fs::Permissions::from_mode(0o700))?;
    }
    fs::write(namespace.join("lock"), b"")?;
    fs::write(namespace.join("owner"), b"ai-stp-cli-v2 local")?;
    drop(Store::planning(root.path())?);
    assert_eq!(fs::read(namespace.join("owner"))?, b"ai-stp-cli-v2 local");
    fs::write(namespace.join("unowned.txt"), b"do not claim")?;
    assert!(Store::open(root.path(), true).is_err());
    assert_eq!(fs::read(namespace.join("unowned.txt"))?, b"do not claim");
    fs::remove_file(namespace.join("unowned.txt"))?;
    let mut store = Store::open(root.path(), true)?;
    assert_eq!(
        fs::read(namespace.join("owner"))?,
        b"ai-stp-cli-v2 local registry v1\n"
    );
    let first = store.transaction(|transaction| {
        revisions::commit(
            transaction,
            &document,
            device,
            None,
            Write::Advance {
                expected_heads: &[],
            },
        )
    })?;
    let initial = first["revision_id"]
        .as_str()
        .ok_or("revision missing")?
        .to_owned();
    let mut child = first.clone();
    child["parent_revision_ids"] = json!([initial]);
    child["facts"]["name"]["value"] = "Changed".into();
    let second = store.transaction(|transaction| {
        revisions::commit(
            transaction,
            &child,
            device,
            None,
            Write::Advance {
                expected_heads: std::slice::from_ref(&initial),
            },
        )
    })?;
    let current = second["revision_id"]
        .as_str()
        .ok_or("child missing")?
        .to_owned();
    let replay = store.transaction(|transaction| {
        revisions::commit(
            transaction,
            &document,
            device,
            None,
            Write::Advance {
                expected_heads: &[],
            },
        )
    })?;
    assert_eq!(replay, first);
    child["facts"]["name"]["value"] = "Stale writer".into();
    assert!(
        store
            .transaction(|transaction| revisions::commit(
                transaction,
                &child,
                device,
                None,
                Write::Advance {
                    expected_heads: std::slice::from_ref(&initial)
                }
            ))
            .is_err()
    );
    child["parent_revision_ids"] = json!([current]);
    let outcome: Result<Value, Failure> = store.transaction(|transaction| {
        revisions::content(transaction, b"must roll back together", at)?;
        revisions::commit(
            transaction,
            &child,
            device,
            None,
            Write::Advance {
                expected_heads: std::slice::from_ref(&current),
            },
        )?;
        Err(Failure::precondition("injected interruption before commit"))
    });
    assert!(outcome.is_err());
    store.transaction(|transaction| {
        assert_eq!(
            revisions::heads(transaction, id)?,
            std::slice::from_ref(&current)
        );
        assert_eq!(
            transaction
                .query_row("SELECT count(*) FROM content", [], |row| row
                    .get::<_, i64>(0))
                .map_err(|_| Failure::precondition("proof query failed"))?,
            0
        );
        Ok(())
    })?;
    // Another process cannot initialize or mutate this directory while owned.
    assert!(Store::open(root.path(), true).is_err());
    drop(store);
    let mut planning = Store::planning(root.path())?;
    assert_eq!(
        planning.transaction(|t| revisions::heads(t, id))?,
        std::slice::from_ref(&current)
    );
    assert!(
        planning
            .transaction(|t| revisions::content(t, b"planning must never persist", at))
            .is_err()
    );
    drop(planning);
    let mut reopened = Store::open(root.path(), false)?;
    let cases: Value = serde_json::from_str(include_str!(
        "../../../packages/contracts/src/ai_stp_contracts/fixtures/v1/catalog.json"
    ))?;
    let mut immutable = cases["cases"]
        .as_array()
        .ok_or("fixture cases absent")?
        .iter()
        .find(|case| case["case_id"] == "readComponentVersion.published")
        .ok_or("version fixture absent")?["body"]["passport"]
        .clone();
    immutable["stable_id"] = id.into();
    assert_eq!(
        ai_stp_cli_v2::passport::versions::seal_adaptation(&immutable["adaptations"][0])?,
        immutable["adaptations"][0]
    );
    immutable["owner_id"] = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into();
    assert!(
        reopened
            .transaction(|transaction| revisions::commit(
                transaction,
                &immutable,
                device,
                None,
                Write::Immutable
            ))
            .is_err(),
        "an immutable snapshot changed its entity owner"
    );
    immutable["owner_id"] = document["owner_id"].clone();
    immutable["version"] = "1.0".into();
    reopened.transaction(|transaction| {
        assert_eq!(versions::next(transaction, id, Increment::Minor)?, "1.0");
        versions::record(transaction, &immutable, device, None, at)
    })?;
    let mut substituted = immutable.clone();
    substituted["name"] = "Substituted immutable version".into();
    assert!(
        reopened
            .transaction(|transaction| versions::record(
                transaction,
                &substituted,
                device,
                None,
                at
            ))
            .is_err()
    );
    reopened.transaction(|transaction| {
        versions::record(transaction, &immutable, device, None, at)?;
        assert_eq!(versions::next(transaction, id, Increment::Minor)?, "1.1");
        assert_eq!(versions::next(transaction, id, Increment::Major)?, "2.0");
        assert_eq!(
            revisions::heads(transaction, id)?,
            std::slice::from_ref(&current)
        );
        Ok(())
    })?;
    drop(reopened);
    let path = root.path().join("ai-stp-v2-state/registry.sqlite3");
    let alias = root.path().join("registry-alias");
    fs::hard_link(&path, &alias)?;
    assert!(
        Store::open(root.path(), false).is_err(),
        "a hard-linked writable registry was opened"
    );
    fs::remove_file(alias)?;
    let connection = rusqlite::Connection::open(&path)?;
    let integrity: String = connection.query_row("PRAGMA integrity_check", [], |row| row.get(0))?;
    assert_eq!(integrity, "ok");
    assert_eq!(
        connection.query_row("SELECT count(*) FROM pragma_foreign_key_check", [], |row| {
            row.get::<_, i64>(0)
        })?,
        0
    );
    connection.pragma_update(None, "journal_mode", "DELETE")?;
    drop(connection);
    let bytes = fs::read(&path)?;
    let snapshot = Snapshot::from_bytes(&bytes, &digest::sha256(&bytes))?;
    assert_eq!(snapshot.report()["table_count"], 51);
    assert_eq!(snapshot.report()["row_counts"]["revision"], 3);
    assert_eq!(
        snapshot.exact_version(id, "1.0", None)?["name"],
        immutable["name"]
    );
    assert_eq!(
        snapshot.passport("component", Some(id))?["revision_id"],
        current
    );
    let connection = rusqlite::Connection::open(&path)?;
    connection.pragma_update(None, "user_version", 54)?;
    drop(connection);
    let before = fs::read(&path)?;
    assert!(Store::open(root.path(), true).is_err());
    assert_eq!(
        fs::read(&path)?,
        before,
        "a newer registry was changed before refusal"
    );
    Ok(())
}

fn interrupted_bootstrap_remains_readable_and_resumable() -> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let namespace = root.path().join("ai-stp-v2-state");
    fs::create_dir(&namespace)?;
    fs::write(
        namespace.join("owner"),
        b"ai-stp-cli-v2 local registry v1\n",
    )?;
    fs::write(namespace.join("lock"), b"")?;
    let path = namespace.join("registry.sqlite3");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&namespace, fs::Permissions::from_mode(0o700))?;
        for name in ["owner", "lock"] {
            fs::set_permissions(namespace.join(name), fs::Permissions::from_mode(0o600))?;
        }
    }
    // Interruption after ownership, before creating the database. Orphaned
    // companions must never be mistaken for a fresh, empty registry.
    drop(Store::planning(root.path())?);
    assert!(!path.exists());
    fs::write(namespace.join("registry.sqlite3-wal"), b"foreign companion")?;
    assert!(Store::planning(root.path()).is_err());
    assert!(Store::open(root.path(), true).is_err());
    assert!(!path.exists());
    assert_eq!(
        fs::read(namespace.join("registry.sqlite3-wal"))?,
        b"foreign companion"
    );
    fs::remove_file(namespace.join("registry.sqlite3-wal"))?;
    fs::write(&path, b"")?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
    }
    // Interruption after durable file creation, before the schema transaction.
    drop(Store::planning(root.path())?);
    assert!(fs::read(&path)?.is_empty());
    assert_eq!(fs::read_dir(&namespace)?.count(), 3);
    drop(Store::open(root.path(), true)?);
    let db = rusqlite::Connection::open(&path)?;
    db.pragma_update(None, "journal_mode", "DELETE")?;
    drop(db);
    // Interruption after schema commit, before activation of WAL. Planning is
    // query-only; the next writer resumes the existing valid database in place.
    let before = fs::read(&path)?;
    let mut planning = Store::planning(root.path())?;
    planning.transaction(|tx| {
        let tables:i64=tx.query_row("SELECT count(*) FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'",[],|r|r.get(0)).map_err(|_|Failure::precondition("fixture schema read"))?;
        assert_eq!(tables,51);
        assert!(tx.execute("INSERT INTO operation(operation_id,kind,state,started_at) VALUES ('x','x','x','x')",[]).is_err());
        Ok(())
    })?;
    drop(planning);
    assert_eq!(fs::read(&path)?, before);
    drop(Store::open(root.path(), true)?);
    let db = rusqlite::Connection::open(&path)?;
    assert_eq!(
        db.query_row("PRAGMA journal_mode", [], |r| r.get::<_, String>(0))?,
        "wal"
    );
    assert_eq!(
        db.query_row("PRAGMA integrity_check", [], |r| r.get::<_, String>(0))?,
        "ok"
    );
    Ok(())
}

fn sqlite_process(mode: &str, root: &std::path::Path, allowed: bool) -> Result<(), Box<dyn Error>> {
    let result = std::process::Command::new(std::env::current_exe()?)
        .args([
            "--exact",
            "durable_revision_history_replay_conflict_and_atomic_rollback",
            "--nocapture",
        ])
        .env("AI_STP_STORE_TEST_MODE", mode)
        .env("AI_STP_STORE_TEST_ROOT", root)
        .env(
            "AI_STP_STORE_TEST_ALLOWED",
            if allowed { "yes" } else { "no" },
        )
        .output()?;
    assert!(
        result.status.success(),
        "SQLite child failed: {}{}",
        String::from_utf8_lossy(&result.stdout),
        String::from_utf8_lossy(&result.stderr)
    );
    Ok(())
}

fn sqlite_child(mode: &str) -> Result<(), Box<dyn Error>> {
    let root = std::path::PathBuf::from(
        std::env::var_os("AI_STP_STORE_TEST_ROOT").ok_or("missing fixture root")?,
    );
    let path = root.join("ai-stp-v2-state/registry.sqlite3");
    if mode == "native-crash" {
        let mut store = Store::open(&root, false)?;
        store.transaction(|tx| {
            tx.execute("INSERT INTO operation(operation_id,kind,state,started_at) VALUES ('native-crash','fixture','complete','fixture')", [])
                .map_err(|_| Failure::precondition("fixture insertion"))?;
            Ok(())
        })?;
        // Exit without running destructors or SQLite's close/checkpoint path.
        std::process::exit(0);
    }
    let db = rusqlite::Connection::open(path)?;
    db.busy_timeout(std::time::Duration::ZERO)?;
    if matches!(mode, "standard-write-hold" | "standard-read-hold") {
        db.execute_batch(if mode == "standard-read-hold" {
            "BEGIN; SELECT count(*) FROM operation;"
        } else {
            "BEGIN IMMEDIATE"
        })?;
        fs::write(root.join("sqlite-lock-ready"), b"ready")?;
        use std::io::Read;
        std::io::stdin().read_exact(&mut [0])?;
        db.execute_batch("ROLLBACK")?;
        return Ok(());
    }
    if mode == "standard-crash" {
        db.execute("INSERT INTO operation(operation_id,kind,state,started_at) VALUES ('standard-crash','fixture','complete','fixture')", [])?;
        std::process::exit(0);
    }
    let acquired = db.execute_batch("BEGIN IMMEDIATE; ROLLBACK;");
    if std::env::var("AI_STP_STORE_TEST_ALLOWED")? == "yes" {
        acquired?;
    } else {
        assert!(matches!(
            acquired,
            Err(rusqlite::Error::SqliteFailure(error, _))
                if error.code == rusqlite::ErrorCode::DatabaseBusy
        ));
    }
    Ok(())
}

fn confined_registry_and_wal_recovery() -> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let namespace = root.path().join("ai-stp-v2-state");
    let path = namespace.join("registry.sqlite3");
    let mut store = Store::open(root.path(), true)?;
    sqlite_process("standard-lock", root.path(), false)?;
    store.transaction(|tx| {
        assert_eq!(
            tx.query_row("PRAGMA locking_mode", [], |r| r.get::<_, String>(0))
                .map_err(|_| Failure::precondition("fixture mode"))?,
            "exclusive"
        );
        Ok(())
    })?;
    drop(store);
    sqlite_process("standard-lock", root.path(), true)?;
    for mode in ["standard-write-hold", "standard-read-hold"] {
        let mut child = std::process::Command::new(std::env::current_exe()?)
            .args([
                "--exact",
                "durable_revision_history_replay_conflict_and_atomic_rollback",
            ])
            .env("AI_STP_STORE_TEST_MODE", mode)
            .env("AI_STP_STORE_TEST_ROOT", root.path())
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::null())
            .spawn()?;
        let started = std::time::Instant::now();
        while !root.path().join("sqlite-lock-ready").exists() {
            if started.elapsed() > std::time::Duration::from_secs(10) {
                child.kill()?;
                child.wait()?;
                return Err("SQLite lock holder did not start".into());
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        let refused = Store::open(root.path(), false).is_err();
        use std::io::Write;
        child
            .stdin
            .take()
            .ok_or("missing child input")?
            .write_all(b"x")?;
        assert!(child.wait()?.success());
        assert!(
            refused,
            "native SQLite ignored the existing standard connection"
        );
        fs::remove_file(root.path().join("sqlite-lock-ready"))?;
    }
    for mode in ["standard-crash", "native-crash"] {
        sqlite_process(mode, root.path(), true)?;
        assert!(namespace.join("registry.sqlite3-wal").metadata()?.len() > 0);
        let mut store = Store::open(root.path(), false)?;
        store.transaction(|tx| {
            let found: i64 = tx
                .query_row(
                    "SELECT count(*) FROM operation WHERE operation_id=?",
                    [mode],
                    |r| r.get(0),
                )
                .map_err(|_| Failure::precondition("fixture recovery"))?;
            assert_eq!(found, 1);
            Ok(())
        })?;
        drop(store);
        let db = rusqlite::Connection::open(&path)?;
        assert_eq!(
            db.query_row("PRAGMA integrity_check", [], |r| r.get::<_, String>(0))?,
            "ok"
        );
    }
    for companion in ["registry.sqlite3-journal", "registry.sqlite3-wal"] {
        let companion = namespace.join(companion);
        fs::write(&companion, b"foreign companion must remain intact")?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&companion, fs::Permissions::from_mode(0o600))?;
        }
        assert!(Store::open(root.path(), true).is_err());
        assert_eq!(
            fs::read(&companion)?,
            b"foreign companion must remain intact"
        );
        fs::remove_file(companion)?;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::{PermissionsExt, symlink};
        let foreign = root.path().join("foreign");
        fs::write(&foreign, b"unchanged")?;
        fs::set_permissions(&foreign, fs::Permissions::from_mode(0o600))?;
        for companion in [
            "registry.sqlite3-wal",
            "registry.sqlite3-journal",
            "registry.sqlite3-shm",
        ] {
            let companion = namespace.join(companion);
            symlink(&foreign, &companion)?;
            assert!(Store::open(root.path(), true).is_err());
            fs::remove_file(&companion)?;
            fs::hard_link(&foreign, &companion)?;
            assert!(Store::open(root.path(), true).is_err());
            fs::remove_file(companion)?;
            assert_eq!(fs::read(&foreign)?, b"unchanged");
        }
        let mut store = Store::open(root.path(), false)?;
        let held = root.path().join("held-original");
        fs::rename(&namespace, &held)?;
        fs::create_dir(&namespace)?;
        fs::set_permissions(&namespace, fs::Permissions::from_mode(0o700))?;
        fs::write(&path, b"replacement database must remain intact")?;
        assert!(store.transaction(|_| Ok(())).is_err());
        drop(store);
        assert_eq!(fs::read(&path)?, b"replacement database must remain intact");
        fs::remove_file(&path)?;
        fs::remove_dir(&namespace)?;
        fs::rename(&held, &namespace)?;
        drop(Store::open(root.path(), false)?);
    }
    Ok(())
}
