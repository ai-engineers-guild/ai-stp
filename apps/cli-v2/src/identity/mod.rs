//! Isolated offline identity. Public plans never contain key material or cloud claims.

mod credentials;
#[cfg(target_os = "linux")]
mod secret_service;

use base64::{Engine, engine::general_purpose::STANDARD};
use cap_std::fs::Dir;
use ed25519_dalek::{Signer, SigningKey};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use zeroize::Zeroizing;

use crate::{
    authoring, canonical, digest,
    error::{ErrorKind, Failure, Result},
    files::{self, OwnedDirectory},
    passport,
    wire::Schema,
};
use credentials::Credentials;

const NAMESPACE: &str = "ai-stp-v2-identity";
const OWNER: &[u8] = b"ai-stp-cli-v2 isolated identity v1\n";
static REPORT: Schema = Schema::new(include_str!(
    "../../../../schemas/v1/cli-device-identity.schema.json"
));

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Storage {
    OsKeyring,
    File,
}

impl Storage {
    fn validate(self) -> Result<()> {
        if self == Self::File && !cfg!(unix) {
            return Err(Failure::precondition(
                "the file credential backend requires Unix owner-only permissions; select os_keyring on this platform",
            ));
        }
        Ok(())
    }
    fn detail(self) -> &'static str {
        match self {
            Self::File => "explicit owner-only file; not encrypted at rest",
            Self::OsKeyring => "explicit native operating system credential store",
        }
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub root: PathBuf,
    pub root_identity: [String; 2],
    pub account_id: String,
    pub device_id: String,
    pub credential_store: Storage,
    pub algorithm: String,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
    fn validate(&self) -> Result<()> {
        self.credential_store.validate()?;
        if self.schema_version != 1
            || self.action != "device.initialize"
            || self.algorithm != "Ed25519"
            || !self.root.is_absolute()
            || !passport::stable_id(&self.operation_id, "operation")
            || !passport::stable_id(&self.account_id, "account")
            || !passport::stable_id(&self.device_id, "device")
            || self.expires_at != authoring::expiry(&self.created_at)?
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Record {
    plan: Plan,
    plan_digest: String,
    device: Value,
}

/// No Serialize or Debug implementation: only report() and explicit signing can leave this type.
pub struct Identity {
    context: authoring::Identity,
    key: SigningKey,
    device: Value,
}

impl Identity {
    pub fn context(&self) -> authoring::Identity {
        self.context.clone()
    }
    pub fn report(&self) -> Value {
        self.device.clone()
    }
    pub fn sign(&self, payload: &[u8]) -> Result<[u8; 64]> {
        if payload.len() > 16 * 1024 * 1024 {
            return Err(Failure::input("the signing payload exceeds 16 MiB"));
        }
        if self.device["state"] != "active" {
            return Err(Failure::precondition(
                "a revoked device cannot sign or author new state",
            ));
        }
        Ok(self.key.sign(payload).to_bytes())
    }
}

fn invalid() -> Failure {
    Failure::precondition("the local identity, key or initialization record is inconsistent")
}

fn root(path: &Path) -> Result<(PathBuf, [String; 2])> {
    let location = PathBuf::from(files::location(path)?);
    let dir =
        Dir::open_ambient_dir(&location, cap_std::ambient_authority()).map_err(|_| invalid())?;
    let meta = dir.dir_metadata().map_err(|_| invalid())?;
    Ok((
        location,
        [
            cap_fs_ext::MetadataExt::dev(&meta).to_string(),
            cap_fs_ext::MetadataExt::ino(&meta).to_string(),
        ],
    ))
}

fn revalidate(plan: &Plan) -> Result<()> {
    revalidate_at(plan, &plan.root)
}

fn revalidate_at(plan: &Plan, parent: &Path) -> Result<()> {
    if root(parent)? != (plan.root.clone(), plan.root_identity.clone()) {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "the planned identity directory changed",
        ));
    }
    Ok(())
}

