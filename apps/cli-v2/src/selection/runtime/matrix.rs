//! Independent local candidates assessed against authenticated harness targets.

use std::{collections::BTreeSet, path::Path};

use rusqlite::{Connection, OptionalExtension, params};
use serde::Deserialize;
use serde_json::{Value, json};

use super::{MAX_CONTENT, Selector, inputs_with_budget, owner};
use crate::{
    authoring::Identity,
    canonical,
    error::{Failure, Result},
    files,
    objects::Objects,
    passport,
    provider::{Info, artifact, runtime, trust},
    selection::eligibility,
    store::{Store, database},
};

const MAX_REPORT: usize = 8 * 1024 * 1024;

fn default_limit() -> usize {
    10
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Request {
    targets: Vec<Selector>,
    #[serde(default)]
    after: Option<String>,
    #[serde(default = "default_limit")]
    limit: usize,
    #[serde(default)]
    for_redistribution: bool,
}

fn invalid() -> Failure {
    Failure::input(
        "the matrix requires one to seven distinct harness targets, an object cursor and a limit from 1 to 50",
    )
}

impl Request {
    pub(super) fn parse(path: &Path) -> Result<Self> {
        let mut request: Self =
            serde_json::from_value(canonical::parse(&files::read(path, 16 * 1024)?)?)
                .map_err(|_| invalid())?;
        if request.targets.is_empty()
            || request.targets.len() > 7
            || !(1..=50).contains(&request.limit)
            || request.after.as_ref().is_some_and(|id| {
                !passport::stable_id(id, "component") && !passport::stable_id(id, "setup")
            })
        {
            return Err(invalid());
        }
        let mut unique = BTreeSet::new();
        for target in &request.targets {
            target.validate()?;
            if !unique.insert(&target.harness_id) {
                return Err(invalid());
            }
        }
        request
            .targets
            .sort_by(|a, b| a.harness_id.cmp(&b.harness_id));
        Ok(request)
    }
}

struct Candidate {
    id: String,
    kind: String,
    coordinate: Option<Value>,
}

fn page(connection: &Connection, request: &Request) -> Result<(Vec<Candidate>, Option<String>)> {
    let mut statement = connection.prepare(
        "SELECT stable_id,kind FROM entity e WHERE kind IN ('component','setup') AND stable_id>? AND NOT EXISTS(SELECT 1 FROM tombstone t WHERE t.stable_id=e.stable_id) ORDER BY stable_id LIMIT ?",
    ).map_err(database)?;
    let rows = statement
        .query_map(
            params![
                request.after.as_deref().unwrap_or(""),
                request.limit as i64 + 1
            ],
            |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)),
        )
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    let next = if rows.len() > request.limit {
        rows.get(request.limit - 1).map(|r| r.0.clone())
    } else {
        None
    };
    let mut candidates = Vec::new();
    for (id, kind) in rows.into_iter().take(request.limit) {
        if !passport::stable_id(&id, &kind) {
            return Err(Failure::precondition(
                "a local candidate identity is invalid",
            ));
        }
        let version: Option<(String,String)> = connection.query_row(
            "SELECT version,passport_digest FROM object_version WHERE stable_id=? ORDER BY major DESC,minor DESC LIMIT 1",
            [&id],|r|Ok((r.get(0)?,r.get(1)?))).optional().map_err(database)?;
        let coordinate = version.map(|(version,passport_digest)|json!({"stable_id":id,"version":version,"passport_digest":passport_digest}));
        candidates.push(Candidate {
            id,
            kind,
            coordinate,
        });
    }
    Ok((candidates, next))
}

