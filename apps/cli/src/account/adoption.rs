//! Preserve an existing session without claiming a fresh authorization response.

use cap_std::fs::Dir;
use serde::{Deserialize, Serialize};
use zeroize::Zeroizing;

use super::{Action, Outcome, Plan, Session, State, invalid, journal::Journal, model::Secret};
use crate::{
    authoring,
    error::Result,
    identity::{self, Storage},
    passport,
};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Metadata {
    pub account_id: String,
    pub device_id: String,
    pub expires_at: String,
    pub revoked: bool,
}

fn read(parent: &Dir, storage: Storage, device: &str) -> Result<Option<(Metadata, Session)>> {
    if identity::legacy::read(parent, storage, "pending-authorization")?.is_some() {
        return Err(invalid());
    }
    let Some(mut value) = identity::legacy::read(parent, storage, "cloud-credentials")? else {
        return Ok(None);
    };
    let field = |key: &str| value.get(key).cloned().ok_or_else(invalid);
    let metadata = Metadata {
        account_id: field("account_id")?,
        device_id: field("device_id")?,
        expires_at: field("expires_at")?,
        revoked: value.get("state").is_some_and(|v| v == "revoked"),
    };
    if metadata.device_id != device
        || value
            .get("state")
            .is_some_and(|state| !matches!(state.as_str(), "active" | "revoked"))
        || !passport::stable_id(&metadata.account_id, "account")
        || !passport::timestamp(&metadata.expires_at)
        || value.keys().any(|key| {
            !matches!(
                key.as_str(),
                "account_id"
                    | "device_id"
                    | "expires_at"
                    | "state"
                    | "access_token"
                    | "refresh_token"
            )
        })
    {
        return Err(invalid());
    }
    let session = if metadata.revoked {
        Session::Closed {
            reason: "device_revoked".into(),
        }
    } else {
        let take =
            |value: &mut std::collections::BTreeMap<String, String>, key: &str| -> Result<Secret> {
                let secret = Zeroizing::new(value.remove(key).ok_or_else(invalid)?);
                if secret.is_empty()
                    || secret.len() > 4096
                    || secret
                        .bytes()
                        .any(|b| b.is_ascii_whitespace() || b.is_ascii_control())
                {
                    return Err(invalid());
                }
                Ok(Secret(secret))
            };
        Session::Authorized {
            account_id: metadata.account_id.clone(),
            expires_at: metadata.expires_at.clone(),
            access_token: take(&mut value, "access_token")?,
            refresh_token: take(&mut value, "refresh_token")?,
        }
    };
    Ok(Some((metadata, session)))
}

pub(crate) fn inspect(parent: &Dir, storage: Storage, device: &str) -> Result<Option<Metadata>> {
    read(parent, storage, device).map(|value| value.map(|(metadata, _)| metadata))
}

pub(crate) fn apply(
    identity: &identity::Identity,
    expected: &Option<Metadata>,
    operation: &str,
    origin: &str,
    provider: &str,
    at: &str,
) -> Result<()> {
    let existing = Journal::open(identity, false)?;
    if let Some(journal) = &existing
        && let Some(held) = journal.state()?
    {
        if held.plan.action != Action::Import
            || held.plan.operation_id != operation
            || held.plan.origin != origin
            || held.plan.provider != provider
            || held.plan.identity != identity.context()
            || held.plan.public_key != identity.report()["public_key"]
            || !matches_metadata(&held.session, expected)
        {
            return Err(invalid());
        }
        journal.complete(&held)?;
        return Ok(());
    }
    let current = read(
        identity.root_directory(),
        identity.storage(),
        &identity.context().device_id,
    )?;
    if current.as_ref().map(|(metadata, _)| metadata) != expected.as_ref() {
        return Err(invalid());
    }
    let Some((metadata, session)) = current else {
        return Ok(());
    };
    let plan = Plan {
        schema_version: 1,
        action: Action::Import,
        operation_id: operation.into(),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        root: identity.root_binding().0.into(),
        root_identity: identity.root_binding().1.clone(),
        identity: identity.context(),
        public_key: identity.report()["public_key"]
            .as_str()
            .ok_or_else(invalid)?
            .into(),
        credential_store: identity.storage(),
        origin: super::transport::origin(origin)?,
        provider: provider.into(),
        expected_revision: None,
        attachment: None,
        recovery: None,
        expected_account_id: None,
        revoked_public_key: None,
        connection: None,
    };
    let state = State {
        revision: operation.into(),
        plan,
        session,
        outcome: if metadata.revoked {
            Outcome::Revoked
        } else {
            Outcome::Authorized
        },
        completed_at: at.into(),
    };
    let journal = match existing {
        Some(journal) => journal,
        None => Journal::open(identity, true)?.ok_or_else(invalid)?,
    };
    journal.write(&state)?;
    let observed = journal.state()?.ok_or_else(invalid)?;
    if observed.public(at) != state.public(at) {
        return Err(invalid());
    }
    journal.complete(&state)?;
    Ok(())
}

fn matches_metadata(session: &Session, expected: &Option<Metadata>) -> bool {
    match (session, expected) {
        (
            Session::Authorized {
                account_id,
                expires_at,
                ..
            },
            Some(metadata),
        ) => {
            !metadata.revoked
                && account_id == &metadata.account_id
                && expires_at == &metadata.expires_at
        }
        (Session::Closed { reason }, Some(metadata)) => {
            metadata.revoked && reason == "device_revoked"
        }
        _ => false,
    }
}

pub(crate) fn retire_source(
    identity: &identity::Identity,
    expected: &Option<Metadata>,
) -> Result<()> {
    let Some(value) = identity::legacy::read(
        identity.root_directory(),
        identity.storage(),
        "cloud-credentials",
    )?
    else {
        return Ok(());
    };
    let current = read(
        identity.root_directory(),
        identity.storage(),
        &identity.context().device_id,
    )?
    .ok_or_else(invalid)?;
    if Some(&current.0) != expected.as_ref() {
        return Err(invalid());
    }
    let journal = Journal::open(identity, false)?.ok_or_else(invalid)?;
    let state = journal.state()?.ok_or_else(invalid)?;
    let equal = match (&state.session, &current.1) {
        (
            Session::Authorized {
                access_token: a,
                refresh_token: r,
                ..
            },
            Session::Authorized {
                access_token: b,
                refresh_token: s,
                ..
            },
        ) => a.0 == b.0 && r.0 == s.0,
        (Session::Closed { reason: a }, Session::Closed { reason: b }) => a == b,
        _ => false,
    };
    if !equal {
        return Err(invalid());
    }
    identity::legacy::retire(
        identity.root_directory(),
        identity.storage(),
        "cloud-credentials",
        &value,
    )
}

pub(crate) fn origin(value: &str) -> Result<String> {
    super::transport::origin(value)
}
