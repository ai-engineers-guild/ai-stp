//! Public identity succession; retired private keys are never retained here.

use std::collections::BTreeSet;

use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{Identity, Record, Vault, invalid};
use crate::{account, authoring, canonical, error::Result, files::OwnedDirectory, passport};

pub(crate) const OWNER: &[u8] = b"ai-stp-cli-v2 isolated identity v2\n";
const HISTORY: &str = "recoveries.json";
const PENDING: &str = "recovery-pending.json";
const LIMIT: u64 = 4 * 1024 * 1024;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Intent {
    pub device_id: String,
    pub account_id: Option<String>,
    pub owner_id: String,
    pub previous: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub interrupted_sync: Vec<crate::sync::runtime::Checkpoint>,
}

impl Intent {
    pub(crate) fn validate(&self, original: &authoring::Identity) -> Result<()> {
        if self.interrupted_sync.len() > 128
            || self
                .interrupted_sync
                .windows(2)
                .any(|v| v[0].operation_id >= v[1].operation_id)
        {
            return Err(invalid());
        }
        for checkpoint in &self.interrupted_sync {
            checkpoint.validate()?;
        }
        if !passport::stable_id(&self.device_id, "device")
            || self.device_id == original.device_id
            || self
                .account_id
                .as_ref()
                .is_some_and(|id| !passport::stable_id(id, "account"))
            || !passport::stable_id(&self.owner_id, "account")
            || self.owner_id != original.account_id
                && self.account_id.as_deref() != Some(&self.owner_id)
            || self.previous.as_ref().is_some_and(|v| {
                v.strip_prefix("sha256:").is_none_or(|v| {
                    v.len() != 64
                        || !v
                            .bytes()
                            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
                })
            })
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Entry {
    pub plan: account::Plan,
    pub device: Value,
    pub completed_at: String,
}

#[derive(Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct History {
    pub entries: Vec<Entry>,
}

impl Entry {
    fn replacement(
        plan: &account::Plan,
        history: &History,
        public: &[u8; 32],
        at: &str,
    ) -> Result<Self> {
        let intent = plan.recovery.as_ref().ok_or_else(invalid)?;
        let mut retired = history
            .entries
            .iter()
            .map(|e| e.plan.identity.device_id.clone())
            .collect::<Vec<_>>();
        retired.push(plan.identity.device_id.clone());
        Ok(Self {
            plan: plan.clone(),
            device: super::public_report(
                &intent.device_id,
                &plan.created_at,
                plan.credential_store,
                &retired,
                public,
            ),
            completed_at: at.into(),
        })
    }
}

impl History {
    fn raw(directory: &OwnedDirectory) -> Result<Self> {
        directory
            .read_file(HISTORY, LIMIT)?
            .map(|bytes| serde_json::from_value(canonical::parse(&bytes)?).map_err(|_| invalid()))
            .transpose()
            .map(|value| value.unwrap_or_default())
    }

