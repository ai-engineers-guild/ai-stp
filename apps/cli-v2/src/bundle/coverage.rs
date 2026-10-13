//! A scope package can claim a complete setup only through its full exact graph.

use rusqlite::Connection;
use serde_json::{Value, json};

use super::{exact, invalid, text};
use crate::{error::Result, projection, selection::graph, store::Store};

/// Check the complete transitive graph, including nested setups and dependencies.
/// This establishes package coverage, not evidence that a target was installed.
pub fn verify(
    store: &mut Store,
    setup: &Value,
    harness: &str,
    scope: projection::Scope,
    bindings: &[Value],
) -> Result<()> {
    store.transaction(|connection| verify_snapshot(connection, setup, harness, scope, bindings))
}

pub(crate) fn verify_snapshot(
    connection: &Connection,
    setup: &Value,
    harness: &str,
    scope: projection::Scope,
    bindings: &[Value],
) -> Result<()> {
    let refused =
        || invalid("project installation requires complete exact setup coverage at its scope");
    super::validate_inputs(setup, &super::Hosts::new())?;
    let graph = graph::exact(connection, std::slice::from_ref(setup))?;
    if graph["resolved"] != true {
        return Err(refused());
    }
    let mut expected = Vec::new();
    for node in graph["nodes"].as_array().ok_or_else(refused)? {
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
    Ok(())
}
