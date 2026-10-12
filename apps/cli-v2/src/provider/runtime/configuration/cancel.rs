//! Exact component cancellation, independently observed before native retirement.

use jiff::Timestamp;
use serde_json::{Value, json};
use std::path::Path;

use super::{identity, invalid, journal::Journal, outcome, plan::Plan};
use crate::{
    digest,
    error::Result,
    provider::{
        Info, artifact,
        plan::Observed,
        runtime::{Runtime, execution::Configuration, platform, target::Target},
        trust,
    },
};

use crate::provider::configuration::require_cancellation as require_component;

fn observe(
    runtime: &Runtime,
    executable: &[u8],
    target: &Target,
    info: &Info,
    plan: &Plan,
) -> Result<String> {
    let mut files = Vec::new();
    let mut total = 0usize;
    for effect in &plan.effects {
        let observed = target.observe(&effect.path)?;
        let content = observed.content.map(|content| {
            total += content.bytes.len();
            json!({"digest":digest::sha256(&content.bytes), "bytes":content.bytes.len(), "mode":content.mode})
        });
        if total > 64 * 1024 * 1024 {
            return Err(invalid());
        }
        files.push(json!({"path":effect.path, "parents":observed.parents,
            "identity":observed.identity, "content":content}));
    }
    let status = runtime
        .launcher
        .status(executable, target, plan.target_scope)?;
    let value = json!({"files":files,"status":target.response(&status, info)?});
    Ok(digest::sha256(
        &serde_json_canonicalizer::to_vec(&value).map_err(|_| invalid())?,
    ))
}

pub(in crate::provider::runtime) fn cancel(
    parent: &Path,
    bytes: &[u8],
    digest: &str,
) -> Result<Value> {
    let plan = Plan::parse(bytes, digest)?;
    if let Some(prior) = Journal::history(parent, &plan, digest)?
        && prior.state != "applying"
    {
        Journal::open(parent, &plan, digest)?.cleanup()?;
        return prior.result.ok_or_else(invalid);
    }
    require_component(&plan.provider_version)?;
    let target = Target::open(Path::new(&plan.target_path))?;
    let state = Target::open(parent)?;
    if identity(&target)? != plan.target_identity || identity(&state)? != plan.state_identity {
        return Err(invalid());
    }
    target.disjoint(&state.directory()?)?;
    let journal = Journal::open(parent, &plan, digest)?;
    if let Some(prior) = journal.read(&plan, digest)?
        && prior.state != "applying"
    {
        journal.cleanup()?;
        return prior.result.ok_or_else(invalid);
    }
    let created = plan
        .created_at
        .parse::<Timestamp>()
        .map_err(|_| invalid())?;
    let request = plan.request(created)?;
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
    if report["artifact"]["archive_digest"] != plan.archive_digest
        || report["artifact"]["executable_digest"] != plan.executable_digest
        || report["provider_info_digest"] != plan.info_digest
    {
        return Err(invalid());
    }
    request.planned(
        &serde_json::to_vec(&plan.provider_plan).map_err(|_| invalid())?,
        &Observed {
            provider: &info,
            release_digest: &plan.executable_digest,
            target: target.path(),
            scope: plan.target_scope,
            target_digest: plan.provider_plan["plan"]["expected_target_digest"]
                .as_str()
                .ok_or_else(invalid)?,
        },
        created,
    )?;
    let before = observe(&runtime, artifact.executable()?, &target, &info, &plan)?;
    // Cancellation consumes the original binding, never bundle payload bytes.
    // The component's durable tombstone precedes native terminal retirement.
    let response = runtime.launcher.configure(
        artifact.executable()?,
        &target,
        &Configuration {
            plan: &plan.provider_plan,
            request: &request,
            cancel: true,
        },
        &[],
    )?;
    let provider = outcome::cancelled(&response, &plan)?;
    if observe(&runtime, artifact.executable()?, &target, &info, &plan)? != before {
        return Err(invalid());
    }
    artifact.executable()?;
    target.revalidate()?;
    state.revalidate()?;
    let result = outcome::cancellation(&plan, digest, &provider, &before);
    journal.cancel(&plan, digest, &result)?;
    Ok(result)
}
