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
    let extracted = reader::Package::read_native(
        &mut store,
        &bundle.archive,
        "codex",
        projection::Scope::Global,
        &Hosts::new(),
    )?;
    assert_eq!(extracted.setup, setup);
    assert_eq!(extracted.files["AGENTS.md"].bytes, guidance);
    assert_eq!(extracted.binding.artifact_digest, bundle.artifact_digest);
    assert!(
        reader::Package::read_native(
            &mut store,
            &bundle.archive,
            "codex",
            projection::Scope::Project,
            &Hosts::new(),
        )
        .is_err()
    );
    assert!(
        reader::Package::read_native(
            &mut store,
            &bundle.archive,
            "claude-code",
            projection::Scope::Global,
            &Hosts::new(),
        )
        .is_err()
    );
    let unrelated_host = Hosts::from([("config.toml".into(), Some(b"unowned = true".to_vec()))]);
    assert!(
        reader::Package::read_native(
            &mut store,
            &bundle.archive,
            "codex",
            projection::Scope::Global,
            &unrelated_host,
        )
        .is_err()
    );
    for (field, value) in [
        (
            "projection_profile",
            json!({"profile_id":"foreign","profile_digest":digest::sha256(b"foreign"),"target_scope":"global"}),
        ),
        ("target_scope", json!("project")),
        ("component_adaptations", json!([])),
        ("managed_paths", json!([])),
        ("input_digest", json!("invalid")),
    ] {
        let changed = change_package(&bundle.archive, |manifest, _| {
            manifest[field] = value;
            Ok(())
        })?;
        // Historical extraction keeps its original data interpretation. A
        // rehashed manifest is still not native profile/source authority.
        assert!(reader::Package::read(&changed).is_ok(), "legacy {field}");
        assert!(
            reader::Package::read_native(
                &mut store,
                &changed,
                "codex",
                projection::Scope::Global,
                &Hosts::new(),
            )
            .is_err(),
            "native {field}"
        );
    }
    let substituted = change_package(&bundle.archive, |manifest, entries| {
        let entry = entries
            .iter_mut()
            .find(|entry| entry.path == "files/AGENTS.md")
            .ok_or("payload absent")?;
        entry.bytes = b"Unrelated but self-consistent package bytes.\n"
            .to_vec()
            .into();
        manifest["files"][0]["digest"] = digest::sha256(&entry.bytes).into();
        manifest["files"][0]["byte_length"] = json!(entry.bytes.len());
        Ok(())
    })?;
    assert!(reader::Package::read(&substituted).is_ok());
    assert!(
        reader::Package::read_native(
            &mut store,
            &substituted,
            "codex",
            projection::Scope::Global,
            &Hosts::new(),
        )
        .is_err()
    );
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

// Construct packages whose internal hashes are valid, so rejection proves the
// native source/profile checks rather than merely a damaged ZIP or digest.
fn change_package(
    bytes: &[u8],
    change: impl FnOnce(
        &mut Value,
        &mut Vec<archive::Entry<'_>>,
    ) -> std::result::Result<(), Box<dyn std::error::Error>>,
) -> std::result::Result<Vec<u8>, Box<dyn std::error::Error>> {
    let limits = archive::Limits {
        entries: MAX_FILES + 6,
        file_bytes: MAX_FILE_BYTES,
        content_bytes: MAX_BYTES,
        archive_bytes: MAX_BYTES,
    };
    let mut entries = archive::decode(bytes, limits)?;
    let mut manifest = crate::wire::parse(&entries[0].bytes)?;
    change(&mut manifest, &mut entries)?;
    manifest
        .as_object_mut()
        .ok_or("manifest absent")?
        .remove("bundle_digest");
    manifest["bundle_digest"] = digest::canonical("ai-stp:bundle:v1", &manifest)?.into();
    entries[0].bytes = canonical::bytes(&manifest)?.into();
    Ok(archive::encode(&entries, limits)?)
}

#[test]
fn shared_reader_checks_actual_authored_packages_for_all_seven_harnesses()
-> std::result::Result<(), Box<dyn std::error::Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().canonicalize()?;
    let input = root.join("input");
    std::fs::create_dir(&input)?;
    std::fs::write(input.join("guide.md"), b"# Guidance\nVerify each change.\n")?;
    let mut store = Store::open(&root, true)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let (os, arch) = crate::platform::current()
        .and_then(|platform| platform.split_once('/'))
        .ok_or("unsupported fixture platform")?;
    let at = "2026-11-03T00:00:00.000Z";
    let mut checked = 0;
    for harness in crate::harnesses::definitions()? {
        if harness.harness_id == "undefined" {
            continue;
        }
        let plan = embedded::plan(
            &mut store,
            embedded::Request {
                directory: input.clone(),
                harness_id: harness.harness_id.clone(),
                component_type: "instruction".into(),
                name: format!("native-{}", harness.harness_id),
                license_spdx: "MIT".into(),
            },
            identity.clone(),
            at,
        )?;
        embedded::apply(&mut store, &plan, &plan.digest()?, &identity, at)?;
        let setup = json!({"stable_id":plan.setup["stable_id"],"version":plan.setup["version"],
            "passport_digest":digest::canonical("ai-stp:passport:v1", &plan.setup)?});
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
        // Embedded authoring deliberately captures its declared native scope;
        // it does not invent project adaptations for a global source.
        let scope: projection::Scope = serde_json::from_value(
            plan.component["adaptations"][0]["scope_adaptations"][0]["scope"].clone(),
        )?;
        {
            let target = Target {
                harness_id: harness.harness_id.clone(),
                scope,
                os: os.into(),
                arch: arch.into(),
                harness_version: "unknown".into(),
                owner_id: identity.account_id.clone(),
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
            let package = compile_native(&mut store, &setup, &target, &evidence, &Hosts::new())?;
            let read = reader::Package::read_native(
                &mut store,
                &package.archive,
                &harness.harness_id,
                scope,
                &Hosts::new(),
            )?;
            assert_eq!(read.setup, setup);
            assert_eq!(read.binding.artifact_digest, package.artifact_digest);
            assert!(!read.files.is_empty());
            checked += 1;
        }
    }
    assert_eq!(checked, 7);
    Ok(())
}

