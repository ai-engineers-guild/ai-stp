//! Read the previous engine's explicitly selected credentials without discovery.

use cap_fs_ext::{DirExt, MetadataExt};
use cap_std::fs::Dir;
use std::{collections::BTreeMap, io::Read, path::Path};
use zeroize::{Zeroize, Zeroizing};

#[cfg(not(target_os = "linux"))]
use super::credentials::unavailable;
use super::{Storage, invalid};
use crate::{error::Result, files, passport};

/// No Debug or Serialize implementation: legacy credential values stay private.
pub(crate) struct Document(BTreeMap<String, String>);
impl std::ops::Deref for Document {
    type Target = BTreeMap<String, String>;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}
impl std::ops::DerefMut for Document {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.0
    }
}
impl Drop for Document {
    fn drop(&mut self) {
        for value in self.0.values_mut() {
            value.zeroize();
        }
    }
}

impl<'de> serde::Deserialize<'de> for Document {
    fn deserialize<D: serde::Deserializer<'de>>(
        deserializer: D,
    ) -> std::result::Result<Self, D::Error> {
        struct Unique;
        impl<'de> serde::de::Visitor<'de> for Unique {
            type Value = Document;
            fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                formatter.write_str("a credential object with unique string fields")
            }
            fn visit_map<M: serde::de::MapAccess<'de>>(
                self,
                mut map: M,
            ) -> std::result::Result<Document, M::Error> {
                let mut value = Document(BTreeMap::new());
                while let Some(key) = map.next_key::<String>()? {
                    if value.contains_key(&key) {
                        return Err(serde::de::Error::custom("duplicate credential field"));
                    }
                    value.insert(key, map.next_value()?);
                }
                Ok(value)
            }
        }
        deserializer.deserialize_map(Unique)
    }
}

fn name(id: &str) -> Result<()> {
    if !matches!(id, "cloud-credentials" | "pending-authorization")
        && !id
            .strip_prefix("device-key.")
            .is_some_and(|id| passport::stable_id(id, "device"))
    {
        return Err(invalid());
    }
    Ok(())
}

fn file(parent: &Dir, id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    let directory = match parent.open_dir_nofollow("secrets") {
        Ok(directory) => directory,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(invalid()),
    };
    #[cfg(unix)]
    if cap_std::fs::MetadataExt::mode(&directory.dir_metadata().map_err(|_| invalid())?) & 0o077
        != 0
    {
        return Err(invalid());
    }
    let path = format!("{id}.secret");
    let file = match files::open_regular(&directory, Path::new(&path)) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(invalid()),
    };
    let meta = file.metadata().map_err(|_| invalid())?;
    if meta.nlink() != 1 || meta.len() > 65536 {
        return Err(invalid());
    }
    #[cfg(unix)]
    if cap_std::fs::MetadataExt::mode(&meta) & 0o077 != 0 {
        return Err(invalid());
    }
    let mut bytes = Zeroizing::new(Vec::new());
    file.take(65537)
        .read_to_end(&mut bytes)
        .map_err(|_| invalid())?;
    if bytes.len() > 65536 {
        return Err(invalid());
    }
    Ok(Some(bytes))
}

#[cfg(target_os = "macos")]
fn native(id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    use keyring_core::api::CredentialStoreApi;
    let _access = super::credentials::KEYCHAIN_ACCESS
        .lock()
        .map_err(|_| unavailable())?;
    let _interaction = super::credentials::no_interaction()?;
    let entry = apple_native_keyring_store::keychain::Store::new()
        .and_then(|store| store.build("ai-stp", id, None))
        .map_err(|_| unavailable())?;
    match entry.get_password() {
        Ok(value) => Ok(Some(Zeroizing::new(value.into_bytes()))),
        Err(keyring_core::Error::NoEntry) => Ok(None),
        Err(_) => Err(unavailable()),
    }
}

