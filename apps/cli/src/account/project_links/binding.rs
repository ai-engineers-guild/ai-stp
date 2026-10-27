//! Retained active binding evidence for a separately reviewed unlink operation.

use std::path::{Path, PathBuf};

use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{
    Binding, Context, invalid,
    journal::{Checkpoint, Record},
    model::{Change, Effect, project_link},
    workflow,
};
use crate::{
    authoring::runtime::{self, Owner},
    files,
    projects::passports,
    store::{database, has_checkout_links},
};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Reservation {
    pub request_operation_id: String,
    pub local_project_id: String,
    pub root_device: String,
    pub root_inode: String,
    pub confirmation_operation_id: Option<String>,
    pub binding_operation_id: String,
    pub context_id: String,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Snapshot {
    pub source: Checkpoint,
    pub request: Checkpoint,
    pub context: Context,
    pub account: Binding,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub checkout_root: PathBuf,
    pub physical_root: [String; 2],
    pub local_project: Value,
    pub link: Value,
    pub reservation: Reservation,
}

pub(crate) fn capture(root: &Path, binding_id: &str) -> crate::error::Result<(Owner, Snapshot)> {
    let owner = runtime::owner(root)?;
    let snapshot = read(root, &owner, binding_id)?;
    Ok((owner, snapshot))
}

pub(crate) fn revalidate(root: &Path, owner: &Owner, held: &Snapshot) -> crate::error::Result<()> {
    if read(root, owner, &held.source.operation_id)? != *held {
        return Err(invalid());
    }
    Ok(())
}

fn read(root: &Path, owner: &Owner, binding_id: &str) -> crate::error::Result<Snapshot> {
    let store = owner.planning()?;
    read_in(&store.connection, root, owner, binding_id)
}

pub(crate) fn read_in(
    connection: &Connection,
    root: &Path,
    owner: &Owner,
    binding_id: &str,
) -> crate::error::Result<Snapshot> {
    let version: u32 = connection
        .pragma_query_value(None, "user_version", |r| r.get(0))
        .map_err(database)?;
    if !has_checkout_links(version) {
        return Err(invalid());
    }
    let binding = Record::load(connection, binding_id)?.ok_or_else(invalid)?;
    workflow::owned(root, owner, &binding.plan)?;
    let Change::Adopt {
        request_operation_id,
        ..
    } = &binding.plan.change
    else {
        return Err(invalid());
    };
    let Some(Effect::Adopted { link: original }) = &binding.effect else {
        return Err(invalid());
    };
    if binding.state != "completed" {
        return Err(invalid());
    }
    super::retirement::request_open(connection, request_operation_id)?;
    let request = Record::load(connection, request_operation_id)?.ok_or_else(invalid)?;
    workflow::owned(root, owner, &request.plan)?;
    if !matches!(&request.plan.change, Change::Request { .. }) || request.state == "retired" {
        return Err(invalid());
    }
    let source = binding.plan.snapshot();
    let registered = passports::registered(connection, &binding.plan.checkout_root, owner)?;
    if registered.project["stable_id"] != source.project_id()?
        || registered.identity != source.physical_root()?
        || request.plan.snapshot().project_id()? != source.project_id()?
        || request.plan.snapshot().physical_root()? != registered.identity
        || request.plan.snapshot().organization_id()? != source.organization_id()?
        || request.plan.snapshot().account.account_id != source.account.account_id
        || request.plan.snapshot().account.origin != source.account.origin
    {
        return Err(invalid());
    }
    let reservation = connection.query_row(
        "SELECT request_operation_id,local_project_id,root_device,root_inode,confirmation_operation_id,binding_operation_id,context_id FROM native_checkout_reservation WHERE binding_operation_id=?",
        [binding_id], |r| Ok(Reservation {
            request_operation_id:r.get(0)?, local_project_id:r.get(1)?, root_device:r.get(2)?, root_inode:r.get(3)?,
            confirmation_operation_id:r.get(4)?,binding_operation_id:r.get(5)?,context_id:r.get(6)?,
        })).optional().map_err(database)?.ok_or_else(invalid)?;
    if reservation.request_operation_id != *request_operation_id
        || reservation.local_project_id != source.project_id()?
        || [
            reservation.root_device.clone(),
            reservation.root_inode.clone(),
        ] != registered.identity
        || reservation.context_id != source.context.context_id
    {
        return Err(invalid());
    }
    let encoded: String = connection.query_row(
        "SELECT json_object('schema_version',1,'link_id',link_id,'organization_id',organization_id,'local_project_id',local_project_id,'remote_project_id',remote_project_id,'provider_project_id',provider_project_id,'state',state,'local_revision',local_revision,'remote_revision',remote_revision,'provider_revision',provider_revision,'revision',link_revision,'updated_at',updated_at,'plan_id',plan_id,'plan_digest',plan_digest,'conflict_server_revision',NULL,'conflict_client_revision',NULL,'conflict_common_ancestor',NULL) FROM project_link WHERE local_project_id=?",
        params![source.project_id()?], |r| r.get(0)).map_err(database)?;
    if encoded.len() > 262144 {
        return Err(invalid());
    }
    let link = project_link(&serde_json::from_str(&encoded).map_err(|_| invalid())?)?;
    for field in [
        "link_id",
        "organization_id",
        "local_project_id",
        "remote_project_id",
        "provider_project_id",
        "plan_id",
        "plan_digest",
    ] {
        if link[field] != original[field] {
            return Err(invalid());
        }
    }
    if !matches!(link["state"].as_str(), Some("linked" | "conflict")) {
        return Err(invalid());
    }
    let snapshot = Snapshot {
        source: binding.checkpoint()?,
        request: request.checkpoint()?,
        context: source.context.clone(),
        account: source.account.clone(),
        checkout_root: registered.path,
        physical_root: registered.identity,
        local_project: registered.project,
        link,
        reservation,
    };
    Ok(snapshot)
}

pub(crate) fn open(connection: &Connection, binding: &str) -> crate::error::Result<()> {
    let version: u32 = connection
        .pragma_query_value(None, "user_version", |r| r.get(0))
        .map_err(database)?;
    if version == crate::store::BINDING_RETIREMENT_SCHEMA && connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM native_binding_retirement WHERE binding_operation_id=?)",
        [binding], |r| r.get::<_,bool>(0)).map_err(database)? {
        return Err(crate::error::Failure::precondition("the original active checkout binding was explicitly retired"));
    }
    Ok(())
}