#[test]
fn native_scope_packages_establish_complete_coverage_only_as_their_exact_set()
-> std::result::Result<(), Box<dyn std::error::Error>> {
    use crate::authoring::setups;
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().canonicalize()?;
    let mut store = Store::open(&root, true)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let at = "2026-11-03T00:00:00.000Z";
    let mut components = Vec::new();
    for (kind, name, leaf, content) in [
        (
            "instruction",
            "native-guidance",
            "guide.md",
            "# Guidance\nVerify each change.\n",
        ),
        (
            "skill",
            "native-review",
            "SKILL.md",
            "---\nname: native-review\ndescription: Review current source.\n---\nInspect the current change.\n",
        ),
    ] {
        let input = root.join(kind);
        std::fs::create_dir(&input)?;
        std::fs::write(input.join(leaf), content)?;
        let plan = embedded::plan(
            &mut store,
            embedded::Request {
                directory: input,
                harness_id: "codex".into(),
                component_type: kind.into(),
                name: name.into(),
                license_spdx: "MIT".into(),
            },
            identity.clone(),
            at,
        )?;
        embedded::apply(&mut store, &plan, &plan.digest()?, &identity, at)?;
        components.push(plan.component);
    }
    let planned = setups::plan(
        &mut store,
        setups::Request {
            harness_id: "codex".into(),
            name: "Native scoped setup".into(),
            description: "One exact setup across two declared roots.".into(),
            purpose: "Verify complete native scope coverage without an external declaration."
                .into(),
            requirements: None,
            members: components
                .iter()
                .map(|document| {
                    Ok(setups::Member {
                        stable_id: text(document, "stable_id")?.into(),
                        version: text(document, "version")?.into(),
                        passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
                    })
                })
                .collect::<Result<Vec<_>>>()?,
        },
        identity.clone(),
        at,
    )?;
    let document = setups::apply(&mut store, &planned, &planned.digest()?, &identity, at)?;
    let setup = json!({"stable_id":document["stable_id"],"version":document["version"],
        "passport_digest":digest::canonical("ai-stp:passport:v1", &document)?});
    components.push(document);
    let evidence = components
        .iter()
        .map(|document| {
            Ok((
                text(document, "stable_id")?.into(),
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
        .and_then(|v| v.split_once('/'))
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
    let hosts = BTreeMap::from([
        (projection::Scope::Global, Hosts::new()),
        (projection::Scope::UserRoot, Hosts::new()),
    ]);
    let changes: i64 = store
        .connection
        .query_row("SELECT total_changes()", [], |row| row.get(0))?;
    assert!(compile_native(&mut store, &setup, &target, &evidence, &Hosts::new()).is_err());
    let compiled = scopes::compile_native(
        &mut store,
        &setup,
        &target,
        &evidence,
        &hosts,
        &BTreeMap::new(),
    )?;
    assert_eq!(compiled.bundles.len(), 2);
    let inputs = compiled
        .bundles
        .iter()
        .map(|(scope, bundle)| {
            Ok((
                *scope,
                reader::Input {
                    archive: &bundle.archive,
                    hosts: hosts.get(scope).ok_or("host absent")?,
                },
            ))
        })
        .collect::<std::result::Result<BTreeMap<_, _>, Box<dyn std::error::Error>>>()?;
    let packages = reader::Package::read_native_set(&mut store, "codex", &inputs)?;
    assert_eq!(packages.len(), 2);
    for (scope, input) in &inputs {
        assert!(
            reader::Package::read_native(&mut store, input.archive, "codex", *scope, input.hosts)
                .is_err()
        );
        let partial = BTreeMap::from([(
            *scope,
            reader::Input {
                archive: input.archive,
                hosts: input.hosts,
            },
        )]);
        assert!(reader::Package::read_native_set(&mut store, "codex", &partial).is_err());
    }
    let wrong = BTreeMap::from([
        (
            projection::Scope::Global,
            reader::Input {
                archive: inputs[&projection::Scope::UserRoot].archive,
                hosts: &hosts[&projection::Scope::Global],
            },
        ),
        (
            projection::Scope::UserRoot,
            reader::Input {
                archive: inputs[&projection::Scope::Global].archive,
                hosts: &hosts[&projection::Scope::UserRoot],
            },
        ),
    ]);
    assert!(reader::Package::read_native_set(&mut store, "codex", &wrong).is_err());
    let repeated = scopes::compile_native(
        &mut store,
        &setup,
        &target,
        &evidence,
        &hosts,
        &BTreeMap::new(),
    )?;
    for (scope, bundle) in &compiled.bundles {
        assert_eq!(bundle.archive, repeated.bundles[scope].archive);
    }
    assert_eq!(
        store
            .connection
            .query_row("SELECT total_changes()", [], |row| row.get::<_, i64>(0))?,
        changes
    );
    Ok(())
}
