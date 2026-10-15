//! Registered-project observation and atomic installation attribution.

use super::{bundle::Bundle, invalid, plan::Plan};
use crate::{
    authoring::runtime::owner,
    digest,
    error::Result,
    objects::Objects,
    projects,
    provider::configuration::project::{Binding, Selection},
    store::database,
};
use rusqlite::{Connection, OptionalExtension, params};
use std::path::Path;

pub(super) fn observe(plan: &Plan, project: &str, bundle: Option<&Bundle>) -> Result<Binding> {
    let parent = Path::new(&plan.state_parent);
    let owner = owner(parent)?;
    let mut store = owner.planning()?;
    store.transaction(|connection| {
        let registered = projects::passports::registered(connection, Path::new(&plan.target_path), &owner)?;
        if registered.project["stable_id"] != project || registered.identity != plan.target_identity {
            return Err(invalid());
        }
        let selection = connection.query_row(
            "SELECT stable_id,version,selected_at FROM selected_version WHERE project_id=? AND harness_id=?",
            params![project,plan.harness_id], |r| Ok(Selection {stable_id:r.get(0)?,version:r.get(1)?,selected_at:r.get(2)?}))
            .optional().map_err(database)?;
        if let Some(selection) = &selection {
            let document = Objects { connection }.exact_version(&selection.stable_id, &selection.version, None)?;
            if document["harness_id"] != plan.harness_id ||
                (plan.operation()? != "remove" && digest::canonical("ai-stp:passport:v1", &document)? != plan.setup["passport_digest"]) {
                return Err(invalid());
            }
            if plan.operation()? != "remove" {
                let bundle = bundle.ok_or_else(invalid)?;
                let host = crate::bundle::hosts::Root::open(Some(Path::new(&plan.target_path)), parent, parent)?;
                let paths = crate::bundle::hosts::paths(connection, &bundle.setup, &plan.harness_id, plan.target_scope)?;
                let before = host.read(&paths)?;
                crate::bundle::coverage::verify_payload_snapshot(
                    connection, &bundle.setup, &plan.harness_id, plan.target_scope,
                    &bundle.adaptations, &bundle.files, &before,
                )?;
                if host.read(&paths)? != before { return Err(invalid()); }
            }
        }
        let binding = Binding {project_id:project.into(),identity:owner.clone(),
            passport_digest:digest::canonical("ai-stp:passport:v1", &registered.project)?,selection};
        binding.validate(plan)?;
        Ok(binding)
    })
}

/// Same SQLite commit as the verified receipt. A later selection is never
/// overwritten by recovery of an older installation. Unbound writes only
/// invalidate a recorded selection; they cannot claim a project association.
pub(crate) fn completed(connection: &Connection, plan: &Plan) -> Result<()> {
    connection.execute("UPDATE selected_version SET state='pending_install' WHERE harness_id=? AND project_id IN (SELECT stable_id FROM project_root WHERE root=?)",
        params![plan.harness_id,plan.target_path]).map_err(database)?;
    let Some(binding) = &plan.project else {
        return Ok(());
    };
    if plan.operation()? == "remove" {
        return Ok(());
    }
    let selection = binding.selection.as_ref().ok_or_else(invalid)?;
    connection.execute("UPDATE selected_version SET state='installed' WHERE project_id=? AND harness_id=? AND stable_id=? AND version=? AND selected_at=? AND EXISTS (SELECT 1 FROM project_root WHERE stable_id=? AND root=?)",
        params![binding.project_id,plan.harness_id,selection.stable_id,selection.version,selection.selected_at,binding.project_id,plan.target_path]).map_err(database)?;
    Ok(())
}

/// Check the database precondition inside native admission's writer transaction.
pub(crate) fn admitting(connection: &Connection, plan: &Plan) -> Result<()> {
    let Some(binding) = &plan.project else {
        return Ok(());
    };
    let objects = Objects { connection };
    objects.require_active(&binding.project_id)?;
    let passport = objects.head("project", &binding.project_id)?;
    let root: Option<String> = connection
        .query_row(
            "SELECT root FROM project_root WHERE stable_id=?",
            [&binding.project_id],
            |row| row.get(0),
        )
        .optional()
        .map_err(database)?;
    let selection = connection.query_row("SELECT stable_id,version,selected_at FROM selected_version WHERE project_id=? AND harness_id=?", params![binding.project_id,plan.harness_id], |r| Ok(Selection { stable_id:r.get(0)?,version:r.get(1)?,selected_at:r.get(2)?})).optional().map_err(database)?;
    if root.as_deref() != Some(plan.target_path.as_str())
        || digest::canonical("ai-stp:passport:v1", &passport)? != binding.passport_digest
        || selection != binding.selection
    {
        return Err(invalid());
    }
    Ok(())
}

/// Invalidate the latest installed project relationship when any of its roots
/// changes. Exclude the current operation and its aggregate so their pending
/// rows cannot hide the installation whose configuration is being replaced.
pub(super) fn invalidate_related(connection: &Connection, plan: &Plan) -> Result<()> {
    for installed in crate::selection::impact::installed_before(connection, &plan.operation_id)? {
        let Some((project, harness)) = installed.target.rsplit_once(':') else {
            continue;
        };
        if harness != plan.harness_id || !crate::passport::stable_id(project, "project") {
            continue;
        }
        if installed.native_roots.iter().any(|(root, identity)| {
            identity == &plan.target_identity
                || Path::new(root).starts_with(&plan.target_path)
                || Path::new(&plan.target_path).starts_with(root)
        }) {
            connection.execute("UPDATE selected_version SET state='pending_install' WHERE project_id=? AND harness_id=?",
                [project,harness]).map_err(database)?;
        }
    }
    Ok(())
}
