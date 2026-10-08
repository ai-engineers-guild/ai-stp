#![cfg(unix)]

use ai_stp_cli_v2::{
    canonical,
    identity::{self, Storage},
};
use base64::{Engine, engine::general_purpose::STANDARD};
use ed25519_dalek::{Signature, VerifyingKey};
use serde_json::json;
use std::{error::Error, fs, os::unix::fs::PermissionsExt};
use zeroize::Zeroizing;

#[test]
fn offline_identity_is_exact_recoverable_and_never_replaces_a_lost_key()
-> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let parent = temporary.path();
    let at = "2026-10-08T00:00:00.000Z";
    let later = "2026-10-08T00:00:01.000Z";
    assert!(identity::current(parent)?.is_none());
    assert_eq!(fs::read_dir(parent)?.count(), 0);
    let plan = identity::plan(parent, Storage::File, at)?;
    let encoded = canonical::bytes(&serde_json::to_value(&plan)?)?;
    let plan: identity::Plan = serde_json::from_slice(&encoded)?;
    assert_eq!(fs::read_dir(parent)?.count(), 0);
    assert!(identity::apply(&plan, "wrong", later).is_err());
    assert!(identity::apply(&plan, &plan.digest()?, "2026-10-09T00:00:00.000Z").is_err());
    assert_eq!(fs::read_dir(parent)?.count(), 0);
    let identity = identity::apply(&plan, &plan.digest()?, later)?;
    let report = identity.report();
    assert_eq!(identity.context().account_id, plan.account_id);
    assert_eq!(identity.context().device_id, plan.device_id);
    assert_eq!(report["credential_store"], "file");
    let public: [u8; 32] = STANDARD
        .decode(report["public_key"].as_str().ok_or("public key missing")?)?
        .try_into()
        .map_err(|_| "public key size")?;
    let verifier = VerifyingKey::from_bytes(&public)?;
    let message = b"native identity ownership proof";
    let signature = identity.sign(message)?;
    verifier.verify_strict(message, &Signature::from_bytes(&signature))?;
    assert!(
        verifier
            .verify_strict(b"changed", &Signature::from_bytes(&signature))
            .is_err()
    );
    if let Some(destination) = std::env::var_os("AI_STP_IDENTITY_PROOF_DIR") {
        let destination = std::path::PathBuf::from(destination);
        fs::create_dir_all(&destination)?;
        fs::write(
            destination.join("public.json"),
            canonical::bytes(
                &json!({"report":report,"payload":STANDARD.encode(message),"signature":STANDARD.encode(signature)}),
            )?,
        )?;
    }
    let directory = parent.join("ai-stp-v2-identity");
    let secret_path = directory.join(format!("device-key.{}", plan.device_id));
    let public_path = directory.join("identity.json");
    let secret = Zeroizing::new(fs::read(&secret_path)?);
    assert_eq!(
        fs::metadata(&secret_path)?.permissions().mode() & 0o777,
        0o600
    );
    assert_eq!(
        fs::metadata(&directory)?.permissions().mode() & 0o777,
        0o700
    );
    assert!(!String::from_utf8(encoded)?.contains(std::str::from_utf8(&secret)?));
    let initial = fs::read(&public_path)?;
    assert!(!std::str::from_utf8(&initial)?.contains(std::str::from_utf8(&secret)?));
    assert_eq!(
        identity::apply(&plan, &plan.digest()?, "2026-10-09T00:00:00.000Z")?.report(),
        report
    );
    assert_eq!(
        identity::current(parent)?
            .ok_or("identity absent")?
            .sign(message)?,
        signature
    );
    assert!(identity::plan(parent, Storage::File, later).is_err());

    // Simulate interruption after durable key storage and before the public commit.
    fs::remove_file(&public_path)?;
    assert!(identity::current(parent)?.is_none());
    assert_eq!(
        identity::plan(parent, Storage::File, later)?.digest()?,
        plan.digest()?
    );
    assert!(identity::plan(parent, Storage::OsKeyring, later).is_err());
    assert_eq!(
        identity::apply(&plan, &plan.digest()?, "2026-10-09T00:00:00.000Z")?.report(),
        report
    );
    assert_eq!(fs::read(&public_path)?, initial);
    assert_eq!(fs::read(&secret_path)?.as_slice(), secret.as_slice());

    // Copying a public receipt and its key does not authorize another state root.
    let copied_parent = tempfile::tempdir()?;
    let copied = copied_parent.path().join("ai-stp-v2-identity");
    fs::create_dir(&copied)?;
    fs::set_permissions(&copied, fs::Permissions::from_mode(0o700))?;
    for entry in fs::read_dir(&directory)? {
        let entry = entry?;
        fs::copy(entry.path(), copied.join(entry.file_name()))?;
    }
    assert!(identity::current(copied_parent.path()).is_err());
    fs::remove_file(copied.join("identity.json"))?;
    assert!(identity::plan(copied_parent.path(), Storage::File, later).is_err());

    let pending_path = directory.join("pending.json");
    let pending = fs::read(&pending_path)?;
    fs::remove_file(&pending_path)?;
    assert!(identity::current(parent).is_err());
    fs::remove_file(&public_path)?;
    assert!(identity::current(parent).is_err());
    assert!(identity::plan(parent, Storage::File, later).is_err());
    assert!(identity::apply(&plan, &plan.digest()?, later).is_err());
    assert_eq!(fs::read(&secret_path)?.as_slice(), secret.as_slice());
    fs::write(&pending_path, pending)?;
    fs::write(&public_path, &initial)?;

    fs::remove_file(&secret_path)?;
    assert!(identity::current(parent).is_err());
    assert!(identity::apply(&plan, &plan.digest()?, later).is_err());
    assert!(!secret_path.exists());
    assert_eq!(fs::read(&public_path)?, initial);
    fs::write(&secret_path, secret.as_slice())?;
    fs::set_permissions(&secret_path, fs::Permissions::from_mode(0o600))?;
    fs::set_permissions(&secret_path, fs::Permissions::from_mode(0o644))?;
    assert!(identity::current(parent).is_err());
    fs::set_permissions(&secret_path, fs::Permissions::from_mode(0o600))?;
    let alias = parent.join("secret-alias");
    fs::hard_link(&secret_path, &alias)?;
    assert!(identity::current(parent).is_err());
    fs::remove_file(&alias)?;
    let other = tempfile::tempdir()?;
    let other_plan = identity::plan(other.path(), Storage::File, at)?;
    identity::apply(&other_plan, &other_plan.digest()?, later)?;
    let other_key = Zeroizing::new(fs::read(
        other
            .path()
            .join("ai-stp-v2-identity")
            .join(format!("device-key.{}", other_plan.device_id)),
    )?);
    fs::write(&secret_path, other_key.as_slice())?;
    assert!(identity::current(parent).is_err());
    assert!(identity::apply(&plan, &plan.digest()?, later).is_err());
    fs::write(&secret_path, secret.as_slice())?;
    assert_eq!(
        identity::current(parent)?
            .ok_or("identity absent")?
            .report(),
        report
    );
    let mut revoked = canonical::parse(&initial)?;
    revoked["device"]["state"] = "revoked".into();
    fs::write(&public_path, canonical::bytes(&revoked)?)?;
    assert!(identity::current(parent).is_err());
    assert!(identity::apply(&plan, &plan.digest()?, later).is_err());
    fs::write(&public_path, initial)?;
    let mut forged = plan.clone();
    forged.account_id = other_plan.account_id;
    assert!(identity::apply(&forged, &forged.digest()?, later).is_err());
    let stale_root = parent.join("new-root");
    fs::create_dir(&stale_root)?;
    let stale = identity::plan(&stale_root, Storage::File, at)?;
    fs::rename(&stale_root, parent.join("moved-root"))?;
    fs::create_dir(&stale_root)?;
    assert!(identity::apply(&stale, &stale.digest()?, later).is_err());
    assert_eq!(fs::read_dir(&stale_root)?.count(), 0);
    Ok(())
}
