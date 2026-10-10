//! Authenticated software plans over a held target and an observed program prefix.

use cap_std::fs::Dir;
use serde_json::{Value, json};

use super::{
    Runtime, TargetRequest, platform,
    prefix::{Prefix, View},
    target::Target,
    unavailable,
};
use crate::{
    digest,
    error::{Failure, Result},
    files,
    provider::{artifact, plan::Observed, software::Request, trust},
};
use std::path::Path;

struct Observation {
    report: Value,
    target: Target,
    prefix: Prefix,
    state: Dir,
}

pub(super) fn observe(
    runtime: &Runtime,
    context: &TargetRequest<'_>,
    prefix: &Path,
    request: &Request,
) -> Result<Value> {
    Ok(observe_held(runtime, context, prefix, request, View::Observed)?.report)
}

fn observe_held(
    runtime: &Runtime,
    context: &TargetRequest<'_>,
    prefix: &Path,
    request: &Request,
    view: View,
) -> Result<Observation> {
    request.check_time(jiff::Timestamp::now())?;
    let target = Target::open(context.path)?;
    let prefix = Prefix::open(prefix)?;
    if view == View::EmptyStage {
        prefix.parent_identity()?;
    }
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
        view,
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
        view,
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
    if view == View::EmptyStage {
        report["network"]["filesystem"] =
            "declared_runtime_readonly_target_and_empty_namespace_prefix".into();
        report["prefix"]["host_state"] = "missing".into();
        report["prefix"]["provider_view"] = "empty_private_stage".into();
        report["prefix"]["observation"] = "planned_staging_effects".into();
    }
    report["status"] = after;
    report["status_before_digest"] = digest::sha256(&before_bytes).into();
    report["status_after_digest"] = digest::sha256(&after_bytes).into();
    report["plan"] = plan;
    report["plan_response_digest"] = digest::sha256(&bytes).into();
    report["planned_at"] = jiff::Timestamp::now().to_string().into();
    Ok(Observation {
        report,
        target,
        prefix,
        state,
    })
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
    let Observation {
        mut report,
        target,
        prefix,
        state,
    } = observe_held(runtime, context, prefix, request, View::Observed)?;
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

/// A new installation has two preconditions: host absence and an empty private
/// provider stage. No existing provider plan is transformed or silently replanned.
pub(super) fn install_plan(
    runtime: &Runtime,
    context: &TargetRequest<'_>,
    prefix: &Path,
    version: Option<&str>,
) -> Result<Value> {
    let now = jiff::Timestamp::now();
    let expires = now
        .checked_add(std::time::Duration::from_secs(900))
        .map_err(|_| unavailable())?;
    let request = Request::parse(
        &serde_json::to_vec(&json!({
            "operation":"software_install",
            "operation_id":format!("operation_{}", ulid::Ulid::generate()),
            "expires_at":format!("{expires:.3}"),
            "software_version":version,
        }))
        .map_err(|_| unavailable())?,
        now,
    )?;
    let Observation {
        report,
        target,
        prefix,
        state,
    } = observe_held(runtime, context, prefix, &request, View::EmptyStage)?;
    let state_parent = files::location(context.state_parent)?;
    let current = target.state_parent(Path::new(&state_parent))?;
    let state_identity = |directory: &Dir| -> Result<[String; 2]> {
        let metadata = directory.dir_metadata().map_err(|_| unavailable())?;
        Ok([
            cap_fs_ext::MetadataExt::dev(&metadata).to_string(),
            cap_fs_ext::MetadataExt::ino(&metadata).to_string(),
        ])
    };
    if state_identity(&state)? != state_identity(&current)? {
        return Err(Failure::precondition(
            "the explicit state parent changed during planning",
        ));
    }
    let pair = |(device, inode): (u64, u64)| [device.to_string(), inode.to_string()];
    let plan = json!({
        "schema_version":1, "action":"program.install", "operation_id":request.operation_id,
        "created_at":format!("{now:.3}"), "expires_at":request.expires_at,
        "state_parent":state_parent, "state_parent_identity":state_identity(&state)?,
        "harness_id":context.harness, "provider_version":context.version,
        "target":{"path":target.path(),"scope":context.scope.as_str(),"identity":pair(target.identity()?)},
        "prefix":{"path":prefix.path(),"expected_state":"missing","parent_identity":pair(prefix.parent_identity()?)},
        "component":{"archive_digest":report["artifact"]["archive_digest"],
            "executable_digest":report["artifact"]["executable_digest"],
            "info_digest":report["provider_info_digest"]},
        "provider_plan":report["plan"],
    });
    // Provider plans and filesystem paths retain their exact Unicode spelling.
    // The ordinary authoring canonicalizer normalizes strings and cannot own this.
    let encoded = serde_json_canonicalizer::to_vec(&plan).map_err(|_| unavailable())?;
    if encoded.len() > 64 * 1024 {
        return Err(Failure::precondition(
            "the program installation plan exceeds 64 KiB",
        ));
    }
    target.revalidate()?;
    prefix.revalidate()?;
    request.check_time(jiff::Timestamp::now())?;
    Ok(
        json!({"plan_digest":digest::bytes("ai-stp:installation-operation:v1", &encoded)?,
        "plan":plan,"observation":report,"installation_performed":false,"execution_authorized":false}),
    )
}
