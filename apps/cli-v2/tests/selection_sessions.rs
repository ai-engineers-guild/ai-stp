use std::{collections::BTreeMap, error::Error, sync::Barrier};

use ai_stp_cli_v2::{
    artifacts::{self, Member as File},
    authoring::{Identity, releases, setups},
    digest,
    error::{ErrorKind, Failure},
    passport::developer,
    projection::Scope,
    provider::Info,
    selection::{
        eligibility::{Evidence, Target},
        sessions::{self, Runtime},
    },
    store::{
        Store,
        revisions::{self, Write},
        versions::{self, Increment},
    },
};
use serde_json::{Value, json};

const AT: &str = "2026-10-08T00:00:00.000Z";
const LATER: &str = "2026-10-09T00:00:00.000Z";
const PROJECT: &str = "project_01ARZ3NDEKTSV4RRFFQ69G5FAV";

fn field<'a>(document: &'a Value, key: &str) -> Result<&'a str, Box<dyn Error>> {
    document[key]
        .as_str()
        .ok_or_else(|| format!("missing {key}").into())
}
fn reference(document: &Value) -> Result<setups::Member, Box<dyn Error>> {
    Ok(setups::Member {
        stable_id: field(document, "stable_id")?.into(),
        version: field(document, "version")?.into(),
        passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
    })
}
fn counts(store: &mut Store) -> Result<Vec<i64>, Failure> {
    store.transaction(|t| t.query_row("SELECT (SELECT count(*) FROM entity),(SELECT count(*) FROM revision),(SELECT count(*) FROM content),(SELECT count(*) FROM operation),(SELECT count(*) FROM object_version),(SELECT count(*) FROM recommendation_trace)",[],|r| (0..6).map(|i|r.get(i)).collect()).map_err(|_| Failure::precondition("proof query failed")))
}
fn seed(
    store: &mut Store,
    identity: &Identity,
    provider: &Info,
    name: &str,
    requires: Vec<Value>,
) -> Result<Value, Box<dyn Error>> {
    let bytes = artifacts::encode_tree(&[File {
        path: "SKILL.md".into(),
        bytes: format!(
            "---\nname: {name}\ndescription: Inspect conventions.\n---\nReview conventions.\n"
        )
        .into_bytes(),
        mode: 0o644,
    }])?;
    let draft = store.transaction(|t| {
        let address = revisions::content(t,&bytes,AT)?;
        let values = json!({"name":name,"description":"Inspect project conventions.","tags":["development"],
            "harness_id":"claude-code","component_type":"skill","projection_kind":"native_files","scope":"global",
            "content_digest":address,"byte_length":bytes.len(),"content_format":artifacts::TREE_FORMAT,
            "native_ids":[name],"managed_paths":[format!("skills/{name}")],"requires_components":requires,
            "license":{"spdx_id":"MIT","redistribution_allowed":true}});
        let facts: serde_json::Map<String,Value> = values.as_object().ok_or_else(||Failure::input("facts missing"))?.iter()
            .map(|(k,v)|(k.clone(),json!({"value":v,"origin":"declared","confirmation":"none"}))).collect();
        revisions::commit(t,&json!({"kind":"component","stable_id":format!("component_{}",ulid::Ulid::generate()),
            "owner_id":identity.account_id,"created_at":AT,"facts":facts}),&identity.device_id,None,Write::Advance {expected_heads:&[]})
    })?;
    let providers = [Info::parse(&serde_json::to_vec(provider.document())?)?];
    let plan = releases::plan(
        store,
        field(&draft, "stable_id")?,
        field(&draft, "revision_id")?,
        Increment::Minor,
        &providers,
        identity.clone(),
        AT,
    )?;
    Ok(releases::apply(
        store,
        &plan,
        &plan.digest()?,
        identity,
        AT,
    )?)
}
fn advance(store: &mut Store, id: &str, identity: &Identity) -> Result<(), Failure> {
    store.transaction(|t| {
        let heads = revisions::heads(t, id)?;
        let bytes: String = t
            .query_row(
                "SELECT content FROM revision WHERE revision_id=?",
                [&heads[0]],
                |r| r.get(0),
            )
            .map_err(|_| Failure::precondition("proof head missing"))?;
        let mut next = ai_stp_cli_v2::canonical::parse(bytes.as_bytes())?;
        next["parent_revision_ids"] = json!(heads);
        next["lifecycle_state"] = "draft".into();
        next["facts"]["name"] =
            json!({"value":"Later draft","origin":"declared","confirmation":"none"});
        revisions::commit(
            t,
            &next,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: &heads,
            },
        )?;
        Ok(())
    })
}

