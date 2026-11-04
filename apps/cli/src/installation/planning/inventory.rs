//! Content-free owned corporate observations, never a fabricated full scan.

use super::{invalid, value};
use crate::{
    account::contexts::{self, Authority},
    authoring::runtime,
    error::Result,
    installation::custody::Custody,
    objects::Objects,
};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

pub fn inventory_observation(
    root: &Path,
    custody: &Custody,
    context_id: &str,
    at: &str,
) -> Result<Value> {
    if !crate::passport::timestamp(at) {
        return Err(invalid());
    }
    let context = contexts::resolve(root, Some(context_id))?;
    let owner = runtime::owner(root)?;
    context.require_current_native_identity(&owner)?;
    let Authority::Remote {
        account,
        organization,
        ..
    } = &context.authority
    else {
        return Err(invalid());
    };
    if organization["kind"] != "corporate" {
        return Err(invalid());
    }
    let mut groups = BTreeMap::<String, Vec<Value>>::new();
    let mut operations = BTreeSet::new();
    let mut links = BTreeMap::new();
    for operation in custody.current_operations()? {
        let Some(review) = custody.retained(&operation)? else {
            continue;
        };
        let Some(plan) = review.original_plan()? else {
            continue;
        };
        if plan.state.path != root || plan.context.context_id != context_id {
            continue;
        }
        let corporate = plan.corporate.as_ref().ok_or_else(invalid)?;
        if corporate.organization_id != organization["organization_id"]
            || corporate.original_account.account_id != account.account_id
            || corporate.original_account.origin != account.origin
            || corporate.original_account.device_id != account.device_id
        {
            return Err(invalid());
        }
        let status = custody.status(&review)?;
        if status["state"] != "completed" {
            continue;
        }
        links.insert(
            corporate.link_id.clone(),
            corporate.remote_project_id.clone(),
        );
        let observations = custody.inventory(&operation)?;
        let mut components = BTreeMap::<(String, String, String), Vec<Value>>::new();
        for observation in observations {
            let source = &observation["source"];
            components
                .entry((
                    source["stable_id"].as_str().ok_or_else(invalid)?.into(),
                    source["version"].as_str().ok_or_else(invalid)?.into(),
                    source["passport_digest"]
                        .as_str()
                        .ok_or_else(invalid)?
                        .into(),
                ))
                .or_default()
                .push(observation);
        }
        let store = owner.planning()?;
        for ((id, version, digest), rows) in components {
            let document = Objects {
                connection: &store.connection,
            }
            .exact_version(&id, &version, Some(&digest))?;
            let mut locations = rows
                .iter()
                .map(|row| row["location_digest"].clone())
                .collect::<Vec<_>>();
            locations.sort_by(|a, b| a.as_str().cmp(&b.as_str()));
            let states = rows
                .iter()
                .map(|row| row["state"].as_str().unwrap_or("unknown"))
                .collect::<Vec<_>>();
            let state = if states.contains(&"unknown") {
                "unknown"
            } else if states.iter().all(|s| *s == "missing") {
                "missing"
            } else if states.iter().all(|s| *s == "present") {
                "present"
            } else {
                "modified"
            };
            groups.entry(corporate.remote_project_id.clone()).or_default().push(json!({
                "location_digest":crate::digest::canonical("ai-stp:installation-operation:v1",&json!({"kind":"native.inventory.component_location","locations":locations}))?,
                "kind":document["component_type"],"harness":plan.target.harness_id,"source":"managed","state":state,
                "stable_id":id,"version":version,"setup_stable_id":plan.setup["stable_id"],"setup_version":plan.setup["version"]}));
        }
        operations.insert(operation);
    }
    let mut snapshots = Vec::new();
    for (project, components) in groups {
        if components.len() > 1024 {
            return Err(invalid());
        }
        snapshots.push(json!({"schema_version":1,"scan_id":format!("native_inventory_{}",ulid::Ulid::generate()),
            "organization_id":organization["organization_id"],"employee_id":account.account_id,"device_id":account.device_id,
            "project_id":project,"scope":"project","scanned_at":at,"complete":false,"components":components}));
    }
    if snapshots.len() > 64 {
        return Err(invalid());
    }
    Ok(
        json!({"context":value(&context)?,"account":value(account)?,"coverage":"owned_native_only",
        "operations":operations,"links":links.into_iter().map(|(link_id,project_id)|json!({"link_id":link_id,"project_id":project_id})).collect::<Vec<_>>(),"snapshots":snapshots,"runtime_loading_observed":false,"network_delivery":false}),
    )
}

