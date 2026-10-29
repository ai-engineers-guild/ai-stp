//! Reviewed terminal location receipts; original remote intents remain immutable.

use std::path::{Path, PathBuf};

use cap_fs_ext::DirExt;
use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    Access, binding, contexts, corporate, invalid,
    journal::Record,
    model::{self, Change, ServerPlan},
    reader::Reader,
    workflow,
};
use crate::{
    authoring::{self, runtime},
    canonical, digest,
    error::Result,
    files::{self, physical::DirectoryIdentity},
    identity, passport,
    projects::{self, checkout, passports},
    store::{CHECKOUT_LOCATION_SCHEMA, database, has_checkout_links, has_checkout_locations},
};

const KIND: &str = "corporate.project_location";
const LIMIT: u64 = 262144;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Locator {
    operation_id: String,
    plan_digest: String,
    pub physical: DirectoryIdentity,
}

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
enum Action {
    Anchor,
    Relocate,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    schema_version: u32,
    pub operation_id: String,
    action: Action,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    state_parent: PathBuf,
    created_at: String,
    expires_at: String,
    registry_schema_before: u32,
    registry_schema_after: u32,
    local_identity: authoring::Identity,
    binding: binding::Snapshot,
    original: Box<model::Plan>,
    reader: Reader,
    remote: Value,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    destination: PathBuf,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    checkout_spelling: PathBuf,
    physical: DirectoryIdentity,
    git_physical: DirectoryIdentity,
    checkout: Value,
    relocation: Option<passports::Relocation>,
}

fn value(value: &impl Serialize) -> Result<Value> {
    serde_json::to_value(value).map_err(|_| invalid())
}

fn projected_remote(
    remote: &Value,
    original: &model::Plan,
    held: &binding::Snapshot,
    reader: &Reader,
) -> Result<()> {
    let request = corporate::Request::LinkOutcome {
        plan_id: held.link["plan_id"].as_str().ok_or_else(invalid)?.into(),
    };
    if request.project(
        remote,
        original.snapshot().organization_id()?,
        &reader.account.account_id,
    )? != *remote
        || remote["state"] != "applied"
        || !matches!(
            remote["link"]["state"].as_str(),
            Some("linked" | "conflict")
        )
        || remote["authorization_revision"]
            != reader.observation["capabilities"]["authorization_revision"]
    {
        return Err(invalid());
    }
    let server = ServerPlan::read(&remote["plan"], original.snapshot())?;
    if server.plan_id != held.link["plan_id"] || server.plan_digest != held.link["plan_digest"] {
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
        if remote["link"][field] != held.link[field] {
            return Err(invalid());
        }
    }
    Ok(())
}

impl Plan {
    pub fn state_parent(&self) -> &Path {
        &self.state_parent
    }

    pub fn digest(&self) -> Result<String> {
        self.local_identity.validate()?;
        self.binding.source.validate()?;
        self.binding.request.validate()?;
        self.reader.validate(&self.original)?;
        self.physical.validate()?;
        self.git_physical.validate()?;
        projected_remote(&self.remote, &self.original, &self.binding, &self.reader)?;
        if self.schema_version != 1
            || !passport::stable_id(&self.operation_id, "operation")
            || self.original.operation_id != self.binding.source.operation_id
            || self.original.digest()? != self.binding.source.plan_digest
            || !matches!(&self.original.change, Change::Adopt { .. })
            || self.binding.reservation.binding_operation_id != self.binding.source.operation_id
            || self.binding.reservation.local_project_id != self.original.snapshot().project_id()?
            || self.operation_id == self.binding.source.operation_id
            || self.operation_id == self.binding.request.operation_id
            || self.state_parent != self.reader.context.root
            || self.reader.context.local_identity != self.local_identity
            || !self.destination.is_absolute()
            || !has_checkout_links(self.registry_schema_before)
            || self.registry_schema_after != CHECKOUT_LOCATION_SCHEMA
            || self.expires_at != authoring::expiry(&self.created_at)?
        {
            return Err(invalid());
        }
        embedded_checkout(&self.checkout, &self.checkout_spelling)?;
        match (&self.action, &self.relocation) {
            (Action::Anchor, None) if self.destination == self.binding.checkout_root => (),
            (Action::Relocate, Some(relocation))
                if self
                    .binding
                    .location
                    .as_ref()
                    .is_some_and(|locator| locator.physical == self.physical)
                    && relocation.root == self.destination
                    && relocation.previous_root == self.binding.checkout_root
                    && relocation.previous == self.binding.local_project
                    && relocation.root_identity == self.binding.physical_root => {}
            _ => return Err(invalid()),
        }
        let encoded = value(self)?;
        if canonical::bytes(&encoded)?.len() as u64 > LIMIT {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &encoded)
    }
}

