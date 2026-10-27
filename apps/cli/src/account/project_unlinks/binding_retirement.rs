//! Atomically retire one local active binding using fresh terminal server evidence.

use std::path::{Path, PathBuf};

use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{invalid, model::Snapshot, project_links, workflow};
use crate::{
    authoring::{self, runtime},
    canonical, digest,
    error::Result,
    files, identity, passport,
    store::{BINDING_RETIREMENT_SCHEMA, database, has_checkout_links},
};

const KIND: &str = "corporate.project_binding.retire";
const LIMIT: u64 = 262144;

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    schema_version: u32,
    pub operation_id: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    state_parent: PathBuf,
    created_at: String,
    expires_at: String,
    registry_schema_before: u32,
    registry_schema_after: u32,
    snapshot: Snapshot,
}

impl Plan {
    pub fn state_parent(&self) -> &Path {
        &self.state_parent
    }

    pub fn digest(&self) -> Result<String> {
        self.snapshot.validate_unlinked()?;
        if self.schema_version != 1
            || !passport::stable_id(&self.operation_id, "operation")
            || self.operation_id == self.snapshot.binding.source.operation_id
            || self.operation_id == self.snapshot.binding.request.operation_id
            || self.state_parent != self.snapshot.context.root
            || !has_checkout_links(self.registry_schema_before)
            || self.registry_schema_after != BINDING_RETIREMENT_SCHEMA
            || self.expires_at != authoring::expiry(&self.created_at)?
        {
            return Err(invalid());
        }
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        if canonical::bytes(&value)?.len() as u64 > LIMIT {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }
}

pub fn plan(root: &Path, context: Option<&str>, binding: &str, at: &str) -> Result<Plan> {
    workflow::inspect_unlinked(root, context, binding, |snapshot, _, owner, _| {
        let before = {
            let store = owner.planning()?;
            project_links::binding::settled(&store.connection, &snapshot.binding)?;
            store.version()?
        };
        let plan = Plan {
            schema_version: 1,
            operation_id: format!("operation_{}", ulid::Ulid::generate()),
            state_parent: identity::root(root)?.0,
            created_at: at.into(),
            expires_at: authoring::expiry(at)?,
            registry_schema_before: before,
            registry_schema_after: BINDING_RETIREMENT_SCHEMA,
            snapshot,
        };
        plan.digest()?;
        Ok(plan)
    })
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let value = canonical::parse(&files::read(path, LIMIT)?)?;
    let plan: Plan = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    if plan.digest()? != digest::canonical("ai-stp:plan:v1", &value)? {
        return Err(invalid());
    }
    Ok(plan)
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    plan: Plan,
    plan_digest: String,
    completed_at: String,
}

struct Row {
    kind: String,
    state: String,
    started: String,
    finished: Option<String>,
    detail: Option<String>,
}

fn read_receipt(connection: &Connection, plan: &Plan) -> Result<Option<Receipt>> {
    let row: Option<Row> = connection.query_row(
        "SELECT kind,state,started_at,finished_at,CASE WHEN length(CAST(detail AS BLOB))<=262144 THEN detail ELSE NULL END FROM operation WHERE operation_id=?",
        [&plan.operation_id], |r| Ok(Row {kind:r.get(0)?,state:r.get(1)?,started:r.get(2)?,finished:r.get(3)?,detail:r.get(4)?})).optional().map_err(database)?;
    let Some(row) = row else {
        return Ok(None);
    };
    let raw = canonical::parse(row.detail.as_ref().ok_or_else(invalid)?.as_bytes())?;
    let receipt: Receipt = serde_json::from_value(raw.clone()).map_err(|_| invalid())?;
    if row.kind != KIND
        || row.state != "verified"
        || receipt.plan_digest != plan.digest()?
        || receipt.plan.digest()? != receipt.plan_digest
        || canonical::bytes(&raw)?
            != canonical::bytes(&serde_json::to_value(&receipt).map_err(|_| invalid())?)?
        || !passport::timestamp(&row.started)
        || row.started < plan.created_at
        || row.started >= plan.expires_at
        || !passport::timestamp(&receipt.completed_at)
        || receipt.completed_at < row.started
        || row.finished.as_deref() != Some(receipt.completed_at.as_str())
    {
        return Err(invalid());
    }
    Ok(Some(receipt))
}

fn output(receipt: &Receipt) -> Result<Value> {
    Ok(
        json!({"schema_version":1,"operation_id":receipt.plan.operation_id,
        "plan_digest":receipt.plan_digest,"plan":receipt.plan,"state":"verified",
        "outcome":"local_binding_retired","binding_operation_id":receipt.plan.snapshot.binding.source.operation_id,
        "original_request_operation_id":receipt.plan.snapshot.binding.request.operation_id,
        "local_binding_retired":true,"reservation_released":true,"remote_write_submitted":false,
        "harness_files_changed":false,"tasks_changed":false,"installation_authority":false}),
    )
}

fn checked_output(connection: &Connection, receipt: &Receipt) -> Result<Value> {
    let held = &receipt.plan.snapshot.binding;
    let present: bool = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM native_binding_retirement WHERE binding_operation_id=? AND request_operation_id=? AND retirement_operation_id=?)",
        params![held.source.operation_id,held.request.operation_id,receipt.plan.operation_id], |r| r.get(0)).map_err(database)?;
    if !present {
        return Err(invalid());
    }
    project_links::binding::retained(connection, held)?;
    // The current cached link, reservation and filesystem may belong to a new
    // binding. Historical replay reads only this immutable marker and receipt.
    output(receipt)
}