fn pending(directory: &OwnedDirectory) -> Result<Option<Plan>> {
    directory
        .read_file("pending.json", 64 * 1024)?
        .map(|bytes| {
            let plan: Plan =
                serde_json::from_value(canonical::parse(&bytes)?).map_err(|_| invalid())?;
            plan.validate()?;
            Ok(plan)
        })
        .transpose()
}

fn inventory(directory: &OwnedDirectory, plan: Option<&Plan>) -> Result<()> {
    let key = plan.map(|plan| format!("device-key.{}", plan.device_id));
    for entry in directory.directory.entries().map_err(|_| invalid())? {
        let entry = entry.map_err(|_| invalid())?;
        let name = entry.file_name();
        let name = name.to_str().ok_or_else(invalid)?;
        if matches!(name, "lock" | "owner") {
            continue;
        }
        // Atomic-write leftovers belong to an already-recorded operation only.
        let temporary = name
            .strip_prefix(".tmp-")
            .is_some_and(|id| ulid::Ulid::from_string(id).is_ok());
        if plan.is_none()
            || !(matches!(name, "pending.json" | "identity.json")
                || key.as_deref() == Some(name)
                || temporary)
        {
            return Err(invalid());
        }
    }
    Ok(())
}

fn record(directory: &OwnedDirectory) -> Result<Option<Record>> {
    directory
        .read_file("identity.json", 64 * 1024)?
        .map(|bytes| {
            let record: Record =
                serde_json::from_value(canonical::parse(&bytes)?).map_err(|_| invalid())?;
            record.plan.validate()?;
            REPORT.validate(&record.device)?;
            if record.plan.digest()? != record.plan_digest
                || pending(directory)?.as_ref() != Some(&record.plan)
                || record.device["device_id"] != record.plan.device_id
                || record.device["created_at"] != record.plan.created_at
                || record.device["credential_store"]
                    != serde_json::to_value(record.plan.credential_store).map_err(|_| invalid())?
            {
                return Err(invalid());
            }
            inventory(directory, Some(&record.plan))?;
            Ok(record)
        })
        .transpose()
}

fn report(plan: &Plan, key: &SigningKey) -> Value {
    let public = key.verifying_key().to_bytes();
    let fingerprint = Sha256::digest(public)[..16]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<Vec<_>>()
        .join(":");
    json!({"schema_version":1,"device_id":plan.device_id,"public_key":STANDARD.encode(public),
        "key_fingerprint":fingerprint,"created_at":plan.created_at,"state":"active",
        "credential_store":plan.credential_store,"credential_store_detail":plan.credential_store.detail(),"retired_device_ids":[]})
}

fn load(directory: &OwnedDirectory, record: &Record) -> Result<Identity> {
    let key = Credentials::new(directory,record.plan.credential_store)?.read(&record.plan.device_id)?
        .ok_or_else(||Failure::precondition("the device has a public record but its private key is missing; initialization will not replace it"))?;
    let public = report(&record.plan, &key);
    if record.device["public_key"] != public["public_key"]
        || record.device["key_fingerprint"] != public["key_fingerprint"]
    {
        return Err(invalid());
    }
    if record.device["state"] != "active" {
        return Err(Failure::precondition("the local device is revoked"));
    }
    Ok(Identity {
        context: authoring::Identity {
            account_id: record.plan.account_id.clone(),
            device_id: record.plan.device_id.clone(),
        },
        key,
        device: record.device.clone(),
    })
}

/// Read-only: absent identity stays absent, and no keyring availability probe is written.
pub fn current(parent: &Path) -> Result<Option<Identity>> {
    let Some(directory) = OwnedDirectory::open(parent, NAMESPACE, OWNER, false)? else {
        return Ok(None);
    };
    let Some(record) = record(&directory)? else {
        inventory(&directory, pending(&directory)?.as_ref())?;
        return Ok(None);
    };
    revalidate_at(&record.plan, parent)?;
    load(&directory, &record).map(Some)
}

