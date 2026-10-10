//! Durable fresh-program installation; the component remains the content writer.

pub(super) mod cancellation;
mod journal;
mod outcome;
mod plan;
mod stage;
#[cfg(test)]
mod tests;
mod verify;

use jiff::Timestamp;
use serde_json::{Value, json};
use std::path::Path;

use super::{
    Runtime,
    execution::Installation,
    platform,
    prefix::{Prefix, View},
    target::Target,
};
use crate::{
    error::{Failure, Result},
    provider::{artifact, managed, plan::Observed, software::download, trust},
    wire,
};
use journal::{Journal, Phase, Record, identity};
use outcome::applied;
use plan::{Plan, invalid};
use stage::Stage;

fn context(plan: &Plan) -> Result<(Target, cap_std::fs::Dir)> {
    let target = Target::open(Path::new(&plan.target.path))?;
    if identity(&target)? != plan.target.identity {
        return Err(invalid());
    }
    let held_state = Target::open(Path::new(&plan.state_parent))?;
    if identity(&held_state)? != plan.state_parent_identity {
        return Err(invalid());
    }
    let state = held_state.directory()?;
    target.disjoint(&state)?;
    let prefix = Prefix::open(Path::new(&plan.prefix.path))?;
    prefix.disjoint(&state)?;
    prefix.disjoint(&target.directory()?)?;
    let parent = Target::open(Path::new(&plan.prefix.path).parent().ok_or_else(invalid)?)?;
    if identity(&parent)? != plan.prefix.parent_identity {
        return Err(invalid());
    }
    Ok((target, state))
}

pub(super) fn apply(parent: &Path, bytes: &[u8], digest: &str) -> Result<Value> {
    let plan = Plan::parse(bytes, digest)?;
    let record = Journal::history(parent, &plan, digest)?;
    if let Some(record) = &record
        && record.phase.terminal()
    {
        // Completion is history, including after a later removal. No provider,
        // network, target, artifact or program directory is needed to read it.
        return record.result.clone().ok_or_else(invalid);
    }
    if record
        .as_ref()
        .is_some_and(|r| r.phase == Phase::Cancelling)
    {
        return cancellation::cancel(parent, bytes, digest);
    }
    if managed::sequence(&plan.provider_version)? < managed::sequence("0.0.89")? {
        return Err(Failure::precondition(
            "program installation requires a setup component with exact-operation recovery (0.0.89 or newer)",
        ));
    }
    if record.is_none() {
        plan.request(Timestamp::now())?;
    }
    let (target, state) = context(&plan)?;
    let journal = Journal::open(parent, &plan, digest)?;
    let mut record = journal.read()?;
    if let Some(record) = &record
        && record.phase.terminal()
    {
        return record.result.clone().ok_or_else(invalid);
    }
    if record
        .as_ref()
        .is_some_and(|r| r.phase == Phase::Cancelling)
    {
        drop(journal);
        return cancellation::cancel(parent, bytes, digest);
    }
    let runtime = Runtime::observe()?;
    let trusted = trust::refresh_at(&state)?;
    let artifact = artifact::fetch(
        &plan.harness_id,
        &plan.provider_version,
        platform()?,
        &trusted,
    )?;
    let (info, observed) = runtime.information(&artifact)?;
    if artifact.report()["archive_digest"] != plan.component.archive_digest
        || artifact.report()["executable_digest"] != plan.component.executable_digest
        || observed["provider_info_digest"] != plan.component.info_digest
    {
        return Err(invalid());
    }
    let status_bytes = runtime
        .launcher
        .status(artifact.executable()?, &target, plan.scope()?)?;
    let before = target.response(&status_bytes, &info)?;
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
            target_digest: before["target_digest"].as_str().ok_or_else(invalid)?,
        },
        Path::new(&plan.prefix.path),
        created,
    )?;
    if record.is_none() {
        // Revalidate the submitted plan with the same authenticated component
        // before first admission. Retried operations retain their original plan.
        let prefix = Prefix::open(Path::new(&plan.prefix.path))?;
        prefix.parent_identity()?;
        let current = runtime.launcher.software_plan(
            artifact.executable()?,
            &target,
            &prefix,
            plan.scope()?,
            &request,
            View::EmptyStage,
        )?;
        if wire::parse(&current)? != plan.provider_plan {
            return Err(invalid());
        }
    }
    download::acquire(&state, &plan.harness_id, &plan.provider_plan)?;
    let mut archive = download::hold(&state, &plan.provider_plan)?;
    if record.is_none() {
        plan.request(Timestamp::now())?;
        let next = Record {
            schema_version: 1,
            plan_digest: digest.into(),
            plan: plan.value()?,
            phase: Phase::Prepared,
            stage_parent: None,
            stage_root: None,
            result: None,
        };
        journal.write(None, &next)?;
        record = Some(next);
    }
    let mut record = record.ok_or_else(invalid)?;
    let mut stage = Stage::open(&plan, &mut record)?;
    if record.phase == Phase::Prepared {
        record.phase = Phase::Staged;
        journal.write(Some(Phase::Prepared), &record)?;
    }
    let version = plan.provider_plan["plan"]["software_version"]
        .as_str()
        .ok_or_else(invalid)?;
    if record.phase == Phase::Staged {
        let response = runtime.launcher.install(
            artifact.executable()?,
            &target,
            &Installation {
                stage: &stage.root,
                prefix: Path::new(&plan.prefix.path),
                plan: &plan.provider_plan,
                archive: &archive.file,
                scope: plan.scope()?,
            },
        )?;
        let provider_result = applied(&response, &plan)?;
        archive.verify()?;
        let verification = verify::payload(
            &stage.root.directory()?,
            &mut archive.file,
            version,
            &archive.entry_point,
            Path::new(&plan.prefix.path),
        )?;
        if provider_result["files"] != verification["archive_entries"] {
            return Err(invalid());
        }
        let after_bytes =
            runtime
                .launcher
                .status(artifact.executable()?, &target, plan.scope()?)?;
        if target.response(&after_bytes, &info)? != before {
            return Err(invalid());
        }
        artifact.executable()?;
        stage.root.revalidate()?;
        Prefix::open(Path::new(&plan.prefix.path))?.parent_identity()?;
        record.result = Some(
            json!({"operation_id":plan.operation_id,"plan_digest":digest,"state":"verified",
            "harness_id":plan.harness_id,"provider_version":plan.provider_version,"prefix":plan.prefix.path,
            "installation_performed":true,"verification":verification,"provider_result":provider_result}),
        );
        record.phase = Phase::Publishing;
        journal.write(Some(Phase::Staged), &record)?;
    } else if record.phase == Phase::Publishing {
        archive.verify()?;
        let verification = verify::payload(
            &stage.root.directory()?,
            &mut archive.file,
            version,
            &archive.entry_point,
            Path::new(&plan.prefix.path),
        )?;
        if record.result.as_ref().ok_or_else(invalid)?["verification"] != verification {
            return Err(invalid());
        }
    } else {
        return Err(invalid());
    }
    let current = runtime
        .launcher
        .status(artifact.executable()?, &target, plan.scope()?)?;
    if target.response(&current, &info)? != before {
        return Err(invalid());
    }
    target.revalidate()?;
    stage.activate()?;
    stage.cleanup(&record)?;
    record.phase = Phase::Complete;
    journal.write(Some(Phase::Publishing), &record)?;
    record.result.ok_or_else(invalid)
}
