//! Read-only validation and planning against one held target and provider image.

use serde_json::{Value, json};

use super::{Runtime, TargetRequest, platform, target::Target, unavailable};
use crate::{
    digest,
    error::{Failure, Result},
    provider::{
        artifact,
        plan::{Observed, Request},
        trust,
    },
};

pub(super) fn observe(
    runtime: &Runtime,
    context: &TargetRequest<'_>,
    request: &Request,
    bundle: &[u8],
) -> Result<Value> {
    request.check_bundle(bundle, jiff::Timestamp::now())?;
    let target = Target::open(context.path)?;
    let state = target.state_parent(context.state_parent)?;
    let trust = trust::refresh_at(&state)?;
    let artifact = artifact::fetch(context.harness, context.version, platform()?, &trust)?;
    let (info, mut report) = runtime.information(&artifact)?;
    if !info.supports_target(context.scope) {
        return Err(Failure::precondition(
            "the observed provider does not support this target scope",
        ));
    }
    target.revalidate()?;
    let before_bytes = runtime
        .launcher
        .status(artifact.executable()?, &target, context.scope)?;
    let before = target.response(&before_bytes, &info)?;
    let validation_bytes =
        runtime
            .launcher
            .validate(artifact.executable()?, &target, request, bundle)?;
    let validation = request.validation(&validation_bytes)?;
    request.check_time(jiff::Timestamp::now())?;
    target.revalidate()?;
    let plan_bytes = runtime.launcher.plan(
        artifact.executable()?,
        &target,
        context.scope,
        request,
        bundle,
    )?;
    let plan = request.planned(
        &plan_bytes,
        &Observed {
            provider: &info,
            release_digest: artifact.report()["executable_digest"]
                .as_str()
                .ok_or_else(unavailable)?,
            target: target.path(),
            scope: context.scope,
            target_digest: before["target_digest"].as_str().ok_or_else(unavailable)?,
        },
        jiff::Timestamp::now(),
    )?;
    let after_bytes = runtime
        .launcher
        .status(artifact.executable()?, &target, context.scope)?;
    let after = target.response(&after_bytes, &info)?;
    if before != after {
        return Err(Failure::precondition(
            "the observed provider target state changed during planning",
        ));
    }
    request.check_time(jiff::Timestamp::now())?;
    artifact.executable()?;
    report
        .as_object_mut()
        .ok_or_else(unavailable)?
        .remove("installed");
    report["installation_performed"] = false.into();
    report["execution_authorized"] = false.into();
    report["network"]["filesystem"] = "declared_runtime_and_readonly_target_bundle".into();
    report["target"] =
        json!({"path":target.path(),"scope":context.scope.as_str(),"access":"read_only"});
    report["status"] = after;
    report["status_before_digest"] = digest::sha256(&before_bytes).into();
    report["status_after_digest"] = digest::sha256(&after_bytes).into();
    report["bundle_validation"] = validation;
    report["bundle_validation_digest"] = digest::sha256(&validation_bytes).into();
    report["plan"] = plan;
    report["plan_response_digest"] = digest::sha256(&plan_bytes).into();
    report["planned_at"] = jiff::Timestamp::now().to_string().into();
    Ok(report)
}
