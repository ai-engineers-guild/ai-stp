//! Exact local intent and the original server-authored link decision.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Binding, Context, corporate, invalid};
use crate::{authoring, canonical, digest, error::Result, files, passport, wire};

pub(super) const LIMIT: u64 = 262144;
pub(super) const KIND: &str = "corporate.project_link";
static REQUEST: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/project-link-plan-request.schema.json"
)));
static CONFIRM: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/project-link-request.schema.json"
)));
static SERVER_PLAN: wire::Schema = wire::Schema::definition(
    include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/resources/schemas/v1/project-link-plan-outcome.schema.json"
    )),
    "ProjectLinkPlanResponse",
);

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Snapshot {
    pub context: Context,
    pub account: Binding,
    pub organization: Value,
    pub observation: Value,
    pub local_project: Value,
    pub checkout: Value,
    pub target: Value,
    pub selected_provider: Option<Value>,
    pub request_coordinates: Value,
}

impl Snapshot {
    pub fn from_preview(value: &Value) -> Result<Self> {
        let value = &value["preview"];
        let snapshot = Self {
            context: serde_json::from_value(value["context"].clone()).map_err(|_| invalid())?,
            account: serde_json::from_value(value["account"].clone()).map_err(|_| invalid())?,
            organization: value["organization"].clone(),
            observation: value["observation"].clone(),
            local_project: value["local_project"].clone(),
            checkout: value["checkout"].clone(),
            target: value["target"].clone(),
            selected_provider: value["selected_provider"]
                .as_object()
                .map(|_| value["selected_provider"].clone()),
            request_coordinates: value["request_coordinates"].clone(),
        };
        snapshot.validate()?;
        Ok(snapshot)
    }

    pub fn organization_id(&self) -> Result<&str> {
        self.organization["organization_id"]
            .as_str()
            .ok_or_else(invalid)
    }

    pub fn project_id(&self) -> Result<&str> {
        self.local_project["local_project_id"]
            .as_str()
            .ok_or_else(invalid)
    }

    pub fn validate(&self) -> Result<()> {
        self.context.digest()?;
        self.account.validate()?;
        let organizations = super::contexts::organizations_projection(
            &json!({"schema_version":1,"items":[self.organization]}),
        )?;
        if organizations["items"][0] != self.organization
            || super::contexts::active_projection(&self.observation)? != self.observation
        {
            return Err(invalid());
        }
        let super::contexts::Authority::Remote {
            account,
            organization,
            ..
        } = &self.context.authority
        else {
            return Err(invalid());
        };
        let mut original = account.as_ref().clone();
        original.revision.clone_from(&self.account.revision);
        let remote_project = self.request_coordinates["remote_project_id"]
            .as_str()
            .ok_or_else(invalid)?;
        let target = corporate::Request::LinkTarget {
            project_id: remote_project.into(),
        }
        .project(
            &self.target,
            self.organization_id()?,
            &self.account.account_id,
        )?;
        let provider_id = self
            .selected_provider
            .as_ref()
            .map(|p| &p["provider_project_id"]);
        let provider_revision = self
            .selected_provider
            .as_ref()
            .map(|p| {
                p["revision"]
                    .as_u64()
                    .map(|n| n.to_string())
                    .ok_or_else(invalid)
            })
            .transpose()?;
        let expected = json!({"schema_version":1,
            "local_project_id":self.local_project["local_project_id"],
            "local_revision":self.local_project["local_revision"],
            "remote_project_id":target["remote_project_id"],
            "remote_revision":target["remote_revision"],
            "provider_project_id":provider_id,"provider_revision":provider_revision,
            "authorization_revision":target["authorization_revision"]});
        if original != self.account
            || organization["organization_id"] != self.organization["organization_id"]
            || self.organization["kind"] != "corporate"
            || self.observation["organization_id"] != self.organization["organization_id"]
            || self.observation["capabilities"]["authorization_revision"]
                != target["authorization_revision"]
            || self.local_project["owner_account_id"] != self.context.local_identity.account_id
            || !passport::stable_id(self.project_id()?, "project")
            || self.local_project["root"]["identity"]
                != self.checkout["checkout"]["topology"]["root"]["identity"]
            || self.checkout["checkout"]["head_state"] != "attached"
            || self.target != target
            || self.request_coordinates != expected
            || self.selected_provider.as_ref().is_some_and(|provider| {
                !target["providers"]
                    .as_array()
                    .is_some_and(|items| items.contains(provider))
            })
        {
            return Err(invalid());
        }
        let mut request = self.request_coordinates.clone();
        request["idempotency_key"] = "native-link-coordinate-validation".into();
        REQUEST.validate(&request)
    }

    pub fn unchanged(&self, fresh: &Self) -> Result<()> {
        self.validate()?;
        fresh.validate()?;
        if self.context != fresh.context
            || self.account != fresh.account
            || self.local_project != fresh.local_project
            || self.checkout != fresh.checkout
            || self.request_coordinates != fresh.request_coordinates
            || super::coordinates(&self.target) != super::coordinates(&fresh.target)
            || corporate::authority(&self.organization, &self.observation)
                != corporate::authority(&fresh.organization, &fresh.observation)
        {
            return Err(invalid());
        }
        Ok(())
    }
}

// Open wire response fields are dropped by deserialization. A local plan reader
// separately compares its original JSON digest, refusing unbound extra fields.
#[derive(Clone, Deserialize, Serialize, PartialEq)]
pub(super) struct ServerPlan {
    pub schema_version: u32,
    pub plan_id: String,
    pub organization_id: String,
    pub local_project_id: String,
    pub remote_project_id: String,
    pub provider_project_id: Option<String>,
    pub local_revision: String,
    pub remote_revision: String,
    pub provider_revision: Option<String>,
    pub authorization_revision: String,
    pub plan_digest: String,
    pub expires_at: String,
}