/// Resolve an agent-reported signal against a currently owned native ref.
/// The signal supplies only correlation, never account or version coordinates.
pub struct UsageSignal<'a> {
    pub operation: &'a str,
    pub component: &'a str,
    pub signal_id: &'a str,
    pub activity_kind: &'a str,
    pub outcome: &'a str,
    pub at: &'a str,
}

pub fn usage_observation(
    root: &Path,
    custody: &Custody,
    context_id: &str,
    signal: &UsageSignal<'_>,
) -> Result<Value> {
    if !crate::passport::timestamp(signal.at)
        || !crate::passport::stable_id(signal.operation, "operation")
        || !crate::passport::stable_id(signal.component, "component")
        || !(8..=128).contains(&signal.signal_id.len())
        || !signal
            .signal_id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._:-".contains(&b))
        || !matches!(signal.activity_kind, "invocation" | "load")
        || !matches!(signal.outcome, "succeeded" | "failed" | "cancelled")
        || !custody.current_operations()?.contains(signal.operation)
    {
        return Err(invalid());
    }
    let review = custody.retained(signal.operation)?.ok_or_else(invalid)?;
    if custody.status(&review)?["state"] != "completed" {
        return Err(invalid());
    }
    let plan = review.original_plan()?.ok_or_else(invalid)?;
    let context = contexts::resolve(root, Some(context_id))?;
    let owner = runtime::owner(root)?;
    context.require_current_native_identity(&owner)?;
    if plan.state.path != root || plan.context != context || plan.target.harness_id.is_empty() {
        return Err(invalid());
    }
    let Authority::Remote {
        account,
        organization,
        ..
    } = &context.authority
    else {
        return Err(invalid());
    };
    let corporate = plan.corporate.as_ref().ok_or_else(invalid)?;
    if organization["kind"] != "corporate"
        || corporate.organization_id != organization["organization_id"]
        || corporate.original_account.account_id != account.account_id
        || corporate.original_account.device_id != account.device_id
        || corporate.original_account.origin != account.origin
    {
        return Err(invalid());
    }
    let rows = custody
        .inventory(signal.operation)?
        .into_iter()
        .filter(|row| row["source"]["stable_id"] == signal.component)
        .collect::<Vec<_>>();
    let source = rows.first().ok_or_else(invalid)?["source"].clone();
    if rows
        .iter()
        .any(|row| row["state"] != "present" || row["source"] != source)
        || !plan.graph_nodes.iter().any(|node| {
            node.stable_id == signal.component
                && source["version"] == node.version
                && source["passport_digest"] == node.passport_digest
        })
    {
        return Err(invalid());
    }
    let store = owner.planning()?;
    let document = Objects {
        connection: &store.connection,
    }
    .exact_version(
        signal.component,
        source["version"].as_str().ok_or_else(invalid)?,
        source["passport_digest"].as_str(),
    )?;
    let digest = crate::digest::canonical(
        "ai-stp:runtime-usage-signal:v1",
        &json!([
            context_id,
            signal.operation,
            signal.component,
            signal.signal_id,
            signal.activity_kind
        ]),
    )?;
    Ok(json!({"link_id":corporate.link_id,"event":{
        "schema_version":1,"event_id":format!("event_{}",&digest[7..39]),
        "organization_id":corporate.organization_id,"employee_id":account.account_id,
        "device_id":account.device_id,"project_id":corporate.remote_project_id,
        "harness":plan.target.harness_id,
        "setup":plan.setup,
        "component":{"kind":document["component_type"],"stable_id":signal.component,
            "version":source["version"],"passport_digest":source["passport_digest"]},
        "invoked_at":signal.at,"outcome":signal.outcome,"source":"agent_reported",
        "activity_kind":signal.activity_kind
    }}))
}
