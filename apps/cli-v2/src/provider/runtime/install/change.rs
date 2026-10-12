//! Updates and removals retain the component's original operation and prefix.

mod verify;

#[cfg(test)]
mod tests;

use super::super::{
    Runtime, TargetRequest,
    execution::Installation,
    platform,
    prefix::View,
    software::{self, Observation},
    target::Target,
};
use super::{
    journal::{Journal, Phase, Record, identity},
    plan::{Plan, invalid},
};
use crate::{
    digest,
    error::Result,
    provider::{
        artifact,
        plan::Observed,
        software::{Request, download},
        trust,
    },
};
use jiff::Timestamp;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::Path;

fn kind(action: &str) -> Result<&'static str> {
    match action {
        "program.update" => Ok("software_update"),
        "program.remove" => Ok("software_remove"),
        _ => Err(invalid()),
    }
}

fn entry_point(
    runtime: &Runtime,
    context: &TargetRequest<'_>,
    prefix: &Path,
    report: &Value,
    request: &Request,
) -> Result<String> {
    let descriptor;
    let planned = if request.operation == "software_remove" {
        let input = Request::parse(&serde_json::to_vec(&json!({
            "operation":"software_install", "operation_id":request.operation_id,
            "expires_at":request.expires_at, "software_version":report["plan"]["plan"]["software_version"],
        })).map_err(|_| invalid())?, Timestamp::now())?;
        descriptor = software::observe(runtime, context, prefix, &input)?;
        if descriptor["provider_info_digest"] != report["provider_info_digest"]
            || descriptor["artifact"]["archive_digest"] != report["artifact"]["archive_digest"]
            || descriptor["artifact"]["executable_digest"]
                != report["artifact"]["executable_digest"]
            || descriptor["status"] != report["status"]
        {
            return Err(invalid());
        }
        &descriptor["plan"]
    } else {
        &report["plan"]
    };
    let artifacts = planned["plan"]["software_artifacts"]
        .as_array()
        .ok_or_else(invalid)?;
    if artifacts.len() != 1 {
        return Err(invalid());
    }
    artifacts[0]["entry_point"]
        .as_str()
        .map(str::to_owned)
        .ok_or_else(invalid)
}

pub(in crate::provider::runtime) fn plan(
    runtime: &Runtime,
    context: &TargetRequest<'_>,
    prefix: &Path,
    version: Option<&str>,
    action: &str,
) -> Result<Value> {
    super::require_component(context.version)?;
    let now = Timestamp::now();
    let expires = now
        .checked_add(std::time::Duration::from_secs(900))
        .map_err(|_| invalid())?;
    let request = Request::parse(
        &serde_json::to_vec(&json!({"operation":kind(action)?,
            "operation_id":format!("operation_{}",ulid::Ulid::generate()),
            "expires_at":format!("{expires:.3}"),"software_version":version,
        }))
        .map_err(|_| invalid())?,
        now,
    )?;
    let Observation {
        report,
        target,
        prefix,
        state,
    } = software::observe_held(runtime, context, prefix, &request, View::Observed)?;
    let existing = prefix.mounted().ok_or_else(invalid)?;
    let entry = entry_point(runtime, context, prefix.path(), &report, &request)?;
    let version = report["plan"]["plan"]["software_version"]
        .as_str()
        .ok_or_else(invalid)?;
    let directory = existing.directory()?;
    let state_parent = Target::open(context.state_parent)?;
    let current = target.state_parent(state_parent.path())?;
    use cap_fs_ext::MetadataExt;
    let pair = |dir: &cap_std::fs::Dir| -> Result<[String; 2]> {
        let meta = dir.dir_metadata().map_err(|_| invalid())?;
        Ok([meta.dev().to_string(), meta.ino().to_string()])
    };
    if pair(&current)? != pair(&state)? {
        return Err(invalid());
    }
    let parent = Target::open(prefix.path().parent().ok_or_else(invalid)?)?;
    let plan = json!({"schema_version":1,"action":action,"operation_id":request.operation_id,
        "created_at":format!("{now:.3}"),"expires_at":request.expires_at,
        "state_parent":state_parent.path(),"state_parent_identity":identity(&state_parent)?,
        "harness_id":context.harness,"provider_version":context.version,
        "target":{"path":target.path(),"scope":context.scope.as_str(),"identity":identity(&target)?},
        "prefix":{"path":prefix.path(),"expected_state":"existing","parent_identity":identity(&parent)?,
            "existing":{"identity":identity(existing)?,"entry_point":entry,
                "preserved_digest":verify::preserved(&directory,version,&entry)?,
                "launch_digest":verify::launch(&directory,&entry)?,
                "selected_is_active":verify::active(&directory,version,&entry)?}},
        "component":{"archive_digest":report["artifact"]["archive_digest"],
            "executable_digest":report["artifact"]["executable_digest"],"info_digest":report["provider_info_digest"]},
        "provider_plan":report["plan"]});
    let bytes = serde_json_canonicalizer::to_vec(&plan).map_err(|_| invalid())?;
    let digest = digest::bytes("ai-stp:installation-operation:v1", &bytes)?;
    Plan::parse(&bytes, &digest)?;
    target.revalidate()?;
    prefix.revalidate()?;
    parent.revalidate()?;
    state_parent.revalidate()?;
    request.check_time(Timestamp::now())?;
    Ok(
        json!({"plan":plan,"plan_digest":digest,"observation":report,"mutation_performed":false,"execution_authorized":false}),
    )
}

