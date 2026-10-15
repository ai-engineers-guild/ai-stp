//! Project context is independent of configuration roots; only complete sets install it.

use super::{Plan, invalid};
use crate::{
    authoring::runtime::owner,
    digest,
    error::Result,
    objects::Objects,
    projects,
    provider::{
        configuration::{
            project::{Binding, Selection},
            set::Project,
        },
        runtime::{configuration::identity, target::Target},
    },
    store::database,
};
use rusqlite::{Connection, OptionalExtension, params};
use std::path::Path;

pub(super) fn observe(parent: &Path, root: &Path, plan: &Plan) -> Result<Project> {
    let identity = owner(parent)?;
    let mut store = identity.planning()?;
    let first = plan.first()?;
    store.transaction(|connection| {
        let registered = projects::passports::registered(connection, root, &identity)?;
        let id = registered.project["stable_id"]
            .as_str()
            .ok_or_else(invalid)?;
        let selection = selected(connection, id, &first.harness_id)?;
        if first.operation()? != "remove" {
            let selected = selection.as_ref().ok_or_else(invalid)?;
            let document = Objects { connection }.exact_version(
                &selected.stable_id,
                &selected.version,
                None,
            )?;
            if document["harness_id"] != first.harness_id
                || digest::canonical("ai-stp:passport:v1", &document)?
                    != first.setup["passport_digest"]
            {
                return Err(invalid());
            }
        }
        Ok(Project {
            root: registered.path.to_str().ok_or_else(invalid)?.into(),
            root_identity: registered.identity,
            binding: Binding {
                project_id: id.into(),
                identity: identity.clone(),
                passport_digest: digest::canonical("ai-stp:passport:v1", &registered.project)?,
                selection,
            },
        })
    })
}

fn selected(connection: &Connection, id: &str, harness: &str) -> Result<Option<Selection>> {
    connection.query_row("SELECT stable_id,version,selected_at FROM selected_version WHERE project_id=? AND harness_id=?",
        params![id,harness], |r| Ok(Selection {stable_id:r.get(0)?,version:r.get(1)?,selected_at:r.get(2)?})).optional().map_err(database)
}

pub(super) fn admitting(connection: &Connection, plan: &Plan) -> Result<()> {
    if let Some(project) = &plan.project {
        let first = plan.first()?;
        let objects = Objects { connection };
        objects.require_active(&project.binding.project_id)?;
        let document = objects.head("project", &project.binding.project_id)?;
        let root: Option<String> = connection
            .query_row(
                "SELECT root FROM project_root WHERE stable_id=?",
                [&project.binding.project_id],
                |r| r.get(0),
            )
            .optional()
            .map_err(database)?;
        let target = Target::open(Path::new(&project.root))?;
        if root.as_deref() != Some(project.root.as_str())
            || identity(&target)? != project.root_identity
            || digest::canonical("ai-stp:passport:v1", &document)?
                != project.binding.passport_digest
            || selected(connection, &project.binding.project_id, &first.harness_id)?
                != project.binding.selection
        {
            return Err(invalid());
        }
        target.revalidate()?;
    }
    Ok(())
}

pub(super) fn publishing(connection: &Connection, plan: &Plan) -> Result<()> {
    for child in &plan.children {
        crate::provider::runtime::configuration::project::invalidate_related(
            connection,
            &child.parsed()?,
        )?;
    }
    if let Some(project) = &plan.project {
        connection.execute("UPDATE selected_version SET state='pending_install' WHERE project_id=? AND harness_id=?",
            params![project.binding.project_id,plan.first()?.harness_id]).map_err(database)?;
    }
    Ok(())
}

pub(super) fn completed(connection: &Connection, plan: &Plan) -> Result<()> {
    let Some(project) = &plan.project else {
        return Ok(());
    };
    let first = plan.first()?;
    if first.operation()? == "remove" {
        return Ok(());
    }
    // A later project revision or selection is preserved, including during recovery.
    if admitting(connection, plan).is_err() {
        return Ok(());
    }
    let selected = project.binding.selection.as_ref().ok_or_else(invalid)?;
    connection.execute("UPDATE selected_version SET state='installed' WHERE project_id=? AND harness_id=? AND stable_id=? AND version=? AND selected_at=?",
        params![project.binding.project_id,first.harness_id,selected.stable_id,selected.version,selected.selected_at]).map_err(database)?;
    Ok(())
}
