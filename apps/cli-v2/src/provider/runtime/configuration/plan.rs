//! Exact configuration intent and physical state bindings; no serialized trust grant.

use jiff::Timestamp;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Component, Path};

use super::{
    effects::{self, Effect},
    invalid,
};
use crate::{
    digest,
    error::Result,
    passport,
    projection::Scope,
    provider::plan::{Request, hash},
    wire,
};

pub(super) const LIMIT: usize = crate::provider::runtime::CONFIGURATION_PLAN_BYTES;
pub(super) type Identity = [String; 2];

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub state_parent: String,
    pub state_identity: Identity,
    pub target_path: String,
    pub target_scope: Scope,
    pub target_identity: Identity,
    pub harness_id: String,
    pub provider_version: String,
    pub archive_digest: String,
    pub executable_digest: String,
    pub info_digest: String,
    pub provider_plan: Value,
    pub status_before: Value,
    pub attachment_path: Option<String>,
    pub setup: Value,
    pub ownership: Value,
    pub effects: Vec<Effect>,
}

fn path(value: &str) -> bool {
    value.len() <= 4096
        && Path::new(value).is_absolute()
        && Path::new(value)
            .components()
            .all(|part| matches!(part, Component::Normal(_) | Component::RootDir))
}

impl Plan {
    pub fn parse(bytes: &[u8], expected: &str) -> Result<Self> {
        if bytes.len() > LIMIT || !hash(expected) {
            return Err(invalid());
        }
        let value = wire::parse(bytes)?;
        if fingerprint(&value)? != expected {
            return Err(invalid());
        }
        let plan: Self = serde_json::from_value(value).map_err(|_| invalid())?;
        let created = plan
            .created_at
            .parse::<Timestamp>()
            .map_err(|_| invalid())?;
        let expires = plan
            .expires_at
            .parse::<Timestamp>()
            .map_err(|_| invalid())?;
        if plan.schema_version != 1
            || !passport::stable_id(&plan.operation_id, "operation")
            || !passport::timestamp(&plan.created_at)
            || !passport::timestamp(&plan.expires_at)
            || expires
                != created
                    .checked_add(std::time::Duration::from_secs(900))
                    .map_err(|_| invalid())?
            || !path(&plan.state_parent)
            || !path(&plan.target_path)
            || [&plan.state_identity, &plan.target_identity]
                .into_iter()
                .flatten()
                .any(|value| {
                    !value
                        .parse::<u64>()
                        .is_ok_and(|number| number.to_string() == *value)
                })
            || [
                &plan.archive_digest,
                &plan.executable_digest,
                &plan.info_digest,
            ]
            .iter()
            .any(|value| !hash(value))
            || plan
                .attachment_path
                .as_deref()
                .is_some_and(|path| !crate::archive::safe_path(path))
        {
            return Err(invalid());
        }
        crate::provider::status::validate(&plan.status_before)?;
        if plan.status_before["configuration_ownership"].is_null()
            || plan.status_before["canonical_target"] != plan.target_path
            || plan.status_before["harness_id"] != plan.harness_id
        {
            return Err(invalid());
        }
        crate::provider::status::ownership_paths(&plan.ownership)?;
        let inner = &plan.provider_plan["plan"];
        if inner["operation_id"] != plan.operation_id
            || inner["expires_at"] != plan.expires_at
            || inner["canonical_target"] != plan.target_path
            || inner["provider_version"] != plan.provider_version
            || inner["provider_release_digest"] != plan.executable_digest
            || inner["operation"] != plan.operation()?
        {
            return Err(invalid());
        }
        if plan.operation()? == "remove" {
            if !plan.setup.is_null() || plan.ownership != json!([]) {
                return Err(invalid());
            }
        } else if plan.setup.as_object().is_none_or(|setup| setup.len() != 3)
            || !passport::stable_id(
                plan.setup["stable_id"].as_str().ok_or_else(invalid)?,
                "setup",
            )
            || !hash(plan.setup["passport_digest"].as_str().ok_or_else(invalid)?)
            || !passport::version_number(plan.setup["version"].as_str().ok_or_else(invalid)?)
        {
            return Err(invalid());
        }
        plan.request(created)?;
        effects::validate(&plan.effects)?;
        Ok(plan)
    }

    pub fn operation(&self) -> Result<&str> {
        self.action
            .strip_prefix("configuration.")
            .filter(|value| matches!(*value, "install" | "replace" | "remove"))
            .ok_or_else(invalid)
    }

    pub fn request(&self, at: Timestamp) -> Result<Request> {
        Request::parse(&serde_json::to_vec(&json!({
            "operation":self.operation()?,"operation_id":self.operation_id,"expires_at":self.expires_at,
            "bundle":self.provider_plan["plan"]["bundle"],"recovery_mode":"forward",
        })).map_err(|_| invalid())?, at)
    }

    pub fn value(&self) -> Result<Value> {
        serde_json::to_value(self).map_err(|_| invalid())
    }
}

pub(super) fn fingerprint(value: &Value) -> Result<String> {
    digest::bytes(
        "ai-stp:installation-operation:v1",
        &serde_json_canonicalizer::to_vec(value).map_err(|_| invalid())?,
    )
}
