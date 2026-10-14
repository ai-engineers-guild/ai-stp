//! Explicit account-scoped reads. Credentials never leave this held session.

use serde::{Deserialize, Serialize};
use std::{path::Path, time::Duration};
use url::Url;

use super::{
    Session, State,
    journal::Journal,
    transport::{Api, Reply},
};
use crate::{
    error::{Failure, Result},
    files::OwnedDirectory,
    http::Endpoint,
    identity, passport,
};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub origin: String,
    pub account_id: String,
    pub device_id: String,
    pub revision: String,
    pub root_identity: [String; 2],
    pub public_key: String,
    pub credential_store: identity::Storage,
}

fn refused(reason: &str) -> Failure {
    Failure::precondition("private catalog access requires the unchanged isolated account session")
        .with_details([("reason".into(), reason.into())])
}

/// Lock order is account, then registry/cache. Load before opening either store.
/// This type deliberately has no Debug or serialization implementation.
pub(crate) struct Access {
    identity: identity::Identity,
    _journal: Journal,
    state: State,
    binding: Binding,
    api: Api,
    verified: bool,
    offline: bool,
}

impl Access {
    pub fn load(root: &Path, origin: &str, offline: bool) -> Result<Self> {
        Self::load_at(root, Some(origin), offline)
    }

    pub fn for_account(root: &Path, origin: Option<&str>) -> Result<Self> {
        Self::load_at(root, origin, false)
    }

    fn load_at(root: &Path, origin: Option<&str>, offline: bool) -> Result<Self> {
        let identity = super::identity_at(root)?;
        let journal =
            Journal::open(&identity, false)?.ok_or_else(|| refused("account_required"))?;
        if journal.pending()?.is_some() {
            return Err(refused("account_operation_unfinished"));
        }
        let state = journal
            .state()?
            .ok_or_else(|| refused("account_required"))?;
        super::check_binding(&identity, &state.plan)?;
        let Session::Authorized { account_id, .. } = &state.session else {
            return Err(refused("account_required"));
        };
        if origin
            .map(super::transport::origin)
            .transpose()?
            .is_some_and(|origin| origin != state.plan.origin)
        {
            return Err(refused("account_origin_mismatch"));
        }
        let binding = Binding {
            origin: state.plan.origin.clone(),
            account_id: account_id.clone(),
            device_id: state.plan.identity.device_id.clone(),
            revision: state.revision.clone(),
            root_identity: state.plan.root_identity.clone(),
            public_key: state.plan.public_key.clone(),
            credential_store: state.plan.credential_store,
        };
        let access = Self {
            identity,
            _journal: journal,
            state,
            api: Api::new(&binding.origin)?,
            binding,
            verified: false,
            offline,
        };
        access.revalidate()?;
        Ok(access)
    }

    pub fn binding(&self) -> &Binding {
        &self.binding
    }

