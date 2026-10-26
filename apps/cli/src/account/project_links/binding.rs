//! Retained active binding evidence for a separately reviewed unlink operation.

use std::path::{Path, PathBuf};

use rusqlite::{OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{
    Binding, Context, invalid,
    journal::{Checkpoint, Record},
    model::{Change, Effect, project_link},
    workflow,
};
use crate::{authoring::runtime::Owner, files, projects::passports, store::database};

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
    let (owner, binding) = workflow::load(root, binding_id)?;
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
    let store = owner.planning()?;
    let request = Record::load(&store.connection, request_operation_id)?.ok_or_else(invalid)?;
    workflow::owned(root, &owner, &request.plan)?;
    if !matches!(&request.plan.change, Change::Request { .. }) || request.state == "retired" {
        return Err(invalid());
    }
    let source = binding.plan.snapshot();
    let registered = passports::registered(&store.connection, &binding.plan.checkout_root, &owner)?;
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
    let reservation = store.connection.query_row(
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
    let encoded: String = store.connection.query_row(
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
    Ok((owner, snapshot))
}
