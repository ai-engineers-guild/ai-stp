//! Exact actor, native binding and server-authored unlink decision.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use super::{Binding, Context, contexts, corporate, invalid, project_links};
use crate::{
    authoring, canonical, digest,
    error::Result,
    files, passport,
    store::{has_checkout_links, unlink_schema_after},
    wire,
};

pub(super) const KIND: &str = "corporate.project_unlink";
pub(super) const LIMIT: u64 = 262144;

pub(super) fn confirmation_id(request: &str) -> Result<String> {
    if !passport::stable_id(request, "operation") {
        return Err(invalid());
    }
    // All reviews of one original request share one confirmation slot/key.
    // Admission binds its exact plan digest; later reviews cannot mint a retry.
    let hash: [u8; 32] = Sha256::digest(canonical::bytes(&json!([
        "ai-stp-native-project-unlink-confirmation/1",
        request
    ]))?)
    .into();
    let mut identity = [0; 16];
    identity.copy_from_slice(&hash[..16]);
    Ok(format!("operation_{}", ulid::Ulid::from_bytes(identity)))
}
static REQUEST: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/project-unlink-plan-request.schema.json"
)));
static CONFIRM: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/project-unlink-request.schema.json"
)));

pub(super) fn validate_write(confirm: bool, value: &Value) -> Result<()> {
    if confirm {
        CONFIRM.validate(value)
    } else {
        REQUEST.validate(value)
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(super) struct Snapshot {
    pub local_identity: authoring::Identity,
    pub binding: project_links::binding::Snapshot,
    pub context: Context,
    pub account: Binding,
    pub organization: Value,
    pub observation: Value,
    pub remote_link: Value,
}

impl Snapshot {
    pub fn organization_id(&self) -> Result<&str> {
        self.organization["organization_id"]
            .as_str()
            .ok_or_else(invalid)
    }
    pub fn validate(&self) -> Result<()> {
        self.validate_state(false)
    }
    pub(super) fn validate_unlinked(&self) -> Result<()> {
        self.validate_state(true)
    }
    fn validate_state(&self, unlinked: bool) -> Result<()> {
        self.local_identity.validate()?;
        self.context.digest()?;
        self.account.validate()?;
        self.binding.source.validate()?;
        self.binding.request.validate()?;
        self.binding.context.digest()?;
        self.binding.account.validate()?;
        let contexts::Authority::Remote {
            account,
            organization,
            ..
        } = &self.context.authority
        else {
            return Err(invalid());
        };
        let contexts::Authority::Remote {
            organization: original_organization,
            ..
        } = &self.binding.context.authority
        else {
            return Err(invalid());
        };
        let mut bound = account.as_ref().clone();
        bound.revision.clone_from(&self.account.revision);
        if bound != self.account
            || self.context.local_identity != self.local_identity
            || self.context.root != self.binding.context.root
            || self.account.root_identity != self.binding.account.root_identity
            || self.account.origin != self.binding.account.origin
            || self.account.account_id != self.binding.account.account_id
            || organization["organization_id"] != self.organization["organization_id"]
            || original_organization["organization_id"] != self.organization["organization_id"]
            || self.organization["kind"] != "corporate"
            || contexts::organizations_projection(
                &json!({"schema_version":1,"items":[self.organization]}),
            )?["items"][0]
                != self.organization
            || contexts::active_projection(&self.observation)? != self.observation
            || self.observation["organization_id"] != self.organization["organization_id"]
            || !self.observation["capabilities"]["capabilities"]
                .as_array()
                .is_some_and(|values| values.iter().any(|value| value == "project.unlink"))
            || self.binding.reservation.binding_operation_id != self.binding.source.operation_id
            || self.binding.reservation.request_operation_id != self.binding.request.operation_id
            || self.binding.reservation.local_project_id != self.binding.local_project["stable_id"]
            || self.binding.reservation.context_id != self.binding.context.context_id
            || [
                self.binding.reservation.root_device.clone(),
                self.binding.reservation.root_inode.clone(),
            ] != self.binding.physical_root
            || self.binding.local_project["owner_id"] != self.local_identity.account_id
            || self.binding.local_project["visibility"] != "private"
            || self.binding.local_project["kind"] != "project"
            || self.binding.local_project["stable_id"] != self.binding.link["local_project_id"]
            || !self.binding.checkout_root.is_absolute()
        {
            return Err(invalid());
        }
        passport::validate(&self.binding.local_project)?;
        let link_id = self.binding.link["link_id"].as_str().ok_or_else(invalid)?;
        let request = corporate::Request::LinkCurrent {
            link_id: link_id.into(),
        };
        if request.project(
            &self.binding.link,
            self.organization_id()?,
            &self.account.account_id,
        )? != self.binding.link
            || request.project(
                &self.remote_link,
                self.organization_id()?,
                &self.account.account_id,
            )? != self.remote_link
            || if unlinked {
                self.remote_link["state"] != "unlinked"
                    || self.remote_link["revision"].as_u64()
                        <= self.binding.link["revision"].as_u64()
                    || !self.remote_link["revision"]
                        .as_u64()
                        .is_some_and(|v| v <= i64::MAX as u64)
            } else {
                !matches!(
                    self.remote_link["state"].as_str(),
                    Some("linked" | "conflict")
                ) || !self.remote_link["revision"]
                    .as_u64()
                    .and_then(|v| v.checked_add(1))
                    .is_some_and(|v| v <= i64::MAX as u64)
            }
            || self.remote_link["revision"].as_u64() < self.binding.link["revision"].as_u64()
        {
            return Err(invalid());
        }
        for field in [
            "link_id",
            "organization_id",
            "local_project_id",
            "remote_project_id",
            "provider_project_id",
            "plan_id",
            "plan_digest",
        ] {
            if self.binding.link[field] != self.remote_link[field] {
                return Err(invalid());
            }
        }
        Ok(())
    }
    pub fn unchanged(&self, other: &Self) -> Result<()> {
        self.unchanged_state(other, false)
    }
    pub(super) fn unchanged_unlinked(&self, other: &Self) -> Result<()> {
        self.unchanged_state(other, true)
    }
    fn unchanged_state(&self, other: &Self, unlinked: bool) -> Result<()> {
        self.validate_state(unlinked)?;
        other.validate_state(unlinked)?;
        if self.local_identity != other.local_identity
            || self.binding != other.binding
            || self.context != other.context
            || self.account != other.account
            || self.remote_link != other.remote_link
            || corporate::authority(&self.organization, &self.observation)
                != corporate::authority(&other.organization, &other.observation)
        {
            return Err(invalid());
        }
        Ok(())
    }
    pub fn same_binding(&self, other: &Self) -> Result<()> {
        if self.binding.source.operation_id != other.binding.source.operation_id
            || self.binding.source.plan_digest != other.binding.source.plan_digest
            || self.binding.request.operation_id != other.binding.request.operation_id
            || self.binding.request.plan_digest != other.binding.request.plan_digest
            || self.binding.physical_root != other.binding.physical_root
            || self.binding.local_project["stable_id"] != other.binding.local_project["stable_id"]
            || self.binding.reservation != other.binding.reservation
            || self.account.origin != other.account.origin
            || self.account.account_id != other.account.account_id
            || self.account.device_id != other.account.device_id
            || self.account.public_key != other.account.public_key
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
pub(super) struct ServerPlan {
    pub schema_version: u32,
    pub plan_id: String,
    pub organization_id: String,
    pub link_id: String,
    pub local_project_id: String,
    pub remote_project_id: String,
    pub provider_project_id: Option<String>,
    pub expected_link_revision: u64,
    pub local_revision: String,
    pub remote_revision: String,
    pub provider_revision: Option<String>,
    pub authorization_revision: String,
    pub plan_digest: String,
    pub expires_at: String,
}

impl ServerPlan {
    pub fn read(value: &Value, snapshot: &Snapshot) -> Result<Self> {
        let plan: Self =
            serde_json::from_value(corporate::unlink_plan(value)?).map_err(|_| invalid())?;
        plan.verify(snapshot)?;
        Ok(plan)
    }
    pub fn verify(&self, snapshot: &Snapshot) -> Result<()> {
        snapshot.validate()?;
        let projected =
            corporate::unlink_plan(&serde_json::to_value(self).map_err(|_| invalid())?)?;
        let link = &snapshot.remote_link;
        let mut preimage = json!({"organization_id":snapshot.organization_id()?,"actor_account_id":snapshot.account.account_id,
            "device_id":snapshot.account.device_id,"expected_link_revision":link["revision"],
            "authorization_revision":snapshot.observation["capabilities"]["authorization_revision"],"expires_at":self.expires_at});
        for field in [
            "link_id",
            "local_project_id",
            "remote_project_id",
            "provider_project_id",
            "local_revision",
            "remote_revision",
            "provider_revision",
        ] {
            preimage[field] = link[field].clone();
        }
        for (field, value) in preimage.as_object().ok_or_else(invalid)? {
            if !matches!(field.as_str(), "actor_account_id" | "device_id")
                && projected[field] != *value
            {
                return Err(invalid());
            }
        }
        if self.plan_digest != digest::sha256(&crate::account::server_plans::bytes(&preimage)?) {
            return Err(invalid());
        }
        Ok(())
    }
    pub fn verify_link(&self, link: &Value, snapshot: &Snapshot) -> Result<()> {
        self.verify(snapshot)?;
        if (corporate::Request::LinkCurrent {
            link_id: self.link_id.clone(),
        })
        .project(
            link,
            snapshot.organization_id()?,
            &snapshot.account.account_id,
        )? != *link
            || link["state"] != "unlinked"
            || link["revision"].as_u64() != self.expected_link_revision.checked_add(1)
        {
            return Err(invalid());
        }
        for field in [
            "link_id",
            "organization_id",
            "local_project_id",
            "remote_project_id",
            "provider_project_id",
            "local_revision",
            "remote_revision",
            "provider_revision",
            "plan_id",
            "plan_digest",
        ] {
            if link[field] != snapshot.remote_link[field] {
                return Err(invalid());
            }
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
        snapshot: Box<Snapshot>,
        request_operation_id: String,
        request_plan_digest: String,
        server_plan: Box<ServerPlan>,
    },
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub operation_id: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub(super) state_parent: PathBuf,
    pub created_at: String,
    pub expires_at: String,
    pub registry_schema_before: u32,
    pub registry_schema_after: u32,
    pub(super) change: Change,
}

impl Plan {
    pub fn state_parent(&self) -> &std::path::Path {
        &self.state_parent
    }
    pub(super) fn snapshot(&self) -> &Snapshot {
        match &self.change {
            Change::Request { snapshot } | Change::Confirm { snapshot, .. } => snapshot,
        }
    }
    pub fn digest(&self) -> Result<String> {
        self.snapshot().validate()?;
        if self.schema_version != 1
            || !passport::stable_id(&self.operation_id, "operation")
            || !has_checkout_links(self.registry_schema_before)
            || self.registry_schema_after != unlink_schema_after(self.registry_schema_before)?
            || self.state_parent != self.snapshot().context.root
            || authoring::expiry(&self.created_at)? != self.expires_at
        {
            return Err(invalid());
        }
        if let Change::Confirm {
            request_operation_id,
            request_plan_digest,
            server_plan,
            ..
        } = &self.change
        {
            if !passport::stable_id(request_operation_id, "operation")
                || request_operation_id == &self.operation_id
                || self.operation_id != confirmation_id(request_operation_id)?
                || !request_plan_digest
                    .strip_prefix("sha256:")
                    .is_some_and(|s| {
                        s.len() == 64
                            && s.bytes()
                                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
                    })
            {
                return Err(invalid());
            }
            server_plan.verify(self.snapshot())?;
        }
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        if canonical::bytes(&value)?.len() as u64 > LIMIT {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }
    pub(super) fn request_key(&self) -> String {
        format!("native.project-unlink.request.{}", self.operation_id)
    }
    pub(super) fn body(&self) -> Result<Value> {
        self.digest()?;
        let snapshot = self.snapshot();
        let value = match &self.change {
            Change::Request { .. } => {
                json!({"schema_version":1,"link_id":snapshot.remote_link["link_id"],"expected_link_revision":snapshot.remote_link["revision"],
                "authorization_revision":snapshot.observation["capabilities"]["authorization_revision"],"idempotency_key":self.request_key()})
            }
            Change::Confirm { server_plan, .. } => {
                json!({"schema_version":1,"plan_id":server_plan.plan_id,"plan_digest":server_plan.plan_digest,
                "authorization_revision":server_plan.authorization_revision,"idempotency_key":format!("native.project-unlink.confirm.{}",self.operation_id)})
            }
        };
        validate_write(matches!(&self.change, Change::Confirm { .. }), &value)?;
        Ok(value)
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "effect", rename_all = "snake_case", deny_unknown_fields)]
pub(super) enum Effect {
    Requested {
        server_plan: Box<ServerPlan>,
        outcome_reader: Option<Binding>,
    },
    Confirmed {
        link: Value,
        outcome_reader: Option<Binding>,
    },
    Interrupted {
        retirement: project_links::Interruption,
    },
    Retired {
        retirement: Box<super::retirement::Plan>,
    },
}

impl Effect {
    pub fn validate(&self, plan: &Plan) -> Result<()> {
        let reader = match (self, &plan.change) {
            (Self::Retired { retirement }, _) => return retirement.validate_source(plan),
            (
                Self::Requested {
                    server_plan,
                    outcome_reader,
                },
                Change::Request { .. },
            ) => {
                server_plan.verify(plan.snapshot())?;
                outcome_reader
            }
            (
                Self::Confirmed {
                    link,
                    outcome_reader,
                },
                Change::Confirm { server_plan, .. },
            ) => {
                server_plan.verify_link(link, plan.snapshot())?;
                outcome_reader
            }
            (Self::Interrupted { retirement }, _) => {
                retirement.validate()?;
                if retirement.checkpoint.operation_id != plan.operation_id
                    || retirement.checkpoint.plan_digest != plan.digest()?
                    || retirement.replacement_device_id == plan.snapshot().account.device_id
                {
                    return Err(invalid());
                }
                return Ok(());
            }
            _ => return Err(invalid()),
        };
        if let Some(reader) = reader {
            reader.validate()?;
            if reader.origin != plan.snapshot().account.origin
                || reader.account_id != plan.snapshot().account.account_id
                || reader.root_identity != plan.snapshot().account.root_identity
            {
                return Err(invalid());
            }
        }
        Ok(())
    }
}