#[test]
fn durable_selection_rechecks_context_and_commits_one_complete_effect() -> Result<(), Box<dyn Error>>
{
    let directory = tempfile::tempdir()?;
    let mut store = Store::open(directory.path(), true)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let provider = Info::parse(&serde_json::to_vec(
        declarations
            .iter()
            .find(|d| d["harness_id"] == "claude-code")
            .ok_or("provider missing")?,
    )?)?;
    let first = seed(&mut store, &identity, &provider, "one", vec![])?;
    let second = seed(
        &mut store,
        &identity,
        &provider,
        "two",
        vec![serde_json::to_value(reference(&first)?)?],
    )?;
    let mut evidence = BTreeMap::new();
    for document in [&first, &second] {
        evidence.insert(
            field(document, "stable_id")?.into(),
            Evidence {
                passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
                registrable: true,
                blocked: false,
                author_verified: false,
                component_verified: false,
                checks_current: false,
                consented: false,
            },
        );
    }
    let target = Target {
        harness_id: "claude-code".into(),
        scope: Scope::Global,
        os: "linux".into(),
        arch: "x86_64".into(),
        harness_version: "2.1.294".into(),
        owner_id: identity.account_id.clone(),
        capabilities: Default::default(),
        permissions: Default::default(),
        entitlements: Default::default(),
        env_present: Default::default(),
        grants: Default::default(),
        pinned_passport_digests: Default::default(),
        for_redistribution: false,
    };
    let runtime = Runtime {
        identity: &identity,
        target: &target,
        evidence: &evidence,
        provider: Some(&provider),
        policy_version: "selection-policy/1",
    };
    let mut legacy = second.clone();
    legacy["version"] = "1.1".into();
    legacy["requires_components"][0]["variant_id"] = "variant_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
    let legacy =
        store.transaction(|t| versions::record(t, &legacy, &identity.device_id, None, AT))?;
    let graph = ai_stp_cli_v2::selection::eligibility::assess_graph(
        &mut store,
        &[serde_json::to_value(reference(&legacy)?)?],
        &target,
        &evidence,
        Some(&provider),
    )?;
    assert_eq!(graph["graph"]["resolved"], false);
    assert_eq!(
        graph["graph"]["refusals"][0]["code"],
        "reference_variant_unsupported"
    );
    let mut unsupported = serde_json::to_value(reference(&first)?)?;
    unsupported["variant_id"] = "variant_01ARZ3NDEKTSV4RRFFQ69G5FAV".into();
    assert!(
        seed(
            &mut store,
            &identity,
            &provider,
            "unsupported",
            vec![unsupported]
        )
        .is_err()
    );
    let roots = [reference(&second)?];
    let developer = developer::plan(&mut store, None, None, identity.clone(), AT)?;
    developer::apply(&mut store, &developer, &developer.digest()?, &identity, AT)?;
    // Neither an identity nor a project declaration substitutes for a device observation.
    store.transaction(|t| revisions::commit(t,&json!({"kind":"project","stable_id":PROJECT,"owner_id":identity.account_id,"created_at":AT}),
        &identity.device_id,None,Write::Advance {expected_heads:&[]}))?;
    assert!(sessions::plan(&mut store, PROJECT, &roots, false, &runtime, AT).is_err());
    store.transaction(|t| revisions::commit(t,&json!({"kind":"device","stable_id":identity.device_id,"owner_id":identity.account_id,"created_at":AT,
        "facts":{"os":{"value":"linux","origin":"observed","confirmation":"none","observed_at":AT}}}),
        &identity.device_id,None,Write::Advance {expected_heads:&[]}))?;
    assert!(sessions::plan(&mut store, PROJECT, &[], false, &runtime, AT).is_err());
    assert!(sessions::plan(&mut store, PROJECT, &roots, true, &runtime, AT).is_err());
    assert!(
        sessions::plan(
            &mut store,
            PROJECT,
            &[],
            true,
            &Runtime {
                provider: None,
                ..runtime
            },
            AT
        )
        .is_err()
    );
    let before = counts(&mut store)?;
    let proposed = sessions::plan(&mut store, PROJECT, &roots, false, &runtime, AT)?;
    assert_eq!(proposed.members.len(), 2);
    let proposed: sessions::Plan = serde_json::from_value(serde_json::to_value(proposed)?)?;
    assert_eq!(counts(&mut store)?, before);
    assert!(sessions::propose(&mut store, &proposed, "wrong", &runtime, AT).is_err());
    let mut forged = proposed.clone();
    forged.members[0].lane = "authoritative".into();
    assert!(sessions::propose(&mut store, &forged, &forged.digest()?, &runtime, AT).is_err());
    let held = sessions::propose(&mut store, &proposed, &proposed.digest()?, &runtime, AT)?;
    assert_eq!(counts(&mut store)?, before);
    assert_eq!(
        sessions::propose(&mut store, &proposed, &proposed.digest()?, &runtime, LATER)?.proposal_id,
        held.proposal_id
    );
    let decision = sessions::decision(&mut store, &held.proposal_id, false, &identity, AT)?;
    assert!(sessions::confirm(&mut store, &decision, "wrong", &runtime, AT).is_err());
    assert!(
        sessions::confirm(
            &mut store,
            &decision,
            &decision.digest()?,
            &runtime,
            &held.expires_at
        )
        .is_err()
    );
    assert_eq!(
        sessions::read(&mut store, &held.proposal_id)?.state(&held.expires_at)?,
        "expired"
    );
    for change in ["policy", "permissions", "consent", "blocked", "missing"] {
        let mut target = target.clone();
        let mut evidence = evidence.clone();
        let id = field(&first, "stable_id")?;
        match change {
            "permissions" => {
                target.permissions.insert("filesystem:read:project".into());
            }
            "consent" => evidence.get_mut(id).ok_or("evidence missing")?.consented = true,
            "blocked" => evidence.get_mut(id).ok_or("evidence missing")?.blocked = true,
            "missing" => {
                evidence.remove(id);
            }
            _ => {}
        }
        let changed = Runtime {
            identity: &identity,
            target: &target,
            evidence: &evidence,
            provider: Some(&provider),
            policy_version: if change == "policy" {
                "selection-policy/2"
            } else {
                runtime.policy_version
            },
        };
        assert!(
            sessions::confirm(&mut store, &decision, &decision.digest()?, &changed, AT).is_err(),
            "accepted {change}"
        );
        assert_eq!(counts(&mut store)?, before);
    }
    let stale = sessions::plan(&mut store, PROJECT, &roots, false, &runtime, AT)?;
    sessions::propose(&mut store, &stale, &stale.digest()?, &runtime, AT)?;
    let page = sessions::view::read(&mut store, PROJECT, "claude-code", None, 1, AT)?;
    assert_eq!(page["proposals"].as_array().ok_or("page missing")?.len(), 1);
    assert!(page["selected"].is_null());
    let cursor = field(&page, "next_after")?;
    let next = sessions::view::read(&mut store, PROJECT, "claude-code", Some(cursor), 1, AT)?;
    assert_eq!(next["proposals"].as_array().ok_or("page missing")?.len(), 1);
    assert!(next["next_after"].is_null());
    assert_ne!(
        page["proposals"][0]["proposal_id"],
        next["proposals"][0]["proposal_id"]
    );
    assert_eq!(
        sessions::view::read(&mut store, PROJECT, "grok-build", None, 20, AT)?["proposals"],
        json!([])
    );
    assert_eq!(
        sessions::view::read(
            &mut store,
            PROJECT,
            "claude-code",
            None,
            20,
            &held.expires_at
        )?["proposals"],
        json!([])
    );
    for limit in [0, 101] {
        assert!(sessions::view::read(&mut store, PROJECT, "claude-code", None, limit, AT).is_err());
    }
    assert!(
        sessions::view::read(&mut store, PROJECT, "claude-code", Some("invalid"), 1, AT).is_err()
    );
    assert_eq!(counts(&mut store)?, before);
    let patch = developer::Patch::parse(br#"{"role":"Maintainer"}"#)?;
    let update = developer::plan(
        &mut store,
        Some(field(&developer.passport, "revision_id")?),
        Some(patch),
        identity.clone(),
        AT,
    )?;
    developer::apply(&mut store, &update, &update.digest()?, &identity, AT)?;
    assert!(sessions::confirm(&mut store, &decision, &decision.digest()?, &runtime, AT).is_err());
    // New context, same exact versions. A later component draft is irrelevant.
    let proposed = sessions::plan(&mut store, PROJECT, &roots, false, &runtime, AT)?;
    let held = sessions::propose(&mut store, &proposed, &proposed.digest()?, &runtime, AT)?;
    let decision = sessions::decision(&mut store, &held.proposal_id, false, &identity, AT)?;
    advance(&mut store, field(&first, "stable_id")?, &identity)?;
    let before = counts(&mut store)?;
    store.transaction(|t| {
        t.execute(
            "INSERT INTO tombstone(stable_id,reason,created_at) VALUES (?,'proof',?)",
            [
                field(&first, "stable_id").map_err(|_| Failure::input("proof id missing"))?,
                AT,
            ],
        )
        .map(|_| ())
        .map_err(|_| Failure::precondition("proof tombstone failed"))
    })?;
    assert!(sessions::confirm(&mut store, &decision, &decision.digest()?, &runtime, AT).is_err());
    assert_eq!(counts(&mut store)?, before);
    store.transaction(|t| {
        t.execute("DELETE FROM tombstone", [])
            .map(|_| ())
            .map_err(|_| Failure::precondition("proof cleanup failed"))
    })?;
    store.transaction(|t|t.execute_batch("CREATE TEMP TRIGGER interrupt_trace BEFORE INSERT ON recommendation_trace BEGIN SELECT RAISE(ABORT,'interrupted'); END;")
        .map_err(|_|Failure::precondition("proof trigger failed")))?;
    assert!(sessions::confirm(&mut store, &decision, &decision.digest()?, &runtime, AT).is_err());
    assert_eq!(counts(&mut store)?, before);
    assert_eq!(
        sessions::read(&mut store, &held.proposal_id)?.state(AT)?,
        "open"
    );
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER interrupt_trace")
            .map_err(|_| Failure::precondition("proof cleanup failed"))
    })?;
    drop(store);
    let graph =
        ai_stp_cli_v2::selection::graph::local(directory.path(), &[], Some(&held.proposal_id))?;
    assert_eq!(graph["resolved"], true);
    assert_eq!(graph["nodes"].as_array().ok_or("graph missing")?.len(), 2);
    let named = [format!("{}@1.0", field(&second, "stable_id")?)];
    assert_eq!(
        ai_stp_cli_v2::selection::graph::local(directory.path(), &named, None)?["order"],
        graph["order"]
    );
    assert!(
        ai_stp_cli_v2::selection::graph::local(directory.path(), &named, Some(&held.proposal_id))
            .is_err()
    );
    let barrier = Barrier::new(2);
    let outcomes = std::thread::scope(|scope| {
        let handles: Vec<_> = (0..2)
            .map(|_| {
                scope.spawn(|| {
                    barrier.wait();
                    let mut store = Store::open(directory.path(), false)?;
                    sessions::confirm(&mut store, &decision, &decision.digest()?, &runtime, AT)
                })
            })
            .collect();
        handles
            .into_iter()
            .map(|h| {
                h.join()
                    .map_err(|_| Failure::precondition("proof writer panicked"))
            })
            .collect::<Result<Vec<_>, Failure>>()
    })?;
    assert_eq!(
        outcomes
            .iter()
            .filter(|outcome| matches!(outcome, Ok(value) if value.created))
            .count(),
        1
    );
    let outcomes = outcomes
        .into_iter()
        .map(|outcome| match outcome {
            Ok(value) => Ok(value),
            Err(error) => {
                assert!(matches!(error.kind, ErrorKind::Unavailable), "{error:?}");
                assert_eq!(
                    error.details.get("stage").and_then(Value::as_str),
                    Some("lock_timeout")
                );
                let mut store = Store::open(directory.path(), false)?;
                let before = counts(&mut store)?;
                let replay =
                    sessions::confirm(&mut store, &decision, &decision.digest()?, &runtime, AT)?;
                assert!(!replay.created);
                assert_eq!(counts(&mut store)?, before);
                Ok(replay)
            }
        })
        .collect::<Result<Vec<_>, Failure>>()?;
    assert_eq!(outcomes.iter().filter(|o| o.created).count(), 1);
    assert_eq!(outcomes[0].passport, outcomes[1].passport);
    if let Some(path) = std::env::var_os("AI_STP_SELECTION_PROOF_FILE") {
        std::fs::write(
            path,
            ai_stp_cli_v2::canonical::bytes(
                &json!({"plan":proposed,"proposal":held,"passport":outcomes[0].passport,"components":[first,second]}),
            )?,
        )?;
    }
    let mut store = Store::open(directory.path(), false)?;
    let after = counts(&mut store)?;
    assert_eq!(after[0], before[0] + 1);
    assert_eq!(after[4], before[4] + 1);
    assert_eq!(after[5], before[5] + 1);
    let cancel = sessions::decision(&mut store, &held.proposal_id, true, &identity, AT)?;
    assert!(sessions::cancel(&mut store, &cancel, &cancel.digest()?, &identity, AT).is_err());
    let empty = sessions::plan(&mut store, PROJECT, &[], true, &runtime, AT)?;
    sessions::propose(&mut store, &empty, &empty.digest()?, &runtime, AT)?;
    let choose_empty = sessions::decision(&mut store, &empty.proposal_id, false, &identity, AT)?;
    let latest = sessions::confirm(
        &mut store,
        &choose_empty,
        &choose_empty.digest()?,
        &runtime,
        AT,
    )?;
    assert_eq!(latest.passport["components"], json!([]));
    let replay = sessions::confirm(
        &mut store,
        &decision,
        &decision.digest()?,
        &Runtime {
            policy_version: "later-policy",
            ..runtime
        },
        LATER,
    )?;
    assert!(!replay.created);
    assert_eq!(replay.passport, outcomes[0].passport);
    let selected: String = store.transaction(|t| {
        t.query_row(
            "SELECT stable_id FROM selected_version WHERE project_id=?",
            [PROJECT],
            |r| r.get(0),
        )
        .map_err(|_| Failure::precondition("proof selection missing"))
    })?;
    assert_eq!(selected, field(&latest.passport, "stable_id")?);
    let current = sessions::view::read(&mut store, PROJECT, "claude-code", None, 20, AT)?;
    assert_eq!(
        current["selected"]["stable_id"],
        latest.passport["stable_id"]
    );
    assert_eq!(current["selected"]["recorded_state"], "pending_install");
    assert_eq!(current["installation_observed"], false);
    assert_eq!(current["context_freshness"], "not_evaluated");
    assert!(
        current["proposals"]
            .as_array()
            .ok_or("page missing")?
            .iter()
            .all(|p| p["proposal_id"] != held.proposal_id && p["proposal_id"] != empty.proposal_id)
    );
    let cancel = sessions::decision(&mut store, &stale.proposal_id, true, &identity, AT)?;
    let before = counts(&mut store)?;
    assert_eq!(
        sessions::cancel(&mut store, &cancel, &cancel.digest()?, &identity, AT)?.state(AT)?,
        "cancelled"
    );
    assert_eq!(
        sessions::cancel(&mut store, &cancel, &cancel.digest()?, &identity, LATER)?.state(LATER)?,
        "cancelled"
    );
    let cancelled = sessions::decision(&mut store, &stale.proposal_id, false, &identity, AT)?;
    assert!(sessions::confirm(&mut store, &cancelled, &cancelled.digest()?, &runtime, AT).is_err());
    assert_eq!(counts(&mut store)?, before);
    let racing = sessions::plan(&mut store, PROJECT, &[], true, &runtime, AT)?;
    sessions::propose(&mut store, &racing, &racing.digest()?, &runtime, AT)?;
    let confirm_plan = sessions::decision(&mut store, &racing.proposal_id, false, &identity, AT)?;
    let cancel_plan = sessions::decision(&mut store, &racing.proposal_id, true, &identity, AT)?;
    drop(store);
    let barrier = Barrier::new(2);
    let race = std::thread::scope(|scope| {
        let handles: Vec<_> = (0..2)
            .map(|index| {
                let barrier = &barrier;
                let directory = &directory;
                let runtime = &runtime;
                let confirm_plan = &confirm_plan;
                let cancel_plan = &cancel_plan;
                scope.spawn(move || {
                    barrier.wait();
                    let mut store = Store::open(directory.path(), false)?;
                    if index == 0 {
                        sessions::confirm(
                            &mut store,
                            confirm_plan,
                            &confirm_plan.digest()?,
                            runtime,
                            AT,
                        )
                        .map(|c| c.created)
                    } else {
                        sessions::cancel(
                            &mut store,
                            cancel_plan,
                            &cancel_plan.digest()?,
                            runtime.identity,
                            AT,
                        )
                        .map(|_| false)
                    }
                })
            })
            .collect();
        handles
            .into_iter()
            .map(|h| {
                h.join()
                    .map_err(|_| Failure::precondition("proof writer panicked"))
            })
            .collect::<Result<Vec<_>, Failure>>()
    })?;
    assert_eq!(race.iter().filter(|r| r.is_ok()).count(), 1);
    let mut store = Store::open(directory.path(), false)?;
    let confirmed = race.iter().any(|r| matches!(r, Ok(true)));
    assert_eq!(
        sessions::read(&mut store, &racing.proposal_id)?.state(AT)?,
        if confirmed { "confirmed" } else { "cancelled" }
    );
    let after = counts(&mut store)?;
    assert_eq!(after[0], before[0] + i64::from(confirmed));
    assert_eq!(after[4], before[4] + i64::from(confirmed));
    assert_eq!(after[5], before[5] + i64::from(confirmed));
    // Completed replay verifies its trace, not merely the terminal flag.
    store.transaction(|t| {
        t.execute(
            "UPDATE recommendation_trace SET body='{}' WHERE proposal_id=?",
            [&held.proposal_id],
        )
        .map(|_| ())
        .map_err(|_| Failure::precondition("proof corruption failed"))
    })?;
    assert!(
        sessions::confirm(&mut store, &decision, &decision.digest()?, &runtime, LATER).is_err()
    );
    assert_eq!(counts(&mut store)?, after);
    Ok(())
}
