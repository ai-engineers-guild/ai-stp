#![cfg(windows)]

use ai_stp_cli_v2::{canonical, identity, invoke};
use base64::{Engine, engine::general_purpose::STANDARD};
use ed25519_dalek::{Signature, VerifyingKey};
use keyring_core::api::CredentialStoreApi;
use serde_json::Value;
use std::{error::Error, ffi::OsString, fs};

struct TemporaryCredential(keyring_core::Entry);
impl Drop for TemporaryCredential {
    fn drop(&mut self) {
        let _ = self.0.delete_credential();
    }
}

fn run(args: &[&str]) -> ai_stp_cli_v2::error::Result<Value> {
    invoke(
        std::iter::once("ai-stp-v2")
            .chain(args.iter().copied())
            .chain(["--json"])
            .map(OsString::from),
    )
    .result
}

#[test]
fn windows_cli_identity_uses_the_real_local_credential_store() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary
        .path()
        .to_str()
        .ok_or("proof path must be Unicode")?;
    let planned = run(&[
        "device",
        "initialize",
        "plan",
        "--state-dir",
        root,
        "--credential-store",
        "os_keyring",
    ])?;
    let device = planned["plan"]["device_id"]
        .as_str()
        .ok_or("device absent")?;
    let entry = windows_native_keyring_store::Store::new()?.build(
        "ai-stp-v2",
        &format!("device-key.{device}"),
        None,
    )?;
    assert!(matches!(
        entry.get_password(),
        Err(keyring_core::Error::NoEntry)
    ));
    // This exact random test entry was absent. Clean only that entry on every exit.
    let credential = TemporaryCredential(entry);
    let path = temporary.path().join("plan.json");
    fs::write(&path, canonical::bytes(&planned["plan"])?)?;
    let args = [
        "device",
        "initialize",
        "apply",
        "--plan",
        path.to_str().ok_or("plan path")?,
        "--plan-digest",
        planned["plan_digest"].as_str().ok_or("digest absent")?,
    ];
    let report = run(&args)?;
    assert_eq!(report["credential_store"], "os_keyring");
    assert_eq!(run(&args)?, report);
    assert_eq!(run(&["device", "show", "--state-dir", root])?, report);
    let signer = identity::current(temporary.path())?.ok_or("identity absent")?;
    let public: [u8; 32] = STANDARD
        .decode(report["public_key"].as_str().ok_or("public key absent")?)?
        .try_into()
        .map_err(|_| "public key size")?;
    let message = b"Windows native identity ownership proof";
    VerifyingKey::from_bytes(&public)?
        .verify_strict(message, &Signature::from_bytes(&signer.sign(message)?))?;
    let owned = temporary.path().join("ai-stp-v2-identity");
    assert_eq!(fs::read_dir(&owned)?.count(), 4);
    assert!(!owned.join(format!("device-key.{device}")).exists());
    credential.0.delete_credential()?;
    assert!(matches!(
        credential.0.get_password(),
        Err(keyring_core::Error::NoEntry)
    ));
    assert!(run(&args).is_err());
    assert!(matches!(
        credential.0.get_password(),
        Err(keyring_core::Error::NoEntry)
    ));
    Ok(())
}
