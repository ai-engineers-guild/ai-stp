//! Real vault, schema-epoch and durable-authorization replay boundaries.

use super::*;
use crate::account::enrollment_recovery as recovery;

struct Fixture {
    root: tempfile::TempDir,
    at: String,
    account: String,
    connection: connections::Plan,
    retained: Plan,
    identity: Value,
}

fn authorized() -> std::result::Result<Fixture, Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = after(&format!("{:.3}", jiff::Timestamp::now()), 60)?;
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let local = identity::apply(&init, &init.digest()?, &at)?;
    let identity = local.report();
    let connection = connections::plan(
        root.path(),
        "Original",
        "https://recovery.example.test",
        "github",
        &at,
    )?;
    connections::apply(&connection, &connection.digest()?, &at)?;
    let account = format!("account_{}", ulid::Ulid::generate());
    let start = plan_for_connection(
        root.path(),
        Action::Start,
        None,
        None,
        Some(&connection.connection_id),
        &at,
    )?;
    let state = State {
        revision: start.operation_id.clone(),
        plan: start.clone(),
        session: Session::Authorized {
            account_id: account.clone(),
            access_token: model::Secret(Zeroizing::new(generated())),
            refresh_token: model::Secret(Zeroizing::new(generated())),
            expires_at: after(&at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.clone(),
    };
    {
        let journal = Journal::for_connection(&local, state.plan.connection.as_ref(), true)?
            .ok_or("journal")?;
        journal.write(&state)?;
        journal.complete(&state)?;
    }
    Ok(Fixture {
        root,
        at,
        account,
        connection,
        retained: start,
        identity,
    })
}

fn revoked() -> std::result::Result<Fixture, Box<dyn Error>> {
    let mut fixture = authorized()?;
    let local = identity_at(fixture.root.path())?;
    let at = after(&fixture.at, 1)?;
    let revoked = plan_for_connection(
        fixture.root.path(),
        Action::Refresh,
        None,
        None,
        Some(&fixture.connection.connection_id),
        &at,
    )?;
    let closed = State {
        revision: revoked.operation_id.clone(),
        plan: revoked.clone(),
        session: Session::Closed {
            reason: "device_revoked".into(),
        },
        outcome: Outcome::Revoked,
        completed_at: at.clone(),
    };
    {
        let journal = Journal::for_connection(&local, closed.plan.connection.as_ref(), false)?
            .ok_or("journal")?;
        journal.write(&closed)?;
        journal.complete(&closed)?;
    }
    fixture.at = at;
    fixture.retained = revoked;
    Ok(fixture)
}

#[test]
fn replacement_keeps_native_identity_old_receipts_and_frozen_profile_plans()
-> std::result::Result<(), Box<dyn Error>> {
    let f = revoked()?;
    let original_receipt = connections::apply(&f.connection, &f.connection.digest()?, &f.at)?;
    let offline = contexts::create_plan(f.root.path(), "Personal", None, None, &f.at)?;
    contexts::apply(&offline, &offline.digest()?, &f.at)?;
    let contexts_before = contexts::list(f.root.path())?;
    let old_plan = connections::plan(
        f.root.path(),
        "Frozen",
        "https://other.example.test",
        "github",
        &f.at,
    )?;
    let old_digest = old_plan.digest()?;
    let recovery = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    let alternative = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Alternative",
        &f.at,
    )?;
    let old_start = plan_for_connection(
        f.root.path(),
        Action::Start,
        None,
        None,
        Some(&f.connection.connection_id),
        &f.at,
    )?;
    assert!(
        connections::apply(
            &recovery.replacement,
            &recovery.replacement.digest()?,
            &f.at
        )
        .is_err()
    );
    assert!(recovery::apply(&recovery, "sha256:wrong", &f.at).is_err());
    assert!(recovery::apply(&recovery, &recovery.digest()?, &recovery.expires_at).is_err());
    let applied = recovery::apply(&recovery, &recovery.digest()?, &f.at)?;
    assert_eq!(applied["state"], "sign_in_required");
    assert!(
        connections::apply(
            &alternative.replacement,
            &alternative.replacement.digest()?,
            &f.at
        )
        .is_err()
    );
    assert!(apply(&old_start, &old_start.digest()?, &f.at).is_err());
    let local = identity_at(f.root.path())?;
    assert!(
        crate::files::OwnedDirectory::open_compatible(
            local.root_directory(),
            &format!("ai-stp-v2-account-{}", f.connection.connection_id),
            b"ai-stp-cli-v2 isolated account sessions v1\n",
            &[b"ai-stp-cli-v2 isolated account sessions v2\n"],
            false
        )
        .is_err()
    );
    assert_eq!(
        recovery::apply(&recovery, &recovery.digest()?, &recovery.expires_at)?,
        applied
    );
    assert_eq!(identity_at(f.root.path())?.report(), f.identity);
    assert_eq!(
        connections::apply(&f.connection, &f.connection.digest()?, &f.at)?,
        original_receipt
    );
    assert_eq!(contexts::list(f.root.path())?, contexts_before);
    assert_eq!(
        contexts::apply(&offline, &offline.digest()?, &f.at)?["context_id"],
        contexts_before["contexts"][0]["context"]["context_id"]
    );
    assert_eq!(old_plan.digest()?, old_digest);
    assert!(connections::apply(&old_plan, &old_digest, &f.at).is_err());
    assert!(
        plan_for_connection(
            f.root.path(),
            Action::Start,
            None,
            None,
            Some(&f.connection.connection_id),
            &f.at
        )
        .is_err()
    );
    assert_eq!(
        apply(&f.retained, &f.retained.digest()?, &f.at)?["outcome"],
        "revoked"
    );
    let id = identity_at(f.root.path())?;
    let previous = connections::enrollment(&id, &f.connection.connection_id)?;
    previous.verify_key(&id)?;
    let replacement = connections::enrollment(&id, &recovery.replacement.connection_id)?;
    assert_ne!(previous.public_key, replacement.public_key);
    let start = plan_for_connection(
        f.root.path(),
        Action::Start,
        None,
        None,
        Some(&replacement.connection_id),
        &f.at,
    )?;
    assert_eq!(
        start.expected_account_id.as_deref(),
        Some(f.account.as_str())
    );
    assert_eq!(
        start.revoked_public_key.as_deref(),
        Some(previous.public_key.as_str())
    );
    let mut crossed = start.clone();
    crossed.expected_account_id = Some(format!("account_{}", ulid::Ulid::generate()));
    assert!(apply(&crossed, &crossed.digest()?, &f.at).is_err());
    crossed.expected_account_id = None;
    crossed.revoked_public_key = None;
    assert!(apply(&crossed, &crossed.digest()?, &f.at).is_err());
    let fresh = connections::plan(
        f.root.path(),
        "Another",
        "https://other.example.test",
        "github",
        &f.at,
    )?;
    assert_eq!(fresh.registry_schema_before, 56);
    assert_eq!(fresh.registry_schema_after, 56);
    assert_eq!(
        connections::apply(&fresh, &fresh.digest()?, &f.at)?["registry_schema_version"],
        56
    );
    let context = contexts::create_plan(f.root.path(), "After recovery", None, None, &f.at)?;
    assert_eq!(context.registry_schema_after, 56);
    contexts::apply(&context, &context.digest()?, &f.at)?;
    Ok(())
}

