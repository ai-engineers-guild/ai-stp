//! A scope package can claim a complete setup only through its full exact graph.

use std::collections::{BTreeMap, BTreeSet};

use rusqlite::Connection;
use serde_json::{Value, json};

use super::{exact, invalid, text};
use crate::{error::Result, projection, selection::graph, store::Store};

/// An extracted package file, independently compared with its source projection.
#[derive(Clone)]
pub struct File {
    pub bytes: Vec<u8>,
    pub mode: u32,
    pub owner: String,
    pub contribution: Option<Value>,
}

/// Check the complete transitive graph, including nested setups and dependencies.
/// This establishes package coverage, not evidence that a target was installed.
pub fn verify(
    store: &mut Store,
    setup: &Value,
    harness: &str,
    scope: projection::Scope,
    bindings: &[Value],
) -> Result<()> {
    store.transaction(|connection| {
        components(connection, setup, harness, scope, bindings).map(|_| ())
    })
}

fn components(
    connection: &Connection,
    setup: &Value,
    harness: &str,
    scope: projection::Scope,
    bindings: &[Value],
) -> Result<Vec<Value>> {
    let refused =
        || invalid("project installation requires complete exact setup coverage at its scope");
    super::validate_inputs(setup, &super::Hosts::new())?;
    let graph = graph::exact(connection, std::slice::from_ref(setup))?;
    if graph["resolved"] != true {
        return Err(refused());
    }
    components_from_nodes(
        connection,
        harness,
        scope,
        bindings,
        graph["nodes"].as_array().ok_or_else(refused)?,
    )
}

fn components_from_nodes(
    connection: &Connection,
    harness: &str,
    scope: projection::Scope,
    bindings: &[Value],
    nodes: &[Value],
) -> Result<Vec<Value>> {
    let refused = || invalid("the package does not match its assigned exact setup members");
    let mut expected = Vec::new();
    let mut components = Vec::new();
    for node in nodes {
        let document = exact(connection, node)?;
        if document["kind"] == "setup" {
            if document["harness_id"] != harness {
                return Err(refused());
            }
            continue;
        }
        let (adaptation, projection) =
            projection::adaptation(&document, harness, scope).ok_or_else(refused)?;
        let mut paths = projection["members"]
            .as_array()
            .ok_or_else(refused)?
            .iter()
            .map(|member| text(member, "path"))
            .collect::<Result<Vec<_>>>()?;
        paths.sort();
        expected.push(
            json!({"stable_id":document["stable_id"],"version":document["version"],
            "passport_digest":node["passport_digest"],"adaptation_id":adaptation["adaptation_id"],
            "projection_artifact":projection["projection_artifact"],
            "provider_component_kind":projection["provider_component_kind"],
            "projection_kind":projection["projection_kind"],"member_paths":paths}),
        );
        components.push(document);
    }
    if expected.is_empty() || expected.len() != bindings.len() {
        return Err(refused());
    }
    let mut observed = bindings.to_vec();
    for values in [&mut expected, &mut observed] {
        values.sort_by(|a, b| a["stable_id"].as_str().cmp(&b["stable_id"].as_str()));
    }
    if expected != observed {
        return Err(refused());
    }
    Ok(components)
}

/// Bind installed attribution to exact source bytes, modes and ownership. Host
/// contributions use the compiler's assembly, including unrelated user content.
pub fn verify_payload(
    store: &mut Store,
    setup: &Value,
    harness: &str,
    scope: projection::Scope,
    bindings: &[Value],
    files: &BTreeMap<String, File>,
    hosts: &super::Hosts,
) -> Result<()> {
    store.transaction(|connection| {
        verify_payload_snapshot(connection, setup, harness, scope, bindings, files, hosts)
    })
}

pub(crate) fn verify_payload_snapshot(
    connection: &Connection,
    setup: &Value,
    harness: &str,
    scope: projection::Scope,
    bindings: &[Value],
    files: &BTreeMap<String, File>,
    hosts: &super::Hosts,
) -> Result<()> {
    let documents = components(connection, setup, harness, scope, bindings)?;
    verify_files(connection, &documents, setup, harness, scope, files, hosts)
}