pub fn apply(root: &Path, plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    if plan.digest()? != expected || !passport::timestamp(at) || at < plan.created_at.as_str() {
        return Err(invalid());
    }
    let owner = runtime::owner(root)?;
    if identity::root(root)?
        != (
            plan.state_parent.clone(),
            plan.snapshot.account.root_identity.clone(),
        )
        || !owner.historical(&plan.snapshot.local_identity)
    {
        return Err(invalid());
    }
    {
        let store = owner.planning()?;
        if let Some(receipt) = read_receipt(&store.connection, plan)? {
            return checked_output(&store.connection, &receipt);
        }
    }
    if at >= plan.expires_at.as_str() {
        return Err(invalid());
    }
    workflow::inspect_unlinked(
        root,
        Some(&plan.snapshot.context.context_id),
        &plan.snapshot.binding.source.operation_id,
        |fresh, access, owner, _| {
            plan.snapshot.unchanged_unlinked(&fresh)?;
            fresh.context.bind()?.revalidate()?;
            access.revalidate()?;
            let mut store = owner.open(false)?;
            if store.version()? != plan.registry_schema_before {
                return Err(invalid());
            }
            store.binding_retirement_transaction(|transaction| {
                if let Some(receipt) = read_receipt(transaction, plan)? {
                    return checked_output(transaction, &receipt);
                }
                let binding = &plan.snapshot.binding;
                let current = project_links::binding::read_in(transaction, root, owner, &binding.source.operation_id)?;
                if current != *binding {
                    return Err(invalid());
                }
                project_links::binding::settled(transaction, binding)?;
                let link = &fresh.remote_link;
                let text = |key: &str| link[key].as_str().ok_or_else(invalid);
                let changed = transaction.execute(
                    "UPDATE project_link SET state='unlinked',local_revision=?,remote_revision=?,provider_revision=?,link_revision=?,updated_at=? WHERE local_project_id=? AND link_id=? AND link_revision=? AND state=?",
                    params![text("local_revision")?,text("remote_revision")?,link["provider_revision"].as_str(),link["revision"].as_i64().ok_or_else(invalid)?,text("updated_at")?,
                        binding.local_project["stable_id"].as_str().ok_or_else(invalid)?,binding.link["link_id"].as_str().ok_or_else(invalid)?,binding.link["revision"].as_i64().ok_or_else(invalid)?,binding.link["state"].as_str().ok_or_else(invalid)?]).map_err(database)?;
                if changed != 1 { return Err(invalid()); }
                let reservation = &binding.reservation;
                let removed = transaction.execute(
                    "DELETE FROM native_checkout_reservation WHERE request_operation_id=? AND local_project_id=? AND root_device=? AND root_inode=? AND confirmation_operation_id IS ? AND binding_operation_id=? AND context_id=?",
                    params![reservation.request_operation_id,reservation.local_project_id,reservation.root_device,reservation.root_inode,reservation.confirmation_operation_id,reservation.binding_operation_id,reservation.context_id]).map_err(database)?;
                if removed != 1 { return Err(invalid()); }
                let receipt = Receipt { plan: plan.clone(), plan_digest: expected.into(), completed_at: super::super::now_after(at) };
                let detail = canonical::bytes(&serde_json::to_value(&receipt).map_err(|_| invalid())?)?;
                if detail.len() as u64 > LIMIT { return Err(invalid()); }
                transaction.execute(
                    "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
                    params![plan.operation_id,KIND,at,receipt.completed_at,String::from_utf8(detail).map_err(|_| invalid())?]).map_err(database)?;
                transaction.execute(
                    "INSERT INTO native_binding_retirement(binding_operation_id,request_operation_id,retirement_operation_id) VALUES (?,?,?)",
                    params![binding.source.operation_id,binding.request.operation_id,plan.operation_id]).map_err(database)?;
                checked_output(transaction, &receipt)
            })
        },
    )
}