#[test]
fn missing_old_key_does_not_replace_native_identity_or_require_its_signature()
-> std::result::Result<(), Box<dyn Error>> {
    let f = revoked()?;
    let local = identity_at(f.root.path())?;
    {
        let directory = crate::files::OwnedDirectory::open_at(
            local.root_directory(),
            connections::NAMESPACE,
            connections::OWNER,
            false,
        )?
        .ok_or("credentials")?;
        identity::credentials::Vault::new(&directory, identity::Storage::File)?
            .retire(&format!("device-key.{}", f.connection.device_id))?;
    }
    let plan = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    assert_eq!(
        recovery::apply(&plan, &plan.digest()?, &f.at)?["state"],
        "sign_in_required"
    );
    assert_eq!(identity_at(f.root.path())?.report(), f.identity);
    assert!(
        connections::enrollment(&local, &f.connection.connection_id)?
            .verify_key(&local)
            .is_err()
    );
    Ok(())
}

#[test]
fn foreign_account_evidence_refuses_before_admission_and_snapshot_reads_schema56()
-> std::result::Result<(), Box<dyn Error>> {
    let f = revoked()?;
    let plan = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    let mut crossed = plan.clone();
    crossed.account_id = format!("account_{}", ulid::Ulid::generate());
    assert!(recovery::apply(&crossed, &crossed.digest()?, &f.at).is_err());
    assert!(
        recovery::list(f.root.path())?["recoveries"]
            .as_array()
            .ok_or("recoveries")?
            .is_empty()
    );
    recovery::apply(&plan, &plan.digest()?, &f.at)?;
    // Inspect only this disposable fixture; no user registry is exported.
    let path = f.root.path().join("ai-stp-v2-state/registry.sqlite3");
    let connection = rusqlite::Connection::open(&path)?;
    connection.pragma_update(None, "journal_mode", "DELETE")?;
    drop(connection);
    let bytes = fs::read(path)?;
    let snapshot = crate::snapshot::Snapshot::from_bytes(&bytes, &crate::digest::sha256(&bytes))?;
    assert_eq!(snapshot.report()["local_schema_version"], 56);
    assert_eq!(snapshot.report()["read_only"], true);
    Ok(())
}

