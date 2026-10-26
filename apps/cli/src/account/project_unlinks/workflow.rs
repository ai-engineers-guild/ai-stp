//! Persist intent before its first write; all admitted retries read the original result.

use std::path::Path;

use cap_fs_ext::MetadataExt;
use rusqlite::{Connection, params};
use serde_json::{Value, json};

use super::{
    Access, Binding, Context, contexts, corporate, invalid,
    journal::Record,
    model::{Change, Effect, KIND, LIMIT, Plan, ServerPlan, Snapshot, confirmation_id},
    project_links,
};
use crate::{
    authoring::{
        self,
        runtime::{self, Owner},
    },
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, identity, passport,
    projects::passports,
    store::{CHECKOUT_UNLINK_SCHEMA, database, journal::checkout_unlink_epoch},
};

fn uncertain(id: &str) -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the original unlink outcome remains unknown; retain its exact operation and request key",
    )
    .with_details([
        ("operation_id".into(), id.into()),
        ("outcome".into(), "unknown".into()),
    ])
}

fn owned(root: &Path, owner: &Owner, plan: &Plan) -> Result<()> {
    if identity::root(root)?
        != (
            plan.state_parent.clone(),
            plan.snapshot().account.root_identity.clone(),
        )
        || !owner.historical(&plan.snapshot().local_identity)
    {
        return Err(invalid());
    }
    Ok(())
}

fn load(root: &Path, id: &str) -> Result<(Owner, Record)> {
    let owner = runtime::owner(root)?;
    let record = {
        let store = owner.planning()?;
        if !checkout_unlink_epoch(&store.connection)? {
            return Err(Failure::new(
                ErrorKind::NotFound,
                "the native unlink has not been admitted",
            ));
        }
        Record::load(&store.connection, id)?
            .ok_or_else(|| Failure::new(ErrorKind::NotFound, "the original unlink is absent"))?
    };
    owned(root, &owner, &record.plan)?;
    Ok((owner, record))
}

fn available(connection: &Connection, binding: &str, except: Option<&str>) -> Result<()> {
    checkout_unlink_epoch(connection)?;
    let mut query=connection.prepare("SELECT operation_id FROM operation WHERE kind=? AND finished_at IS NULL ORDER BY operation_id LIMIT 129").map_err(database)?;
    let ids = query
        .query_map([KIND], |row| row.get::<_, String>(0))
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if ids.len() > 128 {
        return Err(invalid());
    }
    for id in ids {
        let held = Record::load(connection, &id)?.ok_or_else(invalid)?;
        if held.plan.snapshot().binding.source.operation_id == binding
            && except != Some(id.as_str())
        {
            return Err(Failure::precondition(
                "reconcile the retained unlink before reviewing another write for this binding",
            ));
        }
    }
    Ok(())
}

fn check_binding(
    root: &Path,
    owner: &Owner,
    snapshot: &Snapshot,
    registered: &passports::Registered,
) -> Result<()> {
    project_links::binding::revalidate(root, owner, &snapshot.binding)?;
    let physical = registered.directory.dir_metadata().map_err(|_| invalid())?;
    if [physical.dev().to_string(), physical.ino().to_string()] != snapshot.binding.physical_root
        || registered.project != snapshot.binding.local_project
    {
        return Err(invalid());
    }
    snapshot.context.bind()?.revalidate()
}

fn inspect<T>(
    root: &Path,
    context: Option<&str>,
    binding_id: &str,
    finish: impl FnOnce(Snapshot, &mut Access, &Owner, &passports::Registered) -> Result<T>,
) -> Result<T> {
    let (owner, binding) = project_links::binding::capture(root, binding_id)?;
    let registered = {
        let store = owner.planning()?;
        passports::registered(&store.connection, &binding.checkout_root, &owner)?
    };
    let request = corporate::Request::LinkCurrent {
        link_id: binding.link["link_id"].as_str().ok_or_else(invalid)?.into(),
    };
    let observed = corporate::observe(root, context, request.clone())?;
    let observed = &observed["observation"];
    let context: Context =
        serde_json::from_value(observed["context"].clone()).map_err(|_| invalid())?;
    let account: Binding =
        serde_json::from_value(observed["account"].clone()).map_err(|_| invalid())?;
    if context.local_identity != *owner {
        return Err(invalid());
    }
    let mut access = Access::for_binding(root, &account, false)?;
    if access.binding() != &account {
        return Err(invalid());
    }
    let organization_id = observed["organization"]["organization_id"]
        .as_str()
        .ok_or_else(invalid)?;
    let (organization, observation) = contexts::remote(&mut access, Some(organization_id))?;
    let remote_link = request.project(
        &access.corporate(&request, organization_id)?,
        organization_id,
        &account.account_id,
    )?;
    if remote_link != observed["data"]
        || corporate::authority(&organization, &observation)
            != corporate::authority(&observed["organization"], &observed["observation"])
    {
        return Err(invalid());
    }
    let snapshot = Snapshot {
        local_identity: (*owner).clone(),
        binding,
        context,
        account,
        organization,
        observation,
        remote_link,
    };
    snapshot.validate()?;
    check_binding(root, &owner, &snapshot, &registered)?;
    access.revalidate()?;
    finish(snapshot, &mut access, &owner, &registered)
}

