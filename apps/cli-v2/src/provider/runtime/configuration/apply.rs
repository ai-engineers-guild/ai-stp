//! The authenticated component is the only writer of the final configuration root.

use jiff::Timestamp;
use serde_json::Value;
use std::path::Path;

use super::{
    Bundle, effects, identity, invalid, journal::Journal, outcome, plan::Plan, prepare,
    require_component,
};
use crate::{
    digest,
    error::{Failure, Result},
    files,
    provider::{
        artifact,
        plan::Observed,
        runtime::{Runtime, TargetRequest, execution::Configuration, platform, target::Target},
        trust,
    },
};

pub(in crate::provider::runtime) fn apply(
    parent: &Path,
    bytes: &[u8],
    digest: &str,
    bundle_path: Option<&Path>,
) -> Result<Value> {
    let plan = Plan::parse(bytes, digest)?;
    let prior = Journal::history(parent, &plan, digest)?;
    if let Some(prior) = &prior
        && prior.state != "applying"
    {
        // Cleanup may have been interrupted after the terminal SQLite commit.
        // This path never opens the target, provider, bundle source or network.
        Journal::open(parent, &plan, digest)?.cleanup()?;
        return prior.result.clone().ok_or_else(invalid);
    }
    if prior.is_none() {
        plan.request(Timestamp::now())?;
    }
    require_component(&plan.provider_version)?;
    let target = Target::open(Path::new(&plan.target_path))?;
    let state = Target::open(parent)?;
    if identity(&target)? != plan.target_identity || identity(&state)? != plan.state_identity {
        return Err(invalid());
    }
    target.disjoint(&state.directory()?)?;
    require_inactive(&target)?;
    let journal = Journal::open(parent, &plan, digest)?;
    let prior = journal.read(&plan, digest)?;
    if let Some(prior) = &prior
        && prior.state != "applying"
    {
        journal.cleanup()?;
        return prior.result.clone().ok_or_else(invalid);
    }
    let created = plan
        .created_at
        .parse::<Timestamp>()
        .map_err(|_| invalid())?;
    let request = plan.request(created)?;
    if prior.is_none() {
        request.check_time(Timestamp::now())?;
        effects::verify(&target, &plan.effects, false)?;
    }
    let supplied = if prior.is_none() {
        bundle_path
            .map(|path| files::read(path, 64 * 1024 * 1024))
            .transpose()?
    } else {
        None
    };
    let bundle_bytes = journal.payload(&plan, supplied.as_deref(), prior.is_some())?;
    let bundle = if request.bundle.is_some() {
        Some(Bundle::read(&bundle_bytes)?)
    } else {
        None
    };
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
    if prior.is_none() {
        let context = TargetRequest {
            state_parent: parent,
            harness: &plan.harness_id,
            version: &plan.provider_version,
            path: target.path(),
            scope: plan.target_scope,
        };
        let (mut current, _) = prepare(
            &runtime,
            &context,
            &request,
            &plan.created_at,
            &bundle_bytes,
            bundle.as_ref(),
        )?;
        current.project = plan
            .project
            .as_ref()
            .map(|binding| super::project::observe(&current, &binding.project_id))
            .transpose()?;
        if current.value()? != plan.value()? {
            return Err(invalid());
        }
        request.check_time(Timestamp::now())?;
        journal.admit(&plan, digest)?;
    }
    let response = runtime.launcher.configure(
        artifact.executable()?,
        &target,
        &Configuration {
            plan: &plan.provider_plan,
            request: &request,
            cancel: false,
        },
        &bundle_bytes,
    )?;
    let provider = outcome::applied(&response, &plan)?;
    effects::verify(&target, &plan.effects, true)?;
    let status = runtime
        .launcher
        .status(artifact.executable()?, &target, plan.target_scope)?;
    outcome::status(&target.response(&status, &info)?, &provider, &plan)?;
    artifact.executable()?;
    target.revalidate()?;
    state.revalidate()?;
    let result = outcome::build(&plan, digest, &provider, &digest::sha256(&status))?;
    journal.complete(&plan, digest, &result)?;
    Ok(result)
}

fn require_inactive(target: &Target) -> Result<()> {
    let refused = || {
        Failure::precondition(
            "the current project or configured harness root requires staged replacement and agent handoff",
        )
    };
    let home = files::home()
        .filter(|path| path.is_absolute())
        .ok_or_else(refused)?;
    let mut roots = vec![
        std::env::current_dir().map_err(|_| refused())?,
        home.join(".agents"),
    ];
    let xdg = std::env::var_os("XDG_CONFIG_HOME")
        .map(std::path::PathBuf::from)
        .filter(|path| path.is_absolute())
        .unwrap_or_else(|| home.join(".config"));
    for harness in crate::harnesses::definitions()? {
        if let Some(root) = &harness.config_root {
            roots.push(if harness.xdg_config {
                xdg.join(root)
            } else {
                home.join(root)
            });
        }
        if let Some(root) = &harness.xdg_config_root {
            roots.push(xdg.join(root));
        }
        if let Some(value) = harness
            .root_override
            .as_ref()
            .and_then(std::env::var_os)
            .filter(|value| !value.is_empty())
        {
            roots.push(value.into());
        }
    }
    for root in roots {
        match cap_std::fs::Dir::open_ambient_dir(root, cap_std::ambient_authority()) {
            Ok(root) => target.disjoint(&root).map_err(|_| refused())?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
            Err(_) => return Err(refused()),
        }
    }
    Ok(())
}
