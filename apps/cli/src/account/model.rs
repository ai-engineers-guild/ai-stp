//! Public intent and private credential state have separate serialization owners.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::PathBuf;
use zeroize::Zeroizing;

use crate::{authoring, digest, error::Result, files, identity, passport};

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    Import,
    Start,
    Poll,
    Refresh,
    Logout,
    Attach,
    Recover,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: Action,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub root: PathBuf,
    pub root_identity: [String; 2],
    pub identity: authoring::Identity,
    pub public_key: String,
    pub credential_store: identity::Storage,
    pub origin: String,
    pub provider: String,
    pub expected_revision: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub attachment: Option<super::attachment::Selection>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recovery: Option<identity::recovery::Intent>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expected_account_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub revoked_public_key: Option<String>,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| super::invalid())?,
        )
    }

    pub(crate) fn validate(&self) -> Result<()> {
        self.identity.validate()?;
        match (&self.attachment, self.action) {
            (Some(selection), Action::Attach) => selection.validate(&self.identity)?,
            (None, action) if action != Action::Attach => {}
            _ => return Err(super::invalid()),
        }
        match (&self.recovery, self.action) {
            (Some(intent), Action::Recover) => intent.validate(&self.identity)?,
            (None, action) if action != Action::Recover => {}
            _ => return Err(super::invalid()),
        }
        if self.schema_version != 1
            || !passport::stable_id(&self.operation_id, "operation")
            || !self.root.is_absolute()
            || !matches!(self.provider.as_str(), "github" | "google")
            || self.expires_at != authoring::expiry(&self.created_at)?
            || self
                .expected_revision
                .as_ref()
                .is_some_and(|v| !passport::stable_id(v, "operation"))
            || super::transport::origin(&self.origin)? != self.origin
            || self
                .expected_account_id
                .as_ref()
                .is_some_and(|id| !passport::stable_id(id, "account"))
        {
            return Err(super::invalid());
        }
        Ok(())
    }
}

/// Deliberately has no Debug, Clone or conversion into a public JSON value.
pub(super) struct Secret(pub Zeroizing<String>);

impl Serialize for Secret {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for Secret {
    fn deserialize<D: serde::Deserializer<'de>>(
        deserializer: D,
    ) -> std::result::Result<Self, D::Error> {
        let value = Zeroizing::new(String::deserialize(deserializer)?);
        if value.is_empty()
            || value.len() > 4096
            || value
                .bytes()
                .any(|b| b.is_ascii_control() || b.is_ascii_whitespace())
        {
            return Err(serde::de::Error::custom("invalid private credential"));
        }
        Ok(Self(value))
    }
}

#[derive(Deserialize, Serialize)]
#[serde(tag = "state", rename_all = "snake_case", deny_unknown_fields)]
pub(super) enum Session {
    Pending {
        device_code: Secret,
        user_code: String,
        verification_uri: String,
        verification_uri_complete: String,
        expires_at: String,
        interval: u64,
        next_poll_at: String,
    },
    Authorized {
        account_id: String,
        access_token: Secret,
        refresh_token: Secret,
        expires_at: String,
    },
    Closed {
        reason: String,
    },
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct State {
    pub plan: Plan,
    pub revision: String,
    pub session: Session,
    pub outcome: Outcome,
    pub completed_at: String,
}

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub(super) enum Outcome {
    Pending,
    Authorized,
    Closed,
    Expired,
    Declined,
    Revoked,
    DeviceReplaced,
    RateLimited,
    ExchangeUnknown,
    RequestUnknown,
    Refused,
    LocallyClosed,
    #[serde(rename = "locally_closed_unconfirmed")]
    LogoutUnconfirmed,
}

impl State {
    pub fn public(&self, at: &str) -> Value {
        let session = match &self.session {
            Session::Pending {
                user_code,
                verification_uri,
                verification_uri_complete,
                expires_at,
                interval,
                next_poll_at,
                ..
            } => {
                json!({"state":if at >= expires_at.as_str() {"expired"} else {"pending"},"user_code":user_code,"verification_uri":verification_uri,"verification_uri_complete":verification_uri_complete,"expires_at":expires_at,"interval":interval,"next_poll_at":next_poll_at})
            }
            Session::Authorized {
                account_id,
                expires_at,
                ..
            } => {
                json!({"state":"authorized","account_id":account_id,"access_expires_at":expires_at,"access_expired":at >= expires_at.as_str()})
            }
            Session::Closed { reason } => json!({"state":"closed","reason":reason}),
        };
        json!({"schema_version":1,"revision":self.revision,"origin":self.plan.origin,"provider":self.plan.provider,"device_id":self.plan.identity.device_id,"local_owner_id":self.plan.identity.account_id,"owner_attached":false,"online_verified":false,"session":session})
    }

    pub fn receipt(&self) -> Result<Receipt> {
        Ok(Receipt {
            plan: self.plan.clone(),
            plan_digest: self.plan.digest()?,
            outcome: self.outcome,
            completed_at: self.completed_at.clone(),
            account_id: match &self.session {
                Session::Authorized { account_id, .. } => Some(account_id.clone()),
                _ => None,
            },
        })
    }
}

/// Permanent replay evidence intentionally excludes credentials and browser codes.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Receipt {
    pub plan: Plan,
    pub plan_digest: String,
    pub outcome: Outcome,
    pub completed_at: String,
    pub account_id: Option<String>,
}

impl Receipt {
    pub fn validate(&self) -> Result<()> {
        self.plan.validate()?;
        if self.plan.digest()? != self.plan_digest
            || !passport::timestamp(&self.completed_at)
            || self
                .account_id
                .as_ref()
                .is_some_and(|v| !passport::stable_id(v, "account"))
            || (self.outcome == Outcome::DeviceReplaced) != (self.plan.action == Action::Recover)
        {
            return Err(super::invalid());
        }
        Ok(())
    }
    pub fn public(&self) -> Value {
        let mut value = json!({"schema_version":1,"operation_id":self.plan.operation_id,"plan_digest":self.plan_digest,"action":self.plan.action,"outcome":self.outcome,"completed_at":self.completed_at,"account_id":self.account_id,"owner_attached":false,"warnings":if self.outcome==Outcome::LogoutUnconfirmed {vec!["remote_logout_unconfirmed"]} else {vec![]}});
        if let Some(intent) = &self.plan.recovery {
            value["device_id"] = intent.device_id.clone().into();
            value["retired_device_id"] = self.plan.identity.device_id.clone().into();
        }
        value
    }
}

pub(super) fn after(at: &str, seconds: u64) -> Result<String> {
    let timestamp: jiff::Timestamp = at.parse().map_err(|_| super::invalid())?;
    let value = timestamp
        .checked_add(std::time::Duration::from_secs(seconds))
        .map_err(|_| super::invalid())?;
    Ok(format!("{value:.3}"))
}
