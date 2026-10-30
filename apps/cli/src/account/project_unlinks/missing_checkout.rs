//! Explicit local retirement after an absent checkout and an exact server unlink.

use std::path::{Path, PathBuf};

use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    Access, Context,
    absent_checkout::{self, Parent},
    contexts, corporate, invalid, local_retirement, project_links,
};
use crate::{
    account::project_links::reader::Reader,
    authoring::{self, runtime},
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, identity, passport,
    store::{MISSING_CHECKOUT_RETIREMENT_SCHEMA, database, has_checkout_links},
};

pub(super) const KIND: &str = "corporate.project_binding.retire_missing";
const LIMIT: u64 = 262144;

fn same_remote(before: &Value, after: &Value) -> bool {
    ["plan", "state", "link", "authorization_revision"]
        .iter()
        .all(|field| before[field] == after[field])
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    local_identity: authoring::Identity,
    binding: project_links::binding::Snapshot,
    reader: Reader,
    remote_outcome: Value,
}

impl Snapshot {
    fn validate(&self) -> Result<()> {
        self.local_identity.validate()?;
        self.binding.source.validate()?;
        self.binding.request.validate()?;
        self.binding.context.digest()?;
        self.binding.account.validate()?;
        self.reader.validate_binding(&self.binding)?;
        let binding = &self.binding;
        if self.reader.context.local_identity != self.local_identity
            || binding.reservation.binding_operation_id != binding.source.operation_id
            || binding.reservation.request_operation_id != binding.request.operation_id
            || binding.reservation.local_project_id != binding.local_project["stable_id"]
            || binding.reservation.context_id != binding.context.context_id
            || [
                binding.reservation.root_device.clone(),
                binding.reservation.root_inode.clone(),
            ] != binding.physical_root
            || binding.local_project["owner_id"] != self.local_identity.account_id
            || binding.local_project["visibility"] != "private"
            || binding.local_project["kind"] != "project"
            || binding.local_project["stable_id"] != binding.link["local_project_id"]
            || !binding.checkout_root.is_absolute()
        {
            return Err(invalid());
        }
        passport::validate(&binding.local_project)?;
        let request = corporate::Request::LinkOutcome {
            plan_id: binding.link["plan_id"].as_str().ok_or_else(invalid)?.into(),
        };
        let organization = binding.link["organization_id"]
            .as_str()
            .ok_or_else(invalid)?;
        if request.project(
            &self.remote_outcome,
            organization,
            &self.reader.account.account_id,
        )? != self.remote_outcome
            || self.remote_outcome["state"] != "applied"
            || self.remote_outcome["plan"]["plan_digest"] != binding.link["plan_digest"]
            || self.remote_outcome["authorization_revision"]
                != self.reader.observation["capabilities"]["authorization_revision"]
        {
            return Err(invalid());
        }
        local_retirement::validate_unlinked(binding, &self.remote_outcome["link"])
    }

    fn unchanged(&self, fresh: &Self) -> Result<()> {
        self.validate()?;
        fresh.validate()?;
        self.reader.unchanged(&fresh.reader)?;
        if self.local_identity != fresh.local_identity
            || self.binding != fresh.binding
            || self.binding.checkout_root.as_os_str() != fresh.binding.checkout_root.as_os_str()
            || !same_remote(&self.remote_outcome, &fresh.remote_outcome)
        {
            return Err(invalid());
        }
        Ok(())
    }
}

/// This transition never falls back from failed present-root inspection. The
/// exact parent capability is checked before disclosing an original plan ID.
fn inspect<T>(
    root: &Path,
    context: Option<&str>,
    binding_id: &str,
    expected_parent: Option<&Parent>,
    finish: impl FnOnce(Snapshot, &Access, &runtime::Owner, &absent_checkout::Observation) -> Result<T>,
) -> Result<T> {
    let owner = runtime::owner(root)?;
    let binding = {
        let store = owner.planning()?;
        project_links::binding::retained_in(&store.connection, root, &owner, binding_id)?
    };
    let selected = contexts::resolve(root, context)?;
    Reader::matches_binding(&selected, &binding)?;
    selected.require_current_native_identity(&owner)?;
    let absent = match expected_parent {
        Some(parent) => parent.open(&binding.checkout_root)?,
        None => Parent::observe(&binding.checkout_root)?,
    };
    let read = || -> Result<(Reader, Value)> {
        let observed = corporate::observe(
            root,
            Some(&selected.context_id),
            corporate::Request::LinkOutcome {
                plan_id: binding.link["plan_id"].as_str().ok_or_else(invalid)?.into(),
            },
        )?;
        let observed = &observed["observation"];
        let context: Context =
            serde_json::from_value(observed["context"].clone()).map_err(|_| invalid())?;
        if context != selected {
            return Err(invalid());
        }
        let reader = Reader {
            context,
            account: serde_json::from_value(observed["account"].clone()).map_err(|_| invalid())?,
            organization: observed["organization"].clone(),
            observation: observed["observation"].clone(),
        };
        reader.validate_binding(&binding)?;
        Ok((reader, observed["data"].clone()))
    };
    let (reader, remote_outcome) = read()?;
    let (fresh_reader, fresh_remote) = read()?;
    reader.unchanged(&fresh_reader)?;
    if !same_remote(&remote_outcome, &fresh_remote) {
        return Err(invalid());
    }
    let snapshot = Snapshot {
        local_identity: (*owner).clone(),
        binding,
        reader,
        remote_outcome,
    };
    snapshot.validate()?;
    absent.revalidate(&snapshot.binding.checkout_root)?;
    {
        let store = owner.planning()?;
        let current =
            project_links::binding::retained_in(&store.connection, root, &owner, binding_id)?;
        if current != snapshot.binding
            || current.checkout_root.as_os_str() != snapshot.binding.checkout_root.as_os_str()
        {
            return Err(invalid());
        }
    }
    let access = Access::for_binding(root, &snapshot.reader.account, false)?;
    if access.binding() != &snapshot.reader.account {
        return Err(invalid());
    }
    snapshot.reader.context.bind()?.revalidate()?;
    access.revalidate()?;
    finish(snapshot, &access, &owner, &absent)
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    schema_version: u32,
    kind: String,
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
    parent: Parent,
}

