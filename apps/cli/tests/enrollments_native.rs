#![cfg(any(target_os = "macos", windows))]

//! Native credential-store proof, using only previously absent random test slots.

use ai_stp_cli::{account::connections, identity};
use keyring_core::api::CredentialStoreApi;
use std::error::Error;

#[path = "enrollments_native/recovery.rs"]
mod recovery;

struct TemporaryCredential(keyring_core::Entry);
impl Drop for TemporaryCredential {
    fn drop(&mut self) {
        let _ = self.0.delete_credential();
    }
}

fn owned_slot(name: &str) -> Result<TemporaryCredential, Box<dyn Error>> {
    #[cfg(target_os = "macos")]
    let entry =
        apple_native_keyring_store::keychain::Store::new()?.build("ai-stp-v2", name, None)?;
    #[cfg(windows)]
    let entry = windows_native_keyring_store::Store::new()?.build(
        "ai-stp-v2",
        name,
        Some(&std::collections::HashMap::from([("persistence", "Local")])),
    )?;
    if !matches!(entry.get_password(), Err(keyring_core::Error::NoEntry)) {
        return Err("random test slot was not absent".into());
    }
    Ok(TemporaryCredential(entry))
}

#[test]
fn native_connections_keep_independent_keys_and_never_recreate_a_missing_ready_key()
-> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::OsKeyring, &at)?;
    let _local_slot = owned_slot(&format!("device-key.{}", init.device_id))?;
    let local = identity::apply(&init, &init.digest()?, &at)?;
    let original = local.report();
    let first = connections::plan(
        root.path(),
        "Personal",
        "https://same-origin.example.test",
        "github",
        &at,
    )?;
    let first_slot = owned_slot(&format!("device-key.{}", first.device_id))?;
    let created = connections::apply(&first, &first.digest()?, &at)?;
    let second = connections::plan(
        root.path(),
        "Corporate",
        "https://same-origin.example.test",
        "keycloak",
        &at,
    )?;
    let _second_slot = owned_slot(&format!("device-key.{}", second.device_id))?;
    let another = connections::apply(&second, &second.digest()?, &at)?;
    assert_ne!(
        created["connection"]["public_key"],
        another["connection"]["public_key"]
    );
    assert_ne!(created["connection"]["public_key"], original["public_key"]);
    assert_eq!(
        created,
        connections::apply(&first, &first.digest()?, &first.expires_at)?
    );
    assert_eq!(
        identity::current(root.path())?.ok_or("identity")?.report(),
        original
    );
    assert_eq!(
        std::fs::read_dir(root.path().join("ai-stp-v2-connections"))?.count(),
        2
    );
    first_slot.0.delete_credential()?;
    assert!(connections::apply(&first, &first.digest()?, &at).is_err());
    assert!(matches!(
        first_slot.0.get_password(),
        Err(keyring_core::Error::NoEntry)
    ));
    assert_eq!(
        another,
        connections::apply(&second, &second.digest()?, &at)?
    );
    Ok(())
}
