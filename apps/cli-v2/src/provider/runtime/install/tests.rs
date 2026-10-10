use super::*;
use std::{
    error::Error,
    fs,
    os::unix::fs::{PermissionsExt, symlink},
};

fn encoded(value: &Value) -> Result<(Vec<u8>, String)> {
    let bytes = serde_json_canonicalizer::to_vec(value).map_err(|_| invalid())?;
    let digest = crate::digest::bytes("ai-stp:installation-operation:v1", &bytes)?;
    Ok((bytes, digest))
}

#[test]
fn original_installation_survives_publication_retries_and_never_recreates_removed_content()
-> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir_in("/tmp")?;
    let state = temporary.path().join("state");
    let target = temporary.path().join("target");
    let prefix = temporary.path().join("program-e\u{301}");
    fs::create_dir(&state)?;
    fs::create_dir(&target)?;
    let created = Timestamp::now();
    let expires = created.checked_add(std::time::Duration::from_secs(900))?;
    let hash = crate::digest::sha256(b"fixture-only component identity");
    let operation = format!("operation_{}", ulid::Ulid::generate());
    let document = json!({
        "schema_version":1,"action":"program.install","operation_id":operation,
        "created_at":format!("{created:.3}"),"expires_at":format!("{expires:.3}"),
        "state_parent":state,"state_parent_identity":identity(&Target::open(&state)?)?,
        "harness_id":"codex","provider_version":"0.0.89",
        "target":{"path":target,"scope":"global","identity":identity(&Target::open(&target)?)?},
        "prefix":{"path":prefix,"expected_state":"missing","parent_identity":identity(&Target::open(temporary.path())?)?},
        "component":{"archive_digest":hash,"executable_digest":hash,"info_digest":hash},
        "provider_plan":{"plan":{"operation":"software_install","operation_id":operation,
            "expires_at":format!("{expires:.3}"),"canonical_target":target,"software_prefix":prefix,
            "provider_version":"0.0.89","provider_release_digest":hash,"software_version":"2.0",
            "software_artifacts":[{"entry_point":"bin/program"}]},"plan_digest":hash}
    });
    let (bytes, digest) = encoded(&document)?;
    let plan = Plan::parse(&bytes, &digest)?;
    assert_eq!(plan.prefix.path, prefix.to_string_lossy());
    assert!(Plan::parse(&bytes, &hash).is_err());
    assert!(Journal::history(&state, &plan, &digest)?.is_none());
    assert_eq!(fs::read_dir(&state)?.count(), 0);
    let journal = Journal::open(&state, &plan, &digest)?;
    let mut record = Record {
        schema_version: 1,
        plan_digest: digest.clone(),
        plan: document.clone(),
        phase: Phase::Prepared,
        stage_parent: None,
        stage_root: None,
        result: None,
    };
    journal.write(None, &record)?;
    let mut stage = Stage::open(&plan, &mut record)?;
    let stage_path = stage.root.path().to_path_buf();
    let expected_root = identity(&stage.root)?;
    record.phase = Phase::Staged;
    journal.write(Some(Phase::Prepared), &record)?;

    // A small raw vendor fixture exercises independent content/mode/membership
    // verification. It is not a provider identity or release-attestation proof.
    let source = temporary.path().join("vendor");
    fs::write(&source, b"vendor executable bytes")?;
    let mut archive = fs::File::open(&source)?;
    for name in ["2.0", "bin", ".nddev-software"] {
        fs::create_dir(stage_path.join(name))?;
        fs::set_permissions(stage_path.join(name), fs::Permissions::from_mode(0o755))?;
    }
    let installed = stage_path.join("2.0/program");
    fs::copy(&source, &installed)?;
    fs::set_permissions(&installed, fs::Permissions::from_mode(0o755))?;
    let entry = stage_path.join("bin/program");
    symlink(prefix.join("2.0/program"), &entry)?;
    let marker = stage_path.join("bin/.program.version");
    fs::write(&marker, b"2.0")?;
    fs::set_permissions(&marker, fs::Permissions::from_mode(0o600))?;
    let manifest = stage_path.join("bin/.program.manifest.json");
    fs::write(
        &manifest,
        serde_json::to_vec(
            &json!({"schema_version":1,"version":"2.0","executable":"2.0/program","executable_sha256":crate::digest::sha256(&fs::read(&source)?)}),
        )?,
    )?;
    fs::set_permissions(&manifest, fs::Permissions::from_mode(0o600))?;
    let verify = |file: &mut fs::File| {
        verify::payload(
            &stage.root.directory()?,
            file,
            "2.0",
            "bin/program",
            &prefix,
        )
    };
    let verified = verify(&mut archive)?;
    fs::write(&installed, b"changed executable bytes")?;
    assert!(verify(&mut archive).is_err());
    fs::copy(&source, &installed)?;
    fs::set_permissions(&installed, fs::Permissions::from_mode(0o644))?;
    assert!(verify(&mut archive).is_err());
    fs::set_permissions(&installed, fs::Permissions::from_mode(0o755))?;
    fs::create_dir(stage_path.join("2.0/extra"))?;
    assert!(verify(&mut archive).is_err());
    fs::remove_dir(stage_path.join("2.0/extra"))?;
    fs::hard_link(&installed, temporary.path().join("linked"))?;
    assert!(verify(&mut archive).is_err());
    fs::remove_file(temporary.path().join("linked"))?;
    fs::remove_file(&entry)?;
    symlink("../../vendor", &entry)?;
    assert!(verify(&mut archive).is_err());
    fs::remove_file(&entry)?;
    symlink(prefix.join("2.0/program"), &entry)?;
    assert_eq!(verified, verify(&mut archive)?);

    let result = json!({"operation_id":operation,"plan_digest":digest,"state":"verified",
        "harness_id":"codex","provider_version":"0.0.89","prefix":prefix,
        "installation_performed":true,"verification":verified,
        "provider_result":{"state":"verified","recovered":[],"operation":"software_install",
            "command":"program","version":"2.0","entry_point":"bin/program",
            "executable":prefix.join("bin/program"),"files":1,"plan_digest":hash}});
    record.result = Some(result.clone());
    record.phase = Phase::Publishing;
    journal.write(Some(Phase::Staged), &record)?;
    fs::create_dir(&prefix)?;
    fs::write(prefix.join("foreign"), b"retained")?;
    assert!(stage.activate().is_err());
    assert_eq!(fs::read(prefix.join("foreign"))?, b"retained");
    assert_eq!(identity(&stage.root)?, expected_root);
    fs::remove_file(prefix.join("foreign"))?;
    fs::remove_dir(&prefix)?;
    stage.activate()?;
    assert_eq!(identity(&stage.root)?, expected_root);
    drop(stage);
    drop(journal);
    assert!(cancellation::cancel(&state, &bytes, &digest).is_err());
    let journal = Journal::open(&state, &plan, &digest)?;
    // The durable publishing phase recognizes the same root after its move.
    let mut stage = Stage::open(&plan, &mut record)?;
    assert_eq!(identity(&stage.root)?, expected_root);
    assert_eq!(
        verified,
        verify::payload(
            &stage.root.directory()?,
            &mut archive,
            "2.0",
            "bin/program",
            &prefix
        )?
    );
    stage.activate()?;
    stage.cleanup(&record)?;
    drop(stage);
    // Interruption after removing the private parent also remains resumable.
    let mut stage = Stage::open(&plan, &mut record)?;
    stage.activate()?;
    stage.cleanup(&record)?;
    record.phase = Phase::Complete;
    journal.write(Some(Phase::Publishing), &record)?;
    drop(stage);
    drop(journal);
    fs::remove_dir_all(&prefix)?;
    fs::remove_dir(&target)?;
    fs::remove_file(&source)?;
    assert_eq!(apply(&state, &bytes, &digest)?, result);
    assert!(!prefix.exists());
    for (field, changed) in [
        (
            "operation_id",
            json!("operation_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
        ),
        ("prefix", json!("/another-program")),
        ("installation_performed", json!(false)),
        ("verification", json!({"files":1})),
        ("unexpected", json!(true)),
    ] {
        let mut corrupt = record.clone();
        corrupt.result.as_mut().ok_or_else(invalid)?[field] = changed;
        let mut store = crate::store::Store::open(&state, false)?;
        store.transaction(|tx| {
            tx.execute(
                "UPDATE operation SET detail=? WHERE operation_id=?",
                rusqlite::params![
                    serde_json::to_string(&corrupt).map_err(|_| invalid())?,
                    operation
                ],
            )
            .map_err(crate::store::database)?;
            Ok(())
        })?;
        drop(store);
        assert!(apply(&state, &bytes, &digest).is_err());
    }
    let mut store = crate::store::Store::open(&state, false)?;
    store.transaction(|tx| {
        tx.execute(
            "UPDATE operation SET detail=? WHERE operation_id=?",
            rusqlite::params![
                serde_json::to_string(&record).map_err(|_| invalid())?,
                operation
            ],
        )
        .map_err(crate::store::database)?;
        Ok(())
    })?;
    drop(store);
    assert_eq!(apply(&state, &bytes, &digest)?, result);
    let mut changed = document.clone();
    changed["component"]["info_digest"] = crate::digest::sha256(b"another exact intent").into();
    let (changed, changed_digest) = encoded(&changed)?;
    assert!(apply(&state, &changed, &changed_digest).is_err());
    cancelled_stage_keeps_foreign_paths(&state, temporary.path(), document)?;
    let store = crate::store::Store::open(&state, false)?;
    assert_eq!(
        store
            .connection
            .query_row("PRAGMA integrity_check", [], |row| row.get::<_, String>(0))?,
        "ok"
    );
    assert_eq!(
        store.connection.query_row(
            "SELECT count(*) FROM operation_event WHERE operation_id=?",
            [operation],
            |row| row.get::<_, i64>(0)
        )?,
        4
    );
    Ok(())
}

