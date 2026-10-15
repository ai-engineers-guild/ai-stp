//! Exact existing owner/device adoption; no key generation or owner rewriting.

use base64::Engine;
use cap_std::fs::Dir;
use ed25519_dalek::SigningKey;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{collections::BTreeSet, path::Path};
use zeroize::Zeroizing;

use super::{Identity, Record, Storage, Vault, invalid};
use crate::{authoring, canonical, digest, error::Result, files, passport};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Plan {
    pub identity: super::Plan,
    pub public_key: String,
    pub retired: Vec<String>,
    pub owner_digest: String,
    pub device_digest: String,
}

fn public(parent: &Dir, name: &str) -> Result<Vec<u8>> {
    use std::io::Read;
    let file = files::open_regular(parent, Path::new(name)).map_err(|_| invalid())?;
    let metadata = file.metadata().map_err(|_| invalid())?;
    if cap_fs_ext::MetadataExt::nlink(&metadata) != 1 {
        return Err(invalid());
    }
    #[cfg(unix)]
    if cap_std::fs::MetadataExt::mode(&metadata) & 0o077 != 0 {
        return Err(invalid());
    }
    let mut bytes = Vec::new();
    file.take(65537)
        .read_to_end(&mut bytes)
        .map_err(|_| invalid())?;
    if bytes.len() > 65536 {
        return Err(invalid());
    }
    Ok(bytes)
}

fn key(parent: &Dir, storage: Storage, id: &str) -> Result<SigningKey> {
    let value =
        super::legacy::read(parent, storage, &format!("device-key.{id}"))?.ok_or_else(invalid)?;
    if value.len() != 1 {
        return Err(invalid());
    }
    let encoded = value.get("seed").ok_or_else(invalid)?;
    let mut seed = Zeroizing::new([0u8; 32]);
    if super::STANDARD
        .decode_slice(encoded.as_bytes(), seed.as_mut())
        .map_err(|_| invalid())?
        != 32
    {
        return Err(invalid());
    }
    Ok(SigningKey::from_bytes(&seed))
}

pub(crate) fn plan(root: &Path, storage: Storage, operation: &str) -> Result<Plan> {
    storage.validate()?;
    let (root, root_identity) = super::root(root)?;
    let parent =
        Dir::open_ambient_dir(&root, cap_std::ambient_authority()).map_err(|_| invalid())?;
    if super::open(&parent, false)?.is_some() {
        return Err(invalid());
    }
    let owner_bytes = public(&parent, "owner.json")?;
    let owner = canonical::parse(&owner_bytes)?;
    let account_id = owner["account_id"]
        .as_str()
        .filter(|id| passport::stable_id(id, "account"))
        .ok_or_else(invalid)?
        .to_owned();
    let device_bytes = public(&parent, "device.json")?;
    let device = canonical::parse(&device_bytes)?;
    let device_id = device["device_id"]
        .as_str()
        .filter(|id| passport::stable_id(id, "device"))
        .ok_or_else(invalid)?
        .to_owned();
    let created_at = device["created_at"]
        .as_str()
        .filter(|at| passport::timestamp(at))
        .ok_or_else(invalid)?
        .to_owned();
    if device["state"] != "active" {
        return Err(invalid());
    }
    let mut retired = Vec::new();
    let mut seen = BTreeSet::new();
    if let Some(entries) = device.get("retired") {
        for entry in entries.as_array().ok_or_else(invalid)? {
            let id = entry["device_id"].as_str().ok_or_else(invalid)?;
            if !passport::stable_id(id, "device")
                || id == device_id
                || !seen.insert(id)
                || retired.len() >= 128
                || !entry["retired_at"]
                    .as_str()
                    .is_some_and(passport::timestamp)
            {
                return Err(invalid());
            }
            retired.push(id.to_owned());
        }
    }
    let held = key(&parent, storage, &device_id)?;
    Ok(Plan {
        identity: super::Plan {
            schema_version: 1,
            action: "device.adopt".into(),
            operation_id: operation.into(),
            expires_at: authoring::expiry(&created_at)?,
            created_at,
            root,
            root_identity,
            account_id,
            device_id,
            credential_store: storage,
            algorithm: "Ed25519".into(),
        },
        public_key: super::STANDARD.encode(held.verifying_key().to_bytes()),
        retired,
        owner_digest: digest::sha256(&owner_bytes),
        device_digest: digest::sha256(&device_bytes),
    })
}

