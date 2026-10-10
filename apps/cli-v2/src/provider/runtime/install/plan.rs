//! Exact installation intent; decoding does not establish component trust.

use std::path::{Component, Path};

use jiff::Timestamp;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{
    digest,
    error::{Failure, Result},
    passport,
    projection::Scope,
    provider::{plan::hash, software::Request},
    wire,
};

pub(super) const LIMIT: usize = 64 * 1024;
pub(super) type Identity = [String; 2];

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Target {
    pub path: String,
    pub scope: String,
    pub identity: Identity,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Prefix {
    pub path: String,
    pub expected_state: String,
    pub parent_identity: Identity,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ComponentIdentity {
    pub archive_digest: String,
    pub executable_digest: String,
    pub info_digest: String,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub state_parent: String,
    pub state_parent_identity: Identity,
    pub harness_id: String,
    pub provider_version: String,
    pub target: Target,
    pub prefix: Prefix,
    pub component: ComponentIdentity,
    pub provider_plan: Value,
}

pub(super) fn invalid() -> Failure {
    Failure::precondition(
        "the original program installation plan or its physical binding is invalid",
    )
}

fn path(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 4096
        && Path::new(value).is_absolute()
        && Path::new(value)
            .components()
            .all(|part| matches!(part, Component::RootDir | Component::Normal(_)))
}

pub(super) fn valid_identity(value: &Identity) -> bool {
    value.iter().all(|part| {
        part.parse::<u64>()
            .is_ok_and(|number| number.to_string() == *part)
    })
}

impl Plan {
    pub fn parse(bytes: &[u8], expected: &str) -> Result<Self> {
        if bytes.len() > LIMIT || !hash(expected) {
            return Err(invalid());
        }
        let document = wire::parse(bytes)?;
        let canonical = serde_json_canonicalizer::to_vec(&document).map_err(|_| invalid())?;
        if digest::bytes("ai-stp:installation-operation:v1", &canonical)? != expected {
            return Err(invalid());
        }
        let plan: Self = serde_json::from_value(document).map_err(|_| invalid())?;
        let created = plan
            .created_at
            .parse::<Timestamp>()
            .map_err(|_| invalid())?;
        let expires = plan
            .expires_at
            .parse::<Timestamp>()
            .map_err(|_| invalid())?;
        if plan.schema_version != 1
            || plan.action != "program.install"
            || !passport::stable_id(&plan.operation_id, "operation")
            || !passport::timestamp(&plan.created_at)
            || !passport::timestamp(&plan.expires_at)
            || expires
                != created
                    .checked_add(std::time::Duration::from_secs(900))
                    .map_err(|_| invalid())?
            || !path(&plan.state_parent)
            || !path(&plan.target.path)
            || !path(&plan.prefix.path)
            || !valid_identity(&plan.state_parent_identity)
            || !valid_identity(&plan.target.identity)
            || !valid_identity(&plan.prefix.parent_identity)
            || plan.prefix.expected_state != "missing"
            || [
                &plan.component.archive_digest,
                &plan.component.executable_digest,
                &plan.component.info_digest,
            ]
            .iter()
            .any(|value| !hash(value))
        {
            return Err(invalid());
        }
        plan.scope()?;
        let inner = &plan.provider_plan["plan"];
        if inner["operation_id"] != plan.operation_id
            || inner["expires_at"] != plan.expires_at
            || inner["canonical_target"] != plan.target.path
            || inner["software_prefix"] != plan.prefix.path
            || inner["provider_version"] != plan.provider_version
            || inner["provider_release_digest"] != plan.component.executable_digest
            || inner["operation"] != "software_install"
        {
            return Err(invalid());
        }
        // Creation-time validation accepts expired original intents for history
        // lookup. First admission separately enforces the current deadline.
        plan.request(created)?;
        Ok(plan)
    }

    pub fn scope(&self) -> Result<Scope> {
        match self.target.scope.as_str() {
            "global" => Ok(Scope::Global),
            "project" => Ok(Scope::Project),
            "user_root" => Ok(Scope::UserRoot),
            _ => Err(invalid()),
        }
    }

    pub fn request(&self, at: Timestamp) -> Result<Request> {
        Request::parse(
            &serde_json::to_vec(&json!({
                "operation":"software_install", "operation_id":self.operation_id,
                "expires_at":self.expires_at,
                "software_version":self.provider_plan["plan"]["software_version"],
            }))
            .map_err(|_| invalid())?,
            at,
        )
    }

    pub fn value(&self) -> Result<Value> {
        serde_json::to_value(self).map_err(|_| invalid())
    }
}