/// Match the server's Python JSON encoding, including its default ASCII escape
/// policy. This is deliberately distinct from the native canonical-plan format.
fn server_bytes(value: &Value) -> Result<Vec<u8>> {
    use std::fmt::Write;
    let fields: std::collections::BTreeMap<_, _> =
        value.as_object().ok_or_else(invalid)?.iter().collect();
    if fields
        .values()
        .any(|value| !value.is_string() && !value.is_null())
    {
        return Err(invalid());
    }
    let text = serde_json::to_string(&fields).map_err(|_| invalid())?;
    let mut encoded = String::with_capacity(text.len());
    for character in text.chars() {
        if character >= '\u{7f}' {
            let mut units = [0; 2];
            for unit in character.encode_utf16(&mut units) {
                write!(&mut encoded, "\\u{unit:04x}").map_err(|_| invalid())?;
            }
        } else {
            encoded.push(character);
        }
    }
    Ok(encoded.into_bytes())
}

impl ServerPlan {
    pub fn read(value: &Value, original: &Snapshot) -> Result<Self> {
        SERVER_PLAN.validate(value)?;
        let plan: Self = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
        plan.verify(original)?;
        Ok(plan)
    }

    pub fn verify(&self, original: &Snapshot) -> Result<()> {
        original.validate()?;
        let mut preimage = original.request_coordinates.clone();
        preimage
            .as_object_mut()
            .ok_or_else(invalid)?
            .remove("schema_version");
        preimage["organization_id"] = original.organization_id()?.into();
        preimage["actor_account_id"] = original.account.account_id.clone().into();
        preimage["device_id"] = original.account.device_id.clone().into();
        preimage["expires_at"] = self.expires_at.clone().into();
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        SERVER_PLAN.validate(&value)?;
        for field in [
            "local_project_id",
            "remote_project_id",
            "provider_project_id",
            "local_revision",
            "remote_revision",
            "provider_revision",
            "authorization_revision",
        ] {
            if value[field] != original.request_coordinates[field] {
                return Err(invalid());
            }
        }
        if self.organization_id != original.organization_id()?
            || self.plan_digest != digest::sha256(&server_bytes(&preimage)?)
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
pub(super) enum Change {
    Request {
        snapshot: Box<Snapshot>,
    },
    Confirm {
        request_operation_id: String,
        snapshot: Box<Snapshot>,
        server_plan: ServerPlan,
    },
    Adopt {
        request_operation_id: String,
        snapshot: Box<Snapshot>,
        outcome: Value,
    },
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub(super) schema_version: u32,
    pub(super) operation_id: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub(super) state_parent: PathBuf,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub(super) checkout_root: PathBuf,
    pub(super) created_at: String,
    pub(super) expires_at: String,
    pub(super) registry_schema_before: u32,
    pub(super) change: Change,
}

impl Plan {
    pub(super) fn snapshot(&self) -> &Snapshot {
        match &self.change {
            Change::Request { snapshot }
            | Change::Confirm { snapshot, .. }
            | Change::Adopt { snapshot, .. } => snapshot,
        }
    }

    pub fn digest(&self) -> Result<String> {
        let snapshot = self.snapshot();
        snapshot.validate()?;
        if self.schema_version != 1
            || !passport::stable_id(&self.operation_id, "operation")
            || !self.state_parent.is_absolute()
            || !self.checkout_root.is_absolute()
            || snapshot.context.root != self.state_parent
            || authoring::expiry(&self.created_at)? != self.expires_at
            || ![55, 56, 57].contains(&self.registry_schema_before)
        {
            return Err(invalid());
        }
        match &self.change {
            Change::Request { .. } => (),
            Change::Confirm {
                request_operation_id,
                ..
            }
            | Change::Adopt {
                request_operation_id,
                ..
            } if !passport::stable_id(request_operation_id, "operation")
                || request_operation_id == &self.operation_id =>
            {
                return Err(invalid());
            }
            _ => (),
        }
        if let Change::Confirm { server_plan, .. } = &self.change {
            server_plan.verify(snapshot)?;
        }
        if let Change::Adopt { outcome, .. } = &self.change {
            let plan_id = outcome["plan"]["plan_id"].as_str().ok_or_else(invalid)?;
            let projected = corporate::Request::LinkOutcome {
                plan_id: plan_id.into(),
            }
            .project(
                outcome,
                snapshot.organization_id()?,
                &snapshot.account.account_id,
            )?;
            if projected != *outcome
                || outcome["state"] != "applied"
                || outcome["link"]["state"] != "linked"
                || outcome["authorization_revision"] != snapshot.target["authorization_revision"]
            {
                return Err(invalid());
            }
        }
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        if canonical::bytes(&value)?.len() as u64 > LIMIT {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }

    pub(super) fn request_key(&self) -> String {
        format!("native.project-link.request.{}", self.operation_id)
    }

    pub(super) fn request_body(&self) -> Result<Value> {
        let mut value = match &self.change {
            Change::Request { snapshot } => {
                let mut value = snapshot.request_coordinates.clone();
                value["idempotency_key"] = self.request_key().into();
                REQUEST.validate(&value)?;
                return Ok(value);
            }
            Change::Confirm { server_plan, .. } => json!({"schema_version":1,
                "plan_id":server_plan.plan_id,"plan_digest":server_plan.plan_digest,
                "authorization_revision":server_plan.authorization_revision}),
            Change::Adopt { .. } => return Err(invalid()),
        };
        value["idempotency_key"] =
            format!("native.project-link.confirm.{}", self.operation_id).into();
        CONFIRM.validate(&value)?;
        Ok(value)
    }
}