impl Plan {
    pub(crate) fn validate(&self) -> Result<()> {
        self.identity.validate()?;
        let mut seen = BTreeSet::new();
        if self.identity.action != "device.adopt"
            || self.retired.len() > 128
            || self.retired.iter().any(|id| {
                !passport::stable_id(id, "device")
                    || id == &self.identity.device_id
                    || !seen.insert(id)
            })
            || super::STANDARD
                .decode(&self.public_key)
                .map_err(|_| invalid())?
                .len()
                != 32
        {
            return Err(invalid());
        }
        Ok(())
    }

    pub(crate) fn revalidate(&self, parent: &Dir) -> Result<()> {
        self.validate()?;
        super::revalidate(&self.identity)?;
        if digest::sha256(&public(parent, "owner.json")?) != self.owner_digest
            || digest::sha256(&public(parent, "device.json")?) != self.device_digest
        {
            return Err(invalid());
        }
        Ok(())
    }
}

pub(crate) fn apply(plan: &Plan, parent: &Dir) -> Result<Identity> {
    plan.revalidate(parent)?;
    let directory = super::open(parent, true)?.ok_or_else(invalid)?;
    if let Some(record) = super::record(&directory)? {
        if record.plan != plan.identity
            || record.device["public_key"] != plan.public_key
            || record.device["retired_device_ids"] != serde_json::json!(plan.retired)
        {
            return Err(invalid());
        }
        return super::load(
            &directory,
            &record,
            parent.try_clone().map_err(|_| invalid())?,
        );
    }
    match super::pending(&directory)? {
        Some(held) if held == plan.identity => super::inventory(&directory, Some(&held))?,
        Some(_) => return Err(invalid()),
        None => {
            super::inventory(&directory, None)?;
            directory.atomic(
                "pending.json",
                &canonical::bytes(&serde_json::to_value(&plan.identity).map_err(|_| invalid())?)?,
            )?;
        }
    }
    let source = key(
        parent,
        plan.identity.credential_store,
        &plan.identity.device_id,
    )?;
    if super::STANDARD.encode(source.verifying_key().to_bytes()) != plan.public_key {
        return Err(invalid());
    }
    let vault = Vault::new(&directory, plan.identity.credential_store)?;
    match vault.read_key(&plan.identity.device_id)? {
        Some(existing) if existing.verifying_key() != source.verifying_key() => {
            return Err(invalid());
        }
        Some(_) => (),
        None => vault.create_key(&plan.identity.device_id, &source)?,
    }
    let record = Record {
        plan: plan.identity.clone(),
        plan_digest: plan.identity.digest()?,
        device: super::report_for(
            &plan.identity.device_id,
            &plan.identity.created_at,
            plan.identity.credential_store,
            &plan.retired,
            &source,
        ),
    };
    super::REPORT.validate(&record.device)?;
    directory.atomic(
        "identity.json",
        &canonical::bytes(&serde_json::to_value(&record).map_err(|_| invalid())?)?,
    )?;
    super::load(
        &directory,
        &record,
        parent.try_clone().map_err(|_| invalid())?,
    )
}

pub(super) fn retired(device: &Value) -> Result<Vec<String>> {
    serde_json::from_value(device["retired_device_ids"].clone()).map_err(|_| invalid())
}

pub(crate) fn retire_source(plan: &Plan, parent: &Dir) -> Result<()> {
    let id = format!("device-key.{}", plan.identity.device_id);
    let Some(value) = super::legacy::read(parent, plan.identity.credential_store, &id)? else {
        return Ok(());
    };
    let held = key(
        parent,
        plan.identity.credential_store,
        &plan.identity.device_id,
    )?;
    if super::STANDARD.encode(held.verifying_key().to_bytes()) != plan.public_key {
        return Err(invalid());
    }
    super::legacy::retire(parent, plan.identity.credential_store, &id, &value)
}
