//! One complete setup across explicit roots; receipts never imply cross-root atomicity.

use std::collections::BTreeSet;

use jiff::Timestamp;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{invalid, outcome, plan, project::Binding};
use crate::{digest, error::Result, passport, provider::managed, wire};

pub(crate) const KIND: &str = "configuration.set";
pub(crate) const LIMIT: usize = 32 * 1024 * 1024;
pub(crate) const RECORD_LIMIT: usize = 48 * 1024 * 1024;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Child {
    pub plan: Value,
    pub plan_digest: String,
    pub bundle_source: Option<String>,
}

impl Child {
    pub fn parsed(&self) -> Result<plan::Plan> {
        plan::Plan::parse(
            &serde_json::to_vec(&self.plan).map_err(|_| invalid())?,
            &self.plan_digest,
        )
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Project {
    pub root: String,
    pub root_identity: plan::Identity,
    pub binding: Binding,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub children: Vec<Child>,
    pub project: Option<Project>,
}

pub(crate) fn fingerprint(value: &Value) -> Result<String> {
    digest::bytes(
        "ai-stp:multi-root-transaction:v1",
        &serde_json_canonicalizer::to_vec(value).map_err(|_| invalid())?,
    )
}

impl Plan {
    pub fn value(&self) -> Result<Value> {
        serde_json::to_value(self).map_err(|_| invalid())
    }

    pub fn first(&self) -> Result<plan::Plan> {
        self.children.first().ok_or_else(invalid)?.parsed()
    }

    pub fn parse(bytes: &[u8], expected: &str) -> Result<Self> {
        if bytes.len() > LIMIT || !super::super::plan::hash(expected) {
            return Err(invalid());
        }
        let value = wire::parse(bytes)?;
        if fingerprint(&value)? != expected {
            return Err(invalid());
        }
        let plan: Self = serde_json::from_value(value).map_err(|_| invalid())?;
        if plan.schema_version != 1
            || plan.action != KIND
            || !passport::stable_id(&plan.operation_id, "operation")
            || !(2..=3).contains(&plan.children.len())
            || !passport::timestamp(&plan.created_at)
            || !passport::timestamp(&plan.expires_at)
            || fingerprint(&plan.value()?)? != expected
        {
            return Err(invalid());
        }
        let created = plan
            .created_at
            .parse::<Timestamp>()
            .map_err(|_| invalid())?;
        let expires = plan
            .expires_at
            .parse::<Timestamp>()
            .map_err(|_| invalid())?;
        if created >= expires {
            return Err(invalid());
        }
        let first = plan.first()?;
        if managed::sequence(&first.provider_version)? < managed::sequence("0.0.94")? {
            return Err(invalid());
        }
        let mut ids = BTreeSet::from([plan.operation_id.as_str()]);
        let mut scopes = BTreeSet::new();
        let mut roots = BTreeSet::new();
        let mut previous = None;
        let mut effects = 0usize;
        for child in &plan.children {
            let held = child.parsed()?;
            if !ids.insert(child.plan["operation_id"].as_str().ok_or_else(invalid)?)
                || !scopes.insert(held.target_scope)
                || !roots.insert(held.target_identity.clone())
                || previous.is_some_and(|scope| scope >= held.target_scope)
                || held.state_parent != first.state_parent
                || held.state_identity != first.state_identity
                || held.harness_id != first.harness_id
                || held.provider_version != first.provider_version
                || held.archive_digest != first.archive_digest
                || held.executable_digest != first.executable_digest
                || held.info_digest != first.info_digest
                || held.action != first.action
                || held.setup != first.setup
                || held.project.is_some()
                || held
                    .created_at
                    .parse::<Timestamp>()
                    .map_err(|_| invalid())?
                    < created
                || held
                    .expires_at
                    .parse::<Timestamp>()
                    .map_err(|_| invalid())?
                    < expires
                || child.bundle_source.is_some() != (held.operation()? != "remove")
                || child.bundle_source.as_ref().is_some_and(|path| {
                    path.len() > 4096
                        || !std::path::Path::new(path).is_absolute()
                        || path.contains('\0')
                })
            {
                return Err(invalid());
            }
            effects = effects
                .checked_add(held.effects.len())
                .ok_or_else(invalid)?;
            previous = Some(held.target_scope);
        }
        if effects > 8192 {
            return Err(invalid());
        }
        if let Some(project) = &plan.project {
            let binding = &project.binding;
            binding.identity.validate()?;
            if !std::path::Path::new(&project.root).is_absolute()
                || project.root.len() > 4096
                || project.root.contains('\0')
                || !passport::stable_id(&binding.project_id, "project")
                || !super::super::plan::hash(&binding.passport_digest)
                || project
                    .root_identity
                    .iter()
                    .any(|value| !value.parse::<u64>().is_ok_and(|n| n.to_string() == *value))
            {
                return Err(invalid());
            }
            if let Some(selection) = &binding.selection {
                if !passport::stable_id(&selection.stable_id, "setup")
                    || !passport::version_number(&selection.version)
                    || !passport::timestamp(&selection.selected_at)
                    || (first.operation()? != "remove"
                        && (first.setup["stable_id"] != selection.stable_id
                            || first.setup["version"] != selection.version))
                {
                    return Err(invalid());
                }
            } else if first.operation()? != "remove" {
                return Err(invalid());
            }
        }
        Ok(plan)
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Record {
    pub schema_version: u32,
    pub plan_digest: String,
    pub plan: Value,
    pub phase: String,
    pub prepared: Vec<Option<Value>>,
    pub results: Vec<Option<Value>>,
}

impl Record {
    pub fn state(&self) -> &str {
        match self.phase.as_str() {
            "verified" => "verified",
            "cancelled" => "cancelled",
            _ => "applying",
        }
    }

    pub fn parse(detail: &str, state: &str) -> Result<(Self, Plan)> {
        if detail.len() > RECORD_LIMIT {
            return Err(invalid());
        }
        let record: Self =
            serde_json::from_value(wire::parse(detail.as_bytes())?).map_err(|_| invalid())?;
        let plan = Plan::parse(
            &serde_json::to_vec(&record.plan).map_err(|_| invalid())?,
            &record.plan_digest,
        )?;
        if record.schema_version != 1
            || record.state() != state
            || !matches!(
                record.phase.as_str(),
                "preparing" | "applying" | "cancelling" | "verified" | "cancelled"
            )
            || record.prepared.len() != plan.children.len()
            || record.results.len() != plan.children.len()
        {
            return Err(invalid());
        }
        let publishing = matches!(record.phase.as_str(), "applying" | "verified");
        let cancelling = matches!(record.phase.as_str(), "cancelling" | "cancelled");
        let mut pending = false;
        let mut preparation_pending = false;
        for (index, child) in plan.children.iter().enumerate() {
            let child_plan = child.parsed()?;
            if let Some(prepared) = &record.prepared[index] {
                if preparation_pending || prepared != &outcome::preparation(&child_plan)? {
                    return Err(invalid());
                }
            } else {
                if publishing {
                    return Err(invalid());
                }
                preparation_pending = true;
            }
            if let Some(result) = &record.results[index] {
                if pending || record.phase == "preparing" {
                    return Err(invalid());
                }
                if cancelling {
                    outcome::validate_cancellation(result, &child_plan, &child.plan_digest)?;
                } else {
                    outcome::validate(result, &child_plan, &child.plan_digest)?;
                }
            } else {
                pending = true;
            }
        }
        if record.state() != "applying" && pending {
            return Err(invalid());
        }
        Ok((record, plan))
    }

    pub fn result(&self, plan: &Plan) -> Result<Value> {
        let first = plan.first()?;
        Ok(
            json!({"operation_id":plan.operation_id,"plan_digest":self.plan_digest,
            "action":KIND,"state":self.phase,"harness_id":first.harness_id,
            "provider_version":first.provider_version,"setup":first.setup,
            "project_id":plan.project.as_ref().map(|p| &p.binding.project_id),
            "children":self.results,"prepared":self.prepared.iter().map(Option::is_some).collect::<Vec<_>>(),
            "complete":self.state() != "applying","cross_root_atomicity":false}),
        )
    }
}
