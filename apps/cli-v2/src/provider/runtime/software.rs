//! Authenticated software plans over a held target and an observed program prefix.

use serde_json::{Value, json};

use super::{Runtime, TargetRequest, platform, prefix::Prefix, target::Target, unavailable};
use crate::{
    digest,
    error::{Failure, Result},
    provider::{artifact, plan::Observed, software::Request, trust},
};
use std::path::Path;

pub(super) fn observe(
    runtime: &Runtime,
    context: &TargetRequest<'_>,
    prefix: &Path,
    request: &Request,
) -> Result<Value> {
    request.check_time(jiff::Timestamp::now())?;
    let target = Target::open(context.path)?;
    let prefix = Prefix::open(prefix)?;
    let state = target.state_parent(context.state_parent)?;
    prefix.disjoint(&state)?;
    prefix.disjoint(&target.directory()?)?;
    let trust = trust::refresh_at(&state)?;
    let artifact = artifact::fetch(context.harness, context.version, platform()?, &trust)?;
    let (info, mut report) = runtime.information(&artifact)?;
    if !info.supports_target(context.scope)
        || !info.document()["supported_operations"]
            .as_array()
            .is_some_and(|ops| ops.iter().any(|op| op == &request.operation))
    {
        return Err(Failure::precondition(
            "the authenticated provider does not support the requested software operation or scope",
        ));
    }
    let before_bytes = runtime
        .launcher
        .status(artifact.executable()?, &target, context.scope)?;
    let before = target.response(&before_bytes, &info)?;
    let observed = Observed {
        provider: &info,
        release_digest: artifact.report()["executable_digest"]
            .as_str()
            .ok_or_else(unavailable)?,
        target: target.path(),
        scope: context.scope,
        target_digest: before["target_digest"].as_str().ok_or_else(unavailable)?,
    };
    let bytes = runtime.launcher.software_plan(
        artifact.executable()?,
        &target,
        &prefix,
        context.scope,
        request,
    )?;
    let plan = request.planned(&bytes, &observed, prefix.path(), jiff::Timestamp::now())?;
    // Provider effects describe the prefix layout; they do not attest every
    // installed byte. Reobserve them without manufacturing installation trust.
    let repeated = runtime.launcher.software_plan(
        artifact.executable()?,
        &target,
        &prefix,
        context.scope,
        request,
    )?;
    if plan != request.planned(&repeated, &observed, prefix.path(), jiff::Timestamp::now())? {
        return Err(Failure::precondition(
            "the observed software plan changed during planning",
        ));
    }
    let after_bytes = runtime
        .launcher
        .status(artifact.executable()?, &target, context.scope)?;
    let after = target.response(&after_bytes, &info)?;
    if before != after {
        return Err(Failure::precondition(
            "the observed target state changed during software planning",
        ));
    }
    target.revalidate()?;
    prefix.revalidate()?;
    request.check_time(jiff::Timestamp::now())?;
    artifact.executable()?;
    report
        .as_object_mut()
        .ok_or_else(unavailable)?
        .remove("installed");
    report["installation_performed"] = false.into();
    report["execution_authorized"] = false.into();
    report["installed_software_verified"] = false.into();
    report["software_downloaded"] = false.into();
    report["network"]["filesystem"] = "declared_runtime_and_readonly_target_prefix".into();
    report["target"] =
        json!({"path":target.path(),"scope":context.scope.as_str(),"access":"read_only"});
    report["prefix"] =
        json!({"path":prefix.path(),"access":"read_only","observation":"provider_effects_only"});
    report["status"] = after;
    report["status_before_digest"] = digest::sha256(&before_bytes).into();
    report["status_after_digest"] = digest::sha256(&after_bytes).into();
    report["plan"] = plan;
    report["plan_response_digest"] = digest::sha256(&bytes).into();
    report["planned_at"] = jiff::Timestamp::now().to_string().into();
    Ok(report)
}

/// Acquisition owns only isolated cache files; a report is not write authority.
pub(super) fn acquire(
    runtime: &Runtime,
    context: &TargetRequest<'_>,
    prefix: &Path,
    request: &Request,
) -> Result<Value> {
    if request.operation == "software_remove" {
        return Err(Failure::input(
            "software removal requires no artifact acquisition",
        ));
    }
    let mut report = observe(runtime, context, prefix, request)?;
    let target = Target::open(context.path)?;
    let prefix = Prefix::open(prefix)?;
    let state = target.state_parent(context.state_parent)?;
    prefix.disjoint(&state)?;
    prefix.disjoint(&target.directory()?)?;
    let acquired =
        crate::provider::software::download::acquire(&state, context.harness, &report["plan"])?;
    target.revalidate()?;
    prefix.revalidate()?;
    request.check_time(jiff::Timestamp::now())?;
    report["software_downloaded"] = acquired["artifacts"]
        .as_array()
        .is_some_and(|items| items.iter().any(|item| item["cache_hit"] == false))
        .into();
    report["software_acquired"] = true.into();
    report["acquisition"] = acquired;
    report["acquired_at"] = jiff::Timestamp::now().to_string().into();
    Ok(report)
}
