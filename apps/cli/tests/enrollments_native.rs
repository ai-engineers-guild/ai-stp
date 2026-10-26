#![cfg(any(target_os = "linux", target_os = "macos", windows))]

//! Native credential-store proof, using only previously absent random test slots.

use ai_stp_cli::{account::connections, identity};
#[cfg(any(target_os = "macos", windows))]
use keyring_core::api::CredentialStoreApi;
use std::error::Error;

#[path = "enrollments_native/recovery.rs"]
mod recovery;
#[cfg(target_os = "linux")]
#[path = "enrollments_native/secret_service.rs"]
mod secret_service;

struct TemporaryCredential {
    #[cfg(any(target_os = "macos", windows))]
    entry: keyring_core::Entry,
    #[cfg(target_os = "linux")]
    name: String,
}

impl TemporaryCredential {
    fn bytes(&self) -> Result<Option<Vec<u8>>, Box<dyn Error>> {
        #[cfg(target_os = "linux")]
        return secret_service::read(&self.name);
        #[cfg(any(target_os = "macos", windows))]
        match self.entry.get_secret() {
            Ok(bytes) => Ok(Some(bytes)),
            Err(keyring_core::Error::NoEntry) => Ok(None),
            Err(error) => Err(error.into()),
        }
    }
    fn secret(&self) -> Result<Vec<u8>, Box<dyn Error>> {
        self.bytes()?
            .ok_or_else(|| "owned credential is absent".into())
    }
    fn password(&self) -> Result<String, Box<dyn Error>> {
        #[cfg(target_os = "linux")]
        return Ok(String::from_utf8(self.secret()?)?);
        #[cfg(any(target_os = "macos", windows))]
        Ok(self.entry.get_password()?)
    }
    fn remove(&self) -> Result<(), Box<dyn Error>> {
        #[cfg(target_os = "linux")]
        return secret_service::remove(&self.name);
        #[cfg(any(target_os = "macos", windows))]
        match self.entry.delete_credential() {
            Ok(()) | Err(keyring_core::Error::NoEntry) => Ok(()),
            Err(error) => Err(error.into()),
        }
    }
}

impl Drop for TemporaryCredential {
    fn drop(&mut self) {
        let _ = self.remove();
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
    #[cfg(any(target_os = "macos", windows))]
    let absent = match entry.get_secret() {
        Ok(_) => false,
        Err(keyring_core::Error::NoEntry) => true,
        Err(error) => return Err(error.into()),
    };
    #[cfg(target_os = "linux")]
    let absent = secret_service::read(name)?.is_none();
    if !absent {
        return Err("random test slot was not absent".into());
    }
    Ok(TemporaryCredential {
        #[cfg(any(target_os = "macos", windows))]
        entry,
        #[cfg(target_os = "linux")]
        name: name.into(),
    })
}

#[test]
#[cfg_attr(
    target_os = "linux",
    ignore = "requires the isolated CI Secret Service bus"
)]
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
    first_slot.remove()?;
    assert!(connections::apply(&first, &first.digest()?, &at).is_err());
    assert!(first_slot.bytes()?.is_none());
    assert_eq!(
        another,
        connections::apply(&second, &second.digest()?, &at)?
    );
    Ok(())
}
