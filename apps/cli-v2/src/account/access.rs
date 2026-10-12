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
    verified: bool,
    offline: bool,
}

impl Access {
    pub fn load(root: &Path, origin: &str, offline: bool) -> Result<Self> {
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
        if super::transport::origin(origin)? != state.plan.origin {
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
        let account = match Api::new(&self.binding.origin)?.me(access_token)? {
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
