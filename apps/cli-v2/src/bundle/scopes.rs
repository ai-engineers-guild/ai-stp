//! Complete graph coverage across explicitly selected provider scopes.
//! Per-root packages keep the original setup identity and exact immutable bytes.

use std::collections::{BTreeMap, BTreeSet};

use rusqlite::Connection;
use serde_json::{Value, json};

use super::{Bundle, Hosts, Qualified, composition::Composition, exact, invalid, text};
use crate::{
    error::Result,
    projection::{self, Scope},
    provider::Info,
    selection::{
        eligibility::{self, Evidence, Target},
        graph,
    },
    store::Store,
};

pub struct Compiled {
    pub assessment: Value,
    pub bundles: BTreeMap<Scope, Bundle>,
}

pub fn compile(
    store: &mut Store,
    setup: &Value,
    target: &Target,
    evidence: &BTreeMap<String, Evidence>,
    provider: &Info,
    hosts: &BTreeMap<Scope, Hosts>,
    placements: &BTreeMap<String, Scope>,
) -> Result<Compiled> {
    store.transaction(|connection| {
        compile_snapshot(
            connection, setup, target, evidence, provider, hosts, placements,
        )
    })
}

pub(crate) fn compile_snapshot(
    connection: &Connection,
    setup: &Value,
    target: &Target,
    evidence: &BTreeMap<String, Evidence>,
    provider: &Info,
    hosts: &BTreeMap<Scope, Hosts>,
    placements: &BTreeMap<String, Scope>,
) -> Result<Compiled> {
    if !(2..=3).contains(&hosts.len()) || placements.len() > 512 {
        return Err(invalid(
            "a complete multi-root bundle requires two or three explicit scopes",
        ));
    }
    let mut host_identities = BTreeMap::new();
    let mut total_hosts = 0usize;
    for (scope, values) in hosts {
        if !provider.supports_target(*scope) {
            return Err(invalid(
                "the component does not support a requested projection scope",
            ));
        }
        host_identities.insert(*scope, super::validate_inputs(setup, values)?);
        for value in values.values().flatten() {
            total_hosts = total_hosts
                .checked_add(value.len())
                .ok_or_else(|| invalid("multi-root host inputs exceed their bounds"))?;
        }
    }
    if total_hosts > super::MAX_BYTES {
        return Err(invalid(
            "multi-root host inputs exceed their aggregate byte bound",
        ));
    }
    let routed = route(
        connection,
        setup,
        &target.harness_id,
        &hosts.keys().copied().collect(),
        placements,
    )?;
    let mut assessments = Vec::new();
    let first = *hosts
        .keys()
        .next()
        .ok_or_else(|| invalid("projection scopes are absent"))?;
    for document in &routed.documents {
        let id = text(document, "stable_id")?;
        let held = evidence.get(id).ok_or_else(|| {
            invalid("an exact graph member has no established eligibility evidence")
        })?;
        let mut scoped = target.clone();
        scoped.scope = routed.assigned.get(id).copied().unwrap_or(first);
        assessments.push(eligibility::assess(
            document,
            &scoped,
            held,
            Some(provider),
        )?);
    }
    let Routed {
        graph,
        documents,
        assigned,
        selected,
    } = routed;
    let admissible = assessments.iter().all(|item| item["admissible"] == true);
    let automatic = admissible
        && assessments
            .iter()
            .all(|item| item["auto_selectable"] == true);
    let assessment = json!({"schema_version":1,"graph":graph,"assessments":assessments,
        "admissible":admissible,"auto_selectable":automatic,"scope_bindings":assigned});
    if !admissible {
        return Err(
            invalid("the complete multi-root setup is not mechanically admissible")
                .with_details([("eligibility".into(), assessment)]),
        );
    }
    let mut composition = Composition::new(&target.harness_id);
    let mut projection_bytes = 0u64;
    for document in &documents {
        if document["kind"] == "setup" {
            continue;
        }
        let id = text(document, "stable_id")?;
        let selected_scope = *assigned
            .get(id)
            .ok_or_else(|| invalid("component placement is absent"))?;
        let (_, scope) = projection::adaptation(document, &target.harness_id, selected_scope)
            .ok_or_else(|| invalid("an exact scope adaptation disappeared"))?;
        projection_bytes = projection_bytes
            .checked_add(
                scope["projection_artifact"]["size_bytes"]
                    .as_u64()
                    .ok_or_else(|| invalid("projection size is absent"))?,
            )
            .ok_or_else(|| invalid("multi-root projections exceed their bounds"))?;
        if projection_bytes > super::MAX_BYTES as u64 {
            return Err(invalid(
                "multi-root projections exceed their aggregate byte bound",
            ));
        }
        composition.include_at(document, scope, &assessment, Some(selected_scope))?;
        for member in scope["members"]
            .as_array()
            .ok_or_else(|| invalid("projection members are absent"))?
        {
            composition.claim(
                id,
                &format!("{}/{}", selected_scope.as_str(), text(member, "path")?),
            )?;
        }
    }
    composition.validate_declared_conflicts()?;
    let mut bundles = BTreeMap::new();
    let mut total_bytes = 0usize;
    let mut total_files = 0usize;
    let mut content_bytes = 0u64;
    for (scope, nodes) in selected {
        let mut scoped = target.clone();
        scoped.scope = scope;
        let bundle = super::compile_qualified(
            connection,
            setup,
            &scoped,
            provider,
            hosts
                .get(&scope)
                .ok_or_else(|| invalid("scope host inputs are absent"))?,
            Qualified {
                assessment: assessment.clone(),
                nodes,
            },
            host_identities
                .remove(&scope)
                .ok_or_else(|| invalid("scope host identities are absent"))?,
        )?;
        total_bytes = total_bytes
            .checked_add(bundle.archive.len())
            .ok_or_else(|| invalid("multi-root bundles exceed their bounds"))?;
        total_files += bundle.manifest["files"]
            .as_array()
            .ok_or_else(|| invalid("bundle files are absent"))?
            .len();
        for file in bundle.manifest["files"]
            .as_array()
            .ok_or_else(|| invalid("bundle files are absent"))?
        {
            content_bytes = content_bytes
                .checked_add(
                    file["byte_length"]
                        .as_u64()
                        .ok_or_else(|| invalid("bundle file size is absent"))?,
                )
                .ok_or_else(|| invalid("multi-root content exceeds its bounds"))?;
        }
        if total_bytes > super::MAX_BYTES
            || total_files > super::MAX_FILES
            || content_bytes > super::MAX_BYTES as u64
        {
            return Err(invalid(
                "multi-root bundles exceed their aggregate content bounds",
            ));
        }
        bundles.insert(scope, bundle);
    }
    Ok(Compiled {
        assessment,
        bundles,
    })
}