fn make(
    root: &Path,
    owner: &Owner,
    snapshot: Snapshot,
    change: impl FnOnce(Box<Snapshot>) -> Change,
    at: &str,
) -> Result<Plan> {
    let change = change(Box::new(snapshot));
    let operation_id = match &change {
        Change::Request { .. } => format!("operation_{}", ulid::Ulid::generate()),
        Change::Confirm {
            request_operation_id,
            ..
        } => confirmation_id(request_operation_id)?,
    };
    let plan = Plan {
        schema_version: 1,
        operation_id,
        state_parent: identity::root(root)?.0,
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        registry_schema_before: owner.planning()?.version()?,
        registry_schema_after: CHECKOUT_UNLINK_SCHEMA,
        change,
    };
    plan.digest()?;
    Ok(plan)
}

pub fn request_plan(root: &Path, context: Option<&str>, binding: &str, at: &str) -> Result<Plan> {
    inspect(root, context, binding, |snapshot, _, owner, _| {
        available(&owner.planning()?.connection, binding, None)?;
        make(
            root,
            owner,
            snapshot,
            |snapshot| Change::Request { snapshot },
            at,
        )
    })
}

fn reader_matches(context: &Context, original: &Snapshot) -> Result<()> {
    let contexts::Authority::Remote {
        account,
        organization,
        ..
    } = &context.authority
    else {
        return Err(invalid());
    };
    if account.origin != original.account.origin
        || account.account_id != original.account.account_id
        || account.root_identity != original.account.root_identity
        || organization["organization_id"] != original.organization["organization_id"]
        || organization["kind"] != "corporate"
    {
        return Err(invalid());
    }
    Ok(())
}

fn project_outcome(value: &Value, original: &Plan) -> Result<()> {
    ServerPlan::read(&value["plan"], original.snapshot())?;
    if let Change::Confirm { server_plan, .. } = &original.change {
        if server_plan.as_ref() != &ServerPlan::read(&value["plan"], original.snapshot())? {
            return Err(invalid());
        }
        if value["state"] == "applied" {
            server_plan.verify_link(&value["link"], original.snapshot())?;
        }
    }
    Ok(())
}

fn original_request(root: &Path, plan: &Plan) -> Result<Record> {
    let (id, hash) = match &plan.change {
        Change::Request { .. } => (&plan.operation_id, None),
        Change::Confirm {
            request_operation_id,
            request_plan_digest,
            ..
        } => (request_operation_id, Some(request_plan_digest)),
    };
    let (_, request) = load(root, id)?;
    let request_hash = request.plan.digest()?;
    if !matches!(request.plan.change, Change::Request { .. })
        || hash.is_some_and(|hash| hash != &request_hash)
    {
        return Err(invalid());
    }
    if matches!(plan.change, Change::Confirm { .. }) {
        request.plan.snapshot().same_binding(plan.snapshot())?;
    }
    Ok(request)
}

fn read_original(root: &Path, plan: &Plan, context: Option<&str>) -> Result<(Value, Binding)> {
    let selected = contexts::resolve(
        root,
        Some(context.unwrap_or(&plan.snapshot().context.context_id)),
    )?;
    reader_matches(&selected, plan.snapshot())?;
    let key = match &plan.change {
        Change::Request { .. } => plan.request_key(),
        Change::Confirm {
            request_operation_id,
            ..
        } => format!("native.project-unlink.request.{request_operation_id}"),
    };
    let observed = corporate::observe(
        root,
        Some(&selected.context_id),
        corporate::Request::UnlinkRequestOutcome { request_key: key },
    )
    .map_err(|error| {
        if matches!(error.kind, ErrorKind::NotFound) {
            uncertain(&plan.operation_id)
        } else {
            error
        }
    })?;
    let observed = &observed["observation"];
    let reader: Binding =
        serde_json::from_value(observed["account"].clone()).map_err(|_| invalid())?;
    if observed["context"] != serde_json::to_value(selected).map_err(|_| invalid())? {
        return Err(invalid());
    }
    project_outcome(&observed["data"], plan)?;
    Ok((observed["data"].clone(), reader))
}

