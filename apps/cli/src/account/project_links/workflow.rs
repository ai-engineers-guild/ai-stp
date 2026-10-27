//! Review and admit exact requests; uncertain effects are observed, never resent.

use std::path::Path;

use cap_fs_ext::MetadataExt;
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};

use super::{
    Access, Binding, Context, contexts, corporate, inspect, invalid,
    journal::Record,
    model::{Change, Effect, LIMIT, Plan, ServerPlan, Snapshot, project_link},
};
use crate::{
    authoring::{
        self,
        runtime::{self, Owner},
    },
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, identity, passport,
    projects::{checkout, passports},
    store::{
        CHECKOUT_RETIREMENT_SCHEMA, checkout_schema_after, database, has_checkout_links,
        has_checkout_unlinks,
    },
};

fn uncertain(id: &str) -> Failure {
    Failure::new(ErrorKind::Unavailable, "the original project-link outcome remains unknown; retain its exact operation and request key")
        .with_details([("operation_id".into(), id.into()), ("outcome".into(), "unknown".into())])
}

fn outcome_coordinates(value: &Value) -> Value {
    json!([
        value["plan"],
        value["state"],
        value["link"],
        value["authorization_revision"]
    ])
}

pub(super) fn owned(root: &Path, owner: &Owner, plan: &Plan) -> Result<()> {
    let (path, physical) = identity::root(root)?;
    if plan.state_parent != path
        || plan.snapshot().account.root_identity != physical
        || !owner.historical(&plan.snapshot().context.local_identity)
    {
        return Err(invalid());
    }
    Ok(())
}

pub(super) fn load(root: &Path, id: &str) -> Result<(Owner, Record)> {
    let owner = runtime::owner(root)?;
    let record = {
        let store = owner.planning()?;
        if !has_checkout_links(store.version()?) {
            return Err(Failure::new(
                ErrorKind::NotFound,
                "the native checkout operation has not been admitted",
            ));
        }
        Record::load(&store.connection, id)?.ok_or_else(|| {
            Failure::new(
                ErrorKind::NotFound,
                "the native checkout operation is absent",
            )
        })?
    };
    owned(root, &owner, &record.plan)?;
    Ok((owner, record))
}

fn request(root: &Path, plan: &Plan) -> Result<Record> {
    let id = match &plan.change {
        Change::Request { .. } => &plan.operation_id,
        Change::Confirm {
            request_operation_id,
            ..
        }
        | Change::Adopt {
            request_operation_id,
            ..
        } => request_operation_id,
    };
    let (_, record) = load(root, id)?;
    check_request_open(root, id)?;
    if !matches!(&record.plan.change, Change::Request { .. }) || record.state == "retired" {
        return Err(invalid());
    }
    Ok(record)
}

fn check_request_open(root: &Path, id: &str) -> Result<()> {
    let owner = runtime::owner(root)?;
    let store = owner.planning()?;
    super::retirement::request_open(&store.connection, id)
}

