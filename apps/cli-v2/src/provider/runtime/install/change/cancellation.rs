//! Negative authorization is persisted by the exact component before retirement.

use super::super::{
    journal::{Journal, Phase, Record},
    plan::{Plan, invalid},
};
use super::{context, kind, verify};
use crate::{
    digest,
    error::{Failure, Result},
    provider::{
        artifact, managed,
        plan::Observed,
        runtime::{Runtime, execution::Installation, platform},
        trust,
    },
};
use jiff::Timestamp;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::Path;

fn require_component(version: &str) -> Result<()> {
    if managed::sequence(version)? < managed::sequence("0.0.93")? {
        return Err(Failure::precondition(
            "the original plan requires exact program cancellation (component 0.0.93 or newer); its release identity cannot be replaced",
        ));
    }
    Ok(())
}

pub(in crate::provider::runtime) fn cancel(
    parent: &Path,
    bytes: &[u8],
    digest: &str,
    action: &str,
) -> Result<Value> {
    kind(action)?;
    let plan = Plan::parse(bytes, digest)?;
    if plan.action != action {
        return Err(invalid());
    }
    if let Some(prior) = Journal::history(parent, &plan, digest)?
        && prior.phase.terminal()
    {
        return prior.result.ok_or_else(invalid);
    }
    require_component(&plan.provider_version)?;
    let (target, state, prefix) = context(&plan)?;
    let journal = Journal::open(parent, &plan, digest)?;
    let prior = journal.read()?;
    if let Some(prior) = &prior
        && prior.phase.terminal()
    {
        return prior.result.clone().ok_or_else(invalid);
    }
    if prior.as_ref().is_some_and(|r| r.phase != Phase::Applying) {
        return Err(invalid());
    }
    let runtime = Runtime::observe()?;
    let state_directory = state.directory()?;
    let trusted = trust::refresh_at(&state_directory)?;
    let artifact = artifact::fetch(
        &plan.harness_id,
        &plan.provider_version,
        platform()?,
        &trusted,
    )?;
    let (info, report) = runtime.information(&artifact)?;
    if artifact.report()["archive_digest"] != plan.component.archive_digest
        || artifact.report()["executable_digest"] != plan.component.executable_digest
        || report["provider_info_digest"] != plan.component.info_digest
    {
        return Err(invalid());
    }
    let created = plan
        .created_at
        .parse::<Timestamp>()
        .map_err(|_| invalid())?;
    let request = plan.request(created)?;
    request.planned(
        &serde_json::to_vec(&plan.provider_plan).map_err(|_| invalid())?,
        &Observed {
            provider: &info,
            release_digest: &plan.component.executable_digest,
            target: target.path(),
            scope: plan.scope()?,
            target_digest: plan.provider_plan["plan"]["expected_target_digest"]
                .as_str()
                .ok_or_else(invalid)?,
        },
        prefix.path(),
        created,
    )?;
    let observe = || -> Result<String> {
        let status = runtime
            .launcher
            .status(artifact.executable()?, &target, plan.scope()?)?;
        let value = json!({"prefix":verify::unchanged(&prefix.directory()?)?,
            "target":target.response(&status, &info)?});
        Ok(digest::sha256(
            &serde_json_canonicalizer::to_vec(&value).map_err(|_| invalid())?,
        ))
    };
    let before = observe()?;
    let response = runtime.launcher.install(
        artifact.executable()?,
        &target,
        &Installation {
            stage: &prefix,
            prefix: prefix.path(),
            plan: &plan.provider_plan,
            archive: None,
            cancel: true,
        },
    )?;
    let provider = applied(&response, &plan)?;
    if observe()? != before {
        return Err(invalid());
    }
    artifact.executable()?;
    target.revalidate()?;
    prefix.revalidate()?;
    state.revalidate()?;
    let result = outcome(&plan, digest, &provider, &before);
    let previous = prior.as_ref().map(|r| r.phase);
    let record = Record {
        schema_version: 1,
        plan_digest: digest.into(),
        plan: plan.value()?,
        phase: Phase::Cancelled,
        stage_parent: None,
        stage_root: None,
        result: Some(result.clone()),
    };
    journal.write(previous, &record)?;
    Ok(result)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Cancelled {
    state: String,
    operation: String,
    operation_id: String,
    command: String,
    version: String,
    software_changed: bool,
    expected_software_digest: String,
    plan_digest: String,
}

fn applied(bytes: &[u8], plan: &Plan) -> Result<Value> {
    let value = crate::provider::plan::response(bytes)?;
    let result: Cancelled = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    let expected = plan.prefix.existing.as_ref().ok_or_else(invalid)?;
    if result.state != "cancelled"
        || result.operation != kind(&plan.action)?
        || result.operation_id != plan.operation_id
        || result.software_changed
        || format!("bin/{}", result.command) != expected.entry_point
        || result.version != plan.provider_plan["plan"]["software_version"]
        || result.expected_software_digest != plan.provider_plan["plan"]["expected_software_digest"]
        || result.plan_digest != plan.provider_plan["plan_digest"]
    {
        return Err(invalid());
    }
    Ok(value)
}

pub(super) fn outcome(plan: &Plan, digest: &str, provider: &Value, observation: &str) -> Value {
    json!({"operation_id":plan.operation_id,"plan_digest":digest,"state":"cancelled",
        "action":plan.action,"harness_id":plan.harness_id,"provider_version":plan.provider_version,
        "prefix":plan.prefix.path,"mutation_performed":false,"provider_result":provider,
        "unchanged_observation_digest":observation})
}

pub(in crate::provider::runtime::install) fn validate_outcome(
    value: &Value,
    plan: &Plan,
    digest: &str,
) -> Result<()> {
    require_component(&plan.provider_version)?;
    let provider = applied(
        &serde_json::to_vec(&value["provider_result"]).map_err(|_| invalid())?,
        plan,
    )?;
    let observation = value["unchanged_observation_digest"]
        .as_str()
        .ok_or_else(invalid)?;
    if !crate::provider::plan::hash(observation)
        || *value != outcome(plan, digest, &provider, observation)
    {
        return Err(invalid());
    }
    Ok(())
}
