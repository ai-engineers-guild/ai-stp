use std::{error::Error, fs, sync::Barrier};

use ai_stp_cli_v2::{
    authoring::{Identity, discovery, importing, passports, releases, setups},
    digest,
    error::{ErrorKind, Failure},
    harnesses::{Root, Scope},
    store::{
        Store,
        revisions::{self, Write},
        versions::Increment,
    },
};
use serde_json::{Value, json};

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
    let results = [left, right.map_err(|_| "import worker panicked")?];
    let imported = results
        .iter()
        .find_map(|result| result.as_ref().ok())
        .ok_or("neither import completed")?
        .clone();
    for result in results {
        match result {
            Ok(receipt) => assert_eq!(receipt, imported),
            Err(error) => {
                // A durable import may outlast the bounded directory-lock wait.
                // Only that busy refusal can retry the same committed operation.
                assert!(matches!(error.kind, ErrorKind::Precondition), "{error:?}");
                assert_eq!(
                    error.details.get("stage").and_then(Value::as_str),
                    Some("lock_timeout")
                );
                let mut store = Store::open(state.path(), false)?;
                let before = counts(&mut store)?;
                assert_eq!(
                    importing::apply(&mut store, &plan, &digest, &identity, AT)?,
                    imported
                );
                assert_eq!(counts(&mut store)?, before);
            }
        }
    }
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
    let released = complete_import(&mut store, &imported, &identity)?;
    store.transaction(|t| {
        t.execute("UPDATE content SET byte_length=byte_length+1", [])
            .map(|_| ())
            .map_err(|_| Failure::input("proof corruption failed"))
    })?;
    assert!(importing::apply(&mut store, &plan, &digest, &identity, LATER).is_err());
    assert!(
        setups::releases::apply(&mut store, &released, &released.digest()?, &identity, LATER)
            .is_err()
    );
    let encoded = serde_json::to_value(&imported)?;
    assert!(
        encoded["facts"]["components"]["value"]
            .as_array()
            .is_some_and(|v| v.len() == 2)
    );
    Ok(())
}

fn field<'a>(value: &'a Value, name: &str) -> Result<&'a str, Box<dyn Error>> {
    value[name]
        .as_str()
        .ok_or_else(|| format!("missing {name}").into())
}

fn head(store: &mut Store, id: &str) -> Result<Value, Failure> {
    store.transaction(|t| {
        let content: String = t.query_row("SELECT r.content FROM revision r JOIN head h USING(revision_id) WHERE h.stable_id=?",[id],|r|r.get(0)).map_err(|_|Failure::input("proof head missing"))?;
        ai_stp_cli_v2::canonical::parse(content.as_bytes())
    })
}

