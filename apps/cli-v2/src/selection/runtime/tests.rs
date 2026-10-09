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
        assert!(Request::parse(&path).is_err(), "{field}");
    }
    Ok(())
}