fn cancelled_stage_keeps_foreign_paths(
    state: &Path,
    root: &Path,
    mut document: Value,
) -> Result<()> {
    let operation = format!("operation_{}", ulid::Ulid::generate());
    let prefix = root.join("cancelled-program");
    document["operation_id"] = operation.clone().into();
    document["provider_plan"]["plan"]["operation_id"] = operation.into();
    document["prefix"]["path"] = prefix.to_str().ok_or_else(invalid)?.into();
    document["provider_plan"]["plan"]["software_prefix"] = document["prefix"]["path"].clone();
    let (bytes, digest) = encoded(&document)?;
    let plan = Plan::parse(&bytes, &digest)?;
    let journal = Journal::open(state, &plan, &digest)?;
    let mut record = Record {
        schema_version: 1,
        plan_digest: digest.clone(),
        plan: document,
        phase: Phase::Prepared,
        stage_parent: None,
        stage_root: None,
        result: None,
    };
    journal.write(None, &record)?;
    let stage = Stage::open(&plan, &mut record)?;
    let path = stage.root.path().to_owned();
    record.phase = Phase::Staged;
    journal.write(Some(Phase::Prepared), &record)?;
    let io = |_| invalid();
    let outside = root.join("retained-canary");
    fs::write(&outside, b"retained").map_err(io)?;
    fs::write(path.join("partial"), b"generated partial payload").map_err(io)?;
    symlink(&outside, path.join("external-link")).map_err(io)?;
    fs::create_dir(&prefix).map_err(io)?;
    fs::write(prefix.join("foreign"), b"preserved").map_err(io)?;
    drop(stage);
    stage::prepare_cancellation(&plan, &mut record)?;
    record.phase = Phase::Cancelling;
    journal.write(Some(Phase::Staged), &record)?;
    // Exercise retry after partial discard; the final foreign root is never
    // touched, and a symbolic link in generated contents is never followed.
    fs::remove_file(path.join("partial")).map_err(io)?;
    drop(journal);
    let result = apply(state, &bytes, &digest)?;
    assert_eq!(result["state"], "cancelled");
    assert_eq!(fs::read(&outside).map_err(io)?, b"retained");
    assert_eq!(fs::read(prefix.join("foreign")).map_err(io)?, b"preserved");
    assert!(!path.parent().ok_or_else(invalid)?.exists());
    assert_eq!(cancellation::cancel(state, &bytes, &digest)?, result);
    assert_eq!(apply(state, &bytes, &digest)?, result);
    Ok(())
}
