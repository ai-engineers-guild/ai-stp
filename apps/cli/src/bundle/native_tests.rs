//! The native engine shares exact graph, payload and access checks with legacy compilation.

use super::*;
use crate::{
    archive,
    authoring::{Identity, embedded},
    selection::eligibility::{Evidence, Target},
};
use std::collections::BTreeSet;

#[test]
fn native_compilation_keeps_exact_payload_and_refusals_without_external_declaration()
-> std::result::Result<(), Box<dyn std::error::Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().canonicalize()?;
    let input = root.join("input");
    std::fs::create_dir(&input)?;
    let guidance = b"# Project guidance\nKeep changes small and verify the affected behavior.\n";
    std::fs::write(input.join("guide.md"), guidance)?;
    let mut store = Store::open(&root, true)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let at = "2026-10-31T00:00:00.000Z";
    let plan = embedded::plan(
        &mut store,
        embedded::Request {
            directory: input.clone(),
            harness_id: "codex".into(),
            component_type: "instruction".into(),
            name: "native-guide".into(),
            license_spdx: "MIT".into(),
        },
        identity.clone(),
        at,
    )?;
    embedded::apply(&mut store, &plan, &plan.digest()?, &identity, at)?;
    let setup = json!({
        "stable_id":plan.setup["stable_id"],
        "version":plan.setup["version"],
        "passport_digest":digest::canonical("ai-stp:passport:v1", &plan.setup)?,
    });
    let evidence = [&plan.component, &plan.setup]
        .into_iter()
        .map(|document| {
            Ok((
                text(document, "stable_id")?.to_owned(),
                Evidence {
                    passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
                    registrable: true,
                    blocked: false,
                    author_verified: false,
                    component_verified: false,
                    checks_current: false,
                    consented: true,
                },
            ))
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let (os, arch) = crate::platform::current()
        .and_then(|platform| platform.split_once('/'))
        .ok_or("unsupported fixture platform")?;
    let target = Target {
        harness_id: "codex".into(),
        scope: projection::Scope::Global,
        os: os.into(),
        arch: arch.into(),
        harness_version: "unknown".into(),
        owner_id: identity.account_id,
        capabilities: BTreeSet::new(),
        permissions: BTreeSet::new(),
        entitlements: BTreeSet::new(),
        env_present: BTreeSet::new(),
        grants: BTreeSet::new(),
        accessible_passport_digests: BTreeSet::new(),
        access_context_digest: None,
        pinned_passport_digests: BTreeSet::new(),
        owned_passport_digests: BTreeSet::new(),
        for_redistribution: false,
    };
    let changes: i64 = store
        .connection
        .query_row("SELECT total_changes()", [], |row| row.get(0))?;
    let bundle = compile_native(&mut store, &setup, &target, &evidence, &Hosts::new())?;
    assert_eq!(bundle.manifest["setup"], setup);
    assert_eq!(bundle.manifest["managed_paths"], json!(["AGENTS.md"]));
    assert_eq!(
        bundle.manifest["component_adaptations"]
            .as_array()
            .ok_or("bindings absent")?
            .len(),
        1
    );
    let entries = archive::decode(
        &bundle.archive,
        archive::Limits {
            entries: MAX_FILES + 6,
            file_bytes: MAX_FILE_BYTES,
            content_bytes: MAX_BYTES,
            archive_bytes: MAX_BYTES,
        },
    )?;
    let file = entries
        .iter()
        .find(|entry| entry.path == "files/AGENTS.md")
        .ok_or("payload absent")?;
    assert_eq!(file.bytes.as_ref(), guidance);
    let repeated = compile_native(&mut store, &setup, &target, &evidence, &Hosts::new())?;
    assert_eq!(bundle.archive, repeated.archive);

    let component = text(&plan.component, "stable_id")?;
    let mut missing = evidence.clone();
    missing.remove(component);
    assert!(compile_native(&mut store, &setup, &target, &missing, &Hosts::new()).is_err());
    let mut blocked = evidence.clone();
    blocked
        .get_mut(component)
        .ok_or("component evidence absent")?
        .blocked = true;
    let error = compile_native(&mut store, &setup, &target, &blocked, &Hosts::new())
        .err()
        .ok_or("blocked object accepted")?;
    assert!(serde_json::to_string(&error.details)?.contains("\"object_blocked\""));
    let mut foreign = target.clone();
    foreign.owner_id = "account_01ARZ3NDEKTSV4RRFFQ69G5FAW".into();
    let error = compile_native(&mut store, &setup, &foreign, &evidence, &Hosts::new())
        .err()
        .ok_or("private graph accepted for another owner")?;
    assert!(serde_json::to_string(&error.details)?.contains("\"grant_missing\""));
    let mut wrong_harness = target.clone();
    wrong_harness.harness_id = "claude-code".into();
    let error = compile_native(&mut store, &setup, &wrong_harness, &evidence, &Hosts::new())
        .err()
        .ok_or("another harness accepted")?;
    assert!(serde_json::to_string(&error.details)?.contains("\"harness_mismatch\""));
    let mut remote = target.clone();
    remote.os = if os == "linux" { "windows" } else { "linux" }.into();
    let error = compile_native(&mut store, &setup, &remote, &evidence, &Hosts::new())
        .err()
        .ok_or("another execution host accepted")?;
    assert!(serde_json::to_string(&error.details)?.contains("\"provider_platform_unsupported\""));
    assert_eq!(
        store
            .connection
            .query_row("SELECT total_changes()", [], |row| row.get::<_, i64>(0))?,
        changes
    );
    assert_eq!(std::fs::read(input.join("guide.md"))?, guidance);
    Ok(())
}
