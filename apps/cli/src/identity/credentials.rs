//! Explicit credential ownership. No backend discovery, migration or fallback.

use base64::{Engine, engine::general_purpose::STANDARD};
use ed25519_dalek::SigningKey;
#[cfg(any(target_os = "macos", windows))]
use keyring_core::api::CredentialStoreApi;
use std::io::Read;
use zeroize::Zeroizing;

use super::Storage;
use crate::{
    error::{ErrorKind, Failure, Result},
    files::OwnedDirectory,
};

pub(crate) const WINDOWS_ACCOUNT_OWNER: &[u8] =
    b"ai-stp-cli-v2 isolated Windows account records v1\n";

#[cfg(target_os = "macos")]
mod macos;

#[cfg(any(test, windows))]
#[path = "credentials/windows_record.rs"]
mod windows_record;

pub(super) fn unavailable() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the selected operating system credential store is unavailable; unlock it in its owning session",
    )
}

#[cfg(any(target_os = "macos", windows))]
fn native_entry(name: &str) -> Result<keyring_core::Entry> {
    #[cfg(target_os = "macos")]
    let entry = apple_native_keyring_store::keychain::Store::new()
        .and_then(|store| store.build("ai-stp-v2", name, None));
    #[cfg(windows)]
    let entry = windows_native_keyring_store::Store::new().and_then(|store| {
        store.build(
            "ai-stp-v2",
            name,
            Some(&std::collections::HashMap::from([("persistence", "Local")])),
        )
    });
    #[cfg(target_os = "macos")]
    {
        entry.map_err(|error| macos::keyring("entry", &error))
    }
    #[cfg(windows)]
    {
        entry.map_err(|_| unavailable())
    }
}