#[test]
fn production_registry_keeps_its_original_filename_and_marker_after_recovery()
-> std::result::Result<(), Box<dyn Error>> {
    let f = revoked()?;
    fs::set_permissions(f.root.path(), fs::Permissions::from_mode(0o700))?;
    let directory = f.root.path().join("ai-stp-v2-state");
    let old = directory.join("registry.sqlite3");
    let connection = rusqlite::Connection::open(&old)?;
    connection.pragma_update(None, "journal_mode", "DELETE")?;
    drop(connection);
    fs::rename(old, f.root.path().join("registry.sqlite"))?;
    let marker = b"ai-stp native production registry v1\n";
    fs::write(directory.join("owner"), marker)?;
    let plan = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    recovery::apply(&plan, &plan.digest()?, &f.at)?;
    assert!(!directory.join("registry.sqlite3").exists());
    assert!(f.root.path().join("registry.sqlite").exists());
    assert_eq!(fs::read(directory.join("owner"))?, marker);
    assert_eq!(identity_at(f.root.path())?.report(), f.identity);
    Ok(())
}

#[test]
fn missing_key_preparation_preserves_authorized_history_and_rechecks_absence_before_admission()
-> std::result::Result<(), Box<dyn Error>> {
    let f = authorized()?;
    assert!(
        recovery::plan(
            f.root.path(),
            &f.connection.connection_id,
            "Replacement",
            &f.at
        )
        .is_err()
    );
    let local = identity_at(f.root.path())?;
    let enrollment = connections::enrollment(&local, &f.connection.connection_id)?;
    let key = {
        let directory = crate::files::OwnedDirectory::open_at(
            local.root_directory(),
            connections::NAMESPACE,
            connections::OWNER,
            false,
        )?
        .ok_or("credentials")?;
        let vault = identity::credentials::Vault::new(&directory, identity::Storage::File)?;
        let key = vault.read_key(&f.connection.device_id)?.ok_or("old key")?;
        vault.retire(&format!("device-key.{}", f.connection.device_id))?;
        key
    };
    let original = status_for_connection(f.root.path(), Some(&f.connection.connection_id), &f.at)?;
    let plan = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    assert_eq!(plan.schema_version, 2);
    assert!(plan.revoked_receipt_digest.is_none());
    assert!(plan.missing_key.is_some());
    let value = serde_json::to_value(&plan)?;
    assert!(value.get("revoked_receipt_digest").is_none());
    {
        let directory = crate::files::OwnedDirectory::open_at(
            local.root_directory(),
            connections::NAMESPACE,
            connections::OWNER,
            false,
        )?
        .ok_or("credentials")?;
        identity::credentials::Vault::new(&directory, identity::Storage::File)?
            .create_key(&f.connection.device_id, &key)?;
    }
    assert!(recovery::apply(&plan, &plan.digest()?, &f.at).is_err());
    assert!(
        recovery::list(f.root.path())?["recoveries"]
            .as_array()
            .ok_or("recoveries")?
            .is_empty()
    );
    {
        let directory = crate::files::OwnedDirectory::open_at(
            local.root_directory(),
            connections::NAMESPACE,
            connections::OWNER,
            false,
        )?
        .ok_or("credentials")?;
        identity::credentials::Vault::new(&directory, identity::Storage::File)?
            .retire(&format!("device-key.{}", f.connection.device_id))?;
    }
    let result = recovery::apply(&plan, &plan.digest()?, &f.at)?;
    assert_eq!(result["state"], "sign_in_required");
    assert_eq!(result["preparation_reason"], "missing_enrollment_key");
    assert_eq!(
        result["server_preconditions"],
        json!(["same_account", "revoked_previous_key", "distinct_new_key"])
    );
    assert_eq!(
        status_for_connection(f.root.path(), Some(&f.connection.connection_id), &f.at)?,
        original
    );
    {
        let directory = crate::files::OwnedDirectory::open_at(
            local.root_directory(),
            connections::NAMESPACE,
            connections::OWNER,
            false,
        )?
        .ok_or("credentials")?;
        identity::credentials::Vault::new(&directory, identity::Storage::File)?
            .create_key(&f.connection.device_id, &key)?;
    }
    assert_eq!(
        recovery::apply(&plan, &plan.digest()?, &plan.expires_at)?,
        result
    );
    enrollment.verify_key(&local)?;
    assert!(
        plan_for_connection(
            f.root.path(),
            Action::Refresh,
            None,
            None,
            Some(&f.connection.connection_id),
            &f.at
        )
        .is_err()
    );
    assert_eq!(identity_at(f.root.path())?.report(), f.identity);
    Ok(())
}

