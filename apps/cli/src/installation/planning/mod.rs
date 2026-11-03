//! Exact native installation observations, distinct from external provider plans.
//!
//! Planning creates no configuration transaction, target metadata or harness writes.
//! A retained document is data, never a grant for later protected effects.

mod application;
mod execution;
mod model;
mod removal;
mod retained;
#[cfg(test)]
mod tests;

pub use application::{apply_prepared, configuration_status, confirm_session, effective, pending};
pub use execution::{Reviewed, cancel_preparation};
pub use model::{Operation, Plan, Planned, Request};
pub use removal::create_removal;

use super::{forward, profiles::Profiles, target::Target};
use crate::{
    account::{
        contexts::{self, Context},
        corporate as company, project_links,
    },
    authoring::runtime,
    bundle::{
        self,
        reader::{Input, Package},
    },
    digest,
    error::{Failure, Result},
    files::physical::DirectoryIdentity,
    projection::Scope,
    selection::graph,
    store::Store,
};
use model::{Corporate, File, Root};
use serde_json::Value;
use std::{collections::BTreeMap, path::Path};

const CONTROL: &str = ".ai-stp-native";
fn invalid() -> Failure {
    Failure::precondition(
        "the original native installation plan, context, graph or physical roots changed",
    )
}
fn native<T>(value: super::Result<T>) -> Result<T> {
    value.map_err(|source| {
        invalid().with_details([("reason".into(), source.reason().as_str().into())])
    })
}
fn value<T: serde::Serialize>(value: &T) -> Result<Value> {
    serde_json::to_value(value).map_err(|_| invalid())
}
fn binding(target: &Target) -> Result<model::Directory> {
    Ok(model::Directory {
        path: target.root().to_owned(),
        physical: DirectoryIdentity::capture(&native(target.directory())?)?,
    })
}
fn corporate(
    root: &Path,
    context: &Context,
    id: Option<&str>,
    harness: &str,
    setup: &Value,
) -> Result<Option<Corporate>> {
    let is_corporate = matches!(&context.authority,
        contexts::Authority::Remote { organization,.. } if organization["kind"]=="corporate");
    match (is_corporate, id) {
        (false, None) => Ok(None),
        (true, Some(id)) => {
            let (_, held) = project_links::binding::capture(root, id)?;
            project_links::reader::Reader::matches_binding(context, &held)?;
            if held.link["state"] != "linked" {
                return Err(invalid());
            }
            let linked = company::observe(
                root,
                Some(&context.context_id),
                company::Request::LinkOutcome {
                    plan_id: held.link["plan_id"].as_str().ok_or_else(invalid)?.into(),
                },
            )?;
            let link = &linked["observation"];
            if link["data"]["state"] != "applied" || link["data"]["link"] != held.link {
                return Err(invalid());
            }
            let assigned = company::observe(
                root,
                Some(&context.context_id),
                company::Request::AssignmentPreview {
                    harness: harness.into(),
                    project_id: Some(
                        held.link["remote_project_id"]
                            .as_str()
                            .ok_or_else(invalid)?
                            .into(),
                    ),
                    technology_id: None,
                },
            )?;
            let assigned = &assigned["observation"];
            let (assignment_id, assignment_digest, authorization_digest) =
                assignment(context, &held.link, link, assigned, harness, setup)?;
            Ok(Some(Corporate {
                binding_operation_id: id.into(),
                binding_digest: digest::canonical("ai-stp:plan:v1", &value(&held)?)?,
                original_context: held.context,
                original_account: held.account,
                organization_id: held.link["organization_id"]
                    .as_str()
                    .ok_or_else(invalid)?
                    .into(),
                local_project_id: held.local_project["stable_id"]
                    .as_str()
                    .ok_or_else(invalid)?
                    .into(),
                remote_project_id: held.link["remote_project_id"]
                    .as_str()
                    .ok_or_else(invalid)?
                    .into(),
                link_id: held.link["link_id"].as_str().ok_or_else(invalid)?.into(),
                link_digest: digest::canonical("ai-stp:plan:v1", &held.link)?,
                authorization_digest,
                assignment_digest,
                assignment_id,
                checkout_root: held.checkout_root,
            }))
        }
        _ => Err(invalid()),
    }
}

