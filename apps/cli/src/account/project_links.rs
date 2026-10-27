//! Registered checkout inspection and separately reviewed durable corporate linking.

pub(crate) mod binding;
pub(crate) mod interruption;
mod journal;
mod model;
pub mod retirement;
mod workflow;

pub use journal::Checkpoint;
pub use model::Plan;
// Account replacement binds the same checkpoint encoding in both journals.
pub(crate) use model::{Interruption, RetirementKind};
pub use workflow::{
    adoption_plan, apply, confirmation_plan, list, outcome, read_plan, request_plan, status,
};

use std::path::Path;

use cap_fs_ext::MetadataExt;
use serde_json::{Value, json};

use super::{
    access::{Access, Binding},
    contexts::{self, Context},
    corporate::{self, Request},
};
use crate::{
    authoring::runtime,
    canonical, digest,
    error::{Failure, Result},
    passport,
    projects::{checkout, passports},
};

pub(super) fn validate_write(confirm: bool, value: &Value) -> Result<()> {
    model::validate_write(confirm, value)
}

fn invalid() -> Failure {
    Failure::precondition(
        "the original checkout, private project, context or current link coordinates changed",
    )
}

fn coordinates(target: &Value) -> Value {
    json!([
        target["organization_id"],
        target["remote_project_id"],
        target["remote_revision"],
        target["providers"],
        target["authorization_revision"]
    ])
}

/// This is a fresh observation, not a persisted request/confirmation plan. It
/// sends no local passport, Git routing values or installation inventory.
pub fn preview(
    root: &Path,
    context_id: Option<&str>,
    checkout_root: &Path,
    remote_project: &str,
    provider_project: Option<&str>,
    git_executable: Option<&Path>,
) -> Result<Value> {
    inspect(
        root,
        context_id,
        checkout_root,
        remote_project,
        provider_project,
        git_executable,
        |result, _, _, _| Ok(result),
    )
}

fn inspect<T>(
    root: &Path,
    context_id: Option<&str>,
    checkout_root: &Path,
    remote_project: &str,
    provider_project: Option<&str>,
    git_executable: Option<&Path>,
    finish: impl FnOnce(Value, &mut Access, &runtime::Owner, &passports::Registered) -> Result<T>,
) -> Result<T> {
    if !passport::stable_id(remote_project, "remote_project")
        || provider_project.is_some_and(|id| !passport::stable_id(id, "provider_project"))
    {
        return Err(Failure::input(
            "name exact remote_project and optional provider_project IDs",
        ));
    }
    let owner = runtime::owner(root)?;
    let registered = {
        let store = owner.planning()?;
        passports::registered(&store.connection, checkout_root, &owner)?
    };
    let checkout = checkout::observe(&registered.path, git_executable)?;
    if checkout["checkout"]["head_state"] != "attached"
        || checkout["checkout"]["topology"]["root"]["identity"] != json!(registered.identity)
    {
        return Err(Failure::precondition(
            "link preview requires an attached committed checkout at the registered physical root",
        ));
    }
    let request = Request::LinkTarget {
        project_id: remote_project.into(),
    };
    let observed = corporate::observe(root, context_id, request.clone())?;
    let observed = &observed["observation"];
    let context: Context =
        serde_json::from_value(observed["context"].clone()).map_err(|_| invalid())?;
    if context.local_identity != *owner {
        return Err(invalid());
    }
    let binding: Binding =
        serde_json::from_value(observed["account"].clone()).map_err(|_| invalid())?;
    let organization = observed["organization"]["organization_id"]
        .as_str()
        .ok_or_else(invalid)?;
    // Take the original account journal before opening any registry again.
    // A refreshed session can read old evidence, but cannot silently retarget
    // this new preview's current session snapshot.
    let mut access = Access::for_binding(root, &binding, false)?;
    if access.binding().revision != binding.revision {
        return Err(invalid());
    }
    let (current, capabilities) = contexts::remote(&mut access, Some(organization))?;
    if corporate::authority(&current, &capabilities)
        != corporate::authority(&observed["organization"], &observed["observation"])
    {
        return Err(invalid());
    }
    let target = request.project(
        &access.corporate(&request, organization)?,
        organization,
        &binding.account_id,
    )?;
    if coordinates(&target) != coordinates(&observed["data"])
        || target["authorization_revision"]
            != capabilities["capabilities"]["authorization_revision"]
    {
        return Err(invalid());
    }
    let selected = provider_project
        .map(|selected| {
            target["providers"]
                .as_array()
                .ok_or_else(invalid)?
                .iter()
                .find(|provider| provider["provider_project_id"] == selected)
                .cloned()
                .ok_or_else(invalid)
        })
        .transpose()?;
    {
        let store = owner.planning()?;
        let current = passports::registered(&store.connection, &registered.path, &owner)?;
        let held = registered.directory.dir_metadata().map_err(|_| invalid())?;
        if current.identity != registered.identity
            || current.path != registered.path
            || current.project != registered.project
            || [held.dev().to_string(), held.ino().to_string()] != registered.identity
        {
            return Err(invalid());
        }
    }
    // No account revalidation or registry opens occur while Store is held.
    if checkout::observe(&registered.path, git_executable)? != checkout {
        return Err(invalid());
    }
    context.bind()?.revalidate()?;
    access.revalidate()?;
    let provider_revision = selected
        .as_ref()
        .map(|provider| {
            provider["revision"]
                .as_u64()
                .map(|value| value.to_string())
                .ok_or_else(invalid)
        })
        .transpose()?;
    let local = json!({"local_project_id":registered.project["stable_id"],
        "local_revision":registered.project["revision_id"],"owner_account_id":owner.account_id,
        "root":checkout["checkout"]["topology"]["root"]});
    let request_coordinates = json!({"schema_version":1,
        "local_project_id":local["local_project_id"],"local_revision":local["local_revision"],
        "remote_project_id":remote_project,"remote_revision":target["remote_revision"],
        "provider_project_id":provider_project,"provider_revision":provider_revision,
        "authorization_revision":target["authorization_revision"]});
    let result = json!({"schema_version":1,"context":context,"context_digest":context.digest()?,
        "account":binding,"organization":current,"observation":capabilities,"local_project":local,
        "checkout":checkout,"target":target,"selected_provider":selected,
        "request_coordinates":request_coordinates,"online_verified":true,
        "observation_only":true,"installation_authority":false,"provider_identity_verified":false,
        "link_created":false,"binding_created":false,"request_admitted":false});
    let result = json!({"preview_digest":digest::sha256(&canonical::bytes(
        &json!(["ai-stp-native-project-link-preview/1",result]))?),"preview":result});
    finish(result, &mut access, &owner, &registered)
}