fn embedded_checkout(observed: &Value, path: &Path) -> Result<()> {
    if observed["checkout"]["head_state"] != "attached"
        || observed["configuration_scope"] != "repository_only"
        || observed["observation_only"] != true
        || observed["installation_authority"] != false
        || observed["checkout"]["topology"]["root"]["path"]
            != files::serialize_path(path, serde_json::value::Serializer).map_err(|_| invalid())?
    {
        return Err(invalid());
    }
    for field in ["git_directory", "common_directory"] {
        if observed["checkout"]["topology"][field]["path"]
            != files::serialize_path(&path.join(".git"), serde_json::value::Serializer)
                .map_err(|_| invalid())?
        {
            return Err(invalid());
        }
    }
    Ok(())
}

fn physical(path: &Path) -> Result<(DirectoryIdentity, DirectoryIdentity)> {
    let (resolved, directory) = projects::open_root(path)?;
    if PathBuf::from(files::location(&resolved)?) != path {
        return Err(invalid());
    }
    let git = directory.open_dir_nofollow(".git").map_err(|_| invalid())?;
    Ok((
        DirectoryIdentity::capture(&directory)?,
        DirectoryIdentity::capture(&git)?,
    ))
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    plan: Plan,
    plan_digest: String,
    completed_at: String,
}

struct ReceiptRow {
    kind: String,
    state: String,
    started: String,
    finished: Option<String>,
    detail: Option<String>,
}

fn receipt(connection: &Connection, id: &str) -> Result<Option<Receipt>> {
    let row: Option<ReceiptRow> = connection.query_row(
        "SELECT kind,state,started_at,finished_at,CASE WHEN length(CAST(detail AS BLOB))<=262144 THEN detail ELSE NULL END FROM operation WHERE operation_id=?",
        [id], |r| Ok(ReceiptRow { kind:r.get(0)?,state:r.get(1)?,started:r.get(2)?,finished:r.get(3)?,detail:r.get(4)? }),
    ).optional().map_err(database)?;
    let Some(row) = row else {
        return Ok(None);
    };
    let raw = canonical::parse(row.detail.ok_or_else(invalid)?.as_bytes())?;
    let receipt: Receipt = serde_json::from_value(raw.clone()).map_err(|_| invalid())?;
    if row.kind != KIND
        || row.state != "verified"
        || receipt.plan.operation_id != id
        || receipt.plan.digest()? != receipt.plan_digest
        || canonical::bytes(&raw)? != canonical::bytes(&value(&receipt)?)?
        || !passport::timestamp(&row.started)
        || row.started < receipt.plan.created_at
        || row.started >= receipt.plan.expires_at
        || !passport::timestamp(&receipt.completed_at)
        || receipt.completed_at < row.started
        || row.finished.as_deref() != Some(receipt.completed_at.as_str())
    {
        return Err(invalid());
    }
    binding::retained(connection, &receipt.plan.binding)?;
    Ok(Some(receipt))
}

pub(super) fn current(
    connection: &Connection,
    binding_id: &str,
) -> Result<Option<(PathBuf, Locator)>> {
    let version: u32 = connection
        .pragma_query_value(None, "user_version", |r| r.get(0))
        .map_err(database)?;
    if !has_checkout_locations(version) {
        return Ok(None);
    }
    let operation: Option<String> = connection.query_row(
        "SELECT location_operation_id FROM native_checkout_location WHERE binding_operation_id=?",
        [binding_id], |r| r.get(0),
    ).optional().map_err(database)?;
    let Some(operation) = operation else {
        return Ok(None);
    };
    let receipt = receipt(connection, &operation)?.ok_or_else(invalid)?;
    if receipt.plan.binding.source.operation_id != binding_id {
        return Err(invalid());
    }
    Ok(Some((
        receipt.plan.destination,
        Locator {
            operation_id: operation,
            plan_digest: receipt.plan_digest,
            physical: receipt.plan.physical,
        },
    )))
}

fn read_authority(
    root: &Path,
    held: &binding::Snapshot,
    original: &model::Plan,
    context: Option<&str>,
) -> Result<(Reader, Value)> {
    let selected = contexts::resolve(root, context)?;
    workflow::reader_matches(&selected, original.snapshot())?;
    let request = corporate::Request::LinkOutcome {
        plan_id: held.link["plan_id"].as_str().ok_or_else(invalid)?.into(),
    };
    let observed = corporate::observe(root, Some(&selected.context_id), request)?;
    let observed = &observed["observation"];
    let reader = Reader {
        context: selected,
        account: serde_json::from_value(observed["account"].clone()).map_err(|_| invalid())?,
        organization: observed["organization"].clone(),
        observation: observed["observation"].clone(),
    };
    reader.validate(original)?;
    if observed["context"] != value(&reader.context)? {
        return Err(invalid());
    }
    projected_remote(&observed["data"], original, held, &reader)?;
    Ok((reader, observed["data"].clone()))
}

