//! Composition diagnostics over exact projections, before host assembly.

use std::collections::{BTreeMap, BTreeSet};

use rusqlite::Connection;
use serde_json::{Value, json};

use super::{
    File, MAX_BYTES, MAX_FILES, composition::Composition, exact, invalid, projected,
    surface_refusal, text,
};
use crate::{
    canonical,
    error::Result,
    projection,
    provider::Info,
    selection::{
        eligibility::{self, Evidence, Target},
        graph,
    },
    store::Store,
};

pub fn inspect(
    store: &mut Store,
    roots: &[Value],
    target: &Target,
    evidence: &BTreeMap<String, Evidence>,
    provider: Option<&Info>,
) -> Result<Value> {
    store.transaction(|connection| inspect_snapshot(connection, roots, target, evidence, provider))
}

pub(crate) fn inspect_snapshot(
    connection: &Connection,
    roots: &[Value],
    target: &Target,
    evidence: &BTreeMap<String, Evidence>,
    provider: Option<&Info>,
) -> Result<Value> {
    target.validate()?;
    let assessment = if roots.is_empty() {
        json!({"schema_version":1,"graph":graph::exact(connection, roots)?,
            "assessments":[],"admissible":false,"auto_selectable":false})
    } else {
        eligibility::assess_connection(connection, roots, target, evidence, provider)?
    };
    let resolved = assessment["graph"]["resolved"] == true;
    let mut composition = Composition::for_report(&target.harness_id);
    let mut files = Vec::new();
    let mut hosts = BTreeSet::new();
    let mut unsupported = Vec::new();
    let mut unavailable = Vec::new();
    let mut projection_bytes = 0;
    let mut content_bytes = 0usize;
    if resolved {
        for node in assessment["graph"]["nodes"]
            .as_array()
            .ok_or_else(|| invalid("graph nodes missing"))?
        {
            let component = exact(connection, node)?;
            if component["kind"] == "setup" {
                continue;
            }
            let id = text(&component, "stable_id")?;
            let scope = projection::adaptation(&component, &target.harness_id, target.scope)
                .map(|(_, scope)| scope);
            let refusal = match scope {
                Some(scope) => surface_refusal(scope)?,
                None => Some("No exact adaptation exists for the requested harness and scope."),
            };
            if let Some(reason) = refusal {
                let mut losses = scope
                    .and_then(|scope| scope["semantic_losses"].as_array())
                    .cloned()
                    .unwrap_or_default();
                losses.push(reason.into());
                unsupported.push(json!({"schema_version":1,"stable_id":id,
                    "component_type":component["component_type"],"logical_component_type":component["component_type"],
                    "native_surface":"","native_paths":[],"projection_kind":"native_files",
                    "state":"unsupported","losses":losses}));
                unavailable.push(json!({"schema_version":1,"stable_id":id,"version":component["version"],"reason":reason,
                    "refusals":[{"code":"bundle_surface_unsupported","summary":reason}]}));
                continue;
            }
            let scope = scope.ok_or_else(|| invalid("projection scope missing"))?;
            let members = projected(
                connection,
                &component,
                scope,
                &target.harness_id,
                &mut projection_bytes,
            )?;
            composition.include(&component, scope, &assessment)?;
            for declaration in scope["members"]
                .as_array()
                .ok_or_else(|| invalid("projection members missing"))?
            {
                if declaration["ownership"] == "contribution" {
                    hosts.insert(text(declaration, "path")?.to_owned());
                }
            }
            for member in members {
                content_bytes = content_bytes
                    .checked_add(member.bytes.len())
                    .ok_or_else(|| invalid("report projection size overflow"))?;
                if files.len() >= MAX_FILES || content_bytes > MAX_BYTES {
                    return Err(invalid("report projections exceed 2000 files or 64 MiB"));
                }
                composition.claim(id, &member.path)?;
                files.push(File {
                    member,
                    owner: id.into(),
                });
            }
        }
        composition.validate(&files)?;
    }
    let (mut composition, mut conversion) = composition.reports();
    let conflicts = composition["conflicts"]
        .as_array_mut()
        .ok_or_else(|| invalid("composition conflicts missing"))?;
    if !resolved {
        conflicts.extend(
            assessment["graph"]["refusals"]
                .as_array()
                .ok_or_else(|| invalid("graph refusals missing"))?
                .iter()
                .cloned(),
        );
    }
    if resolved && files.is_empty() && unsupported.is_empty() {
        conflicts.push(json!({"schema_version":1,"code":"empty_bundle_unsupported",
            "summary":"Provider protocol v3 requires a nonempty installable bundle.","details":{}}));
    }
    if let Some(profile) = provider.and_then(|p| p.profile(target.scope))
        && (files.len() as u64 > profile["max_files"].as_u64().unwrap_or(0)
            || content_bytes as u64 > profile["max_bytes"].as_u64().unwrap_or(0))
    {
        conflicts.push(json!({"schema_version":1,"code":"provider_bundle_limit",
                "summary":"Selected projection files exceed the authenticated provider profile limits.","details":{}}));
    }
    let mut rejected: Vec<_> = assessment["assessments"].as_array().into_iter().flatten()
        .filter(|entry|entry["admissible"] != true)
        .map(|entry| {
            let coordinate = assessment["graph"]["nodes"].as_array().into_iter().flatten()
                .find(|node|node["stable_id"] == entry["stable_id"]);
            json!({"schema_version":1,"stable_id":entry["stable_id"],
                "version":coordinate.map(|c|&c["version"]),
                "reason":"Current mechanical eligibility refuses this exact version.","refusals":entry["refusals"]})
        }).collect();
    for entry in unavailable {
        if !rejected
            .iter()
            .any(|held| held["stable_id"] == entry["stable_id"])
        {
            rejected.push(entry);
        }
    }
    rejected.sort_by(|a, b| a["stable_id"].as_str().cmp(&b["stable_id"].as_str()));
    let rejected_ids: BTreeSet<_> = rejected
        .iter()
        .filter_map(|entry| entry["stable_id"].as_str())
        .collect();
    composition["chosen"]
        .as_array_mut()
        .ok_or_else(|| invalid("composition choices missing"))?
        .retain(|entry| {
            !entry["stable_id"]
                .as_str()
                .is_some_and(|id| rejected_ids.contains(id))
        });
    composition["blocked"] = (assessment["admissible"] != true
        || !rejected.is_empty()
        || composition["blocked"] == true
        || !composition["conflicts"]
            .as_array()
            .is_some_and(Vec::is_empty))
    .into();
    composition["rejected"] = json!(rejected);
    if composition["blocked"] == true {
        // A conflicting union is not a completed composition operation.
        composition["operations"]
            .as_array_mut()
            .ok_or_else(|| invalid("composition operations missing"))?
            .retain(|operation| operation != "disjoint_managed_path_union");
    }
    let entries = conversion["entries"]
        .as_array_mut()
        .ok_or_else(|| invalid("conversion entries missing"))?;
    entries.extend(unsupported);
    entries.sort_by(|a, b| a["stable_id"].as_str().cmp(&b["stable_id"].as_str()));
    conversion["complete"] =
        (resolved && entries.iter().all(|entry| entry["state"] == "complete")).into();
    let report = json!({"schema_version":1,"assessment":assessment,"composition":composition,"conversion":conversion,
        "required_host_paths":hosts,"host_inputs_observed":false,"assembled_output_checked":false,
        "projection_files":files.len(),"projection_content_bytes":content_bytes,
        "bundle_written":false,"installation_authorized":false,"harness_written":false});
    if canonical::bytes(&report)?.len() > 8 * 1024 * 1024 {
        return Err(invalid("composition reports exceed 8 MiB"));
    }
    Ok(report)
}