// A current assignment remains an observation. The original explicit native
// operation and fresh protected-effect checks are separate authorization layers.
fn assignment(
    context: &Context,
    link: &Value,
    linked: &Value,
    assigned: &Value,
    harness: &str,
    setup: &Value,
) -> Result<(Option<String>, String, String)> {
    context.digest()?;
    let contexts::Authority::Remote {
        account,
        organization,
        ..
    } = &context.authority
    else {
        return Err(invalid());
    };
    let fresh: crate::account::access::Binding =
        serde_json::from_value(assigned["account"].clone()).map_err(|_| invalid())?;
    let mut previous: crate::account::access::Binding =
        serde_json::from_value(linked["account"].clone()).map_err(|_| invalid())?;
    fresh.validate()?;
    previous.validate()?;
    previous.revision.clone_from(&fresh.revision);
    let mut expected = account.as_ref().clone();
    expected.revision.clone_from(&fresh.revision);
    if fresh != previous
        || fresh != expected
        || organization["kind"] != "corporate"
        || organization["organization_id"] != link["organization_id"]
    {
        return Err(invalid());
    }
    let data = &assigned["data"];
    if assigned["context"] != value(context)?
        || linked["context"] != value(context)?
        || assigned["online_verified"] != true
        || linked["online_verified"] != true
        || assigned["observation_only"] != true
        || assigned["installation_authority"] != false
        || assigned["account"]["origin"] != linked["account"]["origin"]
        || assigned["account"]["account_id"] != linked["account"]["account_id"]
        || assigned["account"]["device_id"] != linked["account"]["device_id"]
        || company::authority(&assigned["organization"], &assigned["observation"])
            != company::authority(&linked["organization"], &linked["observation"])
        || data["organization_id"] != link["organization_id"]
        || data["project_id"] != link["remote_project_id"]
        || data["account_id"] != assigned["account"]["account_id"]
        || data["harness"] != harness
        || !data["technology_id"].is_null()
    {
        return Err(invalid());
    }
    let matching = data["items"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .filter(|item| item["object_kind"] == "setup" && item["stable_id"] == setup["stable_id"])
        .collect::<Vec<_>>();
    let [item] = matching.as_slice() else {
        return Err(invalid());
    };
    if item["state"] != "assigned"
        || !matches!(item["action"].as_str(), Some("install" | "update" | "none"))
        || !matches!(
            item["outcome"].as_str(),
            Some("missing" | "installed" | "outdated")
        )
        || item["harness"] != harness
        || item["version"] != setup["version"]
        || item["passport_digest"] != setup["passport_digest"]
    {
        return Err(invalid());
    }
    let id = item["assignment_id"].as_str().map(str::to_owned);
    Ok((
        id,
        digest::canonical("ai-stp:plan:v1", data)?,
        digest::canonical(
            "ai-stp:plan:v1",
            &company::authority(&assigned["organization"], &assigned["observation"]),
        )?,
    ))
}

/// Freeze one original context and complete native package set without writes.
/// Evidence/target observations are supplied by their owning runtime; this API
/// does not authenticate their serialized representation or grant execution.
pub fn create(root: &Path, context_id: &str, request: &Request, at: &str) -> Result<Planned> {
    let owner = runtime::owner(root)?;
    let expected_state = DirectoryIdentity::capture(owner.root_directory())?;
    let context = contexts::resolve(root, Some(context_id))?;
    context.require_current_native_identity(&owner)?;
    if context.root != root || request.target.owner_id != owner.account_id {
        return Err(invalid());
    }
    let corporate = corporate(
        root,
        &context,
        request.corporate_binding.as_deref(),
        &request.target.harness_id,
        &request.setup,
    )?;
    let planned = capture(&mut owner.planning()?, context, corporate, request, at)?;
    if planned.plan.state.physical != expected_state {
        return Err(invalid());
    }
    Ok(planned)
}

fn capture(
    store: &mut Store,
    context: Context,
    corporate: Option<Corporate>,
    request: &Request,
    at: &str,
) -> Result<Planned> {
    context.digest()?;
    request.target.validate()?;
    if request.target.owner_id != context.local_identity.account_id
        || !request.roots.contains_key(&request.target.scope)
        || !(1..=3).contains(&request.roots.len())
    {
        return Err(invalid());
    }
    let state = native(Target::resolve(&context.root, CONTROL))?;
    let mut targets = BTreeMap::new();
    for (scope, path) in &request.roots {
        let target = native(Target::resolve(path, CONTROL))?;
        if *scope == Scope::Project
            && let Some(corporate) = &corporate
        {
            let checkout = native(Target::resolve(&corporate.checkout_root, CONTROL))?;
            if binding(&checkout)?.physical != binding(&target)?.physical {
                return Err(invalid());
            }
        }
        crate::files::physical::require_disjoint(
            &native(state.directory())?,
            &native(target.directory())?,
        )?;
        let observed = binding(&target)?;
        if targets.values().any(|other: &Target| {
            binding(other).is_ok_and(|other| other.physical == observed.physical)
        }) {
            return Err(invalid());
        }
        targets.insert(*scope, target);
    }
    if let Some(company) = &corporate
        && request.roots.get(&Scope::Project) != Some(&company.checkout_root)
    {
        return Err(invalid());
    }
    let paths = bundle::scopes::contribution_paths(
        store,
        &request.setup,
        &request.target.harness_id,
        &request.roots.keys().copied().collect(),
        &request.placements,
    )?;
    let mut hosts = BTreeMap::new();
    for (scope, paths) in paths {
        let target = targets.get(&scope).ok_or_else(invalid)?;
        let mut observed = bundle::Hosts::new();
        for path in paths {
            observed.insert(
                path.clone(),
                native(forward::observe(target, &path))?
                    .1
                    .map(|content| content.bytes),
            );
        }
        hosts.insert(scope, observed);
    }
    let compiled = bundle::scopes::compile_native(
        store,
        &request.setup,
        &request.target,
        &request.evidence,
        &hosts,
        &request.placements,
    )?;
    let inputs = compiled
        .bundles
        .iter()
        .map(|(scope, package)| {
            Ok((
                *scope,
                Input {
                    archive: &package.archive,
                    hosts: hosts.get(scope).ok_or_else(invalid)?,
                },
            ))
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let packages = Package::read_native_set(store, &request.target.harness_id, &inputs)?;
    let mut roots = BTreeMap::new();
    let mut before_bytes = 0usize;
    for (scope, package) in packages {
        let target = targets.get(&scope).ok_or_else(invalid)?;
        let mut files = BTreeMap::new();
        for (path, file) in package.files {
            let (before, current) = native(forward::observe(target, &path))?;
            before_bytes = before_bytes
                .checked_add(before.byte_length())
                .ok_or_else(invalid)?;
            if before_bytes > 64 * 1024 * 1024 {
                return Err(invalid());
            }
            if file.contribution.is_some()
                && hosts.get(&scope).and_then(|hosts| hosts.get(&path))
                    != Some(&current.as_ref().map(|content| content.bytes.clone()))
            {
                return Err(invalid());
            }
            let after_mode = if cfg!(unix) && file.contribution.is_some() {
                current.as_ref().map_or(file.mode, |content| content.mode)
            } else if cfg!(unix) {
                file.mode
            } else {
                0o600
            };
            files.insert(
                path,
                File {
                    before,
                    after_digest: Some(digest::sha256(&file.bytes)),
                    after_bytes: Some(file.bytes.len()),
                    after_mode: Some(after_mode),
                    owner: file.owner,
                    contribution: file
                        .contribution
                        .map(serde_json::from_value)
                        .transpose()
                        .map_err(|_| invalid())?,
                },
            );
        }
        let profile = Profiles::resolve(&request.target.harness_id)?;
        let profile = profile.profile(scope).ok_or_else(invalid)?;
        roots.insert(
            scope,
            Root {
                directory: binding(target)?,
                profile_id: profile["profile_id"].as_str().ok_or_else(invalid)?.into(),
                profile_digest: profile["digest"].as_str().ok_or_else(invalid)?.into(),
                package: package.binding,
                files,
            },
        );
    }
    let graph = &compiled.assessment["graph"];
    let plan = Plan {
        schema_version: 1,
        format: "ai-stp-native-installation/1".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        operation: request.operation,
        source_operation: None,
        created_at: at.into(),
        expires_at: crate::authoring::expiry(at)?,
        state: binding(&state)?,
        context,
        corporate,
        engine_digest: digest::sha256(&crate::canonical::bytes(
            Profiles::resolve(&request.target.harness_id)?.document(),
        )?),
        target: request.target.clone(),
        setup: request.setup.clone(),
        graph_digest: digest::canonical("ai-stp:plan:v1", graph)?,
        graph_nodes: model::coordinates(graph)?,
        evidence: graph["nodes"]
            .as_array()
            .ok_or_else(invalid)?
            .iter()
            .map(|node| {
                let id = node["stable_id"].as_str().ok_or_else(invalid)?;
                Ok((
                    id.to_owned(),
                    request.evidence.get(id).ok_or_else(invalid)?.clone(),
                ))
            })
            .collect::<Result<BTreeMap<_, _>>>()?,
        scope_bindings: serde_json::from_value(compiled.assessment["scope_bindings"].clone())
            .map_err(|_| invalid())?,
        roots,
    };
    plan.validate()?;
    plan.revalidate_targets()?;
    Ok(Planned {
        plan,
        packages: compiled
            .bundles
            .into_iter()
            .map(|(scope, bundle)| (scope, bundle.archive))
            .collect(),
    })
}

impl Plan {
    /// Revalidate local observations before a separately authorized preparation.
    /// Corporate observations are refreshed through the original account; this
    /// still grants no protected effect and creates no harness state.
    pub fn revalidate(&self, root: &Path, at: &str) -> Result<()> {
        self.validate()?;
        let at = at.parse::<jiff::Timestamp>().map_err(|_| invalid())?;
        let created = self
            .created_at
            .parse::<jiff::Timestamp>()
            .map_err(|_| invalid())?;
        let expires = self
            .expires_at
            .parse::<jiff::Timestamp>()
            .map_err(|_| invalid())?;
        if at < created || at >= expires || root != self.state.path {
            return Err(invalid());
        }
        self.authorize(root)?;
        self.revalidate_targets()
    }

    pub(super) fn authorize(&self, root: &Path) -> Result<()> {
        self.validate()?;
        if root != self.state.path {
            return Err(invalid());
        }
        let owner = runtime::owner(root)?;
        if self.operation == Operation::Remove {
            self.context.require_current_native_identity(&owner)?;
            if DirectoryIdentity::capture(owner.root_directory())? != self.state.physical {
                return Err(invalid());
            }
            return Ok(());
        }
        let context = contexts::resolve(root, Some(&self.context.context_id))?;
        context.require_current_native_identity(&owner)?;
        if value(&context)? != value(&self.context)?
            || value(&corporate(
                root,
                &context,
                self.corporate
                    .as_ref()
                    .map(|c| c.binding_operation_id.as_str()),
                &self.target.harness_id,
                &self.setup,
            )?)? != value(&self.corporate)?
        {
            return Err(invalid());
        }
        let state = native(Target::resolve(root, CONTROL))?;
        if binding(&state)? != self.state
            || self.engine_digest
                != digest::sha256(&crate::canonical::bytes(
                    Profiles::resolve(&self.target.harness_id)?.document(),
                )?)
        {
            return Err(invalid());
        }
        let mut store = owner.planning()?;
        let graph = store.transaction(|connection| {
            graph::exact(connection, std::slice::from_ref(&self.setup))
        })?;
        if digest::canonical("ai-stp:plan:v1", &graph)? != self.graph_digest
            || model::coordinates(&graph)? != self.graph_nodes
        {
            return Err(invalid());
        }
        // Fresh account access must precede its own registry observation.
        drop(store);
        drop(owner);
        crate::selection::runtime::native::authorize(
            root,
            &self.context,
            &self.setup,
            &self.target,
            &self.scope_bindings,
            &self
                .evidence
                .values()
                .filter(|e| e.consented)
                .map(|e| e.passport_digest.clone())
                .collect(),
        )
    }

    fn revalidate_targets(&self) -> Result<()> {
        for root in self.roots.values() {
            let target = native(Target::resolve(&root.directory.path, CONTROL))?;
            if binding(&target)? != root.directory {
                return Err(invalid());
            }
            for (path, file) in &root.files {
                if native(forward::observe(&target, path))?.0 != file.before {
                    return Err(invalid());
                }
            }
        }
        Ok(())
    }
}
