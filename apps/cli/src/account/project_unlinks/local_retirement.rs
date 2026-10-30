//! Shared SQL effect for a positively observed terminal server unlink.

use rusqlite::{Connection, params};

use super::{corporate, invalid, project_links};
use crate::{error::Result, passport, store::database};
use serde_json::Value;

#[derive(Clone, Copy)]
pub(super) enum Kind {
    Present,
    Missing,
}

impl Kind {
    pub const fn value(self) -> &'static str {
        match self {
            Self::Present => super::binding_retirement::KIND,
            Self::Missing => super::missing_checkout::KIND,
        }
    }
}

pub(super) struct Terminal<'a> {
    pub operation_id: &'a str,
    pub started_at: &'a str,
    pub completed_at: &'a str,
    pub detail: &'a str,
}

pub(super) fn validate_unlinked(
    binding: &project_links::binding::Snapshot,
    link: &Value,
) -> Result<()> {
    let request = corporate::Request::LinkCurrent {
        link_id: binding.link["link_id"].as_str().ok_or_else(invalid)?.into(),
    };
    let organization = binding.link["organization_id"]
        .as_str()
        .ok_or_else(invalid)?;
    if request.project(link, organization, &binding.account.account_id)? != *link
        || link["state"] != "unlinked"
        || !link["revision"].as_u64().is_some_and(|revision| {
            revision <= i64::MAX as u64
                && binding.link["revision"]
                    .as_u64()
                    .is_some_and(|before| revision > before)
        })
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
        if link[field] != binding.link[field] {
            return Err(invalid());
        }
    }
    Ok(())
}

/// Call inside the owning epoch transaction after its distinct filesystem
/// precondition and current account/context have been revalidated.
pub(super) fn commit(
    connection: &Connection,
    binding: &project_links::binding::Snapshot,
    link: &Value,
    kind: Kind,
    terminal: &Terminal<'_>,
) -> Result<()> {
    validate_unlinked(binding, link)?;
    let version: u32 = connection
        .pragma_query_value(None, "user_version", |row| row.get(0))
        .map_err(database)?;
    let qualified_epoch = match kind {
        Kind::Present => crate::store::has_binding_retirement(version),
        Kind::Missing => crate::store::has_missing_checkout_retirement(version),
    };
    if !qualified_epoch
        || !passport::stable_id(terminal.operation_id, "operation")
        || !passport::timestamp(terminal.started_at)
        || !passport::timestamp(terminal.completed_at)
        || terminal.completed_at < terminal.started_at
        || terminal.detail.len() > 262144
    {
        return Err(invalid());
    }
    project_links::binding::retained(connection, binding)?;
    project_links::binding::settled(connection, binding)?;
    let text = |key: &str| link[key].as_str().ok_or_else(invalid);
    let changed = connection.execute(
        "UPDATE project_link SET state='unlinked',local_revision=?,remote_revision=?,provider_revision=?,link_revision=?,updated_at=? WHERE local_project_id=? AND link_id=? AND link_revision=? AND state=?",
        params![text("local_revision")?,text("remote_revision")?,link["provider_revision"].as_str(),link["revision"].as_i64().ok_or_else(invalid)?,text("updated_at")?,
            binding.local_project["stable_id"].as_str().ok_or_else(invalid)?,binding.link["link_id"].as_str().ok_or_else(invalid)?,binding.link["revision"].as_i64().ok_or_else(invalid)?,binding.link["state"].as_str().ok_or_else(invalid)?]).map_err(database)?;
    if changed != 1 {
        return Err(invalid());
    }
    let reservation = &binding.reservation;
    let removed = connection.execute(
        "DELETE FROM native_checkout_reservation WHERE request_operation_id=? AND local_project_id=? AND root_device=? AND root_inode=? AND confirmation_operation_id IS ? AND binding_operation_id=? AND context_id=?",
        params![reservation.request_operation_id,reservation.local_project_id,reservation.root_device,reservation.root_inode,reservation.confirmation_operation_id,reservation.binding_operation_id,reservation.context_id]).map_err(database)?;
    if removed != 1 {
        return Err(invalid());
    }
    connection.execute(
        "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
        params![terminal.operation_id,kind.value(),terminal.started_at,terminal.completed_at,terminal.detail]).map_err(database)?;
    connection.execute(
        "INSERT INTO native_binding_retirement(binding_operation_id,request_operation_id,retirement_operation_id) VALUES (?,?,?)",
        params![binding.source.operation_id,binding.request.operation_id,terminal.operation_id]).map_err(database)?;
    Ok(())
}