pub(super) fn reader_matches(context: &Context, original: &Snapshot) -> Result<()> {
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

fn read_original(root: &Path, original: &Plan, context: Option<&str>) -> Result<(Value, Binding)> {
    let context = contexts::resolve(
        root,
        Some(context.unwrap_or(&original.snapshot().context.context_id)),
    )?;
    // Refuse before sending the original opaque request key to another origin.
    reader_matches(&context, original.snapshot())?;
    let request = corporate::Request::LinkRequestOutcome {
        request_key: original.request_key(),
    };
    let observed =
        corporate::observe(root, Some(&context.context_id), request).map_err(|failure| {
            if matches!(failure.kind, ErrorKind::NotFound) {
                uncertain(&original.operation_id)
            } else {
                failure
            }
        })?;
    let observed = &observed["observation"];
    let binding: Binding =
        serde_json::from_value(observed["account"].clone()).map_err(|_| invalid())?;
    if observed["context"] != serde_json::to_value(&context).map_err(|_| invalid())?
        || binding.origin != original.snapshot().account.origin
        || binding.account_id != original.snapshot().account.account_id
    {
        return Err(invalid());
    }
    ServerPlan::read(&observed["data"]["plan"], original.snapshot())?;
    Ok((observed["data"].clone(), binding))
}

fn held_outcome(access: &mut Access, fresh: &Snapshot, original: &Plan) -> Result<Value> {
    reader_matches(&fresh.context, original.snapshot())?;
    let request = corporate::Request::LinkRequestOutcome {
        request_key: original.request_key(),
    };
    let value = request.project(
        &access.corporate(&request, fresh.organization_id()?)?,
        fresh.organization_id()?,
        &fresh.account.account_id,
    )?;
    ServerPlan::read(&value["plan"], original.snapshot())?;
    let (organization, observation) = contexts::remote(access, Some(fresh.organization_id()?))?;
    if corporate::authority(&organization, &observation)
        != corporate::authority(&fresh.organization, &fresh.observation)
        || value["authorization_revision"] != observation["capabilities"]["authorization_revision"]
    {
        return Err(invalid());
    }
    Ok(value)
}

fn make(
    root: &Path,
    checkout_root: &Path,
    snapshot: Snapshot,
    before: u32,
    change: impl FnOnce(Box<Snapshot>) -> Change,
    at: &str,
) -> Result<Plan> {
    let plan = Plan {
        schema_version: if has_checkout_unlinks(before) {
            3
        } else if before == CHECKOUT_RETIREMENT_SCHEMA {
            2
        } else {
            1
        },
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        state_parent: identity::root(root)?.0,
        checkout_root: checkout_root.into(),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        registry_schema_before: before,
        registry_schema_after: checkout_schema_after(before)?,
        change: change(Box::new(snapshot)),
    };
    plan.digest()?;
    Ok(plan)
}

pub fn request_plan(
    root: &Path,
    context: Option<&str>,
    checkout_root: &Path,
    project: &str,
    provider: Option<&str>,
    git: Option<&Path>,
    at: &str,
) -> Result<Plan> {
    inspect(
        root,
        context,
        checkout_root,
        project,
        provider,
        git,
        |value, _, owner, registered| {
            let snapshot = Snapshot::from_preview(&value)?;
            let before = owner.planning()?.version()?;
            make(
                root,
                &registered.path,
                snapshot,
                before,
                |snapshot| Change::Request { snapshot },
                at,
            )
        },
    )
}

fn target(original: &Snapshot) -> Result<(&str, Option<&str>)> {
    Ok((
        original.request_coordinates["remote_project_id"]
            .as_str()
            .ok_or_else(invalid)?,
        original.request_coordinates["provider_project_id"].as_str(),
    ))
}

pub fn confirmation_plan(
    root: &Path,
    request_id: &str,
    git: Option<&Path>,
    at: &str,
) -> Result<Plan> {
    let (_, original) = load(root, request_id)?;
    check_request_open(root, request_id)?;
    if !matches!(&original.plan.change, Change::Request { .. }) || original.state == "retired" {
        return Err(invalid());
    }
    let (observed, _) = read_original(root, &original.plan, None)?;
    let server_plan = ServerPlan::read(&observed["plan"], original.plan.snapshot())?;
    if observed["state"] != "ready"
        || server_plan
            .expires_at
            .parse::<jiff::Timestamp>()
            .map_err(|_| invalid())?
            <= at.parse::<jiff::Timestamp>().map_err(|_| invalid())?
    {
        return Err(invalid());
    }
    let (project, provider) = target(original.plan.snapshot())?;
    inspect(
        root,
        Some(&original.plan.snapshot().context.context_id),
        &original.plan.checkout_root,
        project,
        provider,
        git,
        |value, _, owner, registered| {
            let snapshot = Snapshot::from_preview(&value)?;
            server_plan.verify(&snapshot)?;
            if snapshot.physical_root()? != original.plan.snapshot().physical_root()? {
                return Err(invalid());
            }
            make(
                root,
                &registered.path,
                snapshot,
                owner.planning()?.version()?,
                |snapshot| Change::Confirm {
                    request_operation_id: request_id.into(),
                    snapshot,
                    server_plan: Box::new(server_plan),
                },
                at,
            )
        },
    )
}

pub fn adoption_plan(
    root: &Path,
    request_id: &str,
    context: Option<&str>,
    checkout_root: &Path,
    git: Option<&Path>,
    at: &str,
) -> Result<Plan> {
    let (_, original) = load(root, request_id)?;
    check_request_open(root, request_id)?;
    if !matches!(&original.plan.change, Change::Request { .. }) || original.state == "retired" {
        return Err(invalid());
    }
    let selected = contexts::resolve(root, context)?;
    reader_matches(&selected, original.plan.snapshot())?;
    let (observed, _) = read_original(root, &original.plan, Some(&selected.context_id))?;
    let (project, provider) = target(original.plan.snapshot())?;
    inspect(
        root,
        Some(&selected.context_id),
        checkout_root,
        project,
        provider,
        git,
        |value, _, owner, registered| {
            let snapshot = Snapshot::from_preview(&value)?;
            if snapshot.project_id()? != original.plan.snapshot().project_id()?
                || snapshot.physical_root()? != original.plan.snapshot().physical_root()?
            {
                return Err(invalid());
            }
            make(
                root,
                &registered.path,
                snapshot,
                owner.planning()?.version()?,
                |snapshot| Change::Adopt {
                    request_operation_id: request_id.into(),
                    snapshot,
                    outcome: observed,
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
    if has_checkout_links(store.version()?) {
        let mut query = store.connection.prepare("SELECT operation_id FROM operation WHERE kind=? AND operation_id>? ORDER BY operation_id LIMIT ?").map_err(database)?;
        let ids = query
            .query_map(
                params![
                    super::model::KIND,
                    after.unwrap_or(""),
                    u32::from(limit) + 1
                ],
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
            if !owner.historical(&record.plan.snapshot().context.local_identity) {
                return Err(invalid());
            }
            items.push(record.output()?);
        }
    }
    Ok(
        json!({"schema_version":1,"items":items,"next_cursor":next,"online_verified":false,"installation_authority":false}),
    )
}

pub fn outcome(root: &Path, id: &str, context: Option<&str>) -> Result<Value> {
    let (_, record) = load(root, id)?;
    let original = request(root, &record.plan)?;
    let (outcome, reader) = read_original(root, &original.plan, context)?;
    Ok(
        json!({"schema_version":1,"operation_id":id,"original_request_operation_id":original.plan.operation_id,
        "original_request_key":original.plan.request_key(),"outcome":outcome,"reader":reader,
        "online_verified":true,"observation_only":true,"installation_authority":false}),
    )
}

fn check_local(
    plan: &Plan,
    owner: &Owner,
    registered: &passports::Registered,
    git: Option<&Path>,
) -> Result<()> {
    let current = {
        let store = owner.planning()?;
        passports::registered(&store.connection, &registered.path, owner)?
    };
    let held = registered.directory.dir_metadata().map_err(|_| invalid())?;
    if current.path != registered.path
        || current.identity != registered.identity
        || current.project != registered.project
        || [held.dev().to_string(), held.ino().to_string()] != registered.identity
        || checkout::observe(&registered.path, git)? != plan.snapshot().checkout
    {
        return Err(invalid());
    }
    Ok(())
}

struct Reservation {
    request: String,
    project: String,
    physical: [String; 2],
    confirmation: Option<String>,
    binding: Option<String>,
}

fn reserve(t: &Transaction<'_>, plan: &Plan, request_id: &str) -> Result<()> {
    super::retirement::request_open(t, request_id)?;
    let snapshot = plan.snapshot();
    let physical = snapshot.physical_root()?;
    let held: Option<Reservation> = t.query_row(
        "SELECT request_operation_id,local_project_id,root_device,root_inode,confirmation_operation_id,binding_operation_id FROM native_checkout_reservation WHERE local_project_id=? OR (root_device=? AND root_inode=?)",
        params![snapshot.project_id()?,physical[0],physical[1]], |row| Ok(Reservation {
            request: row.get(0)?, project: row.get(1)?, physical: [row.get(2)?,row.get(3)?],
            confirmation: row.get(4)?, binding: row.get(5)? })).optional().map_err(database)?;
    if let Some(held) = held {
        if held.request != request_id
            || held.project != snapshot.project_id()?
            || held.physical != physical
            || held.binding.is_some()
            || matches!(&plan.change, Change::Confirm { .. })
                && held.confirmation.as_deref() != Some(&plan.operation_id)
        {
            return Err(Failure::precondition(
                "the original checkout confirmation or binding still reserves this physical project",
            ));
        }
    } else {
        if t.query_row("SELECT EXISTS(SELECT 1 FROM project_link WHERE local_project_id=? AND state!='unlinked')", [snapshot.project_id()?], |r| r.get::<_,bool>(0)).map_err(database)? { return Err(invalid()); }
        let (confirmation, binding, context) = match &plan.change {
            Change::Confirm { .. } => (Some(plan.operation_id.as_str()), None, None),
            Change::Adopt { .. } => (
                None,
                Some(plan.operation_id.as_str()),
                Some(snapshot.context.context_id.as_str()),
            ),
            Change::Request { .. } => return Err(invalid()),
        };
        t.execute("INSERT INTO native_checkout_reservation(request_operation_id,local_project_id,root_device,root_inode,confirmation_operation_id,binding_operation_id,context_id) VALUES (?,?,?,?,?,?,?)",
            params![request_id,snapshot.project_id()?,physical[0],physical[1],confirmation,binding,context]).map_err(database)?;
    }
    Ok(())
}

fn adopt(t: &Transaction<'_>, plan: &Plan, request_id: &str, link: &Value) -> Result<()> {
    reserve(t, plan, request_id)?;
    let snapshot = plan.snapshot();
    let changed = t.execute("UPDATE native_checkout_reservation SET binding_operation_id=?,context_id=? WHERE request_operation_id=? AND (binding_operation_id IS NULL OR binding_operation_id=?)",
        params![plan.operation_id,snapshot.context.context_id,request_id,plan.operation_id]).map_err(database)?;
    if changed != 1 {
        return Err(invalid());
    }
    let text = |key: &str| link[key].as_str().ok_or_else(invalid);
    let changed = t.execute(
        "INSERT INTO project_link(local_project_id,organization_id,remote_project_id,provider_project_id,state,local_revision,remote_revision,provider_revision,link_revision,updated_at,plan_id,plan_digest,link_id) VALUES (?,?,?,?,'linked',?,?,?,?,?,?,?,?) ON CONFLICT(local_project_id) DO UPDATE SET organization_id=excluded.organization_id,remote_project_id=excluded.remote_project_id,provider_project_id=excluded.provider_project_id,state=excluded.state,local_revision=excluded.local_revision,remote_revision=excluded.remote_revision,provider_revision=excluded.provider_revision,link_revision=excluded.link_revision,updated_at=excluded.updated_at,plan_id=excluded.plan_id,plan_digest=excluded.plan_digest,link_id=excluded.link_id WHERE project_link.state='unlinked'",
        params![snapshot.project_id()?,text("organization_id")?,text("remote_project_id")?,link["provider_project_id"].as_str(),text("local_revision")?,text("remote_revision")?,link["provider_revision"].as_str(),link["revision"].as_i64().ok_or_else(invalid)?,text("updated_at")?,text("plan_id")?,text("plan_digest")?,text("link_id")?]).map_err(database)?;
    if changed != 1 {
        return Err(invalid());
    }
    Ok(())
}

fn reconcile(root: &Path, record: Record, context: Option<&str>, at: &str) -> Result<Value> {
    let original = request(root, &record.plan)?;
    let (observed, reader) = read_original(root, &original.plan, context)?;
    let effect = match &record.plan.change {
        Change::Request { .. } => Effect::Requested {
            server_plan: Box::new(ServerPlan::read(
                &observed["plan"],
                original.plan.snapshot(),
            )?),
            outcome_reader: Some(reader),
        },
        Change::Confirm { server_plan, .. } if observed["state"] == "applied" => {
            if server_plan.as_ref()
                != &ServerPlan::read(&observed["plan"], original.plan.snapshot())?
            {
                return Err(invalid());
            }
            server_plan.verify_link(&observed["link"])?;
            Effect::Confirmed {
                link: observed["link"].clone(),
                outcome_reader: Some(reader),
            }
        }
        _ => return Err(uncertain(&record.plan.operation_id)),
    };
    let owner = runtime::owner(root)?;
    owned(root, &owner, &record.plan)?;
    let mut store = owner.open(false)?;
    store.transaction(|t| {
        let mut current = Record::load(t, &record.plan.operation_id)?.ok_or_else(invalid)?;
        if current.plan.digest()? != record.plan.digest()? {
            return Err(invalid());
        }
        if current.state != "completed" {
            current.save(t, effect, at)?;
        }
        current.output()
    })
}

pub fn apply(
    root: &Path,
    plan: &Plan,
    expected: &str,
    context: Option<&str>,
    git: Option<&Path>,
    at: &str,
) -> Result<Value> {
    if plan.digest()? != expected || !passport::timestamp(at) || at < plan.created_at.as_str() {
        return Err(invalid());
    }
    let owner = runtime::owner(root)?;
    owned(root, &owner, plan)?;
    let known = {
        let store = owner.planning()?;
        Record::load(&store.connection, &plan.operation_id)?
    };
    if let Some(record) = known {
        if record.plan.digest()? != expected {
            return Err(invalid());
        }
        return if matches!(record.state.as_str(), "completed" | "retired") {
            record.output()
        } else {
            reconcile(root, record, context, at)
        };
    }
    if at >= plan.expires_at.as_str()
        || context.is_some_and(|c| c != plan.snapshot().context.context_id)
    {
        return Err(invalid());
    }
    let selected = contexts::resolve(root, Some(&plan.snapshot().context.context_id))?;
    if selected != plan.snapshot().context {
        return Err(invalid());
    }
    let original = if matches!(&plan.change, Change::Request { .. }) {
        None
    } else {
        Some(request(root, plan)?)
    };
    if let Some(original) = &original {
        reader_matches(&selected, original.plan.snapshot())?;
    }
    let (project, provider) = target(plan.snapshot())?;
    inspect(
        root,
        Some(&selected.context_id),
        &plan.checkout_root,
        project,
        provider,
        git,
        |value, access, owner, registered| {
            let fresh = Snapshot::from_preview(&value)?;
            plan.snapshot().unchanged(&fresh)?;
            let observed = original
                .as_ref()
                .map(|original| held_outcome(access, &fresh, &original.plan))
                .transpose()?;
            if let Some(original) = &original {
                if original.plan.snapshot().project_id()? != fresh.project_id()?
                    || original.plan.snapshot().physical_root()? != fresh.physical_root()?
                {
                    return Err(invalid());
                }
                let observed = observed.as_ref().ok_or_else(invalid)?;
                match &plan.change {
                    Change::Confirm { server_plan, .. } => {
                        if observed["state"] != "ready"
                            || server_plan.as_ref()
                                != &ServerPlan::read(&observed["plan"], original.plan.snapshot())?
                        {
                            return Err(invalid());
                        }
                    }
                    Change::Adopt { outcome, .. } => {
                        if outcome_coordinates(outcome) != outcome_coordinates(observed)
                            || observed["state"] != "applied"
                            || observed["link"]["state"] != "linked"
                        {
                            return Err(invalid());
                        }
                    }
                    Change::Request { .. } => return Err(invalid()),
                }
            }
            check_local(plan, owner, registered, git)?;
            access.revalidate()?;
            {
                let mut store = owner.open(false)?;
                if store.version()? != plan.registry_schema_before {
                    return Err(invalid());
                }
                store.checkout_transaction(|t| {
                    if let Some(original) = &original {
                        let mut retained =
                            Record::load(t, &original.plan.operation_id)?.ok_or_else(invalid)?;
                        if retained.plan.digest()? != original.plan.digest()? {
                            return Err(invalid());
                        }
                        let observed = observed.as_ref().ok_or_else(invalid)?;
                        if retained.state != "completed" {
                            retained.save(
                                t,
                                Effect::Requested {
                                    server_plan: Box::new(ServerPlan::read(
                                        &observed["plan"],
                                        retained.plan.snapshot(),
                                    )?),
                                    outcome_reader: Some(access.binding().clone()),
                                },
                                at,
                            )?;
                        }
                    }
                    let mut admitted = Record::admit(t, plan, at)?;
                    match &plan.change {
                        Change::Request { .. } => (),
                        Change::Confirm {
                            request_operation_id,
                            ..
                        } => reserve(t, plan, request_operation_id)?,
                        Change::Adopt {
                            request_operation_id,
                            outcome,
                            ..
                        } => {
                            let link = project_link(&outcome["link"])?;
                            let confirmation: Option<Option<String>> = t.query_row(
                                "SELECT confirmation_operation_id FROM native_checkout_reservation WHERE request_operation_id=?",
                                [request_operation_id], |row| row.get(0)).optional().map_err(database)?;
                            if let Some(Some(confirmation)) = confirmation {
                                let mut retained = Record::load(t, &confirmation)?.ok_or_else(invalid)?;
                                let source = original.as_ref().ok_or_else(invalid)?;
                                let Change::Confirm { request_operation_id: held_request, server_plan, .. } = &retained.plan.change else { return Err(invalid()); };
                                if held_request != request_operation_id || server_plan.as_ref() != &ServerPlan::read(&outcome["plan"], source.plan.snapshot())? {
                                    return Err(invalid());
                                }
                                server_plan.verify_link(&link)?;
                                if retained.state != "completed" {
                                    retained.save(t, Effect::Confirmed { link: link.clone(), outcome_reader: Some(access.binding().clone()) }, at)?;
                                }
                            }
                            adopt(t, plan, request_operation_id, &link)?;
                            admitted.save(t, Effect::Adopted { link }, at)?;
                        }
                    }
                    Ok(())
                })?;
            }
            if !matches!(&plan.change, Change::Adopt { .. }) {
                check_local(plan, owner, registered, git)?;
                let confirm = matches!(&plan.change, Change::Confirm { .. });
                let body = canonical::bytes(&plan.request_body()?)?;
                let response = access.project_link(fresh.organization_id()?, confirm, &body)?;
                let effect = match &plan.change {
                    Change::Request { snapshot } => Effect::Requested {
                        server_plan: Box::new(ServerPlan::read(&response, snapshot)?),
                        outcome_reader: None,
                    },
                    Change::Confirm { server_plan, .. } => {
                        let link = project_link(&response)?;
                        server_plan.verify_link(&link)?;
                        Effect::Confirmed {
                            link,
                            outcome_reader: None,
                        }
                    }
                    Change::Adopt { .. } => return Err(invalid()),
                };
                let mut store = owner.open(false)?;
                store.transaction(|t| {
                    let mut admitted = Record::load(t, &plan.operation_id)?.ok_or_else(invalid)?;
                    admitted.save(t, effect, &super::super::now_after(at))
                })?;
            }
            let store = owner.planning()?;
            Record::load(&store.connection, &plan.operation_id)?
                .ok_or_else(invalid)?
                .output()
        },
    )
}