    pub(super) fn read(directory: &OwnedDirectory, initial: &Record) -> Result<Self> {
        let history = Self::raw(directory)?;
        let mut previous = None;
        let mut device = &initial.device;
        let mut retired = Vec::new();
        let mut operations = BTreeSet::new();
        let mut completed_at = initial.plan.created_at.as_str();
        let mut binding: Option<&Entry> = None;
        for entry in &history.entries {
            entry.plan.validate()?;
            let intent = entry.plan.recovery.as_ref().ok_or_else(invalid)?;
            let id = device["device_id"].as_str().ok_or_else(invalid)?;
            if entry.plan.action != account::Action::Recover
                || entry.plan.root != initial.plan.root
                || entry.plan.root_identity != initial.plan.root_identity
                || entry.plan.credential_store != initial.plan.credential_store
                || entry.plan.identity.account_id != initial.plan.account_id
                || entry.plan.identity.device_id != id
                || device["public_key"] != entry.plan.public_key
                || intent.previous != previous
                || retired.contains(&intent.device_id)
                || !operations.insert(entry.plan.operation_id.clone())
                || !passport::timestamp(&entry.completed_at)
                || entry.completed_at < entry.plan.created_at
                || entry.plan.created_at.as_str() < completed_at
                || entry.plan.expected_account_id.as_ref()
                    != binding
                        .and_then(|e| e.plan.recovery.as_ref())
                        .and_then(|r| r.account_id.as_ref())
                || entry.plan.revoked_public_key.as_ref() != binding.map(|e| &e.plan.public_key)
                || binding.is_some_and(|e| e.plan.origin != entry.plan.origin)
                || entry
                    .plan
                    .expected_account_id
                    .as_ref()
                    .is_some_and(|id| intent.account_id.as_ref() != Some(id))
            {
                return Err(invalid());
            }
            retired.push(id.to_owned());
            super::REPORT.validate(&entry.device)?;
            let public: [u8; 32] = super::STANDARD
                .decode(entry.device["public_key"].as_str().ok_or_else(invalid)?)
                .map_err(|_| invalid())?
                .try_into()
                .map_err(|_| invalid())?;
            if entry.device
                != super::public_report(
                    &intent.device_id,
                    &entry.plan.created_at,
                    initial.plan.credential_store,
                    &retired,
                    &public,
                )
            {
                return Err(invalid());
            }
            if entry.device["device_id"] != intent.device_id
                || entry.device["created_at"] != entry.plan.created_at
                || entry.device["state"] != "active"
                || entry.device["credential_store"] != initial.device["credential_store"]
                || entry.device["retired_device_ids"] != serde_json::json!(retired)
            {
                return Err(invalid());
            }
            previous = Some(entry.plan.digest()?);
            device = &entry.device;
            completed_at = &entry.completed_at;
            binding = Some(entry);
        }
        Ok(history)
    }

    pub(crate) fn tip(&self) -> Result<Option<String>> {
        self.entries
            .last()
            .map(|entry| entry.plan.digest())
            .transpose()
    }

    pub(crate) fn entry(&self, plan: &account::Plan) -> Result<Option<&Entry>> {
        let entry = self
            .entries
            .iter()
            .find(|e| e.plan.operation_id == plan.operation_id);
        if entry.is_some_and(|e| e.plan != *plan) {
            return Err(invalid());
        }
        Ok(entry)
    }

    pub(crate) fn write(&self, directory: &OwnedDirectory) -> Result<()> {
        let bytes = canonical::bytes(&serde_json::to_value(self).map_err(|_| invalid())?)?;
        if bytes.len() as u64 > LIMIT {
            return Err(invalid());
        }
        directory.atomic(HISTORY, &bytes)
    }
}

pub(crate) fn pending(directory: &OwnedDirectory) -> Result<Option<account::Plan>> {
    directory
        .read_file(PENDING, 65536)?
        .map(|bytes| {
            let plan: account::Plan =
                serde_json::from_value(canonical::parse(&bytes)?).map_err(|_| invalid())?;
            plan.validate()?;
            if plan.action != account::Action::Recover {
                return Err(invalid());
            }
            Ok(plan)
        })
        .transpose()
}

pub(super) fn inventory(directory: &OwnedDirectory) -> Result<BTreeSet<String>> {
    let history = History::raw(directory)?;
    let mut allowed = BTreeSet::new();
    if !history.entries.is_empty() {
        allowed.insert(HISTORY.into());
    }
    if let Some(entry) = history.entries.last() {
        entry.plan.validate()?;
        let intent = entry.plan.recovery.as_ref().ok_or_else(invalid)?;
        allowed.insert(format!("device-key.{}", intent.device_id));
    }
    if let Some(plan) = pending(directory)? {
        allowed.insert(PENDING.into());
        allowed.insert(format!("device-key.{}", plan.identity.device_id));
        allowed.insert(format!(
            "device-key.{}",
            plan.recovery.ok_or_else(invalid)?.device_id
        ));
    }
    Ok(allowed)
}

/// The caller owns account, then registry locks before taking this identity lock.
pub(crate) struct Replacement {
    pub directory: OwnedDirectory,
    initial: Record,
    pub history: History,
}

impl Replacement {
    pub fn open(plan: &account::Plan) -> Result<Self> {
        let (path, physical) = super::root(&plan.root)?;
        if path != plan.root || physical != plan.root_identity {
            return Err(invalid());
        }
        let parent = cap_std::fs::Dir::open_ambient_dir(&path, cap_std::ambient_authority())
            .map_err(|_| invalid())?;
        if super::physical_root(&parent)? != plan.root_identity {
            return Err(invalid());
        }
        let directory = super::open(&parent, false)?.ok_or_else(invalid)?;
        let initial = super::record(&directory)?.ok_or_else(invalid)?;
        let history = History::read(&directory, &initial)?;
        if initial.plan.account_id != plan.identity.account_id
            || initial.plan.root != plan.root
            || initial.plan.root_identity != plan.root_identity
            || initial.plan.credential_store != plan.credential_store
        {
            return Err(invalid());
        }
        Ok(Self {
            directory,
            initial,
            history,
        })
    }

