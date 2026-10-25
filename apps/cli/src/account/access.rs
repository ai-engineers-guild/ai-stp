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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub connection: Option<Box<super::connections::Enrollment>>,
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
        Self::load_at(root, Some(origin), offline, None)
    }

    pub fn for_account(root: &Path, origin: Option<&str>) -> Result<Self> {
        Self::load_at(root, origin, false, None)
    }

    pub fn for_connection(
        root: &Path,
        origin: Option<&str>,
        connection: Option<&str>,
        offline: bool,
    ) -> Result<Self> {
        Self::load_at(root, origin, offline, connection)
    }

    pub fn for_binding(root: &Path, binding: &Binding, offline: bool) -> Result<Self> {
        binding.validate()?;
        let held = Self::load_at(
            root,
            Some(&binding.origin),
            offline,
            binding
                .connection
                .as_ref()
                .map(|value| value.connection_id.as_str()),
        )?;
        if held.binding.account_id != binding.account_id
            || held.binding.device_id != binding.device_id
            || held.binding.public_key != binding.public_key
            || held.binding.root_identity != binding.root_identity
            || held.binding.credential_store != binding.credential_store
            || held.binding.connection != binding.connection
        {
            return Err(refused("account_binding_changed"));
        }
        Ok(held)
    }

    fn load_at(
        root: &Path,
        origin: Option<&str>,
        offline: bool,
        connection: Option<&str>,
    ) -> Result<Self> {
        let identity = super::identity_at(root)?;
        let connection = connection
            .map(|value| super::connections::enrollment(&identity, value))
            .transpose()?;
        let journal = Journal::for_connection(&identity, connection.as_ref(), false)?
            .ok_or_else(|| refused("account_required"))?;
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
            device_id: state.plan.device_id().to_owned(),
            revision: state.revision.clone(),
            root_identity: state.plan.root_identity.clone(),
            public_key: state.plan.enrollment_public_key().to_owned(),
            credential_store: state.plan.credential_store,
            connection: state.plan.connection.clone().map(Box::new),
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

    /// A remote enrollment authorizes reads; it does not replace the native
    /// actor which records acquired immutable bytes in this authority root.
    pub(crate) fn check_local_actor(&self, actor: &crate::authoring::Identity) -> Result<()> {
        self.revalidate()?;
        actor.validate()?;
        if actor.device_id != self.identity.context().device_id {
            return Err(refused("local_authority_device_mismatch"));
        }
        Ok(())
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

    pub(super) fn context_read(
        &self,
        route: &str,
        organization: Option<&str>,
    ) -> Result<serde_json::Value> {
        self.revalidate()?;
        if !self.verified || self.offline {
            return Err(refused("account_origin_or_authorization_mismatch"));
        }
        let Session::Authorized { access_token, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        let reply = self.api.context_read(route, organization, access_token)?;
        self.revalidate()?;
        match reply {
            Reply::Resource(value) => Ok(value),
            Reply::Refused(code) => Err(super::grants::refusal(code)),
        }
    }

    pub(super) fn corporate(
        &self,
        request: &super::corporate::Request,
        organization: &str,
    ) -> Result<serde_json::Value> {
        self.revalidate()?;
        if !self.verified || self.offline {
            return Err(refused("account_origin_or_authorization_mismatch"));
        }
        let Session::Authorized { access_token, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        let reply = self.api.corporate(
            request,
            organization,
            &self.binding.account_id,
            access_token,
        )?;
        self.revalidate()?;
        match reply {
            Reply::Resource(value) => Ok(value),
            Reply::Refused(code) => Err(super::grants::refusal(code)),
        }
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

    pub(super) fn visibility(&self, route: &str, body: Option<&[u8]>) -> Result<serde_json::Value> {
        self.revalidate()?;
        if !self.verified || self.offline {
            return Err(refused("account_origin_or_authorization_mismatch"));
        }
        let Session::Authorized { access_token, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        let reply = self.api.visibility(route, body, access_token)?;
        self.revalidate()?;
        match reply {
            Reply::Resource(value) => Ok(value),
            Reply::Refused(code) => Err(super::visibility::refusal(code)),
        }
    }

    pub(super) fn reports(
        &self,
        id: Option<&str>,
        cursor: Option<&str>,
        body: Option<&[u8]>,
    ) -> Result<serde_json::Value> {
        self.revalidate()?;
        if !self.verified || self.offline {
            return Err(refused("account_origin_or_authorization_mismatch"));
        }
        let Session::Authorized { access_token, .. } = &self.state.session else {
            return Err(refused("account_required"));
        };
        let reply = self.api.reports(id, cursor, body, access_token)?;
        self.revalidate()?;
        match reply {
            Reply::Resource(value) => Ok(value),
            Reply::Refused(code) => Err(super::reports::refusal(code)),
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
        let signature = self.state.plan.sign(
            &self.identity,
            crate::attestation::contract::hash(record)?.as_bytes(),
        )?;
        self.revalidate()?;
        Ok(signature)
    }

    pub(crate) fn owned_registry(&self) -> Result<crate::store::Store> {
        self.revalidate()?;
        let store = crate::store::Store::open_at(self.identity.root_directory(), false)?;
        self.check_registry_owner(&store.connection)?;
        Ok(store)
    }

    /// Local authoring and remote transport devices are independent. Only a
    /// verified transfer at this origin can authorize a named enrollment.
    pub(crate) fn owns_registry(&self, connection: &rusqlite::Connection) -> Result<bool> {
        self.revalidate()?;
        let owner = super::attachment::effective(connection, &self.identity)?;
        let origin = super::attachment::owner_origin(connection, &self.identity)?;
        let qualified = match origin {
            Some(origin) => origin == self.binding.origin,
            None => self.binding.connection.is_none() && owner.device_id == self.binding.device_id,
        };
        self.revalidate()?;
        Ok(qualified && owner.account_id == self.binding.account_id)
    }

    pub(crate) fn check_registry_owner(&self, connection: &rusqlite::Connection) -> Result<()> {
        if !self.owns_registry(connection)? {
            return Err(refused("registry_owner_not_attached"));
        }
        Ok(())
    }

    pub(crate) fn publication_recovered(
        &self,
        binding: &Binding,
        receipt: &crate::publication::interruption::Receipt,
    ) -> Result<()> {
        self.revalidate()?;
        if self.binding.connection.is_some() || binding.connection.is_some() {
            return Err(refused(
                "enrollment_recovery_requires_its_original_connection",
            ));
        }
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
        if let Some(connection) = &self.connection {
            connection.validate()?;
            if connection.origin != self.origin
                || connection.device_id != self.device_id
                || connection.public_key != self.public_key
                || connection.credential_store != self.credential_store
            {
                return Err(refused("account_binding_invalid"));
            }
        }
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
