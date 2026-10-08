use std::{error::Error, fs, sync::Barrier};

use ai_stp_cli_v2::{
    authoring::{Identity, discovery, importing},
    error::Failure,
    harnesses::{Root, Scope},
    store::{
        Store,
        revisions::{self, Write},
    },
};
use serde_json::json;

const AT: &str = "2026-10-08T00:00:00.000Z";
const LATER: &str = "2026-10-09T00:00:00.000Z";

fn counts(store: &mut Store) -> Result<[i64; 6], Failure> {
    store.transaction(|t| t.query_row("SELECT (SELECT count(*) FROM entity),(SELECT count(*) FROM revision),(SELECT count(*) FROM content),(SELECT count(*) FROM component_source_binding),(SELECT count(*) FROM operation),(SELECT count(*) FROM object_version)",[],|r|Ok([r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?])).map_err(|_| Failure::input("proof query failed")))
}

#[test]
fn selected_graph_import_is_atomic_owned_and_replayable() -> Result<(), Box<dyn Error>> {
    let state = tempfile::tempdir()?;
    let source = tempfile::tempdir()?;
    let config = "model = 'unchanged-setting'\n[mcp_servers.docs]\ncommand = 'docs-server'\n";
    let instructions = "# Instructions\nReview every changed file.\n";
    fs::write(source.path().join("config.toml"), config)?;
    fs::write(source.path().join("AGENTS.md"), instructions)?;
    let discovered = discovery::at(source.path(), "codex", Scope::Global, Root::Config)?;
    assert!(discovered.complete);
    let request = importing::Request {
        root: source.path().into(),
        harness_id: "codex".into(),
        scope: Scope::Global,
        root_kind: Root::Config,
        candidates: discovered
            .components
            .iter()
            .filter(|c| matches!(c.component_type.as_str(), "instruction" | "mcp"))
            .map(|c| c.candidate_id.clone())
            .collect(),
    };
    assert_eq!(request.candidates.len(), 2);
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let mut store = Store::open(state.path(), true)?;
    let before = counts(&mut store)?;
    for candidates in [
        vec![],
        vec![request.candidates[0].clone(); 2],
        vec!["sha256:".to_owned() + &"0".repeat(64)],
    ] {
        let mut invalid = request.clone();
        invalid.candidates = candidates;
        assert!(importing::plan(&mut store, invalid, identity.clone(), AT).is_err());
    }
    let plan = importing::plan(&mut store, request.clone(), identity.clone(), AT)?;
    assert_eq!(counts(&mut store)?, before);
    assert_eq!(plan.passport["visibility"], "private");
    assert_eq!(
        plan.passport["facts"]["capture_mode"]["value"],
        "selected_components"
    );
    assert!(plan.passport.get("version").is_none());
    assert!(plan.passport["facts"].get("backup_id").is_none());
    let plan: importing::Plan = serde_json::from_value(ai_stp_cli_v2::canonical::parse(
        &ai_stp_cli_v2::canonical::bytes(&serde_json::to_value(plan)?)?,
    )?)?;
    let digest = plan.digest()?;
    assert!(importing::apply(&mut store, &plan, "wrong-digest", &identity, AT).is_err());
    assert!(importing::apply(&mut store, &plan, &digest, &identity, LATER).is_err());
    let mut forged = plan.clone();
    forged.components[0].passport["visibility"] = "public".into();
    assert!(importing::apply(&mut store, &forged, &forged.digest()?, &identity, AT).is_err());
    let mut foreign = identity.clone();
    foreign.account_id = "account_01ARZ3NDEKTSV4RRFFQ69G5FAW".into();
    assert!(importing::apply(&mut store, &plan, &digest, &foreign, AT).is_err());
    fs::write(source.path().join("AGENTS.md"), "Changed after planning.\n")?;
    assert!(importing::apply(&mut store, &plan, &digest, &identity, AT).is_err());
    fs::write(source.path().join("AGENTS.md"), instructions)?;
    let credential = "synthetic-import-credential-must-not-leak";
    fs::write(
        source.path().join("config.toml"),
        format!("{config}env = {{ TOKEN = '{credential}' }}\n"),
    )?;
    let error = importing::apply(&mut store, &plan, &digest, &identity, AT)
        .err()
        .ok_or("credential accepted")?;
    assert!(!format!("{error:?}").contains(credential));
    fs::write(source.path().join("config.toml"), config)?;
    assert_eq!(counts(&mut store)?, before);
    store.transaction(|t|t.execute_batch("CREATE TEMP TRIGGER fail_import BEFORE INSERT ON entity WHEN NEW.kind='setup' BEGIN SELECT RAISE(ABORT,'proof failure'); END;").map_err(|_|Failure::input("proof trigger failed")))?;
    assert!(importing::apply(&mut store, &plan, &digest, &identity, AT).is_err());
    assert_eq!(counts(&mut store)?, before);
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER fail_import;")
            .map_err(|_| Failure::input("proof trigger failed"))
    })?;
    let barrier = Barrier::new(2);
    drop(store);
    let (left, right) = std::thread::scope(|scope| {
        let worker = scope.spawn(|| -> Result<_, Failure> {
            barrier.wait();
            let mut other = Store::open(state.path(), false)?;
            importing::apply(&mut other, &plan, &digest, &identity, AT)
        });
        barrier.wait();
        let left = (|| {
            let mut store = Store::open(state.path(), false)?;
            importing::apply(&mut store, &plan, &digest, &identity, AT)
        })();
        (left, worker.join())
    });
    let imported = left?;
    assert_eq!(imported, right.map_err(|_| "import worker panicked")??);
    let mut store = Store::open(state.path(), false)?;
    assert_eq!(counts(&mut store)?, [3, 3, 2, 2, 1, 0]);
    assert_eq!(
        fs::read_to_string(source.path().join("config.toml"))?,
        config
    );
    assert_eq!(
        fs::read_to_string(source.path().join("AGENTS.md"))?,
        instructions
    );
    // A later draft must invalidate an uncommitted import but remain untouched
    // by the receipt of the already completed graph.
    let stale = importing::plan(&mut store, request.clone(), identity.clone(), AT)?;
    let mut changed = plan.components[0].passport.clone();
    changed["facts"]["description"] =
        json!({"value":"User metadata","origin":"declared","confirmation":"none","observed_at":AT});
    changed["parent_revision_ids"] = json!([changed["revision_id"]]);
    store.transaction(|t| {
        revisions::commit(
            t,
            &changed,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: &[plan.components[0].passport["revision_id"]
                    .as_str()
                    .ok_or_else(|| Failure::input("proof revision missing"))?
                    .into()],
            },
        )
    })?;
    let before = counts(&mut store)?;
    assert!(importing::apply(&mut store, &stale, &stale.digest()?, &identity, AT).is_err());
    assert_eq!(counts(&mut store)?, before);
    let refreshed = importing::plan(&mut store, request, identity.clone(), AT)?;
    let refreshed = importing::apply(&mut store, &refreshed, &refreshed.digest()?, &identity, AT)?;
    assert_ne!(refreshed["stable_id"], imported["stable_id"]);
    assert_eq!(counts(&mut store)?, [4, 5, 2, 2, 2, 0]);
    source.close()?;
    assert_eq!(
        importing::apply(&mut store, &plan, &digest, &identity, LATER)?,
        imported
    );
    assert_eq!(counts(&mut store)?, [4, 5, 2, 2, 2, 0]);
    // A stored receipt cannot mask damage to an immutable member's content.
    store.transaction(|t| {
        t.execute("UPDATE content SET byte_length=byte_length+1", [])
            .map(|_| ())
            .map_err(|_| Failure::input("proof corruption failed"))
    })?;
    assert!(importing::apply(&mut store, &plan, &digest, &identity, LATER).is_err());
    let encoded = serde_json::to_value(&imported)?;
    assert!(
        encoded["facts"]["components"]["value"]
            .as_array()
            .is_some_and(|v| v.len() == 2)
    );
    Ok(())
}
