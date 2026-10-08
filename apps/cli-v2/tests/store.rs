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
