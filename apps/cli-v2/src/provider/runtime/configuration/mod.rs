//! Single-root configuration intent, confined application and independent readback.

pub(super) mod apply;
mod bundle;
pub(super) mod cancel;
mod effects;
mod instructions;
mod journal;
mod project;
#[cfg(test)]
mod project_tests;
#[cfg(test)]
mod tests;

use jiff::Timestamp;
use serde_json::{Value, json};

use super::{Runtime, TargetRequest, target::Target};
use crate::provider::configuration::{invalid, outcome, plan};
use crate::{
    error::{Failure, Result},
    projection::Scope,
    provider::{managed, plan::Request},
};
use bundle::Bundle;
use plan::{Identity, Plan};

fn identity(target: &Target) -> Result<Identity> {
    let (device, inode) = target.identity()?;
    Ok([device.to_string(), inode.to_string()])
}

fn require_component(version: &str) -> Result<()> {
    if managed::sequence(version)? < managed::sequence("0.0.91")? {
        return Err(Failure::precondition(
            "the selected component predates the requested forward configuration operation",
        ));
    }
    Ok(())
}

pub(super) fn plan(
    runtime: &Runtime,
    context: &TargetRequest<'_>,
    operation: &str,
    bytes: Option<&[u8]>,
    project: Option<&str>,
) -> Result<Value> {
    require_component(context.version)?;
    if !matches!(
        (operation, bytes.is_some()),
        ("install" | "replace", true) | ("remove", false)
    ) {
        return Err(invalid());
    }
    let bundle = bytes.map(Bundle::read).transpose()?;
    let created = format!("{:.3}", Timestamp::now());
    let now = created.parse::<Timestamp>().map_err(|_| invalid())?;
    let expires = now
        .checked_add(std::time::Duration::from_secs(900))
        .map_err(|_| invalid())?;
    let request = Request::parse(&serde_json::to_vec(&json!({
        "operation":operation,"operation_id":format!("operation_{}",ulid::Ulid::generate()),
        "expires_at":format!("{expires:.3}"),"recovery_mode":"forward","bundle":bundle.as_ref().map(|bundle| &bundle.binding),
    })).map_err(|_| invalid())?, now)?;
    let (mut plan, report) = prepare(
        runtime,
        context,
        &request,
        &created,
        bytes.unwrap_or_default(),
        bundle.as_ref(),
    )?;
    plan.project = project.map(|id| project::observe(&plan, id)).transpose()?;
    let value = plan.value()?;
    let digest = plan::fingerprint(&value)?;
    Plan::parse(&serde_json::to_vec(&value).map_err(|_| invalid())?, &digest)?;
    Ok(
        json!({"plan":value,"plan_digest":digest,"observation":report,"mutation_performed":false,"execution_authorized":false}),
    )
}

fn prepare(
    runtime: &Runtime,
    context: &TargetRequest<'_>,
    request: &Request,
    created: &str,
    bytes: &[u8],
    bundle: Option<&Bundle>,
) -> Result<(Plan, Value)> {
    let target = Target::open(context.path)?;
    let state = Target::open(context.state_parent)?;
    target.disjoint(&state.directory()?)?;
    let report = runtime.plan(context, request, bytes)?;
    let status = &report["status"];
    if status["configuration_ownership"].is_null() || !status["journal"].is_null() {
        return Err(invalid());
    }
    let attachment = if context.scope == Scope::Global {
        status["instruction_region"]["path"].clone()
    } else {
        // The global public observation names the attachment surface even when
        // this operation uses a scoped projection. It grants no global writes.
        runtime.status(&TargetRequest {
            scope: Scope::Global,
            ..*context
        })?["status"]["instruction_region"]["path"]
            .clone()
    };
    let attachment_path = attachment.as_str().map(str::to_owned);
    let effects = effects::expected(
        &target,
        &status["configuration_ownership"],
        bundle,
        attachment_path.as_deref(),
    )?;
    effects::verify(&target, &effects, false)?;
    let plan = Plan {
        schema_version: 1,
        action: format!("configuration.{}", request.operation),
        operation_id: request.operation_id.clone(),
        created_at: created.into(),
        expires_at: request.expires_at.clone(),
        state_parent: state.path().to_str().ok_or_else(invalid)?.into(),
        state_identity: identity(&state)?,
        target_path: target.path().to_str().ok_or_else(invalid)?.into(),
        target_scope: context.scope,
        target_identity: identity(&target)?,
        harness_id: context.harness.into(),
        provider_version: context.version.into(),
        archive_digest: report["artifact"]["archive_digest"]
            .as_str()
            .ok_or_else(invalid)?
            .into(),
        executable_digest: report["artifact"]["executable_digest"]
            .as_str()
            .ok_or_else(invalid)?
            .into(),
        info_digest: report["provider_info_digest"]
            .as_str()
            .ok_or_else(invalid)?
            .into(),
        provider_plan: report["plan"].clone(),
        status_before: status.clone(),
        attachment_path,
        setup: bundle.map_or(Value::Null, |bundle| bundle.setup.clone()),
        ownership: bundle.map_or_else(|| Ok(json!([])), Bundle::ownership)?,
        effects,
        project: None,
    };
    target.revalidate()?;
    state.revalidate()?;
    request.check_time(Timestamp::now())?;
    Ok((plan, report))
}
