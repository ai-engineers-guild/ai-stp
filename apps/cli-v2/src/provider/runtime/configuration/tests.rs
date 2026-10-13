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
    overlapping_admissions(&plan)?;
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

fn overlapping_admissions(template: &Plan) -> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir_in("/tmp")?;
    let state = temporary.path().join("state");
    let root = temporary.path().join("target");
    fs::create_dir(&state)?;
    fs::create_dir(&root)?;
    fs::create_dir(root.join("nested"))?;
    let make = |path: &Path| -> std::result::Result<(Plan, String), Box<dyn Error>> {
        let mut value = template.value()?;
        let operation = format!("operation_{}", ulid::Ulid::generate());
        value["operation_id"] = json!(operation);
        value["state_parent"] = json!(state);
        value["state_identity"] = json!(identity(&Target::open(&state)?)?);
        value["target_path"] = json!(path);
        value["target_identity"] = json!(identity(&Target::open(path)?)?);
        value["status_before"]["canonical_target"] = json!(path);
        value["provider_plan"]["plan"]["canonical_target"] = json!(path);
        value["provider_plan"]["plan"]["operation_id"] = json!(operation);
        value["provider_version"] = json!("0.0.93");
        value["provider_plan"]["plan"]["provider_version"] = json!("0.0.93");
        let digest = plan::fingerprint(&value)?;
        Ok((Plan::parse(&serde_json::to_vec(&value)?, &digest)?, digest))
    };
    let (parent, parent_digest) = make(&root)?;
    let (child, child_digest) = make(&root.join("nested"))?;
    let old_owner = b"ai-stp-cli-v2:configuration-operations/v1\n";
    let namespace =
        crate::files::OwnedDirectory::open(&state, "configuration-operations", old_owner, true)?
            .ok_or("old namespace")?;
    let key = crate::digest::sha256(
        format!(
            "{}:{}",
            parent.target_identity[0], parent.target_identity[1]
        )
        .as_bytes(),
    );
    let old_writer = crate::files::OwnedDirectory::open_at(
        &namespace.directory,
        &format!(
            "target-{}",
            key.strip_prefix("sha256:").ok_or("target key")?
        ),
        format!("ai-stp:configuration-target/v1\n{key}\n").as_bytes(),
        true,
    )?
    .ok_or("old writer")?;
    drop(namespace);
    // The old process holds a target but has not admitted a SQLite operation.
    // A migration based only on durable rows would incorrectly report idle.
    let refused = journal::Journal::open(&state, &parent, &parent_digest)
        .err()
        .ok_or("active old writer was ignored")?;
    assert!(matches!(refused.kind, crate::error::ErrorKind::Unavailable));
    assert_eq!(
        fs::read(state.join("configuration-operations/owner"))?,
        old_owner
    );
    assert!(journal::Journal::history(&state, &parent, &parent_digest)?.is_none());
    drop(old_writer);
    {
        use crate::{provider::configuration::record::Record, store::Store};
        let store = Store::open(&state, true)?;
        for (plan, digest) in [(&parent, &parent_digest), (&child, &child_digest)] {
            let detail = serde_json::to_string(&Record {
                schema_version: 1,
                plan_digest: digest.clone(),
                plan: plan.value()?,
                state: "applying".into(),
                result: None,
            })?;
            store.connection.execute(
                "INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?,?,?,?,?)",
                rusqlite::params![plan.operation_id, plan.action, "applying", plan.created_at, detail],
            )?;
        }
    }
    assert!(journal::Journal::open(&state, &parent, &parent_digest).is_err());
    assert_eq!(
        fs::read(state.join("configuration-operations/owner"))?,
        old_owner
    );
    let historical_root = temporary.path().join("historical");
    fs::create_dir(&historical_root)?;
    let (historical, historical_digest) = make(&historical_root)?;
    let hash = &historical.provider_plan["plan_digest"];
    let provider = json!({"state":"cancelled", "operation_id":historical.operation_id,
        "operation":"remove", "plan_digest":hash, "expected_target_digest":hash,
        "configuration_changed":false});
    let result = outcome::cancellation(
        &historical,
        &historical_digest,
        &provider,
        hash.as_str().ok_or("digest")?,
    );
    {
        let store = crate::store::Store::open(&state, false)?;
        let detail = serde_json::to_string(&crate::provider::configuration::record::Record {
            schema_version: 1,
            plan_digest: historical_digest.clone(),
            plan: historical.value()?,
            state: "cancelled".into(),
            result: Some(result.clone()),
        })?;
        store.connection.execute(
            "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,?,?,?,?)",
            rusqlite::params![historical.operation_id, historical.action, "cancelled", historical.created_at, historical.created_at, detail],
        )?;
    }
    fs::remove_dir(&historical_root)?;
    let bytes = serde_json::to_vec(&historical.value()?)?;
    assert_eq!(
        apply::apply(&state, &bytes, &historical_digest, None)?,
        result
    );
    assert_eq!(cancel::cancel(&state, &bytes, &historical_digest)?, result);
    assert_eq!(
        fs::read(state.join("configuration-operations/owner"))?,
        old_owner
    );
    // Remove only the generated legacy rows, as if the old writer had settled
    // them. The production transition must not fence that recovery path first.
    {
        let store = crate::store::Store::open(&state, false)?;
        assert_eq!(
            store
                .connection
                .query_row("SELECT count(*) FROM operation", [], |row| row
                    .get::<_, i64>(0))?,
            3
        );
        store.connection.execute("DELETE FROM operation", [])?;
    }
    let mut parent_journal = journal::Journal::open(&state, &parent, &parent_digest)?;
    let refused = journal::Journal::open(&state, &child, &child_digest)
        .err()
        .ok_or("unadmitted writer lost serialization")?;
    assert!(matches!(refused.kind, crate::error::ErrorKind::Unavailable));
    parent_journal.admit(&parent, &parent_digest)?;
    parent_journal.resume(&parent, &parent_digest)?;
    assert!(
        crate::files::OwnedDirectory::open(&state, "configuration-operations", old_owner, true)
            .is_err()
    );
    let child_journal = journal::Journal::open(&state, &child, &child_digest)?;
    assert!(
        child_journal.admit(&child, &child_digest).is_err(),
        "a second operation was admitted inside an unfinished configuration root"
    );
    assert!(child_journal.read(&child, &child_digest)?.is_none());
    drop(child_journal);
    // Once admission is durable, disjoint roots can proceed concurrently.
    let sibling_path = temporary.path().join("sibling");
    fs::create_dir(&sibling_path)?;
    let (sibling, sibling_digest) = make(&sibling_path)?;
    let mut sibling_journal = journal::Journal::open(&state, &sibling, &sibling_digest)?;
    sibling_journal.admit(&sibling, &sibling_digest)?;
    sibling_journal.resume(&sibling, &sibling_digest)?;
    drop(parent_journal);
    // Process exit drops locks, but cannot discard the unfinished reservation.
    let child_journal = journal::Journal::open(&state, &child, &child_digest)?;
    assert!(child_journal.admit(&child, &child_digest).is_err());
    drop(child_journal);
    let mut parent_journal = journal::Journal::open(&state, &parent, &parent_digest)?;
    parent_journal.resume(&parent, &parent_digest)?;
    let hash = &parent.provider_plan["plan_digest"];
    let provider = json!({"state":"cancelled", "operation_id":parent.operation_id,
        "operation":"remove", "plan_digest":hash, "expected_target_digest":hash,
        "configuration_changed":false});
    let cancelled = outcome::cancellation(
        &parent,
        &parent_digest,
        &provider,
        hash.as_str().ok_or("digest")?,
    );
    parent_journal.cancel(&parent, &parent_digest, &cancelled)?;
    drop(parent_journal);
    let mut child_journal = journal::Journal::open(&state, &child, &child_digest)?;
    child_journal.admit(&child, &child_digest)?;
    child_journal.resume(&child, &child_digest)?;
    let (ancestor, ancestor_digest) = make(&root)?;
    let ancestor_journal = journal::Journal::open(&state, &ancestor, &ancestor_digest)?;
    assert!(ancestor_journal.admit(&ancestor, &ancestor_digest).is_err());
    assert!(
        ancestor_journal
            .read(&ancestor, &ancestor_digest)?
            .is_none()
    );
    drop(ancestor_journal);
    // The retained terminal receipt is independent of another active root.
    assert_eq!(
        apply::apply(
            &state,
            &serde_json::to_vec(&parent.value()?)?,
            &parent_digest,
            None
        )?,
        cancelled
    );
    Ok(())
}