#[cfg(target_os = "macos")]
pub(super) static KEYCHAIN_ACCESS: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn native_read(id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    #[cfg(target_os = "linux")]
    return super::secret_service::read(id);
    #[cfg(target_os = "macos")]
    {
        #[cfg(target_os = "macos")]
        let _access = KEYCHAIN_ACCESS.lock().map_err(|_| unavailable())?;
        #[cfg(target_os = "macos")]
        let _interaction = no_interaction()?;
        match native_entry(id)?.get_password() {
            Ok(value) => Ok(Some(Zeroizing::new(value.into_bytes()))),
            Err(keyring_core::Error::NoEntry) => Ok(None),
            Err(error) => Err(macos::keyring("read", &error)),
        }
    }
    #[cfg(windows)]
    {
        let entry = native_entry(id)?;
        let bytes = match entry.get_secret() {
            Ok(value) => Zeroizing::new(value),
            Err(keyring_core::Error::NoEntry) => return Ok(None),
            Err(_) => return Err(unavailable()),
        };
        if windows_record::recognizes(&bytes) {
            return windows_record::decode(&bytes).map(Some);
        }
        // Existing password entries retain the store's UTF-16 decoding.
        entry
            .get_password()
            .map(|value| Some(Zeroizing::new(value.into_bytes())))
            .map_err(|_| unavailable())
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    {
        let _ = id;
        Err(unavailable())
    }
}

fn native_write(id: &str, value: &str, replace: bool) -> Result<()> {
    #[cfg(any(target_os = "macos", windows))]
    let _ = replace;
    #[cfg(target_os = "linux")]
    return super::secret_service::write(id, value, replace);
    #[cfg(target_os = "macos")]
    {
        #[cfg(target_os = "macos")]
        let _access = KEYCHAIN_ACCESS.lock().map_err(|_| unavailable())?;
        #[cfg(target_os = "macos")]
        let _interaction = no_interaction()?;
        native_entry(id)?
            .set_password(value)
            .map_err(|error| macos::keyring("write", &error))
    }
    #[cfg(windows)]
    {
        let entry = native_entry(id)?;
        if id.starts_with("account-") {
            let bytes = windows_record::encode(value.as_bytes())?;
            entry.set_secret(&bytes).map_err(|_| unavailable())
        } else {
            entry.set_password(value).map_err(|_| unavailable())
        }
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    {
        let _ = (id, value, replace);
        Err(unavailable())
    }
}

fn native_remove(id: &str) -> Result<()> {
    #[cfg(target_os = "linux")]
    return super::secret_service::remove(id);
    #[cfg(any(target_os = "macos", windows))]
    {
        #[cfg(target_os = "macos")]
        let _access = KEYCHAIN_ACCESS.lock().map_err(|_| unavailable())?;
        #[cfg(target_os = "macos")]
        let _interaction = no_interaction()?;
        match native_entry(id)?.delete_credential() {
            Ok(()) | Err(keyring_core::Error::NoEntry) => Ok(()),
            Err(error) => {
                #[cfg(target_os = "macos")]
                {
                    Err(macos::keyring("remove", &error))
                }
                #[cfg(windows)]
                {
                    let _ = error;
                    Err(unavailable())
                }
            }
        }
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    {
        let _ = id;
        Err(unavailable())
    }
}

#[cfg(target_os = "macos")]
pub(super) fn no_interaction()
-> Result<Option<security_framework::os::macos::keychain::KeychainUserInteractionLock>> {
    use security_framework::os::macos::keychain::SecKeychain;
    // Preserve an embedding caller's already-disabled setting. Our own keychain
    // operations serialize the process-wide switch and restore it on every exit.
    if SecKeychain::user_interaction_allowed()
        .map_err(|error| macos::status("interaction_allowed", &error))?
    {
        Ok(Some(SecKeychain::disable_user_interaction().map_err(
            |error| macos::status("disable_interaction", &error),
        )?))
    } else {
        Ok(None)
    }
}

pub(crate) struct Vault<'a> {
    directory: &'a OwnedDirectory,
    storage: Storage,
}

impl<'a> Vault<'a> {
    pub fn new(directory: &'a OwnedDirectory, storage: Storage) -> Result<Self> {
        storage.validate()?;
        Ok(Self { directory, storage })
    }

    pub fn read(&self, name: &str, max: usize) -> Result<Option<Zeroizing<Vec<u8>>>> {
        if name.is_empty()
            || name.len() > 256
            || !name
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
            || max > 64 * 1024
        {
            return Err(super::invalid());
        }
        let value = match self.storage {
            Storage::File => {
                let file = match crate::files::open_regular(
                    &self.directory.directory,
                    std::path::Path::new(name),
                ) {
                    Ok(file) => {
                        let meta = file.metadata().map_err(|_| super::invalid())?;
                        if !meta.is_file() || cap_fs_ext::MetadataExt::nlink(&meta) != 1 {
                            return Err(super::invalid());
                        }
                        #[cfg(unix)]
                        {
                            use cap_std::fs::PermissionsExt;
                            if meta.permissions().mode() & 0o077 != 0 {
                                return Err(super::invalid());
                            }
                        }
                        file
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
                    Err(_) => return Err(super::invalid()),
                };
                let mut bytes = Zeroizing::new(Vec::new());
                file.take(max as u64 + 1)
                    .read_to_end(&mut bytes)
                    .map_err(|_| super::invalid())?;
                Some(bytes)
            }
            Storage::OsKeyring => native_read(name)?,
        };
        if value.as_ref().is_some_and(|bytes| bytes.len() > max) {
            return Err(super::invalid());
        }
        Ok(value)
    }

    pub fn read_key(&self, id: &str) -> Result<Option<SigningKey>> {
        let encoded = self.read(&format!("device-key.{id}"), 64)?;
        let Some(encoded) = encoded else {
            return Ok(None);
        };
        if encoded.len() != 44 {
            return Err(super::invalid());
        }
        let mut seed = Zeroizing::new([0u8; 32]);
        if STANDARD
            .decode_slice(encoded.as_slice(), seed.as_mut())
            .map_err(|_| super::invalid())?
            != 32
        {
            return Err(super::invalid());
        }
        Ok(Some(SigningKey::from_bytes(&seed)))
    }

    /// Only an admitted replacement retires these exact owned credential slots.
    pub fn retire(&self, name: &str) -> Result<()> {
        let id = name
            .strip_prefix("device-key.")
            .or_else(|| name.strip_prefix("account-"))
            .ok_or_else(super::invalid)?;
        if !crate::passport::stable_id(id, "device") {
            return Err(super::invalid());
        }
        if self.read(name, 64 * 1024)?.is_none() {
            return Ok(());
        }
        match self.storage {
            Storage::File => {
                self.directory
                    .directory
                    .remove_file(name)
                    .map_err(|_| super::invalid())?;
                self.directory.sync()?;
            }
            Storage::OsKeyring => native_remove(name)?,
        }
        if self.read(name, 64 * 1024)?.is_some() {
            return Err(super::invalid());
        }
        Ok(())
    }

    pub fn create_key(&self, id: &str, key: &SigningKey) -> Result<()> {
        if self.read_key(id)?.is_some() {
            return Err(super::invalid());
        }
        let encoded = Zeroizing::new(STANDARD.encode(key.as_bytes()));
        match self.storage {
            Storage::File => self
                .directory
                .atomic(&format!("device-key.{id}"), encoded.as_bytes())?,
            Storage::OsKeyring => native_write(&format!("device-key.{id}"), &encoded, false)?,
        }
        let held = self.read_key(id)?.ok_or_else(super::invalid)?;
        if held.verifying_key() != key.verifying_key() {
            return Err(super::invalid());
        }
        Ok(())
    }
    pub fn write_account(&self, name: &str, value: &str) -> Result<()> {
        if !name.starts_with("account-") || value.is_empty() || value.len() > 64 * 1024 {
            return Err(super::invalid());
        }
        let previous = self.read(name, 64 * 1024)?;
        match self.storage {
            Storage::File => self.directory.atomic(name, value.as_bytes())?,
            Storage::OsKeyring => native_write(name, value, previous.is_some())?,
        }
        if self.read(name, 64 * 1024)?.as_deref().map(Vec::as_slice) != Some(value.as_bytes()) {
            return Err(super::invalid());
        }
        Ok(())
    }
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;

    #[test]
    fn retirement_removes_only_the_exact_native_credential()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        struct Cleanup(Vec<String>);
        impl Drop for Cleanup {
            fn drop(&mut self) {
                for name in &self.0 {
                    let _ = native_remove(name);
                }
            }
        }
        let root = tempfile::tempdir()?;
        let directory = OwnedDirectory::open(
            root.path(),
            "credentials",
            b"native credential proof\n",
            true,
        )?
        .ok_or("directory")?;
        let vault = Vault::new(&directory, Storage::OsKeyring)?;
        let old = format!("device_{}", ulid::Ulid::generate());
        let new = format!("device_{}", ulid::Ulid::generate());
        let names = [
            format!("device-key.{old}"),
            format!("account-{old}"),
            format!("device-key.{new}"),
        ];
        for name in &names {
            assert!(vault.read(name, 65536)?.is_none());
        }
        let _cleanup = Cleanup(names.to_vec());
        native_entry(&names[1])?.set_password("legacy-account-state")?;
        assert!(
            vault.read(&names[1], 65536)?.as_deref().map(Vec::as_slice)
                == Some(b"legacy-account-state".as_slice())
        );
        let replacement = super::super::generate()?;
        vault.create_key(&old, &super::super::generate()?)?;
        vault.write_account(&names[1], "disposable-account-state")?;
        vault.create_key(&new, &replacement)?;
        for name in &names[..2] {
            vault.retire(name)?;
            vault.retire(name)?;
            assert!(vault.read(name, 65536)?.is_none());
        }
        assert!(
            vault.read_key(&new)?.ok_or("replacement")?.verifying_key()
                == replacement.verifying_key()
        );
        Ok(())
    }
}