fn verify_files(
    connection: &Connection,
    documents: &[Value],
    setup: &Value,
    harness: &str,
    scope: projection::Scope,
    files: &BTreeMap<String, File>,
    hosts: &super::Hosts,
) -> Result<()> {
    let refused = || invalid("the package content differs from the complete selected setup");
    super::validate_inputs(setup, hosts)?;
    if files.len() > super::MAX_FILES {
        return Err(refused());
    }
    let mut remaining_hosts: BTreeMap<_, _> = hosts
        .iter()
        .map(|(path, bytes)| (path.as_str(), bytes.as_deref()))
        .collect();
    let mut paths = BTreeSet::new();
    let (mut projection_bytes, mut output_bytes) = (0, 0usize);
    for component in documents {
        let id = text(component, "stable_id")?;
        let (_, projection) =
            projection::adaptation(component, harness, scope).ok_or_else(refused)?;
        let declarations: BTreeMap<_, _> = projection["members"]
            .as_array()
            .ok_or_else(refused)?
            .iter()
            .map(|value| Ok((text(value, "path")?, value)))
            .collect::<Result<_>>()?;
        for mut member in super::projected(
            connection,
            component,
            projection,
            harness,
            &mut projection_bytes,
        )? {
            let declaration = declarations.get(member.path.as_str()).ok_or_else(refused)?;
            let host = if declaration["ownership"] == "contribution" {
                remaining_hosts.remove(member.path.as_str())
            } else {
                None
            };
            let contribution = super::assemble(&mut member, declaration, harness, host)?;
            let observed = files.get(&member.path).ok_or_else(refused)?;
            output_bytes = output_bytes
                .checked_add(member.bytes.len())
                .ok_or_else(refused)?;
            if !paths.insert(member.path.clone())
                || paths.len() > super::MAX_FILES
                || member.bytes.len() > super::MAX_FILE_BYTES
                || output_bytes > super::MAX_BYTES
                || observed.bytes != member.bytes
                || observed.mode != member.mode
                || observed.owner != id
                || observed.contribution != contribution
            {
                return Err(refused());
            }
        }
    }
    if paths.len() != files.len() || !remaining_hosts.is_empty() {
        return Err(refused());
    }
    Ok(())
}

pub(crate) struct ScopedPayload<'a> {
    pub bindings: &'a [Value],
    pub files: &'a BTreeMap<String, File>,
    pub hosts: &'a super::Hosts,
}

/// Verify the complete graph once, then every assigned package and cross-root
/// logical conflict. A valid partial package cannot establish setup coverage.
pub(crate) fn verify_scoped_payloads(
    connection: &Connection,
    setup: &Value,
    harness: &str,
    payloads: &BTreeMap<projection::Scope, ScopedPayload<'_>>,
) -> Result<()> {
    let refused = || invalid("the complete setup does not match its scoped packages");
    let mut placements = BTreeMap::new();
    let mut bytes = 0usize;
    let mut count = 0usize;
    for (scope, payload) in payloads {
        for binding in payload.bindings {
            if placements
                .insert(text(binding, "stable_id")?.to_owned(), *scope)
                .is_some()
            {
                return Err(refused());
            }
        }
        count = count.checked_add(payload.files.len()).ok_or_else(refused)?;
        for file in payload.files.values() {
            bytes = bytes.checked_add(file.bytes.len()).ok_or_else(refused)?;
        }
    }
    if count > super::MAX_FILES || bytes > super::MAX_BYTES {
        return Err(refused());
    }
    let routed = super::scopes::route(
        connection,
        setup,
        harness,
        &payloads.keys().copied().collect(),
        &placements,
    )?;
    let mut composition = super::composition::Composition::new(harness);
    for document in &routed.documents {
        if document["kind"] == "setup" {
            continue;
        }
        let id = text(document, "stable_id")?;
        let scope = *routed.assigned.get(id).ok_or_else(refused)?;
        let (_, projection) =
            projection::adaptation(document, harness, scope).ok_or_else(refused)?;
        composition.include_constraints(document, projection, Some(scope))?;
        for member in projection["members"].as_array().ok_or_else(refused)? {
            composition.claim(id, &format!("{}/{}", scope.as_str(), text(member, "path")?))?;
        }
    }
    composition.validate_declared_conflicts()?;
    for (scope, payload) in payloads {
        let documents = components_from_nodes(
            connection,
            harness,
            *scope,
            payload.bindings,
            routed.selected.get(scope).ok_or_else(refused)?,
        )?;
        verify_files(
            connection,
            &documents,
            setup,
            harness,
            *scope,
            payload.files,
            payload.hosts,
        )?;
    }
    Ok(())
}
