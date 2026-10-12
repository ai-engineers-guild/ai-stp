use super::*;
use std::{error::Error, fs, os::unix::fs::symlink};

fn encode(value: &Value) -> Result<(Vec<u8>, String)> {
    let bytes = serde_json_canonicalizer::to_vec(value).map_err(|_| invalid())?;
    let digest = digest::bytes("ai-stp:installation-operation:v1", &bytes)?;
    Ok((bytes, digest))
}

#[test]
fn removal_preserves_other_versions_and_replays_only_the_original_terminal_receipt()
-> std::result::Result<(), Box<dyn Error>> {
    // Local fixtures exercise native binding and journal semantics, not release trust.
    let root = tempfile::tempdir_in("/tmp")?;
    let state = root.path().join("state");
    let target = root.path().join("target");
    let prefix = root.path().join("program");
    for path in [&state, &target, &prefix] {
        fs::create_dir(path)?;
    }
    for name in ["1.0", "2.0", "bin"] {
        fs::create_dir(prefix.join(name))?;
    }
    fs::write(prefix.join("1.0/tool"), b"old")?;
    fs::write(prefix.join("2.0/tool"), b"current")?;
    fs::write(prefix.join("user-file"), b"keep")?;
    fs::write(prefix.join("bin/.tool.version"), b"2.0")?;
    symlink(prefix.join("2.0/tool"), prefix.join("bin/tool"))?;
    let held = Target::open(&prefix)?;
    let directory = held.directory()?;
    let unchanged = verify::unchanged(&directory)?;
    fs::rename(prefix.join("user-file"), prefix.join("held-user-file"))?;
    fs::write(prefix.join("user-file"), b"keep")?;
    assert_ne!(verify::unchanged(&directory)?, unchanged);
    fs::remove_file(prefix.join("user-file"))?;
    fs::rename(prefix.join("held-user-file"), prefix.join("user-file"))?;
    assert_eq!(verify::unchanged(&directory)?, unchanged);
    let preserved = verify::preserved(&directory, "1.0", "bin/tool")?;
    let launch = verify::launch(&directory, "bin/tool")?;
    assert!(!verify::active(&directory, "1.0", "bin/tool")?);
    assert!(verify::active(&directory, "2.0", "bin/tool")?);
    fs::write(prefix.join("user-file"), b"changed")?;
    assert_ne!(verify::preserved(&directory, "1.0", "bin/tool")?, preserved);
    fs::write(prefix.join("user-file"), b"keep")?;

    let created = Timestamp::now();
    let expires = created.checked_add(std::time::Duration::from_secs(900))?;
    let hash = digest::sha256(b"fixture-only component identity");
    let operation = format!("operation_{}", ulid::Ulid::generate());
    let document = json!({
        "schema_version":1,"action":"program.remove","operation_id":operation,
        "created_at":format!("{created:.3}"),"expires_at":format!("{expires:.3}"),
        "state_parent":state,"state_parent_identity":identity(&Target::open(&state)?)?,
        "harness_id":"codex","provider_version":"0.0.89",
        "target":{"path":target,"scope":"global","identity":identity(&Target::open(&target)?)?},
        "prefix":{"path":prefix,"expected_state":"existing","parent_identity":identity(&Target::open(root.path())?)?,
            "existing":{"identity":identity(&held)?,"entry_point":"bin/tool", "preserved_digest":preserved,
                "launch_digest":launch,"selected_is_active":false}},
        "component":{"archive_digest":hash,"executable_digest":hash,"info_digest":hash},
        "provider_plan":{"plan":{"operation":"software_remove","operation_id":operation,
            "expires_at":format!("{expires:.3}"),"canonical_target":target,"software_prefix":prefix,
            "provider_version":"0.0.89","provider_release_digest":hash,"software_version":"1.0",
            "software_artifacts":[]},"plan_digest":hash}
    });
    let (bytes, digest) = encode(&document)?;
    let plan = Plan::parse(&bytes, &digest)?;
    context(&plan)?;
    fs::rename(&prefix, root.path().join("held"))?;
    fs::create_dir(&prefix)?;
    assert!(context(&plan).is_err());
    fs::remove_dir(&prefix)?;
    fs::rename(root.path().join("held"), &prefix)?;
    assert!(super::super::apply(&state, &bytes, &digest).is_err());
    assert!(super::super::cancellation::cancel(&state, &bytes, &digest).is_err());
    assert!(apply(&state, &bytes, &digest, "program.update").is_err());
    assert!(cancellation::cancel(&state, &bytes, &digest, "program.remove").is_err());
    assert_eq!(fs::read_dir(&state)?.count(), 0);

    let journal = Journal::open(&state, &plan, &digest)?;
    let mut record = Record {
        schema_version: 1,
        plan_digest: digest.clone(),
        plan: document.clone(),
        phase: Phase::Applying,
        stage_parent: None,
        stage_root: None,
        result: None,
    };
    journal.write(None, &record)?;
    let mut competing = document.clone();
    let other = format!("operation_{}", ulid::Ulid::generate());
    competing["operation_id"] = other.clone().into();
    competing["provider_plan"]["plan"]["operation_id"] = other.into();
    let (other_bytes, other_digest) = encode(&competing)?;
    let other_plan = Plan::parse(&other_bytes, &other_digest)?;
    assert!(Journal::open(&state, &other_plan, &other_digest).is_err());
    drop(journal);
    // A dead native caller does not reserve the prefix forever. The component
    // still owns admission and recovery of any actual incomplete writes.
    drop(Journal::open(&state, &other_plan, &other_digest)?);
    let journal = Journal::open(&state, &plan, &digest)?;

    let expected = plan.prefix.existing.as_ref().ok_or_else(invalid)?;
    assert!(verify::removed(&directory, "1.0", expected).is_err());
    fs::remove_dir_all(prefix.join("1.0"))?;
    let verification = verify::removed(&directory, "1.0", expected)?;
    assert_eq!(verify::preserved(&directory, "1.0", "bin/tool")?, preserved);
    fs::write(prefix.join("bin/.tool.version"), b"wrong")?;
    assert!(verify::removed(&directory, "1.0", expected).is_err());
    fs::write(prefix.join("bin/.tool.version"), b"2.0")?;
    let result = json!({"operation_id":operation,"plan_digest":digest,"state":"verified",
        "action":"program.remove","harness_id":"codex","provider_version":"0.0.89","prefix":prefix,
        "mutation_performed":true,"verification":verification,
        "provider_result":{"state":"verified","recovered":[],"operation":"software_remove",
            "command":"tool","version":"1.0","removed":true,"plan_digest":hash}});
    validate_outcome(&result, &plan, &digest)?;
    for (field, value) in [
        ("mutation_performed", json!(false)),
        ("verification", json!({})),
        ("action", json!("program.update")),
        ("unexpected", json!(true)),
    ] {
        let mut corrupt = result.clone();
        corrupt[field] = value;
        assert!(validate_outcome(&corrupt, &plan, &digest).is_err());
    }
    record.phase = Phase::Complete;
    record.result = Some(result.clone());
    journal.write(Some(Phase::Applying), &record)?;
    drop(journal);
    fs::remove_dir_all(&prefix)?;
    fs::remove_dir(&target)?;
    assert_eq!(apply(&state, &bytes, &digest, "program.remove")?, result);
    assert!(!prefix.exists() && !target.exists());
    cancellation_history(&state, &document)?;
    let mut changed = document;
    changed["prefix"]["existing"]["selected_is_active"] = true.into();
    let (changed, changed_digest) = encode(&changed)?;
    assert!(apply(&state, &changed, &changed_digest, "program.remove").is_err());
    Ok(())
}