fn remote_equal(before: &Value, after: &Value) -> bool {
    ["plan", "state", "link", "authorization_revision"]
        .iter()
        .all(|field| before[field] == after[field])
}

fn local_available(
    connection: &Connection,
    held: &binding::Snapshot,
    destination: &Path,
) -> Result<()> {
    binding::settled(connection, held)?;
    passports::require_no_pending(
        connection,
        &held.checkout_root,
        held.local_project["stable_id"]
            .as_str()
            .ok_or_else(invalid)?,
    )?;
    crate::tasks::location_unreserved(connection, destination)?;
    crate::provider::configuration::location_unreserved(
        connection,
        &held.checkout_root,
        destination,
        &held.physical_root,
    )?;
    Ok(())
}

fn make(
    root: &Path,
    context: Option<&str>,
    binding_id: &str,
    destination: Option<&Path>,
    git: Option<&Path>,
    at: &str,
) -> Result<Plan> {
    let owner = runtime::owner(root)?;
    let (held, original, before) = {
        let store = owner.planning()?;
        let held = if destination.is_some() {
            binding::retained_in(&store.connection, root, &owner, binding_id)?
        } else {
            binding::read_in(&store.connection, root, &owner, binding_id)?
        };
        let original = Record::load(&store.connection, binding_id)?
            .ok_or_else(invalid)?
            .plan;
        (held, original, store.version()?)
    };
    let destination = match destination {
        Some(path) => PathBuf::from(files::location(&projects::open_root(path)?.0)?),
        None => held.checkout_root.clone(),
    };
    let checkout_spelling = projects::open_root(&destination)?.0;
    let (physical, git_physical) = physical(&destination)?;
    let checkout = checkout::observe(&destination, git)?;
    embedded_checkout(&checkout, &checkout_spelling)?;
    let relocation = {
        let store = owner.planning()?;
        local_available(&store.connection, &held, &destination)?;
        if destination != held.checkout_root {
            let locator = held.location.as_ref().ok_or_else(invalid)?;
            let prior = receipt(&store.connection, &locator.operation_id)?.ok_or_else(invalid)?;
            if prior.plan_digest != locator.plan_digest
                || physical != locator.physical
                || git_physical != prior.plan.git_physical
            {
                return Err(invalid());
            }
            checkout::relocated_observation(&prior.plan.checkout, &checkout, &checkout_spelling)?;
            Some(passports::observe_relocation(
                &store.connection,
                &destination,
                &held.checkout_root,
                &held.local_project,
                &owner,
                at,
            )?)
        } else {
            None
        }
    };
    let (reader, remote) = read_authority(root, &held, &original, context)?;
    let plan = Plan {
        schema_version: 1,
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        action: if relocation.is_some() {
            Action::Relocate
        } else {
            Action::Anchor
        },
        state_parent: identity::root(root)?.0,
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        registry_schema_before: before,
        registry_schema_after: CHECKOUT_LOCATION_SCHEMA,
        local_identity: (*owner).clone(),
        binding: held,
        original: Box::new(original),
        reader,
        remote,
        destination,
        checkout_spelling,
        physical,
        git_physical,
        checkout,
        relocation,
    };
    plan.digest()?;
    let store = owner.planning()?;
    if store.version()? != before
        || binding::retained_in(&store.connection, root, &owner, binding_id)? != plan.binding
    {
        return Err(invalid());
    }
    local_available(&store.connection, &plan.binding, &plan.destination)?;
    Ok(plan)
}

pub fn anchor_plan(
    root: &Path,
    context: Option<&str>,
    binding_id: &str,
    git: Option<&Path>,
    at: &str,
) -> Result<Plan> {
    make(root, context, binding_id, None, git, at)
}

pub fn relocation_plan(
    root: &Path,
    context: Option<&str>,
    binding_id: &str,
    destination: &Path,
    git: Option<&Path>,
    at: &str,
) -> Result<Plan> {
    let plan = make(root, context, binding_id, Some(destination), git, at)?;
    if plan.action != Action::Relocate {
        return Err(invalid());
    }
    Ok(plan)
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let raw = canonical::parse(&files::read(path, LIMIT)?)?;
    let plan: Plan = serde_json::from_value(raw.clone()).map_err(|_| invalid())?;
    if plan.digest()? != digest::canonical("ai-stp:plan:v1", &raw)? {
        return Err(invalid());
    }
    Ok(plan)
}

