use std::{error::Error, fs};

use ai_stp_cli_v2::{
    digest,
    error::Failure,
    snapshot::Snapshot,
    store::{
        Store,
        revisions::{self, Write},
    },
};
use serde_json::{Value, json};

#[test]
fn durable_revision_history_replay_conflict_and_atomic_rollback() -> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    assert!(Store::open(root.path(), false).is_err());
    assert_eq!(fs::read_dir(root.path())?.count(), 0);
    let device = "device_01ARZ3NDEKTSV4RRFFQ69G5FAV";
    let id = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV";
    let at = "2026-10-08T00:00:00.000Z";
    let document = json!({"kind": "component", "stable_id": id,
        "owner_id": "account_01ARZ3NDEKTSV4RRFFQ69G5FAV", "created_at": at,
        "facts": {"name": {"value": "Native", "origin": "declared", "confirmation": "none"}}});
    let mut store = Store::open(root.path(), true)?;
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
    let mut reopened = Store::open(root.path(), false)?;
    reopened.transaction(|transaction| {
        assert_eq!(
            revisions::heads(transaction, id)?,
            std::slice::from_ref(&current)
        );
        Ok(())
    })?;
    drop(reopened);
    let path = root.path().join("ai-stp-v2-state/registry.sqlite3");
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
    assert_eq!(snapshot.report()["row_counts"]["revision"], 2);
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
