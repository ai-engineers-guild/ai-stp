use super::*;
use std::{error::Error, fs, os::unix::fs::PermissionsExt, path::Path};

#[test]
fn removal_binds_physical_parents_and_replays_history_without_the_target()
-> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir_in("/tmp")?;
    let state = temporary.path().join("state");
    let root = temporary.path().join("target-e\u{301}");
    fs::create_dir(&state)?;
    fs::create_dir(&root)?;
    fs::create_dir(root.join("skills"))?;
    fs::write(root.join("skills/owned.md"), b"old setup file")?;
    let section = ":::begin-ai-stp\nretained attachment\n:::end-ai-stp\n";
    fs::write(
        root.join("AGENTS.md"),
        format!("setup instructions\n{section}"),
    )?;
    fs::write(
        root.join("settings.json"),
        br#"{"user":9007199254740993,"managed":{"enabled":true}}"#,
    )?;
    for path in ["AGENTS.md", "settings.json", "skills/owned.md"] {
        fs::set_permissions(root.join(path), fs::Permissions::from_mode(0o644))?;
    }
    let target = Target::open(&root)?;
    let ownership = json!([
        {"path":"AGENTS.md","ownership":"whole","parser_id":null,"ownership_keys":[]},
        {"path":"settings.json","ownership":"contribution","parser_id":"json/1","ownership_keys":["managed"]},
        {"path":"skills/owned.md","ownership":"whole","parser_id":null,"ownership_keys":[]}
    ]);
    let effects = effects::expected(&target, &ownership, None, Some("AGENTS.md"))?;
    effects::verify(&target, &effects, false)?;
    assert!(effects::verify(&target, &effects, true).is_err());
    // Byte-identical contents in a substituted physical parent are not the
    // directory admitted by planning.
    fs::rename(root.join("skills"), root.join("held-skills"))?;
    fs::create_dir(root.join("skills"))?;
    fs::write(root.join("skills/owned.md"), b"old setup file")?;
    fs::set_permissions(
        root.join("skills/owned.md"),
        fs::Permissions::from_mode(0o644),
    )?;
    assert!(effects::verify(&target, &effects, false).is_err());
    fs::remove_dir_all(root.join("skills"))?;
    fs::rename(root.join("held-skills"), root.join("skills"))?;
    effects::verify(&target, &effects, false)?;

    // These private journal fixtures exercise local bindings and replay only.
    // They do not pretend to authenticate a component or authorize live apply.
    let vectors: Value = serde_json::from_str(include_str!(
        "../../../../tests/fixtures/provider-status-ownership.json"
    ))?;
    let mut status = vectors["base"].clone();
    status["canonical_target"] = json!(root);
    status["configuration_ownership"] = ownership;
    status["written_paths"] = json!(["AGENTS.md", "settings.json", "skills/owned.md"]);
    let hash = crate::digest::sha256(b"fixture-only component");
    let operation = format!("operation_{}", ulid::Ulid::generate());
    let plan = Plan {
        schema_version: 1,
        action: "configuration.remove".into(),
        operation_id: operation,
        created_at: "2020-01-01T00:00:00.000Z".into(),
        expires_at: "2020-01-01T00:15:00.000Z".into(),
        state_parent: state.to_str().ok_or("state")?.into(),
        state_identity: identity(&Target::open(&state)?)?,
        target_path: root.to_str().ok_or("target")?.into(),
        target_scope: Scope::Global,
        target_identity: identity(&target)?,
        harness_id: "codex".into(),
        provider_version: "0.0.91".into(),
        archive_digest: hash.clone(),
        executable_digest: hash.clone(),
        info_digest: hash.clone(),
        provider_plan: Value::Null,
        status_before: status,
        attachment_path: Some("AGENTS.md".into()),
        setup: Value::Null,
        ownership: json!([]),
        effects,
        project: None,
    };
    let mut document = plan.value()?;
    document["provider_plan"] = json!({"plan_digest":hash,"plan":{
        "operation":"remove","operation_id":plan.operation_id,"expires_at":plan.expires_at,
        "canonical_target":root,"provider_version":"0.0.91","provider_release_digest":hash,
        "bundle":null,"expected_target_digest":hash,
    }});
    let digest = plan::fingerprint(&document)?;
    let bytes = serde_json::to_vec(&document)?;
    let plan = Plan::parse(&bytes, &digest)?;
    assert!(Plan::parse(&bytes, &hash).is_err());
    let mut ambiguous = document.clone();
    ambiguous["project"] = Value::Null;
    assert!(
        Plan::parse(
            &serde_json::to_vec(&ambiguous)?,
            &plan::fingerprint(&ambiguous)?
        )
        .is_err()
    );

    assert!(journal::Journal::history(&state, &plan, &digest)?.is_none());
    assert_eq!(fs::read_dir(&state)?.count(), 0);
    assert!(
        apply::apply(&state, &bytes, &digest, None).is_err(),
        "an expired unadmitted intent was accepted"
    );
    assert_eq!(fs::read_dir(&state)?.count(), 0);
    assert!(cancel::cancel(&state, &bytes, &digest).is_err());
    assert_eq!(fs::read_dir(&state)?.count(), 0);
    let journal = journal::Journal::open(&state, &plan, &digest)?;
    journal.admit(&plan, &digest)?;
    assert_eq!(
        journal.read(&plan, &digest)?.ok_or("admission")?.state,
        "applying"
    );
    assert!(journal.admit(&plan, &digest).is_err());
    let mut foreign = document.clone();
    foreign["info_digest"] = crate::digest::sha256(b"another component").into();
    let foreign_digest = plan::fingerprint(&foreign)?;
    let foreign = Plan::parse(&serde_json::to_vec(&foreign)?, &foreign_digest)?;
    assert!(journal.read(&foreign, &foreign_digest).is_err());

    fs::remove_file(root.join("skills/owned.md"))?;
    fs::write(root.join("AGENTS.md"), section)?;
    fs::write(root.join("settings.json"), br#"{"user":9007199254740993}"#)?;
    effects::verify(&target, &plan.effects, true)?;
    fs::set_permissions(
        root.join("settings.json"),
        fs::Permissions::from_mode(0o600),
    )?;
    assert!(effects::verify(&target, &plan.effects, true).is_err());
    fs::set_permissions(
        root.join("settings.json"),
        fs::Permissions::from_mode(0o644),
    )?;
    let provider = json!({"state":"verified","operation":"remove","plan_digest":hash,
        "expected_target_digest":hash,"target_identity_digest":hash,"backup_ref":null,"setup_id":null});
    let result = outcome::build(&plan, &digest, &provider, &hash)?;
    journal.complete(&plan, &digest, &result)?;
    drop(journal);
    fs::remove_dir_all(&root)?;
    assert_eq!(
        apply::apply(
            &state,
            &bytes,
            &digest,
            Some(Path::new("/missing/old-bundle.zip"))
        )?,
        result
    );
    assert!(!root.exists());
    for admitted in [false, true] {
        let mut document = document.clone();
        let operation = format!("operation_{}", ulid::Ulid::generate());
        document["operation_id"] = json!(operation);
        document["provider_plan"]["plan"]["operation_id"] = json!(operation);
        document["provider_version"] = json!("0.0.92");
        document["provider_plan"]["plan"]["provider_version"] = json!("0.0.92");
        let digest = plan::fingerprint(&document)?;
        let bytes = serde_json::to_vec(&document)?;
        let plan = Plan::parse(&bytes, &digest)?;
        let journal = journal::Journal::open(&state, &plan, &digest)?;
        if admitted {
            journal.admit(&plan, &digest)?;
        }
        let provider = json!({"state":"cancelled", "operation_id":operation,
            "operation":"remove", "plan_digest":hash, "expected_target_digest":hash,
            "configuration_changed":false});
        let result = outcome::cancellation(&plan, &digest, &provider, &hash);
        let mut forged = result.clone();
        forged["provider_result"]["operation_id"] = json!("another-operation");
        assert!(journal.cancel(&plan, &digest, &forged).is_err());
        journal.cancel(&plan, &digest, &result)?;
        drop(journal);
        assert_eq!(apply::apply(&state, &bytes, &digest, None)?, result);
        assert_eq!(cancel::cancel(&state, &bytes, &digest)?, result);
        assert!(!root.exists());
    }
    super::project_tests::prove(&state, &plan)?;
    Ok(())
}