impl Plan {
    pub fn state_parent(&self) -> &Path {
        &self.state_parent
    }

    pub fn digest(&self) -> Result<String> {
        self.snapshot.validate()?;
        self.parent.validate(&self.snapshot.binding.checkout_root)?;
        if self.schema_version != 1
            || self.kind != KIND
            || !passport::stable_id(&self.operation_id, "operation")
            || self.operation_id == self.snapshot.binding.source.operation_id
            || self.operation_id == self.snapshot.binding.request.operation_id
            || self.state_parent != self.snapshot.reader.context.root
            || !has_checkout_links(self.registry_schema_before)
            || self.registry_schema_after != MISSING_CHECKOUT_RETIREMENT_SCHEMA
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
    inspect(
        root,
        context,
        binding,
        None,
        |snapshot, _, owner, observed| {
            let before = {
                let store = owner.planning()?;
                project_links::binding::settled(&store.connection, &snapshot.binding)?;
                store.version()?
            };
            let plan = Plan {
                schema_version: 1,
                kind: KIND.into(),
                operation_id: format!("operation_{}", ulid::Ulid::generate()),
                state_parent: identity::root(root)?.0,
                created_at: at.into(),
                expires_at: authoring::expiry(at)?,
                registry_schema_before: before,
                registry_schema_after: MISSING_CHECKOUT_RETIREMENT_SCHEMA,
                snapshot,
                parent: observed.parent.clone(),
            };
            plan.digest()?;
            Ok(plan)
        },
    )
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

fn read_receipt(connection: &Connection, id: &str) -> Result<Option<Receipt>> {
    let row: Option<Row> = connection.query_row(
        "SELECT kind,state,started_at,finished_at,CASE WHEN length(CAST(detail AS BLOB))<=262144 THEN detail ELSE NULL END FROM operation WHERE operation_id=?",
        [id], |r| Ok(Row {kind:r.get(0)?,state:r.get(1)?,started:r.get(2)?,finished:r.get(3)?,detail:r.get(4)?})).optional().map_err(database)?;
    let Some(row) = row else {
        return Ok(None);
    };
    let version: u32 = connection
        .pragma_query_value(None, "user_version", |row| row.get(0))
        .map_err(database)?;
    let raw = canonical::parse(row.detail.ok_or_else(invalid)?.as_bytes())?;
    let receipt: Receipt = serde_json::from_value(raw.clone()).map_err(|_| invalid())?;
    if !crate::store::has_missing_checkout_retirement(version)
        || row.kind != KIND
        || row.state != "verified"
        || receipt.plan.operation_id != id
        || receipt.plan_digest != receipt.plan.digest()?
        || canonical::bytes(&raw)?
            != canonical::bytes(&serde_json::to_value(&receipt).map_err(|_| invalid())?)?
        || !passport::timestamp(&row.started)
        || row.started < receipt.plan.created_at
        || row.started >= receipt.plan.expires_at
        || !passport::timestamp(&receipt.completed_at)
        || receipt.completed_at < row.started
        || row.finished.as_deref() != Some(receipt.completed_at.as_str())
    {
        return Err(invalid());
    }
    Ok(Some(receipt))
}

fn checked_output(connection: &Connection, receipt: &Receipt) -> Result<Value> {
    let binding = &receipt.plan.snapshot.binding;
    let present: bool = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM native_binding_retirement WHERE binding_operation_id=? AND request_operation_id=? AND retirement_operation_id=?)",
        params![binding.source.operation_id,binding.request.operation_id,receipt.plan.operation_id], |row| row.get(0)).map_err(database)?;
    if !present {
        return Err(invalid());
    }
    project_links::binding::retained(connection, binding)?;
    Ok(
        json!({"schema_version":1,"operation_id":receipt.plan.operation_id,
        "plan_digest":receipt.plan_digest,"plan":receipt.plan,"state":"verified",
        "outcome":"missing_checkout_binding_retired","binding_operation_id":binding.source.operation_id,
        "original_request_operation_id":binding.request.operation_id,"checkout_observation":"absent",
        "local_binding_retired":true,"reservation_released":true,"remote_write_submitted":false,
        "harness_files_changed":false,"tasks_changed":false,"installation_authority":false}),
    )
}