#[test]
fn version_one_recovery_serialization_remains_canonical_without_missing_key_fields()
-> std::result::Result<(), Box<dyn Error>> {
    let f = revoked()?;
    let plan = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    let value = serde_json::to_value(&plan)?;
    assert_eq!(value["schema_version"], 1);
    assert!(value["revoked_receipt_digest"].is_string());
    assert!(value.get("missing_key").is_none());
    let digest = crate::digest::canonical("ai-stp:plan:v1", &value)?;
    let decoded: recovery::Plan = serde_json::from_value(value)?;
    assert_eq!(decoded.digest()?, digest);
    recovery::apply(&decoded, &digest, &f.at)?;
    assert_eq!(
        recovery::list(f.root.path())?["recoveries"][0]["plan_digest"],
        digest
    );
    Ok(())
}

#[test]
fn child_key_write_failure_keeps_atomic_parent_and_child_admission_for_expired_replay()
-> std::result::Result<(), Box<dyn Error>> {
    let f = revoked()?;
    let plan = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    let path = f.root.path().join(connections::NAMESPACE);
    fs::set_permissions(&path, fs::Permissions::from_mode(0o500))?;
    let result = recovery::apply(&plan, &plan.digest()?, &f.at);
    fs::set_permissions(&path, fs::Permissions::from_mode(0o700))?;
    assert!(result.is_err());
    let pending = recovery::list(f.root.path())?;
    assert_eq!(pending["recoveries"][0]["state"], "creating_key");
    assert_eq!(pending["recoveries"][0]["plan_digest"], plan.digest()?);
    assert_eq!(
        recovery::apply(&plan, &plan.digest()?, &plan.expires_at)?["state"],
        "sign_in_required"
    );
    assert!(
        recovery::plan(
            f.root.path(),
            &f.connection.connection_id,
            "Other replacement",
            &f.at
        )
        .is_err()
    );
    assert_eq!(identity_at(f.root.path())?.report(), f.identity);
    Ok(())
}

