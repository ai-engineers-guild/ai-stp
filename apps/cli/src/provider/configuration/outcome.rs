//! Closed component receipts and independently checked public configuration state.

use super::{invalid, plan::Plan};
use crate::{
    error::Result,
    provider::plan::{hash, response},
};
use serde_json::{Value, json};

pub(crate) fn preparation(plan: &Plan) -> Result<Value> {
    Ok(json!({"state":"prepared", "operation_id":plan.operation_id,
        "operation":plan.operation()?, "plan_digest":plan.provider_plan["plan_digest"],
        "expected_target_digest":plan.provider_plan["plan"]["expected_target_digest"],
        "configuration_changed":false}))
}

pub(crate) fn applied(bytes: &[u8], plan: &Plan) -> Result<Value> {
    let result = response(bytes)?;
    if !result["target_identity_digest"].as_str().is_some_and(hash) {
        return Err(invalid());
    }
    let expected = json!({"state":"verified","operation":plan.operation()?,
        "plan_digest":plan.provider_plan["plan_digest"],
        "expected_target_digest":plan.provider_plan["plan"]["expected_target_digest"],
        "target_identity_digest":result["target_identity_digest"],"backup_ref":null,"setup_id":plan.setup["stable_id"]});
    if result != expected {
        return Err(invalid());
    }
    Ok(result)
}

#[cfg(target_os = "linux")]
pub(crate) fn status(value: &Value, result: &Value, plan: &Plan) -> Result<()> {
    let inner = &plan.provider_plan["plan"];
    let expected = json!({"canonical_target":plan.target_path,"harness_id":plan.harness_id,
        "provider_id":inner["provider_id"],"provider_version":plan.provider_version,
        "provider_build_digest":inner["provider_build_digest"],"provider_release_digest":plan.executable_digest,
        "operation_id":plan.operation_id,"provider_plan_digest":plan.provider_plan["plan_digest"],
        "target_precondition_digest":inner["expected_target_digest"],
        "target_digest":result["target_identity_digest"],"target_identity_digest":result["target_identity_digest"],
        "configuration_ownership":plan.ownership,"setup_stable_id":plan.setup["stable_id"],"setup_version":plan.setup["version"],
        "bundle_format":inner["bundle"]["bundle_format"],"bundle_digest":inner["bundle"]["bundle_digest"],
        "artifact_digest":inner["bundle"]["artifact_digest"],"projection_profile_digest":inner["projection_profile_digest"],
        "backup_ref":null,"journal":null,"backups":plan.status_before["backups"],"drift_state":"clean"});
    for (key, expected) in expected.as_object().ok_or_else(invalid)? {
        if value.get(key) != Some(expected) {
            return Err(invalid());
        }
    }
    if value["provider_state"]["present"] != true
        || value["provider_state"]["readable"] != true
        || value["provider_state"]["drift_state"] != "clean"
        || value["provider_state"]["operation_id"] != plan.operation_id
    {
        return Err(invalid());
    }
    Ok(())
}

pub(crate) fn build(
    plan: &Plan,
    digest: &str,
    provider: &Value,
    status_digest: &str,
) -> Result<Value> {
    Ok(
        json!({"operation_id":plan.operation_id,"plan_digest":digest,"state":"verified",
        "action":plan.action,"harness_id":plan.harness_id,"provider_version":plan.provider_version,
        "target":plan.target_path,"scope":plan.target_scope,"mutation_performed":true,
        "verification":{"verification":"exact_configuration_files_and_recorded_ownership","files":plan.effects.len(),
            "effects_digest":crate::digest::sha256(&serde_json_canonicalizer::to_vec(&plan.effects).map_err(|_| invalid())?)},
        "provider_result":provider,"status_digest":status_digest}),
    )
}

pub(crate) fn validate(value: &Value, plan: &Plan, digest: &str) -> Result<()> {
    let status = value["status_digest"]
        .as_str()
        .filter(|value| hash(value))
        .ok_or_else(invalid)?;
    let provider = applied(
        &serde_json::to_vec(&value["provider_result"]).map_err(|_| invalid())?,
        plan,
    )?;
    if value != &build(plan, digest, &provider, status)? {
        return Err(invalid());
    }
    Ok(())
}

pub(crate) fn cancelled(bytes: &[u8], plan: &Plan) -> Result<Value> {
    let value = response(bytes)?;
    let expected = json!({"state":"cancelled", "operation_id":plan.operation_id,
        "operation":plan.operation()?, "plan_digest":plan.provider_plan["plan_digest"],
        "expected_target_digest":plan.provider_plan["plan"]["expected_target_digest"],
        "configuration_changed":false});
    if value != expected {
        return Err(invalid());
    }
    Ok(value)
}

pub(crate) fn cancellation(
    plan: &Plan,
    digest: &str,
    provider: &Value,
    observation: &str,
) -> Value {
    json!({"operation_id":plan.operation_id,"plan_digest":digest,"state":"cancelled",
        "action":plan.action,"harness_id":plan.harness_id,"provider_version":plan.provider_version,
        "target":plan.target_path,"scope":plan.target_scope,"configuration_changed":false,
        "provider_result":provider,"unchanged_observation_digest":observation})
}

pub(crate) fn validate_cancellation(value: &Value, plan: &Plan, digest: &str) -> Result<()> {
    super::require_cancellation(&plan.provider_version)?;
    let observation = value["unchanged_observation_digest"]
        .as_str()
        .filter(|s| hash(s))
        .ok_or_else(invalid)?;
    let provider = cancelled(
        &serde_json::to_vec(&value["provider_result"]).map_err(|_| invalid())?,
        plan,
    )?;
    if value != &cancellation(plan, digest, &provider, observation) {
        return Err(invalid());
    }
    Ok(())
}
