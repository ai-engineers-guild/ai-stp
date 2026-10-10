//! Closed live and historical outcomes bound to the original installation intent.

use super::plan::{Plan, invalid};
use crate::{
    error::{Failure, Result},
    wire,
};
use serde::Deserialize;
use serde_json::Value;
use std::path::Path;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Applied {
    state: String,
    recovered: Vec<String>,
    operation: String,
    command: String,
    version: String,
    entry_point: String,
    executable: String,
    files: usize,
    plan_digest: String,
}

pub(super) fn applied(bytes: &[u8], plan: &Plan) -> Result<Value> {
    if bytes.len() > 1024 * 1024 {
        return Err(invalid());
    }
    let value = wire::parse(bytes)?;
    if value["state"] == "refused" {
        let reason = value["reason"]
            .as_str()
            .filter(|s| {
                !s.is_empty()
                    && s.len() <= 128
                    && s.bytes().all(|b| b.is_ascii_lowercase() || b == b'_')
            })
            .ok_or_else(invalid)?;
        return Err(Failure::precondition("the setup component refused the original program installation; its transaction state was retained")
            .with_details([("provider_reason".into(), reason.into())]));
    }
    let response: Applied = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    if response.state != "verified"
        || !response.recovered.is_empty()
        || response.operation != "software_install"
        || response.version != plan.provider_plan["plan"]["software_version"]
        || response.entry_point
            != plan.provider_plan["plan"]["software_artifacts"][0]["entry_point"]
        || response.entry_point != format!("bin/{}", response.command)
        || Path::new(&response.executable)
            != Path::new(&plan.prefix.path).join(&response.entry_point)
        || !(1..=65_536).contains(&response.files)
        || response.plan_digest != plan.provider_plan["plan_digest"]
    {
        return Err(invalid());
    }
    Ok(value)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Verification {
    verification: String,
    files: usize,
    bytes: u64,
    inventory_digest: String,
    entry_point: String,
    member: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Completed {
    operation_id: String,
    plan_digest: String,
    state: String,
    harness_id: String,
    provider_version: String,
    prefix: String,
    installation_performed: bool,
    verification: Verification,
    provider_result: Value,
}

pub(super) fn validate(value: &Value, plan: &Plan, digest: &str) -> Result<()> {
    let outcome: Completed = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    let proof = &outcome.verification;
    let response = applied(
        &serde_json::to_vec(&outcome.provider_result).map_err(|_| invalid())?,
        plan,
    )?;
    if outcome.operation_id != plan.operation_id
        || outcome.plan_digest != digest
        || outcome.state != "verified"
        || outcome.harness_id != plan.harness_id
        || outcome.provider_version != plan.provider_version
        || outcome.prefix != plan.prefix.path
        || !outcome.installation_performed
        || proof.verification != "exact_vendor_archive_inventory"
        || !(1..=65_536).contains(&proof.files)
        || proof.bytes > 8 * 1024 * 1024 * 1024
        || !crate::provider::plan::hash(&proof.inventory_digest)
        || proof.entry_point != response["entry_point"]
        || proof.files != response["files"]
        || proof.member.is_empty()
        || proof.member.len() > 8192
        || Path::new(&proof.member).components().count() > 64
        || !Path::new(&proof.member)
            .components()
            .all(|p| matches!(p, std::path::Component::Normal(_)))
    {
        return Err(invalid());
    }
    Ok(())
}
