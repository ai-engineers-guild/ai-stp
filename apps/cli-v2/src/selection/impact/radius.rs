//! Exact reverse references within the explicitly opened local registry.

use std::collections::BTreeSet;

use rusqlite::Connection;
use serde_json::{Value, json};

use super::{MAX_BYTES, bytes, coordinate, graph, history, invalid};
use crate::{
    error::{Failure, Result},
    objects::Objects,
    passport,
    projection::artifact,
    store::{Store, database},
    wire::Schema,
};

static REPORT: Schema = Schema::new(include_str!(
    "../../../../../schemas/v1/cli-blast-radius-report.schema.json"
));
const MAX_SETUPS: usize = 4096;

fn device(connection: &Connection) -> Result<Vec<String>> {
    let mut query = connection
        .prepare("SELECT stable_id FROM entity WHERE kind='device' ORDER BY created_at LIMIT 2")
        .map_err(database)?;
    let ids = query
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if ids.len() > 1 {
        return Err(Failure::precondition(
            "the local device identity is ambiguous",
        ));
    }
    for id in &ids {
        Objects { connection }.head("device", id)?;
    }
    Ok(ids)
}

pub fn report(
    store: &mut Store,
    component_id: &str,
    component_version: &str,
    scenario: &str,
    at: &str,
) -> Result<Value> {
    if !passport::stable_id(component_id, "component")
        || !passport::timestamp(at)
        || !matches!(
            scenario,
            "update" | "deprecation" | "blocked" | "expired_evidence" | "advisory"
        )
    {
        return Err(Failure::input(
            "the component, scenario or report timestamp is invalid",
        ));
    }
    store.transaction(|connection| {
        let mut remaining = MAX_BYTES;
        let component = Objects { connection }.exact_version(component_id, component_version, None)?;
        for adaptation in component["adaptations"].as_array().ok_or_else(invalid)? {
            for scope in adaptation["scope_adaptations"].as_array().ok_or_else(invalid)? {
                artifact::verify(scope, &bytes(connection, &scope["projection_artifact"], &mut remaining)?)?;
            }
        }
        let component = coordinate(&component)?;
        let mut query = connection.prepare(
            "SELECT v.stable_id,v.version FROM object_version v JOIN entity e ON e.stable_id=v.stable_id \
             WHERE e.kind='setup' ORDER BY v.stable_id,v.major,v.minor LIMIT ?"
        ).map_err(database)?;
        let rows = query.query_map([(MAX_SETUPS + 1) as i64], |row| Ok((row.get::<_, String>(0)?,row.get::<_, String>(1)?)))
            .map_err(database)?;
        let mut affected = Vec::new();
        let mut pairs = BTreeSet::new();
        let mut visited_members = 0;
        for (index, row) in rows.enumerate() {
            if index == MAX_SETUPS {
                return Err(Failure::precondition("the reverse report exceeds 4096 retained setup versions"));
            }
            let (id, version) = row.map_err(database)?;
            let held = graph(connection, &id, &version, true, &mut remaining)?;
            visited_members += held.members.len();
            if visited_members > 8192 {
                return Err(Failure::precondition("the reverse report exceeds 8192 setup member visits"));
            }
            if held.members.get(component_id) == Some(&component) {
                pairs.insert((id, version));
                affected.push(held.coordinate);
            }
        }
        let mut query = connection.prepare(
            "SELECT project_id,stable_id,version FROM selected_version ORDER BY project_id LIMIT ?"
        ).map_err(database)?;
        let rows = query.query_map([(history::MAX_ROWS + 1) as i64], |row| Ok((row.get::<_, String>(0)?,row.get::<_, String>(1)?,row.get::<_, String>(2)?)))
            .map_err(database)?;
        let mut projects = BTreeSet::new();
        for (index, row) in rows.enumerate() {
            if index == history::MAX_ROWS {
                return Err(Failure::precondition("the reverse report exceeds 100000 project selections"));
            }
            let (project, id, version) = row.map_err(database)?;
            if pairs.contains(&(id,version)) {
                if !passport::stable_id(&project,"project") { return Err(invalid()); }
                projects.insert(project);
            }
        }
        let installed: BTreeSet<_> = history::installed(connection)?.into_iter()
            .filter(|item| pairs.contains(&(item.setup_id.clone(),item.version.clone())))
            .map(|item| item.target).collect();
        let devices = if installed.is_empty() { Vec::new() } else { device(connection)? };
        let result = json!({"schema_version":1,"generated_at":at,"freshness":"local_snapshot",
            "authority_boundary":"local_registry","scenario":scenario,"component":component,
            "setup_versions":affected,"projects":projects,"devices":devices,"installed_targets":installed,"action":"none"});
        REPORT.validate(&result)?;
        Ok(result)
    })
}