pub fn confirmation_plan(root: &Path, request_id: &str, at: &str) -> Result<Plan> {
    let (owner, request) = load(root, request_id)?;
    if !matches!(request.plan.change, Change::Request { .. }) {
        return Err(invalid());
    }
    let id = confirmation_id(request_id)?;
    if Record::load(&owner.planning()?.connection, &id)?.is_some() {
        return Err(Failure::precondition(
            "the original confirmation is already admitted; reconcile its retained operation",
        ));
    }
    let (observed, _) = read_original(root, &request.plan, None)?;
    let server_plan = ServerPlan::read(&observed["plan"], request.plan.snapshot())?;
    if observed["state"] != "ready"
        || server_plan
            .expires_at
            .parse::<jiff::Timestamp>()
            .map_err(|_| invalid())?
            <= at.parse::<jiff::Timestamp>().map_err(|_| invalid())?
    {
        return Err(invalid());
    }
    inspect(
        root,
        Some(&request.plan.snapshot().context.context_id),
        &request.plan.snapshot().binding.source.operation_id,
        |snapshot, _, owner, _| {
            request.plan.snapshot().same_binding(&snapshot)?;
            server_plan.verify(&snapshot)?;
            available(
                &owner.planning()?.connection,
                &snapshot.binding.source.operation_id,
                Some(request_id),
            )?;
            let request_plan_digest = request.plan.digest()?;
            make(
                root,
                owner,
                snapshot,
                |snapshot| Change::Confirm {
                    snapshot,
                    request_operation_id: request_id.into(),
                    request_plan_digest,
                    server_plan: Box::new(server_plan),
                },
                at,
            )
        },
    )
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let value = canonical::parse(&files::read(path, LIMIT)?)?;
    let plan: Plan = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    if plan.digest()? != digest::canonical("ai-stp:plan:v1", &value)? {
        return Err(invalid());
    }
    Ok(plan)
}

pub fn status(root: &Path, id: &str) -> Result<Value> {
    load(root, id)?.1.output()
}

pub fn list(root: &Path, after: Option<&str>, limit: u16) -> Result<Value> {
    if !(1..=100).contains(&limit) || after.is_some_and(|id| !passport::stable_id(id, "operation"))
    {
        return Err(invalid());
    }
    let owner = runtime::owner(root)?;
    let store = owner.planning()?;
    let mut items = Vec::new();
    let mut next = None;
    if checkout_unlink_epoch(&store.connection)? {
        let mut query=store.connection.prepare("SELECT operation_id FROM operation WHERE kind=? AND operation_id>? ORDER BY operation_id LIMIT ?").map_err(database)?;
        let ids = query
            .query_map(
                params![KIND, after.unwrap_or(""), u32::from(limit) + 1],
                |row| row.get::<_, String>(0),
            )
            .map_err(database)?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(database)?;
        if ids.len() > usize::from(limit) {
            next = ids.get(usize::from(limit) - 1).cloned();
        }
        for id in ids.into_iter().take(usize::from(limit)) {
            let record = Record::load(&store.connection, &id)?.ok_or_else(invalid)?;
            owned(root, &owner, &record.plan)?;
            items.push(record.output()?);
        }
    }
    Ok(
        json!({"schema_version":1,"items":items,"next_cursor":next,"online_verified":false,"installation_authority":false}),
    )
}

pub fn outcome(root: &Path, id: &str, context: Option<&str>) -> Result<Value> {
    let (_, record) = load(root, id)?;
    let (outcome, reader) = read_original(root, &record.plan, context)?;
    Ok(
        json!({"schema_version":1,"operation_id":id,"outcome":outcome,"reader":reader,
        "online_verified":true,"observation_only":true,"installation_authority":false,"local_binding_retired":false}),
    )
}

fn save(root: &Path, owner: &Owner, plan: &Plan, effect: Effect, at: &str) -> Result<Value> {
    owned(root, owner, plan)?;
    owner.open(false)?.transaction(|t| {
        if !checkout_unlink_epoch(t)? {
            return Err(invalid());
        }
        let mut held = Record::load(t, &plan.operation_id)?.ok_or_else(invalid)?;
        if held.plan.digest()? != plan.digest()? {
            return Err(invalid());
        }
        if held.state != "completed" {
            held.save(t, effect, at)?;
        }
        held.output()
    })
}

fn reconcile(
    root: &Path,
    owner: &Owner,
    record: Record,
    context: Option<&str>,
    at: &str,
) -> Result<Value> {
    let (observed, reader) = read_original(root, &record.plan, context)?;
    let effect = match &record.plan.change {
        Change::Request { .. } => Effect::Requested {
            server_plan: Box::new(ServerPlan::read(&observed["plan"], record.plan.snapshot())?),
            outcome_reader: Some(reader),
        },
        Change::Confirm { .. } if observed["state"] == "applied" => Effect::Confirmed {
            link: observed["link"].clone(),
            outcome_reader: Some(reader),
        },
        _ => return Err(uncertain(&record.plan.operation_id)),
    };
    save(root, owner, &record.plan, effect, at)
}

