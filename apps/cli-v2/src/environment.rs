//! Declared prerequisites of exact setup graphs, without preparing the environment.

use crate::{
    error::{Failure, Result},
    files, passport, projects,
    snapshot::Snapshot,
};
use cap_fs_ext::DirExt;
use rusqlite::OptionalExtension;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::Read,
    path::Path,
};

fn invalid() -> Failure {
    Failure::precondition("the environment target does not match the snapshot project identity")
}

fn bind_project(state: &Snapshot, project: &str, target: &Path) -> Result<()> {
    if !passport::stable_id(project, "project")
        || (!target.is_absolute() && !target.starts_with("~"))
    {
        return Err(Failure::input(
            "requirements need a project identifier and absolute target",
        ));
    }
    let (root, directory) = projects::open_root(target)?;
    let name = root.to_str().ok_or_else(invalid)?;
    let bound: Option<String> = state
        .connection
        .query_row(
            "SELECT stable_id FROM project_root WHERE root = ?",
            [name],
            |row| row.get(0),
        )
        .optional()
        .map_err(|_| invalid())?;
    let mut statement = state
        .connection
        .prepare("SELECT root FROM project_root WHERE stable_id = ? LIMIT 2")
        .map_err(|_| invalid())?;
    let roots = statement
        .query_map([project], |row| row.get::<_, String>(0))
        .map_err(|_| invalid())?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(|_| invalid())?;
    if roots.len() > 1 {
        return Err(invalid());
    }
    // SQLite stores Python's resolved spelling. Windows Rust canonical paths
    // include a verbatim prefix; compare resolved locations, not those strings.
    let same_location = roots.first().is_some_and(|held| {
        Path::new(held)
            .canonicalize()
            .is_ok_and(|held| held == root)
    });
    if let Some(bound) = bound {
        if bound != project {
            return Err(invalid());
        }
    } else if !same_location {
        let marker = directory
            .open_dir_nofollow(".ai-stp")
            .map_err(|_| invalid())?;
        let file = files::open_regular(&marker, Path::new("project-id")).map_err(|_| invalid())?;
        let mut bytes = Vec::new();
        file.take(129)
            .read_to_end(&mut bytes)
            .map_err(|_| invalid())?;
        if bytes.len() > 128
            || std::str::from_utf8(&bytes).map_err(|_| invalid())?.trim() != project
        {
            return Err(invalid());
        }
        // A copy cannot claim the original identity while its previous location
        // still exists or cannot be inspected.
        if roots
            .iter()
            .any(|root| Path::new(root).try_exists().unwrap_or(true))
        {
            return Err(invalid());
        }
    }
    let known: bool = state
        .connection
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM entity WHERE stable_id = ? AND kind = 'project')",
            [project],
            |row| row.get(0),
        )
        .map_err(|_| invalid())?;
    if !known {
        return Err(invalid());
    }
    Ok(())
}

fn requirement(
    kind: &str,
    identity: &str,
    sources: &BTreeSet<String>,
    state: &str,
    reason: &str,
) -> Value {
    json!({"kind": kind, "identity": identity, "version": "", "digest": "", "sources": sources,
        "state": state, "reason": reason, "actions": []})
}

pub fn requirements(
    state: &Snapshot,
    project: &str,
    target: &Path,
    references: &[String],
) -> Result<Value> {
    bind_project(state, project, target)?;
    let references: BTreeSet<_> = references.iter().collect();
    if references.is_empty() || references.len() > 64 {
        return Err(Failure::input(
            "supply from one to 64 exact setup references",
        ));
    }
    let mut documents = BTreeMap::new();
    let mut edges = 0;
    let mut harnesses: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for reference in &references {
        let (id, number) = reference
            .split_once('@')
            .ok_or_else(|| Failure::input("setups require exact id@X.Y references"))?;
        if !passport::stable_id(id, "setup") {
            return Err(Failure::input("an environment reference must name a setup"));
        }
        let setup = state.exact_version(id, number, None)?;
        let harness = setup["harness_id"].as_str().ok_or_else(invalid)?;
        harnesses
            .entry(harness.into())
            .or_default()
            .insert((*reference).clone());
        for member in setup["components"].as_array().ok_or_else(invalid)? {
            edges += 1;
            if edges > 8192 {
                return Err(Failure::precondition(
                    "environment graph exceeds the dependency limit",
                ));
            }
            let id = member["stable_id"].as_str().ok_or_else(invalid)?;
            let number = member["version"].as_str().ok_or_else(invalid)?;
            let digest = member["passport_digest"].as_str().ok_or_else(invalid)?;
            // Recheck repeated references too: two setups may disagree about
            // the digest at a shared coordinate.
            let component = state.exact_version(id, number, Some(digest))?;
            documents.insert(format!("{id}@{number}"), component);
            if documents.len() > 4096 {
                return Err(Failure::precondition(
                    "environment graph exceeds the component limit",
                ));
            }
        }
        documents.insert((*reference).clone(), setup);
    }
    let mut requirements: Vec<_> = harnesses
        .iter()
        .map(|(name, sources)| {
            requirement(
                "harness_program",
                name,
                sources,
                "not_observed",
                "managed harness evidence requires a provider observation",
            )
        })
        .collect();
    let mut variables: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut authorization: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (reference, document) in &documents {
        for variable in document["required_env"].as_array().ok_or_else(invalid)? {
            variables
                .entry(variable["name"].as_str().ok_or_else(invalid)?.into())
                .or_default()
                .insert(reference.clone());
        }
        let auth = document["requires_authorization"]
            .as_str()
            .unwrap_or("none");
        if auth != "none" || document["requires_credentials"] == true {
            authorization
                .entry(if auth == "none" { "credentials" } else { auth }.into())
                .or_default()
                .insert(reference.clone());
        }
    }
    for (name, sources) in variables {
        // Read names only; an empty value still means present, as in the wire contract.
        let present = std::env::vars_os().any(|(key, _)| key == name.as_str());
        requirements.push(requirement(
            "environment_variable",
            &name,
            &sources,
            if present {
                "satisfied"
            } else {
                "action_required"
            },
            if present {
                "the variable name is present in this process"
            } else {
                "the declared variable is absent from this process"
            },
        ));
    }
    for (name, sources) in authorization {
        requirements.push(requirement(
            "authorization",
            &name,
            &sources,
            "not_observed",
            "authorization requires fresh provider or service evidence",
        ));
    }
    for (reference, document) in &documents {
        if document["component_type"] == "cli" {
            let mut item = requirement(
                "shared_program",
                document["stable_id"].as_str().ok_or_else(invalid)?,
                &BTreeSet::from([reference.clone()]),
                "not_observed",
                "exact shared program bytes have not been observed",
            );
            item["version"] = document["version"].clone();
            item["digest"] = document["artifact"]["digest"].clone();
            requirements.push(item);
        }
    }
    Ok(
        json!({"schema_version": 1, "project_id": project, "setups": references,
        "requirements": requirements, "configuration_state": "not_observed"}),
    )
}