pub(super) fn for_binding(
    connection: &Connection,
    binding: &str,
    operation: &str,
) -> Result<Value> {
    let receipt = read_receipt(connection, operation)?.ok_or_else(invalid)?;
    if receipt.plan.snapshot.binding.source.operation_id != binding {
        return Err(invalid());
    }
    checked_output(connection, &receipt)
}

fn owned(root: &Path, owner: &runtime::Owner, plan: &Plan) -> Result<()> {
    if identity::root(root)?
        != (
            plan.state_parent.clone(),
            plan.snapshot.reader.account.root_identity.clone(),
        )
        || !owner.historical(&plan.snapshot.local_identity)
    {
        return Err(invalid());
    }
    Ok(())
}

pub fn status(root: &Path, operation: &str) -> Result<Value> {
    let owner = runtime::owner(root)?;
    let store = owner.planning()?;
    let receipt = read_receipt(&store.connection, operation)?.ok_or_else(|| {
        Failure::new(
            ErrorKind::NotFound,
            "the missing-checkout retirement receipt is absent",
        )
    })?;
    owned(root, &owner, &receipt.plan)?;
    checked_output(&store.connection, &receipt)
}

pub fn apply(root: &Path, plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    if plan.digest()? != expected || !passport::timestamp(at) || at < plan.created_at.as_str() {
        return Err(invalid());
    }
    let owner = runtime::owner(root)?;
    owned(root, &owner, plan)?;
    {
        let store = owner.planning()?;
        if let Some(receipt) = read_receipt(&store.connection, &plan.operation_id)? {
            if receipt.plan_digest != expected {
                return Err(invalid());
            }
            return checked_output(&store.connection, &receipt);
        }
        if store.version()? != plan.registry_schema_before {
            return Err(invalid());
        }
        let binding = project_links::binding::retained_in(
            &store.connection,
            root,
            &owner,
            &plan.snapshot.binding.source.operation_id,
        )?;
        if binding != plan.snapshot.binding
            || binding.checkout_root.as_os_str() != plan.snapshot.binding.checkout_root.as_os_str()
        {
            return Err(invalid());
        }
    }
    if at >= plan.expires_at.as_str() {
        return Err(invalid());
    }
    inspect(
        root,
        Some(&plan.snapshot.reader.context.context_id),
        &plan.snapshot.binding.source.operation_id,
        Some(&plan.parent),
        |fresh, access, owner, observed| {
            plan.snapshot.unchanged(&fresh)?;
            if fresh.binding.checkout_root.as_os_str()
                != plan.snapshot.binding.checkout_root.as_os_str()
            {
                return Err(invalid());
            }
            fresh.reader.context.bind()?.revalidate()?;
            access.revalidate()?;
            let mut store = owner.open(false)?;
            if store.version()? != plan.registry_schema_before {
                return Err(invalid());
            }
            store.missing_checkout_retirement_transaction(|transaction| {
                if let Some(receipt) = read_receipt(transaction, &plan.operation_id)? {
                    if receipt.plan_digest != expected {
                        return Err(invalid());
                    }
                    return checked_output(transaction, &receipt);
                }
                let binding = project_links::binding::retained_in(
                    transaction,
                    root,
                    owner,
                    &plan.snapshot.binding.source.operation_id,
                )?;
                if binding != plan.snapshot.binding
                    || binding.checkout_root.as_os_str()
                        != plan.snapshot.binding.checkout_root.as_os_str()
                {
                    return Err(invalid());
                }
                observed.revalidate(&binding.checkout_root)?;
                let receipt = Receipt {
                    plan: plan.clone(),
                    plan_digest: expected.into(),
                    completed_at: super::super::now_after(at),
                };
                let detail =
                    canonical::bytes(&serde_json::to_value(&receipt).map_err(|_| invalid())?)?;
                if detail.len() as u64 > LIMIT {
                    return Err(invalid());
                }
                let detail = String::from_utf8(detail).map_err(|_| invalid())?;
                local_retirement::commit(
                    transaction,
                    &fresh.binding,
                    &fresh.remote_outcome["link"],
                    local_retirement::Kind::Missing,
                    &local_retirement::Terminal {
                        operation_id: &plan.operation_id,
                        started_at: at,
                        completed_at: &receipt.completed_at,
                        detail: &detail,
                    },
                )?;
                checked_output(transaction, &receipt)
            })
        },
    )
}
