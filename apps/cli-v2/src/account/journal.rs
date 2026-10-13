//! One account lock owns intent admission, credential replacement and replay receipts.

use serde::{Deserialize, Serialize};
use zeroize::Zeroizing;

use super::model::{Plan, Receipt, State};
use crate::{
    canonical,
    error::Result,
    files::OwnedDirectory,
    identity::{self, credentials::Vault},
};

const OWNER: &[u8] = b"ai-stp-cli-v2 isolated account sessions v1\n";
const RECOVERED: &[u8] = b"ai-stp-cli-v2 isolated account sessions v2\n";
const NAME: &str = "ai-stp-v2-account";

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Pending {
    pub plan: Plan,
    pub requested_at: String,
}

pub(super) struct Journal {
    directory: OwnedDirectory,
    storage: identity::Storage,
    name: String,
}

impl Journal {
    pub fn open(id: &identity::Identity, create: bool) -> Result<Option<Self>> {
        Self::at(
            id.root_directory(),
            id.storage(),
            &id.context().device_id,
            create,
        )
    }

    pub fn at(
        parent: &cap_std::fs::Dir,
        storage: identity::Storage,
        device: &str,
        create: bool,
    ) -> Result<Option<Self>> {
        Ok(
            OwnedDirectory::open_compatible(parent, NAME, OWNER, &[RECOVERED], create)?.map(
                |directory| Self {
                    directory,
                    storage,
                    name: format!("account-{device}"),
                },
            ),
        )
    }

    pub fn fence(&self) -> Result<()> {
        self.directory.atomic("owner", RECOVERED)
    }

    pub fn retire(&self) -> Result<()> {
        self.vault()?.retire(&self.name)
    }

    fn vault(&self) -> Result<Vault<'_>> {
        Vault::new(&self.directory, self.storage)
    }

    pub fn state(&self) -> Result<Option<State>> {
        self.vault()?
            .read(&self.name, 65536)?
            .map(|bytes| {
                let state: State = serde_json::from_slice(&bytes).map_err(|_| super::invalid())?;
                state.plan.validate()?;
                if state.plan.credential_store != self.storage
                    || state.revision != state.plan.operation_id
                {
                    return Err(super::invalid());
                }
                state.receipt()?.validate()?;
                super::validate_session(&state)?;
                Ok(state)
            })
            .transpose()
    }

    pub fn write(&self, state: &State) -> Result<()> {
        super::validate_session(state)?;
        let serialized =
            Zeroizing::new(serde_json::to_string(state).map_err(|_| super::invalid())?);
        self.vault()?.write_account(&self.name, &serialized)
    }

    pub fn pending(&self) -> Result<Option<Pending>> {
        self.directory
            .read_file("pending.json", 65536)?
            .map(|bytes| {
                let pending: Pending = serde_json::from_value(canonical::parse(&bytes)?)
                    .map_err(|_| super::invalid())?;
                pending.plan.validate()?;
                if !crate::passport::timestamp(&pending.requested_at) {
                    return Err(super::invalid());
                }
                Ok(pending)
            })
            .transpose()
    }

    pub fn admit(&self, pending: &Pending) -> Result<()> {
        self.directory.atomic(
            "pending.json",
            &canonical::bytes(&serde_json::to_value(pending).map_err(|_| super::invalid())?)?,
        )
    }

    pub fn receipt(&self, plan: &Plan) -> Result<Option<Receipt>> {
        let receipt = self.receipt_id(&plan.operation_id)?;
        if receipt.as_ref().is_some_and(|held| held.plan != *plan) {
            return Err(super::invalid());
        }
        Ok(receipt)
    }

    pub fn receipt_id(&self, id: &str) -> Result<Option<Receipt>> {
        if !crate::passport::stable_id(id, "operation") {
            return Err(super::invalid());
        }
        self.directory
            .read_file(&format!("{id}.json"), 65536)?
            .map(|bytes| {
                let receipt: Receipt = serde_json::from_value(canonical::parse(&bytes)?)
                    .map_err(|_| super::invalid())?;
                receipt.validate()?;
                if receipt.plan.operation_id != id {
                    return Err(super::invalid());
                }
                Ok(receipt)
            })
            .transpose()
    }

    pub fn complete(&self, state: &State) -> Result<Receipt> {
        let receipt = state.receipt()?;
        self.complete_receipt(&receipt)?;
        Ok(receipt)
    }

    pub fn complete_receipt(&self, receipt: &Receipt) -> Result<()> {
        receipt.validate()?;
        self.directory.atomic(
            &format!("{}.json", receipt.plan.operation_id),
            &canonical::bytes(&serde_json::to_value(receipt).map_err(|_| super::invalid())?)?,
        )?;
        self.clear_pending(&receipt.plan)?;
        Ok(())
    }

    pub fn clear_pending(&self, plan: &Plan) -> Result<()> {
        if let Some(pending) = self.pending()? {
            if pending.plan != *plan {
                return Err(super::invalid());
            }
            self.directory
                .directory
                .remove_file("pending.json")
                .map_err(|_| super::invalid())?;
            self.directory.sync()?;
        }
        Ok(())
    }
}