#[test]
fn durable_authorized_receipt_finishes_recovery_after_a_crash_before_confirmation()
-> std::result::Result<(), Box<dyn Error>> {
    let f = revoked()?;
    let recovery = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    recovery::apply(&recovery, &recovery.digest()?, &f.at)?;
    let connection = &recovery.replacement.connection_id;
    let start = plan_for_connection(
        f.root.path(),
        Action::Start,
        None,
        None,
        Some(connection),
        &f.at,
    )?;
    let local = identity_at(f.root.path())?;
    {
        let journal =
            Journal::for_connection(&local, start.connection.as_ref(), true)?.ok_or("journal")?;
        let state = State {
            revision: start.operation_id.clone(),
            plan: start,
            session: Session::Pending {
                device_code: model::Secret(Zeroizing::new(generated())),
                user_code: "ABCD-1234".into(),
                verification_uri: "https://recovery.example.test/en/device-login".into(),
                verification_uri_complete:
                    "https://recovery.example.test/en/device-login?user_code=ABCD-1234".into(),
                expires_at: after(&f.at, 600)?,
                interval: 1,
                next_poll_at: after(&f.at, 1)?,
            },
            outcome: Outcome::Pending,
            completed_at: f.at.clone(),
        };
        journal.write(&state)?;
        journal.complete(&state)?;
    }
    let later = after(&f.at, 2)?;
    let poll = plan_for_connection(
        f.root.path(),
        Action::Poll,
        None,
        None,
        Some(connection),
        &later,
    )?;
    let receipt = {
        let journal =
            Journal::for_connection(&local, poll.connection.as_ref(), false)?.ok_or("journal")?;
        let state = State {
            revision: poll.operation_id.clone(),
            plan: poll.clone(),
            session: Session::Authorized {
                account_id: f.account.clone(),
                access_token: model::Secret(Zeroizing::new(generated())),
                refresh_token: model::Secret(Zeroizing::new(generated())),
                expires_at: after(&later, 3600)?,
            },
            outcome: Outcome::Authorized,
            completed_at: later.clone(),
        };
        journal.write(&state)?;
        journal.complete(&state)?
    };
    assert_eq!(
        recovery::list(f.root.path())?["recoveries"][0]["state"],
        "sign_in_required"
    );
    assert_eq!(apply(&poll, &poll.digest()?, &later)?, receipt.public());
    let done = recovery::list(f.root.path())?;
    assert_eq!(done["recoveries"][0]["state"], "authorized");
    assert_eq!(done["recoveries"][0]["confirmation"], receipt.public());
    assert_eq!(
        apply(&poll, &poll.digest()?, &poll.expires_at)?,
        receipt.public()
    );
    assert_eq!(recovery::list(f.root.path())?, done);
    assert_eq!(identity_at(f.root.path())?.report(), f.identity);
    Ok(())
}

#[test]
fn enrollment_recovery_preserves_the_stronger_windows_record_writer_fence()
-> std::result::Result<(), Box<dyn Error>> {
    let f = revoked()?;
    let local = identity_at(f.root.path())?;
    let namespace = format!("ai-stp-v2-account-{}", f.connection.connection_id);
    {
        let directory = crate::files::OwnedDirectory::open_compatible(
            local.root_directory(),
            &namespace,
            b"ai-stp-cli-v2 isolated account sessions v1\n",
            &[b"ai-stp-cli-v2 isolated account sessions v2\n"],
            false,
        )?
        .ok_or("journal")?;
        directory.atomic("owner", identity::credentials::WINDOWS_ACCOUNT_OWNER)?;
    }
    let plan = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    recovery::apply(&plan, &plan.digest()?, &f.at)?;
    assert_eq!(
        fs::read(f.root.path().join(&namespace).join("owner"))?,
        identity::credentials::WINDOWS_ACCOUNT_OWNER
    );
    assert!(
        crate::files::OwnedDirectory::open_compatible(
            local.root_directory(),
            &namespace,
            b"ai-stp-cli-v2 isolated account sessions v1\n",
            &[
                b"ai-stp-cli-v2 isolated account sessions v2\n",
                b"ai-stp-cli-v2 isolated enrollment recovery v1\n"
            ],
            false
        )
        .is_err()
    );
    Ok(())
}

