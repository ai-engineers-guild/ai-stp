use ai_stp_cli_v2::{
    artifacts::{self, Member as File},
    authoring::{
        Identity, releases,
        setups::{self, Member, Request},
    },
    digest,
    error::Failure,
    store::{
        Store,
        revisions::{self, Write},
        versions::{self, Increment},
    },
};
use serde_json::{Value, json};
use std::error::Error;

const AT: &str = "2026-10-08T00:00:00.000Z";
const LATER: &str = "2026-10-09T00:00:00.000Z";
fn field<'a>(value: &'a Value, name: &str) -> Result<&'a str, Box<dyn Error>> {
    value[name]
        .as_str()
        .ok_or_else(|| format!("missing {name}").into())
}
fn reference(document: &Value) -> Result<Member, Box<dyn Error>> {
    Ok(Member {
        stable_id: field(document, "stable_id")?.into(),
        version: field(document, "version")?.into(),
        passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
    })
}
fn counts(store: &mut Store) -> Result<(i64, i64, i64, i64, i64), Failure> {
    store.transaction(|t| t.query_row("SELECT (SELECT count(*) FROM entity),(SELECT count(*) FROM revision),(SELECT count(*) FROM content),(SELECT count(*) FROM operation),(SELECT count(*) FROM object_version)",[],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?))).map_err(|_| Failure::precondition("proof query failed")))
}
fn seed(
    store: &mut Store,
    identity: &Identity,
    name: &str,
    extra: Value,
) -> Result<Value, Box<dyn Error>> {
    let bytes = artifacts::encode_tree(&[File {
        path: "SKILL.md".into(),
        bytes: format!("# {name}\n").into_bytes(),
        mode: 0o644,
    }])?;
    let draft = store.transaction(|t| {
        let address = revisions::content(t,&bytes,AT)?;
        let mut values = json!({"name":name,"description":"Inspect project conventions.","tags":["development"],
            "harness_id":"claude-code","component_type":"skill","projection_kind":"native_files","scope":"global",
            "content_digest":address,"content_format":artifacts::TREE_FORMAT,"managed_paths":[format!("skills/{name}")],
            "license":{"spdx_id":"MIT","redistribution_allowed":true}});
        values.as_object_mut().ok_or_else(|| Failure::input("facts missing"))?.extend(extra.as_object().ok_or_else(|| Failure::input("extra missing"))?.clone());
        let facts: serde_json::Map<String,Value> = values.as_object().ok_or_else(|| Failure::input("facts missing"))?.iter()
            .map(|(key,value)|(key.clone(),json!({"value":value,"origin":"declared","confirmation":"none"}))).collect();
        revisions::commit(t,&json!({"kind":"component","stable_id":format!("component_{}",ulid::Ulid::generate()),"owner_id":identity.account_id,"created_at":AT,"facts":facts}),&identity.device_id,None,Write::Advance {expected_heads:&[]})
    })?;
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let providers = declarations
        .iter()
        .map(|value| {
            Ok(ai_stp_cli_v2::provider::Info::parse(&serde_json::to_vec(
                value,
            )?)?)
        })
        .collect::<Result<Vec<_>, Box<dyn Error>>>()?;
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

#[test]
fn exact_setup_closure_constraints_atomicity_and_replay() -> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let mut store = Store::open(root.path(), true)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let first = seed(
        &mut store,
        &identity,
        "first",
        json!({
        "requires_authorization":"external_service","requires_credentials":true,
        "required_env":[{"name":"APP_PROFILE","purpose":"Read configuration"}],
        "permissions":{"filesystem":["read:project"],"network":[],"process":[]},
        "external_endpoints":["https://example.com/one"],"runtime_requirements":["python >=3.13"],
        "license":{"spdx_id":"MIT OR Apache-2.0","redistribution_allowed":true}}),
    )?;
    let second = seed(
        &mut store,
        &identity,
        "second",
        json!({
        "requires_authorization":"user_account","required_env":[{"name":"APP_PROFILE","purpose":"Select workspace"}],
        "permissions":{"filesystem":[],"network":["https:example.com"],"process":["python"]},
        "external_endpoints":["https://example.com/two"],"runtime_requirements":["python >=3.13","node >=24"],
        "requires_components":[serde_json::to_value(reference(&first)?)?],
        "license":{"spdx_id":"BSD-3-Clause","redistribution_allowed":false}}),
    )?;
    let request = Request {
        harness_id: "claude-code".into(),
        name: "Exact setup".into(),
        description: "Inspect the chosen project.".into(),
        purpose: "Check project conventions.".into(),
        members: vec![reference(&second)?],
    };
    // Scope-specific privileges must not become unconditional setup permissions.
    let mut scoped = first.clone();
    scoped["version"] = "1.1".into();
    scoped["adaptations"][0]["scope_adaptations"][0]["permissions"]["network"] =
        json!(["global-only"]);
    scoped["adaptations"][0] =
        ai_stp_cli_v2::passport::versions::seal_adaptation(&scoped["adaptations"][0])?;
    let scoped =
        store.transaction(|t| versions::record(t, &scoped, &identity.device_id, None, AT))?;
    let mut scoped_request = request.clone();
    scoped_request.members = vec![reference(&scoped)?];
    let scoped_setup = setups::plan(&mut store, scoped_request, identity.clone(), AT)?;
    assert_eq!(
        scoped_setup.passport["permissions"]["network"],
        json!([]),
        "unused scopes leaked into unconditional permissions"
    );
    let before = counts(&mut store)?;
    let plan = setups::plan(&mut store, request.clone(), identity.clone(), AT)?;
    assert_eq!(counts(&mut store)?, before);
    assert_eq!(
        plan.passport["components"]
            .as_array()
            .ok_or("members missing")?
            .len(),
        2
    );
    assert_eq!(plan.passport["requires_authorization"], "external_service");
    assert_eq!(plan.passport["requires_credentials"], true);
    assert_eq!(
        plan.passport["required_env"],
        json!([{"name":"APP_PROFILE","purpose":"Read configuration\nSelect workspace"}])
    );
    assert_eq!(
        plan.passport["permissions"],
        json!({"filesystem":["read:project"],"network":["https:example.com"],"process":["python"]})
    );
    assert_eq!(
        plan.passport["runtime_requirements"],
        json!(["node >=24", "python >=3.13"])
    );
    assert_eq!(
        plan.passport["license"],
        json!({"spdx_id":"(BSD-3-Clause) AND (MIT OR Apache-2.0)","redistribution_allowed":false})
    );
    let plan: setups::Plan = serde_json::from_slice(&ai_stp_cli_v2::canonical::bytes(
        &serde_json::to_value(plan)?,
    )?)?;
    let mut ordered = request.clone();
    ordered.members.push(reference(&first)?);
    let left = setups::plan(&mut store, ordered.clone(), identity.clone(), AT)?;
    ordered.members.reverse();
    let right = setups::plan(&mut store, ordered, identity.clone(), AT)?;
    assert_eq!(
        left.passport["facts"]["snapshot"],
        right.passport["facts"]["snapshot"]
    );
    assert_eq!(left.passport["components"], right.passport["components"]);
    let mut wrong = plan.clone();
    wrong.passport["requires_credentials"] = false.into();
    assert!(setups::apply(&mut store, &wrong, &wrong.digest()?, &identity, AT).is_err());
    assert!(setups::apply(&mut store, &plan, &digest::sha256(b"wrong"), &identity, AT).is_err());
    assert!(setups::apply(&mut store, &plan, &plan.digest()?, &identity, LATER).is_err());
    let mut wrong = request.clone();
    wrong.harness_id = "cursor".into();
    assert!(setups::plan(&mut store, wrong, identity.clone(), AT).is_err());
    let mut wrong = request.clone();
    wrong.members[0].passport_digest = digest::sha256(b"substitution");
    assert!(setups::plan(&mut store, wrong, identity.clone(), AT).is_err());
    assert_eq!(counts(&mut store)?, before);
    let first_id = field(&first, "stable_id")?;
    store.transaction(|t| {
        t.execute(
            "INSERT INTO tombstone(stable_id,reason,created_at) VALUES (?,'proof',?)",
            [first_id, AT],
        )
        .map(|_| ())
        .map_err(|_| Failure::precondition("proof tombstone failed"))
    })?;
    assert!(setups::apply(&mut store, &plan, &plan.digest()?, &identity, AT).is_err());
    store.transaction(|t| {
        t.execute("DELETE FROM tombstone WHERE stable_id=?", [first_id])
            .map(|_| ())
            .map_err(|_| Failure::precondition("proof cleanup failed"))
    })?;
    store.transaction(|t| t.execute_batch("CREATE TEMP TRIGGER fail_compose BEFORE INSERT ON object_version BEGIN SELECT RAISE(ABORT,'interrupted'); END;").map_err(|_|Failure::precondition("proof injection failed")))?;
    assert!(setups::apply(&mut store, &plan, &plan.digest()?, &identity, AT).is_err());
    assert_eq!(counts(&mut store)?, before);
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER fail_compose")
            .map_err(|_| Failure::precondition("proof cleanup failed"))
    })?;
    let setup = setups::apply(&mut store, &plan, &plan.digest()?, &identity, AT)?;
    let target = ai_stp_cli_v2::selection::eligibility::Target {
        harness_id: "claude-code".into(),
        scope: ai_stp_cli_v2::projection::Scope::Global,
        os: "linux".into(),
        arch: "x86_64".into(),
        harness_version: "2.1.224".into(),
        owner_id: identity.account_id.clone(),
        capabilities: Default::default(),
        permissions: [
            "filesystem:read:project".into(),
            "network:https:example.com".into(),
            "process:python".into(),
        ]
        .into(),
        entitlements: Default::default(),
        env_present: Default::default(),
        grants: Default::default(),
        pinned_passport_digests: Default::default(),
        for_redistribution: false,
    };
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let declaration = declarations
        .iter()
        .find(|value| value["harness_id"] == "claude-code")
        .ok_or("Claude declaration missing")?;
    let provider = ai_stp_cli_v2::provider::Info::parse(&serde_json::to_vec(declaration)?)?;
    let mut evidence = std::collections::BTreeMap::new();
    for member in [&setup, &first, &second] {
        evidence.insert(
            field(member, "stable_id")?.to_owned(),
            ai_stp_cli_v2::selection::eligibility::Evidence {
                passport_digest: digest::canonical("ai-stp:passport:v1", member)?,
                registrable: true,
                blocked: false,
                author_verified: false,
                component_verified: false,
                checks_current: false,
                consented: false,
            },
        );
    }
    let roots = [serde_json::to_value(reference(&setup)?)?];
    let assessed = ai_stp_cli_v2::selection::eligibility::assess_graph(
        &mut store,
        &roots,
        &target,
        &evidence,
        Some(&provider),
    )?;
    assert_eq!(assessed["admissible"], true, "{assessed:#}");
    assert_eq!(
        assessed["assessments"]
            .as_array()
            .ok_or("assessments missing")?
            .len(),
        3
    );
    evidence
        .get_mut(first_id)
        .ok_or("evidence missing")?
        .blocked = true;
    assert_eq!(
        ai_stp_cli_v2::selection::eligibility::assess_graph(
            &mut store,
            &roots,
            &target,
            &evidence,
            Some(&provider)
        )?["admissible"],
        false
    );
    evidence.remove(first_id);
    assert!(
        ai_stp_cli_v2::selection::eligibility::assess_graph(
            &mut store,
            &roots,
            &target,
            &evidence,
            Some(&provider)
        )
        .is_err()
    );
    assert!(
        ai_stp_cli_v2::selection::eligibility::assess_graph(
            &mut store,
            &[],
            &target,
            &evidence,
            Some(&provider)
        )
        .is_err()
    );
    let id = field(&setup, "stable_id")?;
    let head = field(&setup, "revision_id")?.to_owned();
    let mut edited = setup.clone();
    edited["parent_revision_ids"] = json!([head]);
    edited["name"] = "Later draft".into();
    let edited = store.transaction(|t| {
        revisions::commit(
            t,
            &edited,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: std::slice::from_ref(&head),
            },
        )
    })?;
    let current = field(&edited, "revision_id")?.to_owned();
    for fields in [[true, false], [false, true], [true, true]] {
        let mut invalid = edited.clone();
        invalid["parent_revision_ids"] = json!([current]);
        if fields[0] {
            invalid["harness_id"] = "cursor".into();
        }
        if fields[1] {
            invalid["facts"]["harness_id"]["value"] = "cursor".into();
        }
        assert!(
            store
                .transaction(|t| revisions::commit(
                    t,
                    &invalid,
                    &identity.device_id,
                    None,
                    Write::Advance {
                        expected_heads: std::slice::from_ref(&current)
                    }
                ))
                .is_err()
        );
    }
    let mut invalid = setup.clone();
    invalid["harness_id"] = "cursor".into();
    invalid["facts"]["harness_id"]["value"] = "cursor".into();
    invalid["version"] = "1.1".into();
    assert!(
        store
            .transaction(|t| versions::record(t, &invalid, &identity.device_id, None, AT))
            .is_err()
    );
    let mut empty = request;
    empty.members.clear();
    let empty = setups::plan(&mut store, empty, identity.clone(), AT)?;
    let empty = setups::apply(&mut store, &empty, &empty.digest()?, &identity, AT)?;
    assert_eq!(empty["components"], json!([]));
    assert_eq!(empty["requires_authorization"], "none");
    assert_eq!(empty["member_metadata_complete"], true);
    drop(store);
    let mut store = Store::open(root.path(), false)?;
    assert_eq!(
        setups::apply(&mut store, &plan, &plan.digest()?, &identity, LATER)?,
        setup
    );
    store.transaction(|t| {
        assert_eq!(revisions::heads(t, id)?, [current]);
        t.execute(
            "UPDATE content SET bytes=zeroblob(byte_length) WHERE digest=?",
            [first["artifact"]["digest"]
                .as_str()
                .ok_or_else(|| Failure::input("digest missing"))?],
        )
        .map_err(|_| Failure::precondition("proof corruption failed"))?;
        Ok(())
    })?;
    assert!(setups::apply(&mut store, &plan, &plan.digest()?, &identity, LATER).is_err());
    Ok(())
}