pub fn apply(
    root: &Path,
    plan: &Plan,
    expected: &str,
    context: Option<&str>,
    at: &str,
) -> Result<Value> {
    if plan.digest()? != expected || !passport::timestamp(at) || at < plan.created_at.as_str() {
        return Err(invalid());
    }
    let owner = runtime::owner(root)?;
    owned(root, &owner, plan)?;
    let known = {
        let store = owner.planning()?;
        checkout_unlink_epoch(&store.connection)?;
        Record::load(&store.connection, &plan.operation_id)?
    };
    if let Some(record) = known {
        if record.plan.digest()? != expected {
            return Err(invalid());
        }
        return if record.state == "completed" {
            record.output()
        } else {
            reconcile(root, &owner, record, context, at)
        };
    }
    if at >= plan.expires_at.as_str()
        || context.is_some_and(|id| id != plan.snapshot().context.context_id)
    {
        return Err(invalid());
    }
    let original = if matches!(plan.change, Change::Confirm { .. }) {
        Some(original_request(root, plan)?)
    } else {
        None
    };
    inspect(
        root,
        Some(&plan.snapshot().context.context_id),
        &plan.snapshot().binding.source.operation_id,
        |fresh, access, owner, registered| {
            plan.snapshot().unchanged(&fresh)?;
            let mut confirmed_request = None;
            if let Some(original) = &original {
                let request = corporate::Request::UnlinkRequestOutcome {
                    request_key: original.plan.request_key(),
                };
                let value = request.project(
                    &access.corporate(&request, fresh.organization_id()?)?,
                    fresh.organization_id()?,
                    &fresh.account.account_id,
                )?;
                project_outcome(&value, &original.plan)?;
                let Change::Confirm { server_plan, .. } = &plan.change else {
                    return Err(invalid());
                };
                if value["state"] != "ready"
                    || server_plan.as_ref()
                        != &ServerPlan::read(&value["plan"], original.plan.snapshot())?
                    || server_plan
                        .expires_at
                        .parse::<jiff::Timestamp>()
                        .map_err(|_| invalid())?
                        <= at.parse::<jiff::Timestamp>().map_err(|_| invalid())?
                    || value["authorization_revision"]
                        != fresh.observation["capabilities"]["authorization_revision"]
                {
                    return Err(invalid());
                }
                confirmed_request =
                    Some(ServerPlan::read(&value["plan"], original.plan.snapshot())?);
            }
            check_binding(root, owner, &fresh, registered)?;
            access.revalidate()?;
            {
                let mut store = owner.open(false)?;
                if store.version()? != plan.registry_schema_before {
                    return Err(invalid());
                }
                store.checkout_unlink_transaction(|t| {
                    available(
                        t,
                        &fresh.binding.source.operation_id,
                        original.as_ref().map(|r| r.plan.operation_id.as_str()),
                    )?;
                    if let Some(original) = &original {
                        let mut held =
                            Record::load(t, &original.plan.operation_id)?.ok_or_else(invalid)?;
                        if held.plan.digest()? != original.plan.digest()? {
                            return Err(invalid());
                        }
                        if held.state != "completed" {
                            held.save(
                                t,
                                Effect::Requested {
                                    server_plan: Box::new(
                                        confirmed_request.clone().ok_or_else(invalid)?,
                                    ),
                                    outcome_reader: Some(access.binding().clone()),
                                },
                                at,
                            )?;
                        }
                    }
                    Record::admit(t, plan, at)?;
                    Ok(())
                })?;
            }
            check_binding(root, owner, &fresh, registered)?;
            access.revalidate()?;
            let confirm = matches!(plan.change, Change::Confirm { .. });
            let body = canonical::bytes(&plan.body()?)?;
            let response = access.project_unlink(
                fresh.organization_id()?,
                fresh.remote_link["link_id"].as_str().ok_or_else(invalid)?,
                confirm,
                &body,
            )?;
            let effect = match &plan.change {
                Change::Request { .. } => Effect::Requested {
                    server_plan: Box::new(ServerPlan::read(&response, &fresh)?),
                    outcome_reader: None,
                },
                Change::Confirm { server_plan, .. } => {
                    server_plan.verify_link(&response, &fresh)?;
                    Effect::Confirmed {
                        link: response,
                        outcome_reader: None,
                    }
                }
            };
            fresh.context.bind()?.revalidate()?;
            access.revalidate()?;
            save(root, owner, plan, effect, &super::super::now_after(at))
        },
    )
}
