//! Current composition observations from exact roots or a retained proposal.

use std::path::Path;

use rusqlite::Connection;
use serde::Deserialize;
use serde_json::{Value, json};

use super::{
    MAX_REQUEST, Request, Selector, access, inputs, invalid, owner, program, with_provider,
};
use crate::{
    authoring::Identity,
    bundle, canonical,
    error::{Failure, Result},
    files, passport,
    projection::Scope,
    provider::Info,
    selection::{graph, sessions},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ProposalRequest {
    proposal_id: String,
    scope: Scope,
    provider_version: String,
    #[serde(default)]
    harness_executable: Option<program::Executable>,
    #[serde(default)]
    access: access::Request,
}

enum Source {
    Exact(Request),
    Proposal(ProposalRequest),
}

struct Selected {
    selector: Selector,
    roots: Vec<Value>,
    redistribution: bool,
    proposal: Value,
    access: access::Request,
}

impl Source {
    fn parse(path: &Path) -> Result<Self> {
        let mut value = crate::wire::parse(&files::read(path, MAX_REQUEST)?)?;
        if value.get("proposal_id").is_some() {
            crate::provider::managed::resolve_request(&mut value);
            let request: ProposalRequest = serde_json::from_value(value).map_err(|_| invalid())?;
            if !passport::stable_id(&request.proposal_id, "proposal") {
                return Err(invalid());
            }
            request.access.validate()?;
            Ok(Self::Proposal(request))
        } else {
            Ok(Self::Exact(Request::from_value(value, false)?))
        }
    }

    fn selected(&self, connection: &Connection) -> Result<Selected> {
        let selected = match self {
            Self::Exact(request) => Selected {
                selector: request.selector(),
                roots: request
                    .members
                    .iter()
                    .map(|member| serde_json::to_value(member).map_err(|_| invalid()))
                    .collect::<Result<_>>()?,
                redistribution: request.for_redistribution,
                proposal: Value::Null,
                access: request.access.clone(),
            },
            Self::Proposal(request) => {
                let held = sessions::read_in(connection, &request.proposal_id)?;
                let at = format!("{:.3}", jiff::Timestamp::now());
                Selected {
                    selector: Selector {
                        harness_id: held.harness_id.clone(),
                        scope: request.scope,
                        provider_version: request.provider_version.clone(),
                        harness_executable: request.harness_executable.clone(),
                    },
                    roots: held
                        .members
                        .iter()
                        .map(|member| {
                            serde_json::to_value(member.reference()).map_err(|_| invalid())
                        })
                        .collect::<Result<_>>()?,
                    redistribution: false,
                    proposal: json!({"proposal_id":held.proposal_id,"snapshot":held.snapshot,
                        "state":held.state(&at)?,"context_freshness":"not_evaluated"}),
                    access: request.access.clone(),
                }
            }
        };
        selected.selector.validate()?;
        Ok(selected)
    }
}

fn inspect(
    connection: &Connection,
    parent: &Path,
    selected: Selected,
    identity: &Identity,
    provider: Option<&Info>,
    access: Option<&access::Observed>,
) -> Result<Value> {
    let (mut target, program) = selected.selector.observe(connection, parent, identity)?;
    target.for_redistribution = selected.redistribution;
    let mut observed = inputs(connection, &selected.roots, target)?;
    if let Some(access) = access {
        access.apply(&mut observed)?;
    }
    let mut result = bundle::reports::inspect_snapshot(
        connection,
        &selected.roots,
        &observed.target,
        &observed.evidence,
        provider,
    )?;
    let mut not_observed = program::unobserved(observed.target.harness_version.is_empty());
    not_observed.push("contribution_hosts");
    result["target"] = serde_json::to_value(observed.target).map_err(|_| invalid())?;
    result["program_observation_digest"] = json!(program);
    result["verified_artifact_bytes"] = observed.bytes.into();
    result["proposal"] = selected.proposal;
    result["provider"] = Value::Null;
    result["provider_observed"] = false.into();
    result["not_observed"] = json!(not_observed);
    result["permission_policy"] = "none_granted".into();
    if let Some(access) = access
        && let Some(observation) = access.report()?
    {
        result["access_observation"] = observation;
    }
    bounded(result)
}

fn bounded(result: Value) -> Result<Value> {
    if canonical::bytes(&result)?.len() > 8 * 1024 * 1024 {
        return Err(Failure::precondition("composition reports exceed 8 MiB"));
    }
    Ok(result)
}

pub fn read(parent: &Path, path: &Path) -> Result<Value> {
    let source = Source::parse(path)?;
    let identity = owner(parent)?;
    let mut store = identity.planning()?;
    let (selector, access_request, roots, offline) = store.transaction(|t| {
        let selected = source.selected(t)?;
        let selector = selected.selector.clone();
        let access = selected.access.clone();
        let roots = selected.roots.clone();
        let graph = graph::exact(t, &selected.roots)?;
        let offline = if selected.roots.is_empty() || graph["resolved"] != true {
            Some(inspect(t, parent, selected, &identity, None, None)?)
        } else {
            None
        };
        Ok((selector, access, roots, offline))
    })?;
    drop(store);
    if let Some(report) = offline {
        return Ok(report);
    }
    with_provider(
        parent,
        &selector,
        &identity,
        |provider, artifact, report| {
            let access = access::Observed::capture(
                parent,
                &identity,
                &[roots],
                access::Intent::Review(&access_request),
            )?;
            let mut store = identity.planning()?;
            store.transaction(|t| {
                let selected = source.selected(t)?;
                if selected.selector.harness_id != selector.harness_id {
                    return Err(Failure::precondition(
                        "the proposal harness changed during provider observation",
                    ));
                }
                let mut result = inspect(
                    t,
                    parent,
                    selected,
                    &identity,
                    Some(provider),
                    Some(&access),
                )?;
                artifact.executable()?;
                result["provider"] = report;
                result["provider_observed"] = true.into();
                bounded(result)
            })
        },
    )
}