/// Public intent binds identities and storage; key entropy is generated only during apply.
pub fn plan(parent: &Path, storage: Storage, at: &str) -> Result<Plan> {
    storage.validate()?;
    let expires_at = authoring::expiry(at)?;
    let (root, root_identity) = root(parent)?;
    if let Some(directory) = OwnedDirectory::open(&root, NAMESPACE, OWNER, false)? {
        if record(&directory)?.is_some() {
            return Err(Failure::precondition(
                "this preview installation already has an identity",
            ));
        }
        if let Some(plan) = pending(&directory)? {
            inventory(&directory, Some(&plan))?;
            revalidate_at(&plan, &root)?;
            if plan.credential_store != storage {
                return Err(Failure::new(
                    ErrorKind::Conflict,
                    "initialization already selected another credential store",
                ));
            }
            return Ok(plan);
        }
        inventory(&directory, None)?;
    }
    Ok(Plan {
        schema_version: 1,
        action: "device.initialize".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        root,
        root_identity,
        account_id: format!("account_{}", ulid::Ulid::generate()),
        device_id: format!("device_{}", ulid::Ulid::generate()),
        credential_store: storage,
        algorithm: "Ed25519".into(),
    })
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let plan: Plan = serde_json::from_value(canonical::parse(&files::read(path, 64 * 1024)?)?)
        .map_err(|_| Failure::input("invalid identity initialization plan"))?;
    plan.validate()?;
    Ok(plan)
}

pub fn apply(plan: &Plan, expected_digest: &str, at: &str) -> Result<Identity> {
    plan.validate()?;
    if !passport::timestamp(at) || plan.digest()? != expected_digest {
        return Err(invalid());
    }
    revalidate(plan)?;
    let existing = OwnedDirectory::open(&plan.root, NAMESPACE, OWNER, false)?;
    if existing.is_none() && (at < plan.created_at.as_str() || at > plan.expires_at.as_str()) {
        return Err(Failure::precondition(
            "the initialization plan expired before it started",
        ));
    }
    let directory = match existing {
        Some(dir) => dir,
        None => OwnedDirectory::open(&plan.root, NAMESPACE, OWNER, true)?.ok_or_else(invalid)?,
    };
    if let Some(record) = record(&directory)? {
        if record.plan_digest != expected_digest {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "another plan initialized this installation",
            ));
        }
        return load(&directory, &record);
    }
    match pending(&directory)? {
        Some(held) if held == *plan => {
            inventory(&directory, Some(&held))?;
        }
        Some(_) => {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "another initialization is already in progress",
            ));
        }
        None => {
            inventory(&directory, None)?;
            if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
                return Err(Failure::precondition(
                    "the initialization plan expired before it started",
                ));
            }
            directory.atomic(
                "pending.json",
                &canonical::bytes(&serde_json::to_value(plan).map_err(|_| invalid())?)?,
            )?;
        }
    }
    let credentials = Credentials::new(&directory, plan.credential_store)?;
    let key = match credentials.read(&plan.device_id)? {
        Some(key) => key,
        None => {
            let mut seed = Zeroizing::new([0u8; 32]);
            getrandom::fill(seed.as_mut()).map_err(|_| {
                Failure::new(
                    ErrorKind::Unavailable,
                    "the operating system random source is unavailable",
                )
            })?;
            let key = SigningKey::from_bytes(&seed);
            credentials.create(&plan.device_id, &key)?;
            key
        }
    };
    revalidate(plan)?;
    let record = Record {
        plan: plan.clone(),
        plan_digest: expected_digest.into(),
        device: report(plan, &key),
    };
    REPORT.validate(&record.device)?;
    directory.atomic(
        "identity.json",
        &canonical::bytes(&serde_json::to_value(&record).map_err(|_| invalid())?)?,
    )?;
    // Retain the small public intent as the exact initialization receipt.
    load(&directory, &record)
}
