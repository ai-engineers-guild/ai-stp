use super::*;
use crate::{
    artifacts::{self, Member},
    authoring::releases,
    store::{
        revisions::Write,
        versions::{self, Increment},
    },
};
use std::error::Error;

const AT: &str = "2026-10-09T00:00:00.000Z";

#[test]
fn local_runtime_reads_real_artifacts_without_inventing_rights()
-> std::result::Result<(), Box<dyn Error>> {
    // Defaults belong to new input; a retained selector must stay exact.
    let request = json!({"harness_id":"codex","scope":"global","members":[]});
    assert_eq!(
        Request::from_value(request.clone(), true)?.provider_version,
        crate::provider::managed::RELEASE
    );
    for version in [
        json!(null),
        json!(""),
        json!("latest"),
        json!("01.0.0"),
        json!("1.1000.0"),
        json!("1.0.1000"),
    ] {
        let mut changed = request.clone();
        changed["provider_version"] = version;
        assert!(Request::from_value(changed, true).is_err());
    }
    let mut exact = request;
    exact["provider_version"] = "1.2.3".into();
    assert_eq!(Request::from_value(exact, true)?.provider_version, "1.2.3");
    assert!(
        serde_json::from_value::<Selector>(json!({"harness_id":"codex","scope":"global"})).is_err()
    );
    let directory = tempfile::tempdir()?;
    let mut store = Store::open(directory.path(), true)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let declarations: Vec<Value> = serde_json::from_str(include_str!(
        "../../../tests/fixtures/provider-declarations.json"
    ))?;
    let provider = Info::parse(&serde_json::to_vec(
        declarations
            .iter()
            .find(|d| d["harness_id"] == "claude-code")
            .ok_or("provider")?,
    )?)?;
    let bytes = artifacts::encode_tree(&[Member {
        path: "SKILL.md".into(),
        bytes:
            b"---\nname: inspect\ndescription: Inspect source conventions.\n---\nRead the source.\n"
                .to_vec(),
        mode: 0o644,
    }])?;
    let draft = store.transaction(|t| {
        let address = revisions::content(t, &bytes, AT)?;
        let values = json!({"name":"inspect","description":"Inspect source conventions.","tags":["development"],
            "harness_id":"claude-code","component_type":"skill","projection_kind":"native_files","scope":"global",
            "content_digest":address,"byte_length":bytes.len(),"content_format":artifacts::TREE_FORMAT,
            "native_ids":["inspect"],"managed_paths":["skills/inspect"],
            "license":{"spdx_id":"MIT","redistribution_allowed":true}});
        let facts: serde_json::Map<String,Value> = values.as_object().ok_or_else(invalid)?.iter()
            .map(|(k,v)|(k.clone(),json!({"value":v,"origin":"declared","confirmation":"none"}))).collect();
        revisions::commit(t, &json!({"kind":"component","stable_id":format!("component_{}",ulid::Ulid::generate()),
            "owner_id":identity.account_id,"created_at":AT,"facts":facts}), &identity.device_id, None, Write::Advance{expected_heads:&[]})
    })?;
    let plan = releases::plan(
        &mut store,
        text(&draft, "stable_id")?,
        text(&draft, "revision_id")?,
        Increment::Minor,
        std::slice::from_ref(&provider),
        identity.clone(),
        AT,
    )?;
    let original = releases::apply(&mut store, &plan, &plan.digest()?, &identity, AT)?;
    let target = Request {
        harness_id: "claude-code".into(),
        scope: Scope::Global,
        provider_version: "0.0.88".into(),
        members: vec![],
        for_redistribution: false,
    }
    .target(&identity)?;
    let reference = |document: &Value| -> Result<Value> {
        Ok(
            json!({"stable_id":document["stable_id"],"version":document["version"],
            "passport_digest":crate::digest::canonical("ai-stp:passport:v1", document)?}),
        )
    };
    let roots = [reference(&original)?];
    let observed = store.transaction(|t| assess_snapshot(t, &roots, target.clone(), &provider))?;
    assert_eq!(observed["assessment"]["admissible"], true);
    assert_eq!(observed["target"]["harness_version"], "");
    assert_eq!(observed["target"]["permissions"], json!([]));
    assert_eq!(observed["target"]["grants"], json!([]));
    assert_eq!(observed["installation_authorized"], false);
    assert!(
        observed["verified_artifact_bytes"]
            .as_u64()
            .is_some_and(|n| n > 0)
    );

    for (index, (case, expected)) in [
        ("version", "harness_version_unknown"),
        ("permission", "entitlement_not_granted"),
        ("capability", "capability_missing"),
        ("other_owner", "evidence_stale"),
    ]
    .into_iter()
    .enumerate()
    {
        let mut document = original.clone();
        document["version"] = format!("1.{}", index + 1).into();
        match case {
            "version" => {
                document["adaptations"][0]["scope_adaptations"][0]["supported_harness_versions"] =
                    json!(["1.2.3"])
            }
            "permission" => document["permissions"]["filesystem"] = json!(["read_project"]),
            "capability" => document["requires_capabilities"] = json!(["project.language.rust"]),
            _ => {}
        }
        document["adaptations"][0] =
            passport::versions::seal_adaptation(&document["adaptations"][0])?;
        let document =
            store.transaction(|t| versions::record(t, &document, &identity.device_id, None, AT))?;
        let mut current_target = target.clone();
        if case == "other_owner" {
            current_target.owner_id = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into();
        }
        let observed = store.transaction(|t| {
            assess_snapshot(t, &[reference(&document)?], current_target, &provider)
        })?;
        assert_eq!(observed["assessment"]["admissible"], false, "{case}");
        assert!(
            observed["assessment"]["assessments"][0]["refusals"]
                .as_array()
                .ok_or("refusals")?
                .iter()
                .any(|r| r["code"] == expected),
            "{case}: {observed}"
        );
    }
    // Candidate graphs are independent: the two setups deliberately require
    // different immutable versions of the same component.
    let mut setup_ids = Vec::new();
    for version in ["1.0", "1.4"] {
        let component = store.transaction(|t| {
            Objects { connection: t }.exact_version(text(&original, "stable_id")?, version, None)
        })?;
        let request = setups::Request {
            harness_id: "claude-code".into(),
            name: format!("review-{version}"),
            description: "Review the exact component version.".into(),
            purpose: "Preserve independent candidate graphs.".into(),
            members: vec![serde_json::from_value(reference(&component)?)?],
            requirements: None,
        };
        let plan = setups::plan(&mut store, request, identity.clone(), AT)?;
        let setup = setups::apply(&mut store, &plan, &plan.digest()?, &identity, AT)?;
        setup_ids.push(text(&setup, "stable_id")?.to_owned());
    }
    let unreleased_id = format!("component_{}", ulid::Ulid::generate());
    store.transaction(|t|revisions::commit(t,&json!({"kind":"component","stable_id":unreleased_id,"owner_id":identity.account_id,"created_at":AT}),
        &identity.device_id,None,Write::Advance {expected_heads:&[]}))?;
    let matrix_path = directory.path().join("matrix.json");
    let mut matrix_request = json!({"targets":[
        {"harness_id":"codex","scope":"global"},
        {"harness_id":"claude-code","scope":"global"}]});
    std::fs::write(&matrix_path, serde_json::to_vec(&matrix_request)?)?;
    let request = matrix::Request::parse(&matrix_path)?;
    let providers = ["claude-code", "codex"]
        .iter()
        .map(|harness| {
            let value = declarations
                .iter()
                .find(|d| d["harness_id"] == *harness)
                .ok_or_else(invalid)?;
            Ok((Info::parse(&canonical::bytes(value)?)?, Value::Null))
        })
        .collect::<Result<Vec<_>>>()?;
    let report =
        store.transaction(|t| matrix::assess_snapshot(t, &request, &identity, &providers))?;
    assert_eq!(
        report["targets"][0]["selector"]["harness_id"],
        "claude-code"
    );
    assert_eq!(
        report["targets"][0]["selector"]["provider_version"],
        crate::provider::managed::RELEASE
    );
    let candidates = report["candidates"].as_array().ok_or("candidates")?;
    assert_eq!(candidates.len(), 4);
    for id in &setup_ids {
        let row = candidates
            .iter()
            .find(|r| r["stable_id"] == *id)
            .ok_or("setup row")?;
        assert_eq!(row["graph"]["resolved"], true);
        assert_eq!(row["cells"][0]["assessment"]["admissible"], true);
        assert_eq!(row["cells"][1]["assessment"]["admissible"], false);
    }
    let row = candidates
        .iter()
        .find(|r| r["stable_id"] == original["stable_id"])
        .ok_or("component row")?;
    assert_eq!(row["coordinate"]["version"], "1.4");
    let row = candidates
        .iter()
        .find(|r| r["stable_id"] == unreleased_id)
        .ok_or("draft row")?;
    assert_eq!(row["state"], "unreleased");
    assert_eq!(row["eligible_somewhere"], false);
    assert_eq!(row["refusals"][0]["code"], "immutable_version_missing");
    matrix_request["limit"] = 1.into();
    let mut found = Vec::new();
    loop {
        std::fs::write(&matrix_path, serde_json::to_vec(&matrix_request)?)?;
        let request = matrix::Request::parse(&matrix_path)?;
        let report =
            store.transaction(|t| matrix::assess_snapshot(t, &request, &identity, &providers))?;
        found.push(report["candidates"][0]["stable_id"].clone());
        if report["next_after"].is_null() {
            break;
        }
        matrix_request["after"] = report["next_after"].clone();
    }
    assert_eq!(
        found,
        candidates
            .iter()
            .map(|r| r["stable_id"].clone())
            .collect::<Vec<_>>()
    );
    assert!(
        store
            .transaction(|t| inputs_with_budget(t, &roots, target.clone(), 0))
            .is_err()
    );
    for field in ["owner_id", "permissions", "grants", "provider_info"] {
        let mut claimed = matrix_request.clone();
        claimed["targets"][0][field] = "claim-must-not-be-echoed".into();
        std::fs::write(&matrix_path, serde_json::to_vec(&claimed)?)?;
        assert!(matrix::Request::parse(&matrix_path).is_err(), "{field}");
    }
    // A correctly addressed passport cannot stand in for missing/corrupt bytes.
    store.transaction(|t| {
        t.execute(
            "UPDATE content SET bytes=x'00',byte_length=1 WHERE digest=?",
            [text(&original["artifact"], "digest")?],
        )
        .map_err(crate::store::database)?;
        Ok(())
    })?;
    assert!(
        store
            .transaction(|t| assess_snapshot(t, &roots, target.clone(), &provider))
            .is_err()
    );
    for field in [
        "owner_id",
        "permissions",
        "harness_version",
        "evidence",
        "grants",
        "provider_info",
    ] {
        let mut request = json!({"harness_id":"claude-code","scope":"global","provider_version":"0.0.88","members":roots});
        request[field] = "claim-must-not-be-echoed".into();
        let path = directory.path().join("request.json");
        std::fs::write(&path, serde_json::to_vec(&request)?)?;
        assert!(Request::parse(&path, false).is_err(), "{field}");
    }
    Ok(())
}