pub(super) struct Routed {
    graph: Value,
    pub(super) documents: Vec<Value>,
    pub(super) assigned: BTreeMap<String, Scope>,
    pub(super) selected: BTreeMap<Scope, Vec<Value>>,
}

pub(super) fn route(
    connection: &Connection,
    setup: &Value,
    harness: &str,
    scopes: &BTreeSet<Scope>,
    placements: &BTreeMap<String, Scope>,
) -> Result<Routed> {
    super::validate_inputs(setup, &Hosts::new())?;
    if !(2..=3).contains(&scopes.len()) || placements.len() > 512 {
        return Err(invalid(
            "a complete multi-root bundle requires two or three explicit scopes",
        ));
    }
    let graph = graph::exact(connection, std::slice::from_ref(setup))?;
    if graph["resolved"] != true {
        return Err(invalid("the complete multi-root setup graph is unresolved")
            .with_details([("graph".into(), graph)]));
    }
    let nodes = graph["nodes"]
        .as_array()
        .ok_or_else(|| invalid("graph nodes are missing"))?;
    let mut assigned = BTreeMap::new();
    let mut documents = Vec::new();
    let mut selected: BTreeMap<Scope, Vec<Value>> =
        scopes.iter().map(|scope| (*scope, Vec::new())).collect();
    for node in nodes {
        let document = exact(connection, node)?;
        let id = text(&document, "stable_id")?;
        if document["kind"] != "setup" {
            let candidates: Vec<_> = scopes
                .iter()
                .copied()
                .filter(|scope| projection::adaptation(&document, harness, *scope).is_some())
                .collect();
            let scope = match placements.get(id) {
                Some(scope) if candidates.contains(scope) => *scope,
                None if candidates.len() == 1 => candidates[0],
                _ => return Err(invalid("every component needs one explicit supported scope; ambiguous routing requires a placement")
                    .with_details([("stable_id".into(), id.into()), ("available_scopes".into(), json!(candidates))])),
            };
            assigned.insert(id.to_owned(), scope);
            selected
                .get_mut(&scope)
                .ok_or_else(|| invalid("selected scope is absent"))?
                .push(node.clone());
        }
        documents.push(document);
    }
    if placements.keys().any(|id| !assigned.contains_key(id))
        || selected.values().any(Vec::is_empty)
    {
        return Err(invalid(
            "placements must cover only graph components and every requested root must receive content",
        ));
    }
    Ok(Routed {
        graph,
        documents,
        assigned,
        selected,
    })
}

/// Enumerate contribution hosts without reading target files. Compilation
/// independently revalidates this routing in its own consistent snapshot.
pub fn contribution_paths(
    store: &mut Store,
    setup: &Value,
    harness: &str,
    scopes: &BTreeSet<Scope>,
    placements: &BTreeMap<String, Scope>,
) -> Result<BTreeMap<Scope, BTreeSet<String>>> {
    store.transaction(|connection| paths(connection, setup, harness, scopes, placements))
}

pub(crate) fn paths(
    connection: &Connection,
    setup: &Value,
    harness: &str,
    scopes: &BTreeSet<Scope>,
    placements: &BTreeMap<String, Scope>,
) -> Result<BTreeMap<Scope, BTreeSet<String>>> {
    let routed = route(connection, setup, harness, scopes, placements)?;
    let mut paths: BTreeMap<_, _> = scopes
        .iter()
        .map(|scope| (*scope, BTreeSet::new()))
        .collect();
    for document in &routed.documents {
        if let Some(scope) = routed.assigned.get(text(document, "stable_id")?) {
            super::hosts::include(
                document,
                harness,
                *scope,
                paths
                    .get_mut(scope)
                    .ok_or_else(|| invalid("host scope is absent"))?,
            )?;
        }
    }
    Ok(paths)
}
