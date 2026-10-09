//! Current composition observations from exact roots or a retained proposal.

use std::path::Path;

use rusqlite::Connection;
use serde::Deserialize;
use serde_json::{Value, json};

use super::{MAX_REQUEST, Request, Selector, inputs, invalid, owner, with_provider};
use crate::{
    authoring::Identity,
    bundle, canonical,
    error::{Failure, Result},
    files, passport,
    projection::Scope,
    provider::Info,
    selection::{graph, sessions},
    store::Store,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ProposalRequest {
    proposal_id: String,
    scope: Scope,
    provider_version: String,
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
}

impl Source {
    fn parse(path: &Path) -> Result<Self> {
        let value = canonical::parse(&files::read(path, MAX_REQUEST)?)?;
        if value.get("proposal_id").is_some() {
            let request: ProposalRequest = serde_json::from_value(value).map_err(|_| invalid())?;
            if !passport::stable_id(&request.proposal_id, "proposal") {
                return Err(invalid());
            }
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
            },
            Self::Proposal(request) => {
                let held = sessions::read_in(connection, &request.proposal_id)?;
                let at = format!("{:.3}", jiff::Timestamp::now());
                Selected {
                    selector: Selector {
                        harness_id: held.harness_id.clone(),
                        scope: request.scope,
                        provider_version: request.provider_version.clone(),
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
                }
            }
        };
        selected.selector.validate()?;
        Ok(selected)
    }
}

fn inspect(
    connection: &Connection,
    selected: Selected,
    identity: &Identity,
    provider: Option<&Info>,
) -> Result<Value> {
    let mut target = selected.selector.target(identity)?;
    target.for_redistribution = selected.redistribution;
    let observed = inputs(connection, &selected.roots, target)?;
    let mut result = bundle::reports::inspect_snapshot(
        connection,
        &selected.roots,
        &observed.target,
        &observed.evidence,
        provider,
    )?;
    result["target"] = serde_json::to_value(observed.target).map_err(|_| invalid())?;
    result["verified_artifact_bytes"] = observed.bytes.into();
    result["proposal"] = selected.proposal;
    result["provider"] = Value::Null;
    result["provider_observed"] = false.into();
    result["not_observed"] = json!([
        "harness_version",
        "project_capabilities",
        "cloud_trust",
        "cloud_grants",
        "contribution_hosts"
    ]);
    result["permission_policy"] = "none_granted".into();
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
    let mut store = Store::planning(parent)?;
    let (selector, offline) = store.transaction(|t| {
        let selected = source.selected(t)?;
        let selector = selected.selector.clone();
        let graph = graph::exact(t, &selected.roots)?;
        let offline = if selected.roots.is_empty() || graph["resolved"] != true {
            Some(inspect(t, selected, &identity, None)?)
        } else {
            None
        };
        Ok((selector, offline))
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
            let mut store = Store::planning(parent)?;
            store.transaction(|t| {
                let selected = source.selected(t)?;
                if selected.selector.harness_id != selector.harness_id {
                    return Err(Failure::precondition(
                        "the proposal harness changed during provider observation",
                    ));
                }
                let mut result = inspect(t, selected, &identity, Some(provider))?;
                artifact.executable()?;
                result["provider"] = report;
                result["provider_observed"] = true.into();
                bounded(result)
            })
        },
    )
}