fn render(
    connection: &Connection,
    request: &Request,
    identity: &Identity,
    page: (Vec<Candidate>, Option<String>),
    providers: Option<&[(Info, Value)]>,
) -> Result<Value> {
    if providers.is_some_and(|p| p.len() != request.targets.len()) {
        return Err(Failure::precondition(
            "matrix provider observations are incomplete",
        ));
    }
    let mut targets = Vec::new();
    for (index, selector) in request.targets.iter().enumerate() {
        let mut target = selector.target(identity)?;
        target.for_redistribution = request.for_redistribution;
        targets.push(json!({"selector":selector,"target":target,
            "provider":providers.map(|p|&p[index].1),"provider_observed":providers.is_some()}));
    }
    let mut size = canonical::bytes(&json!(targets))?.len();
    let mut verified = 0u64;
    let mut env_present = BTreeSet::new();
    let mut candidates = Vec::new();
    for candidate in page.0 {
        let mut row = json!({"stable_id":candidate.id,"kind":candidate.kind,
            "coordinate":candidate.coordinate,"state":"unreleased","graph":null,
            "cells":[],"eligible_somewhere":false,"refusals":[{"code":"immutable_version_missing","summary":"Release an exact immutable version before selection."}]});
        if let Some(reference) = candidate.coordinate {
            let providers = providers.ok_or_else(|| {
                Failure::precondition("the matrix requires current provider observations")
            })?;
            let id = reference["stable_id"].as_str().ok_or_else(invalid)?;
            let version = reference["version"].as_str().ok_or_else(invalid)?;
            let digest = reference["passport_digest"].as_str().ok_or_else(invalid)?;
            let document = Objects { connection }.exact_version(id, version, Some(digest))?;
            if document["kind"] != candidate.kind {
                return Err(Failure::precondition(
                    "candidate kind disagrees with its exact version",
                ));
            }
            let roots = [reference];
            let observed = inputs_with_budget(
                connection,
                &roots,
                request.targets[0].target(identity)?,
                MAX_CONTENT - verified,
            )?;
            verified += observed.bytes;
            env_present.extend(observed.target.env_present.iter().cloned());
            let mut cells = Vec::new();
            let mut eligible = false;
            let mut cell_bytes = 0usize;
            for (index, selector) in request.targets.iter().enumerate() {
                let mut target = selector.target(identity)?;
                target.for_redistribution = request.for_redistribution;
                target.env_present.clone_from(&observed.target.env_present);
                let mut assessment = eligibility::assess_connection(
                    connection,
                    &roots,
                    &target,
                    &observed.evidence,
                    Some(&providers[index].0),
                )?;
                eligible |= assessment["admissible"] == true;
                let graph = assessment
                    .as_object_mut()
                    .ok_or_else(invalid)?
                    .remove("graph")
                    .ok_or_else(invalid)?;
                if index == 0 {
                    row["graph"] = graph;
                }
                let cell = json!({"harness_id":selector.harness_id,"scope":selector.scope,"env_present":target.env_present,"assessment":assessment});
                cell_bytes = cell_bytes.saturating_add(canonical::bytes(&cell)?.len());
                if size
                    .saturating_add(cell_bytes)
                    .saturating_add(canonical::bytes(&row)?.len())
                    > MAX_REPORT
                {
                    return Err(Failure::precondition(
                        "the matrix exceeds 8 MiB of report data; reduce the page limit",
                    ));
                }
                cells.push(cell);
            }
            row["state"] = "released".into();
            row["refusals"] = json!([]);
            row["cells"] = json!(cells);
            row["eligible_somewhere"] = eligible.into();
        }
        size = size
            .checked_add(canonical::bytes(&row)?.len())
            .ok_or_else(invalid)?;
        if size > MAX_REPORT {
            return Err(Failure::precondition(
                "the matrix exceeds 8 MiB of report data; reduce the page limit",
            ));
        }
        candidates.push(row);
    }
    for target in &mut targets {
        target["target"]["env_present"] = json!(env_present);
    }
    let report = json!({"schema_version":1,"candidate_policy":"latest_immutable_per_object",
        "targets":targets,"candidates":candidates,"next_after":page.1,"verified_artifact_bytes":verified,
        "not_observed":["harness_version","project_capabilities","cloud_trust","cloud_grants"],
        "permission_policy":"none_granted","installation_authorized":false,"harness_written":false});
    if canonical::bytes(&report)?.len() > MAX_REPORT {
        return Err(Failure::precondition(
            "the matrix exceeds 8 MiB of report data; reduce the page limit",
        ));
    }
    Ok(report)
}

/// Shared with the real-state proof; only this runtime establishes provider authority.
pub(super) fn assess_snapshot(
    connection: &Connection,
    request: &Request,
    identity: &Identity,
    providers: &[(Info, Value)],
) -> Result<Value> {
    render(
        connection,
        request,
        identity,
        page(connection, request)?,
        Some(providers),
    )
}

pub fn assess(parent: &Path, path: &Path) -> Result<Value> {
    let request = Request::parse(path)?;
    let identity = owner(parent)?;
    let mut store = Store::planning(parent)?;
    let empty = store.transaction(|t| {
        let page = page(t, &request)?;
        if page.0.iter().all(|c| c.coordinate.is_none()) {
            render(t, &request, &identity, page, None).map(Some)
        } else {
            Ok(None)
        }
    })?;
    drop(store);
    if let Some(report) = empty {
        return Ok(report);
    }

    // Authenticate once per harness, outside the registry lock. Drop executable
    // payloads after observation so a matrix does not retain seven native binaries.
    let runtime = runtime::Runtime::observe()?;
    let trust = trust::refresh(parent)?;
    let mut providers = Vec::new();
    for selector in &request.targets {
        let artifact = artifact::fetch(
            &selector.harness_id,
            &selector.provider_version,
            runtime::platform()?,
            &trust,
        )?;
        providers.push(runtime.declaration(&artifact)?);
    }
    if owner(parent)? != identity {
        return Err(Failure::precondition(
            "the isolated identity changed during matrix observation",
        ));
    }
    let mut store = Store::planning(parent)?;
    store.transaction(|t| {
        let report = assess_snapshot(t, &request, &identity, &providers)?;
        trust.root()?;
        Ok(report)
    })
}