    pub fn validate(&self, plan: &account::Plan) -> Result<()> {
        let intent = plan.recovery.as_ref().ok_or_else(invalid)?;
        if let Some(entry) = self.history.entry(plan)? {
            if self.history.entries.last().map(|e| &e.plan) != Some(&entry.plan) {
                return Err(invalid());
            }
            return Ok(());
        }
        let device = self
            .history
            .entries
            .last()
            .map_or(&self.initial.device, |e| &e.device);
        if device["device_id"] != plan.identity.device_id
            || device["public_key"] != plan.public_key
            || self.history.tip()? != intent.previous
        {
            return Err(invalid());
        }
        // Public keys and fingerprints have fixed serialized sizes. Check the
        // append before admission so a full history cannot strand a new key.
        let candidate = Entry::replacement(plan, &self.history, &[0; 32], &plan.created_at)?;
        let size = canonical::bytes(&serde_json::to_value(&self.history).map_err(|_| invalid())?)?
            .len()
            + canonical::bytes(&serde_json::to_value(candidate).map_err(|_| invalid())?)?.len()
            + 1;
        if size as u64 > LIMIT {
            return Err(invalid());
        }
        let key = Vault::new(&self.directory, plan.credential_store)?
            .read_key(&plan.identity.device_id)?
            .ok_or_else(invalid)?;
        if super::STANDARD.encode(key.verifying_key().as_bytes()) != plan.public_key {
            return Err(invalid());
        }
        Ok(())
    }

    pub fn knows_original(&self, identity: &authoring::Identity) -> bool {
        identity.account_id == self.initial.plan.account_id
            && (identity.device_id == self.initial.plan.device_id
                || self.history.entries.iter().any(|e| {
                    e.plan
                        .recovery
                        .as_ref()
                        .is_some_and(|r| r.device_id == identity.device_id)
                }))
    }

    pub fn admit(&self, plan: &account::Plan) -> Result<()> {
        self.validate(plan)?;
        if let Some(held) = pending(&self.directory)? {
            if held != *plan {
                return Err(invalid());
            }
        } else {
            self.directory.atomic("owner", OWNER)?;
            self.directory.atomic(
                PENDING,
                &canonical::bytes(&serde_json::to_value(plan).map_err(|_| invalid())?)?,
            )?;
        }
        Ok(())
    }