fn context(plan: &Plan) -> Result<(Target, Target, Target)> {
    let target = Target::open(Path::new(&plan.target.path))?;
    let state = Target::open(Path::new(&plan.state_parent))?;
    let prefix = Target::open(Path::new(&plan.prefix.path))?;
    let parent = Target::open(prefix.path().parent().ok_or_else(invalid)?)?;
    let expected = plan.prefix.existing.as_ref().ok_or_else(invalid)?;
    if identity(&target)? != plan.target.identity
        || identity(&state)? != plan.state_parent_identity
        || identity(&prefix)? != expected.identity
        || identity(&parent)? != plan.prefix.parent_identity
    {
        return Err(invalid());
    }
    target.disjoint(&state.directory()?)?;
    prefix.disjoint(&state.directory()?)?;
    prefix.disjoint(&target.directory()?)?;
    Ok((target, state, prefix))
}

pub(in crate::provider::runtime) fn apply(
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
    let prior = Journal::history(parent, &plan, digest)?;
    if let Some(prior) = &prior
        && prior.phase == Phase::Complete
    {
        return prior.result.clone().ok_or_else(invalid);
    }
    if prior.is_none() {
        plan.request(Timestamp::now())?;
    }
    super::require_component(&plan.provider_version)?;
    let (target, state, prefix) = context(&plan)?;
    let journal = Journal::open(parent, &plan, digest)?;
    let prior = journal.read()?;
    if let Some(prior) = &prior
        && prior.phase == Phase::Complete
    {
        return prior.result.clone().ok_or_else(invalid);
    }
    let expected = plan.prefix.existing.as_ref().ok_or_else(invalid)?;
    let version = plan.provider_plan["plan"]["software_version"]
        .as_str()
        .ok_or_else(invalid)?;
    // A pending component may own temporary extraction or quarantine entries.
    // Its authenticated journal validates recovery; the final native inventory
    // still proves that every unrelated entry survived unchanged.
    if prior.is_none()
        && verify::preserved(&prefix.directory()?, version, &expected.entry_point)?
            != expected.preserved_digest
    {
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
    let status = runtime
        .launcher
        .status(artifact.executable()?, &target, plan.scope()?)?;
    let before = target.response(&status, &info)?;
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
    if prior.is_none() {
        let context = TargetRequest {
            state_parent: state.path(),
            harness: &plan.harness_id,
            version: &plan.provider_version,
            path: target.path(),
            scope: plan.scope()?,
        };
        let fresh = software::observe(&runtime, &context, prefix.path(), &request)?;
        if fresh["plan"] != plan.provider_plan
            || entry_point(&runtime, &context, prefix.path(), &fresh, &request)?
                != expected.entry_point
            || verify::launch(&prefix.directory()?, &expected.entry_point)?
                != expected.launch_digest
            || verify::active(&prefix.directory()?, version, &expected.entry_point)?
                != expected.selected_is_active
        {
            return Err(invalid());
        }
    }
    let mut archive = if action == "program.update" {
        download::acquire(&state_directory, &plan.harness_id, &plan.provider_plan)?;
        Some(download::hold(&state_directory, &plan.provider_plan)?)
    } else {
        None
    };
    let mut record = match prior {
        Some(record) if record.phase == Phase::Applying => record,
        Some(_) => return Err(invalid()),
        None => {
            plan.request(Timestamp::now())?;
            let record = Record {
                schema_version: 1,
                plan_digest: digest.into(),
                plan: plan.value()?,
                phase: Phase::Applying,
                stage_parent: None,
                stage_root: None,
                result: None,
            };
            journal.write(None, &record)?;
            record
        }
    };
    let response = runtime.launcher.install(
        artifact.executable()?,
        &target,
        &Installation {
            stage: &prefix,
            prefix: prefix.path(),
            plan: &plan.provider_plan,
            archive: archive.as_ref().map(|a| &a.file),
        },
    )?;
    let provider_result = applied(&response, &plan)?;
    let verification = if let Some(archive) = archive.as_mut() {
        archive.verify()?;
        let proof = super::verify::payload_at(
            &prefix.directory()?,
            &mut archive.file,
            version,
            &expected.entry_point,
            prefix.path(),
            false,
        )?;
        if provider_result["files"] != proof["archive_entries"] {
            return Err(invalid());
        }
        json!({"verification":"exact_vendor_archive_inventory","payload":proof,"preserved_digest":expected.preserved_digest})
    } else {
        verify::removed(&prefix.directory()?, version, expected)?
    };
    if verify::preserved(&prefix.directory()?, version, &expected.entry_point)?
        != expected.preserved_digest
    {
        return Err(invalid());
    }
    let after = runtime
        .launcher
        .status(artifact.executable()?, &target, plan.scope()?)?;
    if target.response(&after, &info)? != before {
        return Err(invalid());
    }
    target.revalidate()?;
    prefix.revalidate()?;
    state.revalidate()?;
    artifact.executable()?;
    let mutated = action == "program.update" || provider_result["removed"] == true;
    let result = json!({"operation_id":plan.operation_id,"plan_digest":digest,"state":"verified",
        "action":action,"harness_id":plan.harness_id,"provider_version":plan.provider_version,
        "prefix":plan.prefix.path,"mutation_performed":mutated,"verification":verification,"provider_result":provider_result});
    record.phase = Phase::Complete;
    record.result = Some(result.clone());
    journal.write(Some(Phase::Applying), &record)?;
    Ok(result)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Removed {
    state: String,
    recovered: Vec<String>,
    operation: String,
    command: String,
    version: String,
    removed: bool,
    plan_digest: String,
}

fn applied(bytes: &[u8], plan: &Plan) -> Result<Value> {
    if plan.action == "program.update" {
        return super::outcome::applied(bytes, plan);
    }
    let value = crate::provider::plan::response(bytes)?;
    let response: Removed = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    let expected = plan.prefix.existing.as_ref().ok_or_else(invalid)?;
    if response.state != "verified"
        || !response.recovered.is_empty()
        || response.operation != "software_remove"
        || response.version != plan.provider_plan["plan"]["software_version"]
        || format!("bin/{}", response.command) != expected.entry_point
        || response.plan_digest != plan.provider_plan["plan_digest"]
    {
        return Err(invalid());
    }
    let _ = response.removed;
    Ok(value)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Completed {
    operation_id: String,
    plan_digest: String,
    state: String,
    action: String,
    harness_id: String,
    provider_version: String,
    prefix: String,
    mutation_performed: bool,
    verification: Value,
    provider_result: Value,
}

pub(super) fn validate_outcome(value: &Value, plan: &Plan, digest: &str) -> Result<()> {
    let result: Completed = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    let expected = plan.prefix.existing.as_ref().ok_or_else(invalid)?;
    if result.operation_id != plan.operation_id
        || result.plan_digest != digest
        || result.state != "verified"
        || result.action != plan.action
        || result.harness_id != plan.harness_id
        || result.provider_version != plan.provider_version
        || result.prefix != plan.prefix.path
        || result.mutation_performed
            != (plan.action == "program.update" || result.provider_result["removed"] == true)
        || result.verification["preserved_digest"] != expected.preserved_digest
    {
        return Err(invalid());
    }
    applied(
        &serde_json::to_vec(&result.provider_result).map_err(|_| invalid())?,
        plan,
    )?;
    if plan.action == "program.remove" {
        if result.verification
            != json!({"verification":"selected_version_absent","entry_point":expected.entry_point,"preserved_digest":expected.preserved_digest})
        {
            return Err(invalid());
        }
    } else {
        if result
            .verification
            .as_object()
            .is_none_or(|object| object.len() != 3)
            || result.verification["verification"] != "exact_vendor_archive_inventory"
            || result.verification["payload"]["entry_point"] != expected.entry_point
        {
            return Err(invalid());
        }
        super::outcome::validate_verification(
            &result.verification["payload"],
            &result.provider_result,
        )?;
    }
    Ok(())
}
