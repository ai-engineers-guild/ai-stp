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
    let recorded = journal::load(&store.connection, &row.id)?;
    let digest = journal::encode(&recorded.view()?)?;
    assert_eq!(journal::encode(&drain(&mut store, recorded)?)?, digest);
    assert!(journal::unsettled(&store.connection)?.is_empty());
    let after: i64 =
        store
            .connection
            .query_row("SELECT count(*) FROM object_version", [], |row| row.get(0))?;
    assert_eq!(after, objects);
    Ok(())
}