    pub fn replace(&mut self, plan: &account::Plan, at: &str) -> Result<Entry> {
        self.validate(plan)?;
        if pending(&self.directory)?.as_ref() != Some(plan) {
            return Err(invalid());
        }
        let intent = plan.recovery.as_ref().ok_or_else(invalid)?;
        let vault = Vault::new(&self.directory, plan.credential_store)?;
        let key = match vault.read_key(&intent.device_id)? {
            Some(key) => key,
            None if self.history.entry(plan)?.is_none() => {
                let key = super::generate()?;
                vault.create_key(&intent.device_id, &key)?;
                key
            }
            None => return Err(invalid()),
        };
        if super::STANDARD.encode(key.verifying_key().as_bytes()) == plan.public_key {
            return Err(invalid());
        }
        if self.history.entry(plan)?.is_none() {
            let entry =
                Entry::replacement(plan, &self.history, key.verifying_key().as_bytes(), at)?;
            self.history.entries.push(entry);
            self.history.write(&self.directory)?;
        }
        let entry = self.history.entry(plan)?.ok_or_else(invalid)?;
        if entry.device["public_key"] != super::STANDARD.encode(key.verifying_key().as_bytes()) {
            return Err(invalid());
        }
        if let Some(old) = vault.read_key(&plan.identity.device_id)?
            && super::STANDARD.encode(old.verifying_key().as_bytes()) != plan.public_key
        {
            return Err(invalid());
        }
        vault.retire(&format!("device-key.{}", plan.identity.device_id))?;
        Ok(entry.clone())
    }

    pub fn finish(&self, plan: &account::Plan) -> Result<()> {
        if let Some(held) = pending(&self.directory)? {
            if held != *plan {
                return Err(invalid());
            }
            self.directory
                .directory
                .remove_file(PENDING)
                .map_err(|_| invalid())?;
            self.directory.sync()?;
        }
        Ok(())
    }

    pub fn completed(&mut self, plan: &account::Plan, at: &str) -> Result<Entry> {
        let entry = self.history.entries.last_mut().ok_or_else(invalid)?;
        if entry.plan != *plan || at < entry.completed_at.as_str() {
            return Err(invalid());
        }
        entry.completed_at = at.into();
        let result = entry.clone();
        self.history.write(&self.directory)?;
        Ok(result)
    }
}

impl Identity {
    pub(crate) fn recovery_binding(&self) -> Option<&Entry> {
        self.history.entries.last()
    }

    pub(crate) fn recovery_tip(&self) -> Result<Option<String>> {
        self.history.tip()
    }

    pub(crate) fn knows_original(&self, identity: &authoring::Identity) -> bool {
        identity.account_id == self.plan.account_id
            && (identity.device_id == self.context().device_id
                || self
                    .history
                    .entries
                    .iter()
                    .any(|e| e.plan.identity == *identity))
    }

    pub(crate) fn historical(&self, identity: &authoring::Identity) -> bool {
        self.knows_original(identity)
            || self.history.entries.iter().any(|e| {
                e.plan.identity.device_id == identity.device_id
                    && e.plan
                        .recovery
                        .as_ref()
                        .is_some_and(|r| r.owner_id == identity.account_id)
            })
    }

    pub(crate) fn historical_account(&self, plan: &account::Plan) -> Result<()> {
        if self.root_binding() != (plan.root.as_path(), &plan.root_identity)
            || self.storage() != plan.credential_store
            || !self.history.entries.iter().any(|entry| {
                entry.plan.identity == plan.identity && entry.plan.public_key == plan.public_key
            })
        {
            return Err(invalid());
        }
        Ok(())
    }
}

pub(crate) fn pending_at(root: &std::path::Path) -> Result<Option<account::Plan>> {
    let (path, physical) = super::root(root)?;
    let parent = cap_std::fs::Dir::open_ambient_dir(&path, cap_std::ambient_authority())
        .map_err(|_| invalid())?;
    if super::physical_root(&parent)? != physical {
        return Err(invalid());
    }
    let Some(directory) = super::open(&parent, false)? else {
        return Ok(None);
    };
    let plan = pending(&directory)?;
    if plan
        .as_ref()
        .is_some_and(|p| p.root != path || p.root_identity != physical)
    {
        return Err(invalid());
    }
    Ok(plan)
}