fn cancellation_history(state: &Path, document: &Value) -> std::result::Result<(), Box<dyn Error>> {
    // Local terminal fixtures exercise history validation, not component admission.
    for previous in [None, Some(Phase::Applying)] {
        let mut value = document.clone();
        value["operation_id"] = format!("operation_{}", ulid::Ulid::generate()).into();
        value["provider_version"] = "0.0.93".into();
        value["provider_plan"]["plan"]["operation_id"] = value["operation_id"].clone();
        value["provider_plan"]["plan"]["provider_version"] = "0.0.93".into();
        value["provider_plan"]["plan"]["expected_software_digest"] =
            digest::sha256(b"fixture prefix").into();
        let (bytes, digest) = encode(&value)?;
        let plan = Plan::parse(&bytes, &digest)?;
        let provider = json!({"state":"cancelled", "operation":"software_remove",
            "operation_id":plan.operation_id,"command":"tool","version":"1.0",
            "software_changed":false,"expected_software_digest":value["provider_plan"]["plan"]["expected_software_digest"],
            "plan_digest":value["provider_plan"]["plan_digest"]});
        let result =
            cancellation::outcome(&plan, &digest, &provider, &digest::sha256(b"unchanged"));
        cancellation::validate_outcome(&result, &plan, &digest)?;
        for (field, wrong) in [
            ("mutation_performed", json!(true)),
            ("unchanged_observation_digest", json!("bad")),
            ("unexpected", json!(1)),
        ] {
            let mut changed = result.clone();
            changed[field] = wrong;
            assert!(cancellation::validate_outcome(&changed, &plan, &digest).is_err());
        }
        let journal = Journal::open(state, &plan, &digest)?;
        let mut record = Record {
            schema_version: 1,
            plan_digest: digest.clone(),
            plan: value,
            phase: Phase::Applying,
            stage_parent: None,
            stage_root: None,
            result: None,
        };
        if previous.is_some() {
            journal.write(None, &record)?;
        }
        record.phase = Phase::Cancelled;
        record.result = Some(result.clone());
        journal.write(previous, &record)?;
        drop(journal);
        assert_eq!(
            cancellation::cancel(state, &bytes, &digest, "program.remove")?,
            result
        );
        assert_eq!(apply(state, &bytes, &digest, "program.remove")?, result);
        assert!(cancellation::cancel(state, &bytes, &digest, "program.update").is_err());
    }
    Ok(())
}