#[test]
fn child_key_write_failure_keeps_atomic_parent_and_child_admission_for_expired_replay()
-> std::result::Result<(), Box<dyn Error>> {
    let f = revoked()?;
    let plan = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    let path = f.root.path().join(connections::NAMESPACE);
    fs::set_permissions(&path, fs::Permissions::from_mode(0o500))?;
    let result = recovery::apply(&plan, &plan.digest()?, &f.at);
    fs::set_permissions(&path, fs::Permissions::from_mode(0o700))?;
    assert!(result.is_err());
    let pending = recovery::list(f.root.path())?;
    assert_eq!(pending["recoveries"][0]["state"], "creating_key");
    assert_eq!(pending["recoveries"][0]["plan_digest"], plan.digest()?);
    assert_eq!(
        recovery::apply(&plan, &plan.digest()?, &plan.expires_at)?["state"],
        "sign_in_required"
    );
    assert!(
        recovery::plan(
            f.root.path(),
            &f.connection.connection_id,
            "Other replacement",
            &f.at
        )
        .is_err()
    );
    assert_eq!(identity_at(f.root.path())?.report(), f.identity);
    Ok(())
}

#[test]
fn durable_authorized_receipt_finishes_recovery_after_a_crash_before_confirmation()
-> std::result::Result<(), Box<dyn Error>> {
    let f = revoked()?;
    let recovery = recovery::plan(
        f.root.path(),
        &f.connection.connection_id,
        "Replacement",
        &f.at,
    )?;
    recovery::apply(&recovery, &recovery.digest()?, &f.at)?;
    let connection = &recovery.replacement.connection_id;
    let start = plan_for_connection(
        f.root.path(),
        Action::Start,
        None,
        None,
        Some(connection),
        &f.at,
    )?;
    let local = identity_at(f.root.path())?;
    {
        let journal =
            Journal::for_connection(&local, start.connection.as_ref(), true)?.ok_or("journal")?;
        let state = State {
            revision: start.operation_id.clone(),
            plan: start,
            session: Session::Pending {
                device_code: model::Secret(Zeroizing::new(generated())),
                user_code: "ABCD-1234".into(),
                verification_uri: "https://recovery.example.test/en/device-login".into(),
                verification_uri_complete:
                    "https://recovery.example.test/en/device-login?user_code=ABCD-1234".into(),
                expires_at: after(&f.at, 600)?,
                interval: 1,
                next_poll_at: after(&f.at, 1)?,
            },
            outcome: Outcome::Pending,
            completed_at: f.at.clone(),
        };
        journal.write(&state)?;
        journal.complete(&state)?;
    }
    let later = after(&f.at, 2)?;
    let poll = plan_for_connection(
        f.root.path(),
        Action::Poll,
        None,
        None,
        Some(connection),
        &later,
    )?;
    let receipt = {
        let journal =
            Journal::for_connection(&local, poll.connection.as_ref(), false)?.ok_or("journal")?;
        let state = State {
            revision: poll.operation_id.clone(),
            plan: poll.clone(),
            session: Session::Authorized {
                account_id: f.account.clone(),
                access_token: model::Secret(Zeroizing::new(generated())),
                refresh_token: model::Secret(Zeroizing::new(generated())),
                expires_at: after(&later, 3600)?,
            },
            outcome: Outcome::Authorized,
            completed_at: later.clone(),
        };
        journal.write(&state)?;
        journal.complete(&state)?
    };
    assert_eq!(
        recovery::list(f.root.path())?["recoveries"][0]["state"],
        "sign_in_required"
    );
    assert_eq!(apply(&poll, &poll.digest()?, &later)?, receipt.public());
    let done = recovery::list(f.root.path())?;
    assert_eq!(done["recoveries"][0]["state"], "authorized");
    assert_eq!(done["recoveries"][0]["confirmation"], receipt.public());
    assert_eq!(
        apply(&poll, &poll.digest()?, &poll.expires_at)?,
        receipt.public()
    );
    assert_eq!(recovery::list(f.root.path())?, done);
    assert_eq!(identity_at(f.root.path())?.report(), f.identity);
    Ok(())
}