fn output(receipt: &Receipt) -> Value {
    json!({"schema_version":1,"operation_id":receipt.plan.operation_id,"plan_digest":receipt.plan_digest,
        "plan":receipt.plan,"state":"verified","outcome":match receipt.plan.action {Action::Anchor=>"location_anchored",Action::Relocate=>"checkout_relocated"},
        "binding_operation_id":receipt.plan.binding.source.operation_id,
        "remote_write_submitted":false,"harness_files_changed":false,"tasks_changed":false,"installation_authority":false})
}

pub fn apply(
    root: &Path,
    plan: &Plan,
    expected: &str,
    git: Option<&Path>,
    at: &str,
) -> Result<Value> {
    if plan.digest()? != expected || !passport::timestamp(at) || at < plan.created_at.as_str() {
        return Err(invalid());
    }
    let owner = runtime::owner(root)?;
    workflow::owned(root, &owner, &plan.original)?;
    if identity::root(root)?
        != (
            plan.state_parent.clone(),
            plan.binding.account.root_identity.clone(),
        )
        || !owner.historical(&plan.local_identity)
    {
        return Err(invalid());
    }
    {
        let store = owner.planning()?;
        if let Some(known) = receipt(&store.connection, &plan.operation_id)? {
            if known.plan_digest != expected {
                return Err(invalid());
            }
            return Ok(output(&known));
        }
    }
    if at >= plan.expires_at.as_str() || *owner != plan.local_identity {
        return Err(invalid());
    }
    let (reader, remote) = read_authority(
        root,
        &plan.binding,
        &plan.original,
        Some(&plan.reader.context.context_id),
    )?;
    plan.reader.unchanged(&reader)?;
    if !remote_equal(&remote, &plan.remote) {
        return Err(invalid());
    }
    let access = Access::for_binding(root, &reader.account, false)?;
    if access.binding() != &reader.account {
        return Err(invalid());
    }
    reader.context.bind()?.revalidate()?;
    access.revalidate()?;
    let mut store = owner.open(false)?;
    if store.version()? != plan.registry_schema_before {
        return Err(invalid());
    }
    store.checkout_location_transaction(|transaction| {
        if let Some(known) = receipt(transaction, &plan.operation_id)? {
            if known.plan_digest != expected { return Err(invalid()); }
            return Ok(output(&known));
        }
        if binding::retained_in(transaction, root, &owner, &plan.binding.source.operation_id)? != plan.binding {
            return Err(invalid());
        }
        local_available(transaction, &plan.binding, &plan.destination)?;
        if physical(&plan.destination)? != (plan.physical.clone(), plan.git_physical.clone())
            || checkout::observe(&plan.destination, git)? != plan.checkout { return Err(invalid()); }
        if plan.action == Action::Anchor
            && binding::read_in(transaction, root, &owner, &plan.binding.source.operation_id)? != plan.binding {
            return Err(invalid());
        }
        let receipt = Receipt {plan:plan.clone(),plan_digest:expected.into(),completed_at:super::super::now_after(at)};
        let detail = canonical::bytes(&value(&receipt)?)?;
        if detail.len() as u64 > LIMIT { return Err(invalid()); }
        transaction.execute(
            "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,KIND,at,receipt.completed_at,String::from_utf8(detail).map_err(|_| invalid())?],
        ).map_err(database)?;
        if let Some(relocation) = &plan.relocation {
            passports::commit_relocation(transaction, relocation, &plan.operation_id, &owner, &plan.created_at)?;
        }
        match &plan.binding.location {
            Some(previous) => {
                let changed = transaction.execute(
                    "UPDATE native_checkout_location SET location_operation_id=? WHERE binding_operation_id=? AND location_operation_id=?",
                    params![plan.operation_id,plan.binding.source.operation_id,previous.operation_id],
                ).map_err(database)?;
                if changed != 1 { return Err(invalid()); }
            }
            None => { transaction.execute(
                "INSERT INTO native_checkout_location(binding_operation_id,location_operation_id) VALUES (?,?)",
                params![plan.binding.source.operation_id,plan.operation_id],
            ).map_err(database)?; }
        }
        if binding::read_in(transaction, root, &owner, &plan.binding.source.operation_id)?.checkout_root != plan.destination {
            return Err(invalid());
        }
        Ok(output(&receipt))
    })
}