    pub fn revalidate(&self) -> Result<()> {
        super::check_binding(
            &super::identity_at(&self.state.plan.root)?,
            &self.state.plan,
        )?;
        let Session::Authorized { expires_at, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        if !self.offline && format!("{:.3}", jiff::Timestamp::now()) >= *expires_at {
            return Err(refused("account_expired"));
        }
        Ok(())
    }

    /// Prove the credential's account and device before any private graph read.
    /// Cached offline observations never pass this online authorization gate.
    pub fn verify(&mut self) -> Result<()> {
        self.revalidate()?;
        if self.offline {
            return Err(refused("offline_observation_only"));
        }
        let Session::Authorized { access_token, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        let account = match self.api.me(access_token)? {
            Reply::Resource(account) => account,
            Reply::Refused(super::transport::Code::Revoked) => {
                return Err(refused("device_revoked"));
            }
            Reply::Refused(_) => return Err(refused("account_refused")),
        };
        if account.schema_version != 1
            || account.account_id != self.binding.account_id
            || account.device_id.as_deref() != Some(&self.binding.device_id)
            || account.account_status != "active"
        {
            return Err(refused("account_identity_mismatch"));
        }
        self.revalidate()?;
        self.verified = true;
        Ok(())
    }

    pub fn read(
        &self,
        endpoint: &Endpoint,
        url: &Url,
        accept: &str,
        limit: u64,
        remaining: Duration,
    ) -> Result<Vec<u8>> {
        self.revalidate()?;
        if !self.verified
            || self.offline
            || endpoint.base.origin().ascii_serialization() != self.binding.origin
            || url.origin() != endpoint.base.origin()
        {
            return Err(refused("account_origin_or_authorization_mismatch"));
        }
        let Session::Authorized { access_token, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        let bytes = endpoint.read_authenticated(url, accept, limit, remaining, &access_token.0)?;
        self.revalidate()?;
        Ok(bytes)
    }

    pub fn cache(&self, create: bool) -> Result<Option<OwnedDirectory>> {
        self.revalidate()?;
        OwnedDirectory::open_at(
            self.identity.root_directory(),
            "ai-stp-v2-private-catalog",
            b"ai-stp-cli-v2 private catalog cache v1\n",
            create,
        )
    }

    pub(super) fn grants(&self, route: &str, body: Option<&[u8]>) -> Result<serde_json::Value> {
        self.revalidate()?;
        if !self.verified || self.offline {
            return Err(refused("account_origin_or_authorization_mismatch"));
        }
        let Session::Authorized { access_token, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        let reply = self.api.grants(route, body, access_token)?;
        self.revalidate()?;
        match reply {
            Reply::Resource(value) => Ok(value),
            Reply::Refused(code) => Err(super::grants::refusal(code)),
        }
    }

    pub(super) fn github(&self, body: Option<&[u8]>) -> Result<serde_json::Value> {
        self.revalidate()?;
        if !self.verified || self.offline {
            return Err(refused("account_origin_or_authorization_mismatch"));
        }
        let Session::Authorized { access_token, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        let reply = self.api.github(body, access_token)?;
        self.revalidate()?;
        match reply {
            Reply::Resource(value) => Ok(value),
            Reply::Refused(code) => Err(super::github::refusal(code)),
        }
    }

    pub(crate) fn sync(
        &self,
        request: &crate::sync::network::Request<'_>,
    ) -> Result<serde_json::Value> {
        self.revalidate()?;
        if !self.verified || self.offline {
            return Err(refused("account_origin_or_authorization_mismatch"));
        }
        let Session::Authorized { access_token, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        request.validate(&self.binding.account_id, &self.binding.device_id)?;
        let reply = self.api.sync(request, access_token)?;
        self.revalidate()?;
        match reply {
            Reply::Resource(value) => request.response(value, &self.binding.account_id),
            Reply::Refused(code) => Err(super::transport::sync_refusal(code)),
        }
    }

    pub(crate) fn publication(
        &self,
        request: &crate::publication::client::Request<'_>,
    ) -> Result<serde_json::Value> {
        self.revalidate()?;
        if !self.verified || self.offline {
            return Err(refused("account_origin_or_authorization_mismatch"));
        }
        let Session::Authorized { access_token, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        let reply = self.api.publication(request, access_token)?;
        self.revalidate()?;
        match reply {
            Reply::Resource(value) => Ok(value),
            Reply::Refused(code) => Err(super::transport::publication_refusal(code)),
        }
    }

    pub(crate) fn sign_attestation(&self, record: &serde_json::Value) -> Result<[u8; 64]> {
        self.revalidate()?;
        if !self.verified
            || self.offline
            || record["account_id"] != self.binding.account_id
            || record["device_id"] != self.binding.device_id
        {
            return Err(refused("attestation_authorization_changed"));
        }
        let signature = self
            .identity
            .sign(crate::attestation::contract::hash(record)?.as_bytes())?;
        self.revalidate()?;
        Ok(signature)
    }

    pub(crate) fn owned_registry(&self) -> Result<crate::store::Store> {
        self.revalidate()?;
        let store = crate::store::Store::open_at(self.identity.root_directory(), false)?;
        let owner = super::attachment::effective(&store.connection, &self.identity)?;
        if owner.account_id != self.binding.account_id || owner.device_id != self.binding.device_id
        {
            return Err(refused("registry_owner_not_attached"));
        }
        self.revalidate()?;
        Ok(store)
    }

    pub(crate) fn publication_recovered(
        &self,
        binding: &Binding,
        receipt: &crate::publication::interruption::Receipt,
    ) -> Result<()> {
        self.revalidate()?;
        if self.binding.account_id != binding.account_id
            || self.binding.origin != binding.origin
            || self.binding.root_identity != binding.root_identity
            || self.binding.device_id == binding.device_id
        {
            return Err(refused("publication_recovery_binding_changed"));
        }
        let recovery = self.identity.completed_recovery(
            &receipt.recovery_operation_id,
            &receipt.recovery_plan_digest,
        )?;
        crate::publication::interruption::belongs(binding, recovery)?;
        if *receipt
            != crate::publication::interruption::Receipt::for_plan(&receipt.checkpoint, recovery)?
        {
            return Err(refused("publication_recovery_checkpoint_changed"));
        }
        Ok(())
    }
}

impl Binding {
    pub fn validate(&self) -> Result<()> {
        if super::transport::origin(&self.origin)? != self.origin
            || !passport::stable_id(&self.account_id, "account")
            || !passport::stable_id(&self.device_id, "device")
            || !passport::stable_id(&self.revision, "operation")
        {
            return Err(refused("account_binding_invalid"));
        }
        Ok(())
    }
}
