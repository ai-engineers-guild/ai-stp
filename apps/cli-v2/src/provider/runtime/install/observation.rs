//! Current program evidence comes from committed receipts and held live files.

use std::{collections::BTreeSet, path::Path};

use rusqlite::Connection;
use serde_json::{Value, json};

use super::{
    journal::{Phase, Record, identity},
    plan::{Plan, invalid},
    verify,
};
use crate::{
    digest,
    error::{Failure, Result},
    provider::runtime::{prefix::Prefix, target::Target},
    store::database,
};

const HISTORY_BYTES: usize = 16 * 1024 * 1024;

fn history(connection: &Connection, prefix: &str) -> Result<Vec<(Record, Plan)>> {
    let mut statement = connection
        .prepare(
            "SELECT o.operation_id,o.kind,o.state,o.detail,e.global_sequence,e.state_after, \
         CASE WHEN length(CAST(e.evidence AS BLOB))<=1024 THEN e.evidence END,e.result \
         FROM operation o LEFT JOIN operation_event e ON e.operation_id=o.operation_id \
         AND e.sequence=(SELECT max(sequence) FROM operation_event WHERE operation_id=o.operation_id) \
         WHERE o.kind IN ('program.install','program.update','program.remove') AND \
         CASE WHEN length(CAST(o.detail AS BLOB))<=2097152 \
              THEN json_extract(o.detail,'$.plan.prefix.path')=? ELSE 1 END \
         ORDER BY e.global_sequence DESC LIMIT 1025",
        )
        .map_err(database)?;
    let mut rows = statement.query([prefix]).map_err(database)?;
    let mut result = Vec::new();
    let mut bytes = 0usize;
    while let Some(row) = rows.next().map_err(database)? {
        let (id, kind, state, detail): (String, String, String, String) = (
            row.get(0).map_err(database)?,
            row.get(1).map_err(database)?,
            row.get(2).map_err(database)?,
            row.get(3).map_err(database)?,
        );
        bytes = bytes.checked_add(detail.len()).ok_or_else(invalid)?;
        if result.len() == 1024 || bytes > HISTORY_BYTES {
            return Err(Failure::precondition(
                "program observation exceeds the bounded prefix history",
            ));
        }
        let record = Record::parse(&id, &kind, &state, &detail)?;
        let event: String = row.get(6).map_err(database)?;
        if row.get::<_, i64>(4).map_err(database)? <= 0
            || row.get::<_, String>(5).map_err(database)? != state
            || row.get::<_, String>(7).map_err(database)? != "accepted"
            || crate::wire::parse(event.as_bytes())?
                != json!({"plan_digest":record.plan_digest,"phase":record.phase})
        {
            return Err(invalid());
        }
        let plan = Plan::parse(
            &serde_json::to_vec(&record.plan).map_err(|_| invalid())?,
            &record.plan_digest,
        )?;
        result.push((record, plan));
    }
    Ok(result)
}

pub(in crate::provider::runtime) fn observe(
    connection: &Connection,
    parent: &Path,
    harness: &str,
    path: &Path,
) -> Result<Value> {
    crate::harnesses::definition(harness)?;
    if harness == "undefined" {
        return Err(invalid());
    }
    let state = Target::open(parent)?;
    let prefix = Prefix::open(path)?;
    prefix.disjoint(&state.directory()?)?;
    let path = prefix.path().to_str().ok_or_else(invalid)?;
    let records = history(connection, path)?;
    let mut report = json!({"schema_version":1,"harness_id":harness,"prefix":path,
        "state":"unmanaged","program_observed":false,"observation":null,
        "observation_digest":null,"observed_at":jiff::Timestamp::now().to_string(),
        "network_used":false,"vendor_executed":false,"mutation_performed":false});
    for (record, plan) in &records {
        if plan.state_parent != state.path().to_str().ok_or_else(invalid)?
            || plan.state_parent_identity != identity(&state)?
        {
            return Err(invalid());
        }
        if !record.phase.terminal() {
            report["state"] = "recovery_required".into();
            report["pending_operation_id"] = plan.operation_id.clone().into();
            prefix.revalidate()?;
            state.revalidate()?;
            return Ok(report);
        }
    }
    let Some(root) = prefix.mounted() else {
        report["state"] = "missing".into();
        prefix.revalidate()?;
        state.revalidate()?;
        return Ok(report);
    };
    let mut seen = BTreeSet::new();
    for (record, plan) in &records {
        if plan.harness_id != harness || record.phase != Phase::Complete {
            continue;
        }
        let version = plan.provider_plan["plan"]["software_version"]
            .as_str()
            .ok_or_else(invalid)?;
        if !seen.insert(version) || plan.action == "program.remove" {
            continue;
        }
        let result = record.result.as_ref().ok_or_else(invalid)?;
        let proof = if plan.action == "program.install" {
            &result["verification"]
        } else {
            &result["verification"]["payload"]
        };
        let entry = proof["entry_point"].as_str().ok_or_else(invalid)?;
        if verify::active_version(&root.directory()?, entry)?.as_deref() != Some(version) {
            continue;
        }
        let expected_root = if plan.action == "program.install" {
            record.stage_root.as_ref().ok_or_else(invalid)?
        } else {
            &plan.prefix.existing.as_ref().ok_or_else(invalid)?.identity
        };
        let parent = Target::open(root.path().parent().ok_or_else(invalid)?)?;
        if identity(root)? != *expected_root || identity(&parent)? != plan.prefix.parent_identity {
            return Err(Failure::precondition(
                "the observed program directory differs from its installed physical identity",
            ));
        }
        verify::recorded(&root.directory()?, proof, version, root.path())?;
        root.revalidate()?;
        parent.revalidate()?;
        state.revalidate()?;
        let observation = json!({"schema_version":1,"kind":"managed_program","harness_id":harness,"prefix":path,
            "prefix_identity":identity(root)?,"parent_identity":identity(&parent)?,
            "state_identity":identity(&state)?,"software_version":version,
            "entry_point":entry,"member":proof["member"],"inventory_digest":proof["inventory_digest"],
            "operation_id":plan.operation_id,"plan_digest":record.plan_digest,
            "provider_version":plan.provider_version,"provider_identity":record.plan["component"],
            "source":"verified_native_installation_receipt"});
        // Program paths retain their original Unicode spelling, as their installation plans do.
        report["observation_digest"] = digest::bytes(
            "ai-stp:installation-inventory:v1",
            &serde_json_canonicalizer::to_vec(&observation).map_err(|_| invalid())?,
        )?
        .into();
        report["observation"] = observation;
        report["state"] = "verified".into();
        report["program_observed"] = true.into();
        return Ok(report);
    }
    prefix.revalidate()?;
    state.revalidate()?;
    Ok(report)
}
