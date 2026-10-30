use std::{error::Error, fs};

use serde_json::json;

use super::{
    drain,
    input::Input,
    journal::{self, Row},
    moment,
};
use crate::{authoring::Identity, error::Failure, store::Store};

#[test]
fn checkout_location_keeps_unfinished_task_roots_and_proves_unrelated_work_disjoint()
-> Result<(), Box<dyn Error>> {
    let fixture = tempfile::tempdir()?;
    let checkout = fixture.path().join("checkout");
    let descendant = checkout.join("nested-target");
    let unrelated = fixture.path().join("unrelated");
    fs::create_dir(&checkout)?;
    fs::create_dir(&descendant)?;
    fs::create_dir(&unrelated)?;
    for (label, target, refuses) in [
        ("same", checkout.clone(), true),
        ("alias", checkout.join("..").join("checkout"), true),
        ("descendant", descendant, true),
        ("unrelated", unrelated, false),
        (
            "missing",
            fixture.path().join("missing-unfinished-root"),
            true,
        ),
    ] {
        let state = fixture.path().join(format!("state-{label}"));
        fs::create_dir(&state)?;
        let mut store = Store::open(&state, true)?;
        let input = super::install::Input::parse(json!({
            "harness_id":"codex","operation":"remove","targets":{"project":target},
            "project_root":target,"provider_version":"0.0.95",
        }))?;
        let owner = Identity {
            account_id: format!("account_{}", ulid::Ulid::generate()),
            device_id: format!("device_{}", ulid::Ulid::generate()),
        };
        // Retain the actual producer's valid initial row as if interrupted
        // before its first child plan. No provider or vendor process is run.
        let task = Row::new(
            super::service::Input::Install(input),
            owner,
            &format!("location-task-{label}-01"),
            &moment(),
        )?;
        store.transaction(|t| journal::save(t, &task, None))?;
        let before = store.connection.serialize("main")?.to_vec();
        assert_eq!(
            super::location_unreserved(&store.connection, &checkout).is_err(),
            refuses,
            "{label}"
        );
        assert_eq!(
            store.connection.serialize("main")?.to_vec(),
            before,
            "{label}"
        );
        assert_eq!(
            journal::load(&store.connection, &task.id)?.original,
            task.original
        );
    }
    Ok(())
}

#[test]
fn lost_task_receipt_recovers_the_committed_child_without_source() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().canonicalize()?;
    let source = root.join("source");
    fs::create_dir(&source)?;
    fs::write(
        source.join("SKILL.md"),
        "---\nname: recovery\ndescription: Review code.\n---\nReport findings.\n",
    )?;
    let input = Input::parse(
        json!({"directory":source,"harness_id":"codex","component_type":"skill","name":"recovery","license_spdx":"MIT"}),
    )?;
    let identity = Identity {
        account_id: format!("account_{}", ulid::Ulid::generate()),
        device_id: format!("device_{}", ulid::Ulid::generate()),
    };
    let original_owner = identity.clone();
    let row = Row::new(input, identity, "author-recovery-01", &moment())?;
    let mut store = Store::open(&root, true)?;
    store.transaction(|t| journal::save(t, &row, None))?;
    store.transaction(|t|t.execute_batch("CREATE TEMP TRIGGER lose_task_receipt BEFORE UPDATE ON agent_task WHEN NEW.state='completed' BEGIN SELECT RAISE(ABORT,'injected task commit failure'); END;").map_err(|_|Failure::precondition("proof trigger failed")))?;
    let failure = drain(&mut store, row.clone())
        .err()
        .ok_or("injected commit failure was ignored")?;
    let pending = journal::load(&store.connection, &row.id)?;
    assert_eq!(pending.state, "running");
    assert_eq!(pending.children().len(), 1);
    assert!(pending.outcome.is_none());
    let objects: i64 =
        store
            .connection
            .query_row("SELECT count(*) FROM object_version", [], |row| row.get(0))?;
    assert_eq!(
        objects, 2,
        "unexpected failure before task receipt: {failure:?}"
    );
    fs::rename(source, root.join("removed-source"))?;
    drop(store);
    let mut store = Store::open(&root, false)?;
    let restored = journal::load(&store.connection, &row.id)?;
    let done = drain(&mut store, restored)?;
    assert_eq!(done["state"], "completed");
    assert_eq!(done["goal_satisfied"], true);
    assert_eq!(
        done["ownership"],
        json!({"kind":"personal",
        "native_account_id":original_owner.account_id,"native_device_id":original_owner.device_id})
    );
    let recorded = journal::load(&store.connection, &row.id)?;
    let before_read = store.connection.serialize("main")?.to_vec();
    let digest = journal::encode(&recorded.view()?)?;
    assert_eq!(store.connection.serialize("main")?.to_vec(), before_read);
    let retained = serde_json::to_value(&recorded.payload)?;
    assert_eq!(retained["format"], "ai-stp-native-task/1");
    assert!(retained.get("ownership").is_none());
    assert_eq!(journal::encode(&drain(&mut store, recorded)?)?, digest);
    assert!(journal::unsettled(&store.connection)?.is_empty());
    let after: i64 =
        store
            .connection
            .query_row("SELECT count(*) FROM object_version", [], |row| row.get(0))?;
    assert_eq!(after, objects);
    Ok(())
}
