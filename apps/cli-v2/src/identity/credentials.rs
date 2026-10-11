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

pub(super) fn unavailable() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the selected operating system credential store is unavailable; unlock it in its owning session",
    )
}

#[cfg(any(target_os = "macos", windows))]
fn native_entry(id: &str) -> Result<keyring_core::Entry> {
    let name = format!("device-key.{id}");
    #[cfg(target_os = "macos")]
    let entry = apple_native_keyring_store::keychain::Store::new()
        .and_then(|store| store.build("ai-stp-v2", &name, None));
    #[cfg(windows)]
    let entry = windows_native_keyring_store::Store::new().and_then(|store| {
        store.build(
            "ai-stp-v2",
            &name,
            Some(&std::collections::HashMap::from([("persistence", "Local")])),
        )
    });
    entry.map_err(|_| unavailable())
}

#[cfg(target_os = "macos")]
static KEYCHAIN_ACCESS: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn native_read(id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    #[cfg(target_os = "linux")]
    return super::secret_service::read(id);
    #[cfg(any(target_os = "macos", windows))]
    {
        #[cfg(target_os = "macos")]
        let _access = KEYCHAIN_ACCESS.lock().map_err(|_| unavailable())?;
        #[cfg(target_os = "macos")]
        let _interaction = no_interaction()?;
        match native_entry(id)?.get_password() {
            Ok(value) => Ok(Some(Zeroizing::new(value.into_bytes()))),
            Err(keyring_core::Error::NoEntry) => Ok(None),
            Err(_) => Err(unavailable()),
        }
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    {
        let _ = id;
        Err(unavailable())
    }
}

fn native_create(id: &str, value: &str) -> Result<()> {
    #[cfg(target_os = "linux")]
    return super::secret_service::create(id, value);
    #[cfg(any(target_os = "macos", windows))]
    {
        #[cfg(target_os = "macos")]
        let _access = KEYCHAIN_ACCESS.lock().map_err(|_| unavailable())?;
        #[cfg(target_os = "macos")]
        let _interaction = no_interaction()?;
        native_entry(id)?
            .set_password(value)
            .map_err(|_| unavailable())
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    {
        let _ = (id, value);
        Err(unavailable())
    }
}

#[cfg(target_os = "macos")]
fn no_interaction()
-> Result<Option<security_framework::os::macos::keychain::KeychainUserInteractionLock>> {
    use security_framework::os::macos::keychain::SecKeychain;
    // Preserve an embedding caller's already-disabled setting. Our own keychain
    // operations serialize the process-wide switch and restore it on every exit.
    if SecKeychain::user_interaction_allowed().map_err(|_| unavailable())? {
        Ok(Some(
            SecKeychain::disable_user_interaction().map_err(|_| unavailable())?,
        ))
    } else {
        Ok(None)
    }
}

pub(super) struct Credentials<'a> {
    directory: &'a OwnedDirectory,
    storage: Storage,
}

impl<'a> Credentials<'a> {
    pub fn new(directory: &'a OwnedDirectory, storage: Storage) -> Result<Self> {
        storage.validate()?;
        Ok(Self { directory, storage })
    }

    pub fn read(&self, id: &str) -> Result<Option<SigningKey>> {
        let encoded = match self.storage {
            Storage::File => {
                let name = format!("device-key.{id}");
                let file = match crate::files::open_regular(
                    &self.directory.directory,
                    std::path::Path::new(&name),
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
                file.take(65)
                    .read_to_end(&mut bytes)
                    .map_err(|_| super::invalid())?;
                Some(bytes)
            }
            Storage::OsKeyring => native_read(id)?,
        };
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

    pub fn create(&self, id: &str, key: &SigningKey) -> Result<()> {
        if self.read(id)?.is_some() {
            return Err(super::invalid());
        }
        let encoded = Zeroizing::new(STANDARD.encode(key.as_bytes()));
        match self.storage {
            Storage::File => self
                .directory
                .atomic(&format!("device-key.{id}"), encoded.as_bytes())?,
            Storage::OsKeyring => native_create(id, &encoded)?,
        }
        let held = self.read(id)?.ok_or_else(super::invalid)?;
        if held.verifying_key() != key.verifying_key() {
            return Err(super::invalid());
        }
        Ok(())
    }
}