#[cfg(windows)]
fn native(id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    use keyring_core::api::CredentialStoreApi;
    // Python keyring first uses the service slot, moving colliding users to
    // username@service. Require the actual username before accepting either.
    let compound = format!("{id}@ai-stp");
    for target in ["ai-stp", compound.as_str()] {
        let entry = windows_native_keyring_store::Store::new()
            .and_then(|store| {
                store.build(
                    "ai-stp",
                    id,
                    Some(&std::collections::HashMap::from([("target", target)])),
                )
            })
            .map_err(|_| unavailable())?;
        let attributes = match entry.get_attributes() {
            Ok(value) => value,
            Err(keyring_core::Error::NoEntry) => continue,
            Err(_) => return Err(unavailable()),
        };
        if attributes.get("username").map(String::as_str) != Some(id) {
            continue;
        }
        let bytes = Zeroizing::new(entry.get_secret().map_err(|_| unavailable())?);
        if bytes.len() > 65536 || bytes.len() % 2 != 0 {
            return Err(invalid());
        }
        let units = Zeroizing::new(
            bytes
                .chunks_exact(2)
                .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
                .collect::<Vec<_>>(),
        );
        let text = Zeroizing::new(String::from_utf16(&units).map_err(|_| invalid())?);
        return Ok(Some(Zeroizing::new(text.as_bytes().to_vec())));
    }
    Ok(None)
}

#[cfg(target_os = "linux")]
fn native(id: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    super::secret_service::read_legacy(id)
}

#[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
fn native(_: &str) -> Result<Option<Zeroizing<Vec<u8>>>> {
    Err(unavailable())
}

pub(crate) fn read(parent: &Dir, storage: Storage, id: &str) -> Result<Option<Document>> {
    name(id)?;
    storage.validate()?;
    let bytes = match storage {
        Storage::File => file(parent, id)?,
        Storage::OsKeyring => {
            if file(parent, id)?.is_some() {
                return Err(invalid());
            }
            native(id)?
        }
    };
    let Some(bytes) = bytes else {
        return Ok(None);
    };
    if bytes.len() > 65536 {
        return Err(invalid());
    }
    serde_json::from_slice(&bytes)
        .map(Some)
        .map_err(|_| invalid())
}

pub(crate) fn retire(parent: &Dir, storage: Storage, id: &str, expected: &Document) -> Result<()> {
    let Some(current) = read(parent, storage, id)? else {
        return Ok(());
    };
    if current.0 != expected.0 {
        return Err(invalid());
    }
    match storage {
        Storage::File => {
            let directory = parent.open_dir_nofollow("secrets").map_err(|_| invalid())?;
            directory
                .remove_file(format!("{id}.secret"))
                .map_err(|_| invalid())?;
            #[cfg(unix)]
            directory
                .open(".")
                .map_err(|_| invalid())?
                .sync_all()
                .map_err(|_| invalid())?;
        }
        Storage::OsKeyring => remove_native(id)?,
    }
    if read(parent, storage, id)?.is_some() {
        return Err(invalid());
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn remove_native(id: &str) -> Result<()> {
    super::secret_service::remove_legacy(id)
}

#[cfg(target_os = "macos")]
fn remove_native(id: &str) -> Result<()> {
    use keyring_core::api::CredentialStoreApi;
    let _access = super::credentials::KEYCHAIN_ACCESS
        .lock()
        .map_err(|_| unavailable())?;
    let _interaction = super::credentials::no_interaction()?;
    let entry = apple_native_keyring_store::keychain::Store::new()
        .and_then(|store| store.build("ai-stp", id, None))
        .map_err(|_| unavailable())?;
    match entry.delete_credential() {
        Ok(()) | Err(keyring_core::Error::NoEntry) => Ok(()),
        Err(_) => Err(unavailable()),
    }
}

#[cfg(windows)]
fn remove_native(id: &str) -> Result<()> {
    use keyring_core::api::CredentialStoreApi;
    let compound = format!("{id}@ai-stp");
    for target in ["ai-stp", compound.as_str()] {
        let entry = windows_native_keyring_store::Store::new()
            .and_then(|store| {
                store.build(
                    "ai-stp",
                    id,
                    Some(&std::collections::HashMap::from([("target", target)])),
                )
            })
            .map_err(|_| unavailable())?;
        let attributes = match entry.get_attributes() {
            Ok(attributes) => attributes,
            Err(keyring_core::Error::NoEntry) => continue,
            Err(_) => return Err(unavailable()),
        };
        if attributes.get("username").map(String::as_str) == Some(id) {
            return entry.delete_credential().map_err(|_| unavailable());
        }
    }
    Ok(())
}

#[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
fn remove_native(_: &str) -> Result<()> {
    Err(unavailable())
}