/// Validate immutable source evidence without consulting a future active binding.
pub(crate) fn retained(connection: &Connection, held: &Snapshot) -> crate::error::Result<()> {
    let source = Record::load(connection, &held.source.operation_id)?.ok_or_else(invalid)?;
    let request = Record::load(connection, &held.request.operation_id)?.ok_or_else(invalid)?;
    if source.state != "completed"
        || !matches!(&source.effect, Some(Effect::Adopted { .. }))
        || source.checkpoint()? != held.source
        || request.checkpoint()? != held.request
    {
        return Err(invalid());
    }
    Ok(())
}

/// A local release cannot consume any original unknown write for this project.
pub(crate) fn settled(connection: &Connection, held: &Snapshot) -> crate::error::Result<()> {
    let mut query = connection.prepare(
        "SELECT operation_id FROM operation WHERE kind='corporate.project_link' AND (finished_at IS NULL OR state='interrupted') ORDER BY operation_id LIMIT 129"
    ).map_err(database)?;
    let ids = query
        .query_map([], |r| r.get::<_, String>(0))
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if ids.len() > 128 {
        return Err(invalid());
    }
    for id in ids {
        let record = Record::load(connection, &id)?.ok_or_else(invalid)?;
        if record.plan.snapshot().project_id()?
            == held.local_project["stable_id"]
                .as_str()
                .ok_or_else(invalid)?
            || record.plan.snapshot().physical_root()? == held.physical_root
        {
            return Err(crate::error::Failure::precondition(
                "reconcile every retained checkout write for this physical project before retiring its binding",
            ));
        }
    }
    crate::account::project_unlinks::binding_settled(connection, &held.source.operation_id)
}
