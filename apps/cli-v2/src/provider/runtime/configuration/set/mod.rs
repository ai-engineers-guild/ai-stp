//! Complete setup execution: reserve all roots, prepare all, then publish in order.

pub(super) mod journal;
mod project;
#[cfg(test)]
pub(super) mod tests;

use jiff::Timestamp;
use rusqlite::Connection;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

use super::{Bundle, apply, cancel, effects, identity, invalid, outcome};
use crate::{
    bundle::coverage::{self, ScopedPayload},
    error::Result,
    files,
    projection::Scope,
    provider::{
        configuration::{
            plan as single,
            set::{self as model, Child, Plan, Record},
        },
        managed,
        runtime::{Runtime, TargetRequest, execution::Mode, target::Target},
    },
    store::{Store, database},
    wire,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    harness_id: String,
    provider_version: Option<String>,
    operation: String,
    targets: Vec<Root>,
    project_root: Option<PathBuf>,
    harness_executable: Option<PathBuf>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Root {
    scope: Scope,
    path: PathBuf,
    bundle: Option<PathBuf>,
}

pub(in crate::provider::runtime) fn plan(parent: &Path, bytes: &[u8]) -> Result<Value> {
    if bytes.len() > 32 * 1024 {
        return Err(invalid());
    }
    let mut request: Request =
        serde_json::from_value(wire::parse(bytes)?).map_err(|_| invalid())?;
    if !(1..=3).contains(&request.targets.len()) {
        return Err(invalid());
    }
    request.targets.sort_by_key(|root| root.scope);
    let version = managed::version(request.provider_version.as_deref())?;
    let observation =
        crate::program::observe(&request.harness_id, request.harness_executable.as_deref())?;
    let runtime = Runtime::observe()?;
    let created_at = format!("{:.3}", Timestamp::now());
    let mut children = Vec::new();
    for root in &request.targets {
        let bytes = root
            .bundle
            .as_ref()
            .map(|path| files::read(path, 64 * 1024 * 1024))
            .transpose()?;
        let report = super::plan(
            &runtime,
            &TargetRequest {
                state_parent: parent,
                harness: &request.harness_id,
                version,
                path: &root.path,
                scope: root.scope,
            },
            &request.operation,
            bytes.as_deref(),
            None,
        )?;
        children.push(Child {
            plan: report["plan"].clone(),
            plan_digest: report["plan_digest"].as_str().ok_or_else(invalid)?.into(),
            bundle_source: root
                .bundle
                .as_ref()
                .map(|path| path.to_str().ok_or_else(invalid).map(str::to_owned))
                .transpose()?,
        });
    }
    let expires_at = children
        .iter()
        .map(|child| child.plan["expires_at"].as_str().ok_or_else(invalid))
        .collect::<Result<Vec<_>>>()?
        .into_iter()
        .min()
        .ok_or_else(invalid)?
        .to_owned();
    let mut plan = Plan {
        schema_version: 1,
        action: model::KIND.into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at,
        expires_at,
        children,
        project: None,
        program: model::Program {
            executable: request
                .harness_executable
                .as_ref()
                .map(|path| path.to_str().map(str::to_owned).ok_or_else(invalid))
                .transpose()?,
            observation_digest: observation["observation_digest"]
                .as_str()
                .ok_or_else(invalid)?
                .into(),
        },
    };
    plan.project = request
        .project_root
        .as_ref()
        .map(|root| project::observe(parent, root, &plan))
        .transpose()?;
    let value = plan.value()?;
    let digest = model::fingerprint(&value)?;
    Plan::parse(&serde_json::to_vec(&value).map_err(|_| invalid())?, &digest)?;
    roots(&plan, false)?;
    let bundles = supplied(&plan)?;
    let mut store = Store::planning(parent)?;
    store.transaction(|connection| coverage(connection, &plan, &bundles))?;
    Ok(
        json!({"plan":value,"plan_digest":digest,"mutation_performed":false,"execution_authorized":false,"cross_root_atomicity":false}),
    )
}

fn roots(plan: &Plan, inactive: bool) -> Result<Vec<Target>> {
    let first = plan.first()?;
    let state = Target::open(Path::new(&first.state_parent))?;
    if identity(&state)? != first.state_identity {
        return Err(invalid());
    }
    let mut roots: Vec<Target> = Vec::new();
    for child in &plan.children {
        let child = child.parsed()?;
        let root = Target::open(Path::new(&child.target_path))?;
        if identity(&root)? != child.target_identity {
            return Err(invalid());
        }
        root.disjoint(&state.directory()?)?;
        if inactive {
            apply::require_inactive(&root)?;
        }
        for other in &roots {
            root.disjoint(&other.directory()?)?;
        }
        roots.push(root);
    }
    state.revalidate()?;
    Ok(roots)
}

fn supplied(plan: &Plan) -> Result<Vec<Option<Vec<u8>>>> {
    let mut total = 0usize;
    plan.children
        .iter()
        .map(|child| {
            let bytes = child
                .bundle_source
                .as_ref()
                .map(|path| files::read(Path::new(path), 64 * 1024 * 1024))
                .transpose()?;
            total = total
                .checked_add(bytes.as_ref().map_or(0, Vec::len))
                .ok_or_else(invalid)?;
            if total > 64 * 1024 * 1024 {
                return Err(invalid());
            }
            Ok(bytes)
        })
        .collect()
}

fn coverage(connection: &Connection, plan: &Plan, bytes: &[Option<Vec<u8>>]) -> Result<()> {
    let first = plan.first()?;
    if first.operation()? == "remove" {
        return Ok(());
    }
    let bundles = bytes
        .iter()
        .map(|b| Bundle::read(b.as_deref().ok_or_else(invalid)?))
        .collect::<Result<Vec<_>>>()?;
    let roots = roots(plan, false)?;
    let mut hosts = Vec::new();
    let mut paths = Vec::new();
    for (bundle, root) in bundles.iter().zip(&roots) {
        let declared: BTreeSet<_> = bundle
            .files
            .iter()
            .filter(|(_, file)| file.contribution.is_some())
            .map(|(path, _)| path.clone())
            .collect();
        hosts.push(
            declared
                .iter()
                .map(|path| Ok((path.clone(), root.read(path)?.map(|content| content.bytes))))
                .collect::<Result<crate::bundle::Hosts>>()?,
        );
        paths.push(declared);
    }
    let payloads: BTreeMap<_, _> = plan
        .children
        .iter()
        .zip(&bundles)
        .zip(&hosts)
        .map(|((child, bundle), hosts)| {
            Ok((
                child.parsed()?.target_scope,
                ScopedPayload {
                    bindings: &bundle.adaptations,
                    files: &bundle.files,
                    hosts,
                },
            ))
        })
        .collect::<Result<_>>()?;
    coverage::verify_scoped_payloads(connection, &first.setup, &first.harness_id, &payloads)?;
    for ((root, paths), before) in roots.iter().zip(paths).zip(hosts) {
        for path in paths {
            if root.read(&path)?.map(|content| content.bytes)
                != *before.get(&path).ok_or_else(invalid)?
            {
                return Err(invalid());
            }
        }
        root.revalidate()?;
    }
    Ok(())
}

fn admit(journal: &journal::Journal, cancelling: bool) -> Result<Record> {
    let plan = &journal.plan;
    if !cancelling {
        let observation = crate::program::observe(
            &plan.first()?.harness_id,
            plan.program.executable.as_deref().map(Path::new),
        )?;
        if observation["observation_digest"] != plan.program.observation_digest {
            return Err(crate::error::Failure::precondition(
                "the installed harness changed before admission; create a new configuration set plan",
            ));
        }
    }
    let parent = PathBuf::from(plan.first()?.state_parent);
    let roots = roots(plan, !cancelling)?;
    let namespace = journal.namespace.as_ref().ok_or_else(invalid)?;
    let mut held = Vec::new();
    let bundles = if cancelling {
        vec![None; plan.children.len()]
    } else {
        supplied(plan)?
    };
    let runtime = (!cancelling).then(Runtime::observe).transpose()?;
    for (child, bytes) in plan.children.iter().zip(&bundles) {
        let child_plan = child.parsed()?;
        let lock = super::journal::Journal::open_shared(
            &parent,
            &child_plan,
            &child.plan_digest,
            namespace,
        )?;
        if lock.read(&child_plan, &child.plan_digest)?.is_some() {
            return Err(invalid());
        }
        if let Some(runtime) = &runtime {
            let request = child_plan.request(Timestamp::now())?;
            let bundle = bytes.as_deref().map(Bundle::read).transpose()?;
            let (current, _) = super::prepare(
                runtime,
                &TargetRequest {
                    state_parent: &parent,
                    harness: &child_plan.harness_id,
                    version: &child_plan.provider_version,
                    path: Path::new(&child_plan.target_path),
                    scope: child_plan.target_scope,
                },
                &request,
                &child_plan.created_at,
                bytes.as_deref().unwrap_or_default(),
                bundle.as_ref(),
            )?;
            if current.value()? != child.plan {
                return Err(invalid());
            }
            lock.payload(&child_plan, bytes.as_deref(), false)?;
        }
        held.push(lock);
    }
    let record = Record {
        schema_version: 1,
        plan_digest: journal.digest.clone(),
        plan: plan.value()?,
        phase: if cancelling {
            "cancelling"
        } else {
            "preparing"
        }
        .into(),
        prepared: vec![None; plan.children.len()],
        results: vec![None; plan.children.len()],
    };
    let mut store = journal.store()?;
    store.transaction(|connection| {
        if !cancelling {
            coverage(connection, plan, &bundles)?;
            project::admitting(connection, plan)?;
        }
        for (child, lock) in plan.children.iter().zip(&held) {
            let child_plan = child.parsed()?;
            if !cancelling {
                child_plan.request(Timestamp::now())?;
            }
            lock.admit_at(connection, namespace, &child_plan, &child.plan_digest)?;
        }
        for root in &roots {
            root.revalidate()?;
        }
        journal::write(connection, plan, &journal.digest, &record)
    })?;
    Ok(record)
}

pub(in crate::provider::runtime) fn execute(
    parent: &Path,
    bytes: &[u8],
    digest: &str,
    action: &str,
) -> Result<Value> {
    if !matches!(action, "apply" | "cancel" | "status") {
        return Err(invalid());
    }
    let plan = Plan::parse(bytes, digest)?;
    let prior = journal::Journal::history(parent, &plan, digest)?;
    if let Some(record) = &prior
        && (record.state() != "applying" || action == "status")
    {
        return record.result(&plan);
    }
    if action == "status" {
        return Err(invalid());
    }
    let cancelling = action == "cancel";
    let mut journal = journal::Journal::open(parent, plan, digest)?;
    let mut record = match journal::Journal::history(parent, &journal.plan, digest)? {
        Some(record) => record,
        None => admit(&journal, cancelling)?,
    };
    if record.state() != "applying" {
        return record.result(&journal.plan);
    }
    if cancelling && record.phase == "applying" || !cancelling && record.phase == "cancelling" {
        return Err(invalid());
    }
    if cancelling && record.phase == "preparing" {
        record.phase = "cancelling".into();
        journal.save(&record)?;
    }
    journal.namespace.take();
    if record.phase == "preparing" {
        for (index, child) in journal.plan.children.iter().enumerate() {
            if record.prepared[index].is_none() {
                record.prepared[index] = Some(apply::execute(
                    parent,
                    &serde_json::to_vec(&child.plan).map_err(|_| invalid())?,
                    &child.plan_digest,
                    None,
                    Mode::Prepare,
                    Some(&journal),
                )?);
                journal.save(&record)?;
            }
        }
        record.phase = "applying".into();
        let mut store = journal.store()?;
        store.transaction(|connection| {
            project::publishing(connection, &journal.plan)?;
            journal::write(connection, &journal.plan, digest, &record)
        })?;
    }
    for (index, child) in journal.plan.children.iter().enumerate() {
        if record.results[index].is_none() {
            let bytes = serde_json::to_vec(&child.plan).map_err(|_| invalid())?;
            record.results[index] = Some(if cancelling {
                cancel::execute(parent, &bytes, &child.plan_digest, Some(&journal))?
            } else {
                apply::execute(
                    parent,
                    &bytes,
                    &child.plan_digest,
                    None,
                    Mode::Apply,
                    Some(&journal),
                )?
            });
            journal.save(&record)?;
        }
    }
    if !cancelling {
        verify(&journal.plan, &record)?;
    }
    record.phase = if cancelling { "cancelled" } else { "verified" }.into();
    journal.save(&record)?;
    record.result(&journal.plan)
}

fn verify(plan: &Plan, record: &Record) -> Result<()> {
    let runtime = Runtime::observe()?;
    let roots = roots(plan, false)?;
    for ((child, root), result) in plan.children.iter().zip(&roots).zip(&record.results) {
        let plan = child.parsed()?;
        effects::verify(root, &plan.effects, true)?;
        let observed = runtime.status(&TargetRequest {
            state_parent: Path::new(&plan.state_parent),
            harness: &plan.harness_id,
            version: &plan.provider_version,
            path: root.path(),
            scope: plan.target_scope,
        })?;
        if observed["artifact"]["archive_digest"] != plan.archive_digest
            || observed["provider_info_digest"] != plan.info_digest
        {
            return Err(invalid());
        }
        outcome::status(
            &observed["status"],
            &result.as_ref().ok_or_else(invalid)?["provider_result"],
            &plan,
        )?;
        root.revalidate()?;
    }
    Ok(())
}

pub(super) fn authorize(
    parent: &Path,
    child: &single::Plan,
    digest: &str,
    mode: Mode,
    authority: Option<&journal::Journal>,
) -> Result<()> {
    if let Some(authority) = authority {
        authority.validate()?;
    }
    let store = Store::planning(parent)?;
    let mut query = store.connection.prepare("SELECT state,coalesce(detail,'') FROM operation WHERE kind='configuration.set' AND state='applying'").map_err(database)?;
    let mut rows = query.query([]).map_err(database)?;
    let mut authorized = false;
    while let Some(row) = rows.next().map_err(database)? {
        let state: String = row.get(0).map_err(database)?;
        let detail: String = row.get(1).map_err(database)?;
        let (record, plan) = Record::parse(&detail, &state)?;
        for (index, member) in plan.children.iter().enumerate() {
            if member.plan["operation_id"] != child.operation_id {
                continue;
            }
            let authority = authority.ok_or_else(invalid)?;
            if authorized
                || authority.plan.value()? != plan.value()?
                || authority.digest != record.plan_digest
                || member.plan_digest != digest
                || member.plan != child.value()?
            {
                return Err(invalid());
            }
            let valid = match mode {
                Mode::Prepare => {
                    record.phase == "preparing"
                        && record.prepared.iter().position(Option::is_none) == Some(index)
                }
                Mode::Apply => {
                    record.phase == "applying"
                        && record.results.iter().position(Option::is_none) == Some(index)
                }
                Mode::Cancel => {
                    record.phase == "cancelling"
                        && record.results.iter().position(Option::is_none) == Some(index)
                }
            };
            if !valid {
                return Err(invalid());
            }
            authorized = true;
        }
    }
    if authorized != authority.is_some() || mode == Mode::Prepare && !authorized {
        return Err(invalid());
    }
    Ok(())
}