fn complete_import(
    store: &mut Store,
    imported: &Value,
    identity: &Identity,
) -> Result<setups::releases::Plan, Box<dyn Error>> {
    let id = field(imported, "stable_id")?;
    let revision = field(imported, "revision_id")?;
    let before = counts(store)?;
    assert!(
        setups::releases::plan(store, id, revision, Increment::Minor, identity.clone(), AT)
            .is_err()
    );
    assert_eq!(counts(store)?, before);
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let providers = declarations
        .iter()
        .map(|v| ai_stp_cli_v2::provider::Info::parse(&serde_json::to_vec(v).unwrap_or_default()))
        .collect::<Result<Vec<_>, _>>()?;
    let mut members = Vec::new();
    for (index, captured) in imported["facts"]["components"]["value"]
        .as_array()
        .ok_or("missing imported members")?
        .iter()
        .enumerate()
    {
        let component_id = field(captured, "stable_id")?;
        let current = head(store, component_id)?;
        let patch = passports::Patch::try_from(
            json!({"name":format!("imported-{index}"),"description":"Inspect project conventions.",
            "tags":["development"],"license":{"spdx_id":"MIT","redistribution_allowed":true}}),
        )?;
        let updated = passports::plan(
            store,
            component_id,
            field(&current, "revision_id")?,
            patch,
            identity.clone(),
            AT,
        )?;
        let updated = passports::apply(store, &updated, &updated.digest()?, identity, AT)?;
        let release = releases::plan(
            store,
            component_id,
            field(&updated, "revision_id")?,
            Increment::Minor,
            &providers,
            identity.clone(),
            AT,
        )?;
        let release = releases::apply(store, &release, &release.digest()?, identity, AT)?;
        members.push(setups::Member {
            stable_id: component_id.into(),
            version: field(&release, "version")?.into(),
            passport_digest: digest::canonical("ai-stp:passport:v1", &release)?,
        });
    }
    let request = setups::Request {
        harness_id: "codex".into(),
        name: "Imported review".into(),
        description: "Inspect project conventions.".into(),
        purpose: "Review changes".into(),
        members,
        requirements: None,
    };
    let before = counts(store)?;
    let mut foreign = identity.clone();
    foreign.account_id = "account_01ARZ3NDEKTSV4RRFFQ69G5FAW".into();
    assert!(
        setups::drafts::plan(store, id, revision, request.clone(), foreign.clone(), AT).is_err()
    );
    let mut wrong = request.clone();
    wrong.harness_id = "cursor".into();
    assert!(setups::drafts::plan(store, id, revision, wrong, identity.clone(), AT).is_err());
    wrong = request.clone();
    wrong.members[0].passport_digest = digest::sha256(b"substituted");
    assert!(setups::drafts::plan(store, id, revision, wrong, identity.clone(), AT).is_err());
    let update = setups::drafts::plan(store, id, revision, request.clone(), identity.clone(), AT)?;
    let update: setups::drafts::Plan = serde_json::from_slice(&serde_json::to_vec(&update)?)?;
    let mut stale = update.clone();
    stale.operation_id = format!("operation_{}", ulid::Ulid::generate());
    assert_eq!(counts(store)?, before);
    assert!(setups::drafts::apply(store, &update, "wrong-digest", identity, AT).is_err());
    assert!(setups::drafts::apply(store, &update, &update.digest()?, identity, LATER).is_err());
    assert!(setups::drafts::apply(store, &update, &update.digest()?, &foreign, AT).is_err());
    let mut forged = update.clone();
    forged.passport["purpose"] = "Forged result".into();
    assert!(setups::drafts::apply(store, &forged, &forged.digest()?, identity, AT).is_err());
    store.transaction(|t|t.execute_batch("CREATE TEMP TRIGGER fail_setup BEFORE INSERT ON operation WHEN NEW.kind='setup.passport.update' BEGIN SELECT RAISE(ABORT,'proof failure'); END;").map_err(|_|Failure::input("proof trigger failed")))?;
    assert!(setups::drafts::apply(store, &update, &update.digest()?, identity, AT).is_err());
    assert_eq!(counts(store)?, before);
    assert_eq!(head(store, id)?, *imported);
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER fail_setup")
            .map_err(|_| Failure::input("proof trigger failed"))
    })?;
    let completed = setups::drafts::apply(store, &update, &update.digest()?, identity, AT)?;
    assert_eq!(completed["stable_id"], imported["stable_id"]);
    assert_eq!(
        completed["facts"]["components"],
        imported["facts"]["components"]
    );
    assert_eq!(completed["facts"]["origin"], imported["facts"]["origin"]);
    assert_eq!(
        completed["parent_revision_ids"],
        json!([imported["revision_id"]])
    );
    assert_eq!(
        completed["components"]
            .as_array()
            .ok_or("missing members")?
            .len(),
        2
    );
    assert!(setups::drafts::apply(store, &stale, &stale.digest()?, identity, AT).is_err());
    let release = setups::releases::plan(
        store,
        id,
        field(&completed, "revision_id")?,
        Increment::Minor,
        identity.clone(),
        AT,
    )?;
    assert_eq!(release.passport["version"], "1.0");
    let mut competing = release.clone();
    competing.operation_id = format!("operation_{}", ulid::Ulid::generate());
    let before = counts(store)?;
    assert!(setups::releases::apply(store, &release, "wrong-digest", identity, AT).is_err());
    assert!(setups::releases::apply(store, &release, &release.digest()?, identity, LATER).is_err());
    assert!(setups::releases::apply(store, &release, &release.digest()?, &foreign, AT).is_err());
    let mut forged = release.clone();
    forged.passport["version"] = "5.0".into();
    assert!(setups::releases::apply(store, &forged, &forged.digest()?, identity, AT).is_err());
    store.transaction(|t|t.execute_batch("CREATE TEMP TRIGGER fail_release BEFORE INSERT ON operation WHEN NEW.kind='setup.version.release' BEGIN SELECT RAISE(ABORT,'proof failure'); END;").map_err(|_|Failure::input("proof trigger failed")))?;
    assert!(setups::releases::apply(store, &release, &release.digest()?, identity, AT).is_err());
    assert_eq!(counts(store)?, before);
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER fail_release")
            .map_err(|_| Failure::input("proof trigger failed"))
    })?;
    let frozen = setups::releases::apply(store, &release, &release.digest()?, identity, AT)?;
    assert_eq!(head(store, id)?, completed);
    assert_eq!(frozen["parent_revision_ids"], json!([]));
    assert!(
        setups::releases::apply(store, &competing, &competing.digest()?, identity, AT).is_err()
    );
    // A later complete draft can intentionally remove every member. Historical
    // release and update receipts verify without reinstalling the old graph.
    let pending = setups::releases::plan(
        store,
        id,
        field(&completed, "revision_id")?,
        Increment::Minor,
        identity.clone(),
        AT,
    )?;
    let mut empty = request;
    empty.name = "Empty review".into();
    empty.members.clear();
    let changed = setups::drafts::plan(
        store,
        id,
        field(&completed, "revision_id")?,
        empty.clone(),
        identity.clone(),
        AT,
    )?;
    let changed = setups::drafts::apply(store, &changed, &changed.digest()?, identity, AT)?;
    assert!(setups::releases::apply(store, &pending, &pending.digest()?, identity, AT).is_err());
    let next = setups::releases::plan(
        store,
        id,
        field(&changed, "revision_id")?,
        Increment::Major,
        identity.clone(),
        AT,
    )?;
    assert_eq!(next.passport["version"], "2.0");
    let next = setups::releases::apply(store, &next, &next.digest()?, identity, AT)?;
    assert_eq!(next["components"], json!([]));
    let before = counts(store)?;
    assert_eq!(
        setups::drafts::apply(store, &update, &update.digest()?, identity, LATER)?,
        completed
    );
    assert_eq!(
        setups::releases::apply(store, &release, &release.digest()?, identity, LATER)?,
        frozen
    );
    assert_eq!(head(store, id)?, changed);
    assert_eq!(counts(store)?, before);
    // Imported or copied setups can declare requirements beyond their members.
    // A composition-only request has no authority to erase those declarations.
    let mut custom = changed.clone();
    custom["requires_credentials"] = true.into();
    custom["parent_revision_ids"] = json!([changed["revision_id"]]);
    let custom = store.transaction(|t| {
        revisions::commit(
            t,
            &custom,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: &[changed["revision_id"]
                    .as_str()
                    .ok_or_else(|| Failure::input("proof revision missing"))?
                    .into()],
            },
        )
    })?;
    let before = counts(store)?;
    let failure = setups::drafts::plan(
        store,
        id,
        field(&custom, "revision_id")?,
        empty.clone(),
        identity.clone(),
        AT,
    )
    .err()
    .ok_or("additional setup requirements were lost")?;
    assert_eq!(
        failure.details["constraint"],
        "setup_requirements_not_derived"
    );
    assert_eq!(counts(store)?, before);
    assert_eq!(head(store, id)?, custom);
    let preserved = setups::releases::plan(
        store,
        id,
        field(&custom, "revision_id")?,
        Increment::Minor,
        identity.clone(),
        AT,
    )?;
    assert_eq!(preserved.passport["requires_credentials"], true);
    empty.requirements = Some(serde_json::from_value(json!({
        "required_env":[{"name":"SETUP_PROFILE","purpose":"Select the review policy."}],
        "requires_credentials":true,"requires_authorization":"user_account",
        "permissions":{"process":["review-tool"]},
        "runtime_requirements":["node >=24"],
        "external_endpoints":["https://example.com/review"],
        "license":{"spdx_id":"MIT","redistribution_allowed":false}
    }))?);
    let declared = setups::drafts::plan(
        store,
        id,
        field(&custom, "revision_id")?,
        empty.clone(),
        identity.clone(),
        AT,
    )?;
    assert_eq!(declared.passport["requires_credentials"], true);
    assert_eq!(
        declared.passport["runtime_requirements"],
        json!(["node >=24"])
    );
    assert_eq!(
        declared.passport["license"]["redistribution_allowed"],
        false
    );
    let declared_document =
        setups::drafts::apply(store, &declared, &declared.digest()?, identity, AT)?;
    empty.requirements = None;
    empty.description = "Review an explicitly constrained empty setup.".into();
    let inherited = setups::drafts::plan(
        store,
        id,
        field(&declared_document, "revision_id")?,
        empty.clone(),
        identity.clone(),
        LATER,
    )?;
    for key in [
        "required_env",
        "requires_credentials",
        "requires_authorization",
        "permissions",
        "runtime_requirements",
        "external_endpoints",
        "license",
    ] {
        assert_eq!(inherited.passport[key], declared_document[key]);
    }
    assert_eq!(
        inherited.passport["facts"]["setup_requirements"],
        declared_document["facts"]["setup_requirements"]
    );
    let inherited =
        setups::drafts::apply(store, &inherited, &inherited.digest()?, identity, LATER)?;
    empty.requirements = Some(setups::Requirements::default());
    let cleared = setups::drafts::plan(
        store,
        id,
        field(&inherited, "revision_id")?,
        empty,
        identity.clone(),
        LATER,
    )?;
    assert_eq!(cleared.passport["requires_credentials"], false);
    assert_eq!(cleared.passport["required_env"], json!([]));
    assert_eq!(cleared.passport["runtime_requirements"], json!([]));
    let cleared = setups::drafts::apply(store, &cleared, &cleared.digest()?, identity, LATER)?;
    assert_eq!(
        setups::drafts::apply(store, &declared, &declared.digest()?, identity, LATER)?,
        declared_document
    );
    assert_eq!(head(store, id)?, cleared);
    Ok(release)
}
