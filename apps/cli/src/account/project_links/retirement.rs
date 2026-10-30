//! Review local retirement separately from observing an original remote effect.

use std::path::{Path, PathBuf};

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    Access, Binding, contexts, corporate, invalid,
    journal::{Checkpoint, Record},
    model::{self, Change, Effect, LIMIT, ServerPlan},
    reader::Reader,
    workflow,
};
use crate::{
    authoring::{self, runtime},
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, identity, passport,
    store::{
        BINDING_RETIREMENT_SCHEMA, CHECKOUT_LINK_SCHEMA, CHECKOUT_LOCATION_SCHEMA,
        CHECKOUT_RETIREMENT_SCHEMA, CHECKOUT_UNLINK_SCHEMA, database, has_checkout_retirement,
    },
};

const KIND: &str = "corporate.project_link.retire";

fn request_id(source: &model::Plan) -> Result<&str> {
    match &source.change {
        Change::Request { .. } => Ok(&source.operation_id),
        Change::Confirm {
            request_operation_id,
            ..
        } => Ok(request_operation_id),
        Change::Adopt { .. } => Err(invalid()),
    }
}

pub(super) fn request_open(connection: &Connection, request: &str) -> Result<()> {
    let version: u32 = connection
        .pragma_query_value(None, "user_version", |row| row.get(0))
        .map_err(database)?;
    if has_checkout_retirement(version) && connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM native_checkout_retirement WHERE request_operation_id=?)",
        [request], |row| row.get::<_,bool>(0)).map_err(database)? {
        return Err(Failure::precondition("the original checkout request was explicitly retired; review a new request instead"));
    }
    if crate::store::has_binding_retirement(version) && connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM native_binding_retirement WHERE request_operation_id=?)",
        [request], |row| row.get::<_,bool>(0)).map_err(database)? {
        return Err(Failure::precondition("the original binding was retired; review an independent new checkout request"));
    }
    Ok(())
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub(super) enum Reason {
    UnknownRequest,
    ExpiredConfirmation,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(super) struct Evidence {
    operation_id: String,
    plan_digest: String,
    pub source: Checkpoint,
    reason: Reason,
    reader: Option<Binding>,
    settlement: Option<Value>,
}

fn expired(value: &Value, source: &model::Plan) -> Result<()> {
    let Change::Confirm { server_plan, .. } = &source.change else {
        return Err(invalid());
    };
    let projected = corporate::Request::LinkSettlement {
        plan_id: server_plan.plan_id.clone(),
    }
    .project(
        value,
        source.snapshot().organization_id()?,
        &source.snapshot().account.account_id,
    )?;
    if projected != *value
        || value["state"] != "expired"
        || !value["link"].is_null()
        || ServerPlan::read(&value["plan"], source.snapshot())? != **server_plan
        || value["observed_at"]
            .as_str()
            .ok_or_else(invalid)?
            .parse::<jiff::Timestamp>()
            .map_err(|_| invalid())?
            < server_plan
                .expires_at
                .parse::<jiff::Timestamp>()
                .map_err(|_| invalid())?
    {
        return Err(invalid());
    }
    Ok(())
}

impl Evidence {
    pub(super) fn validate(&self, source: &model::Plan) -> Result<()> {
        self.source.validate()?;
        if !passport::stable_id(&self.operation_id, "operation")
            || self.operation_id == source.operation_id
            || !model::hash(&self.plan_digest)
            || self.source.operation_id != source.operation_id
            || self.source.plan_digest != source.digest()?
        {
            return Err(invalid());
        }
        match (&self.reason, &source.change, &self.reader, &self.settlement) {
            (Reason::UnknownRequest, Change::Request { .. }, None, None) => Ok(()),
            (Reason::ExpiredConfirmation, Change::Confirm { .. }, Some(reader), Some(value)) => {
                reader.validate()?;
                let original = &source.snapshot().account;
                if reader.origin != original.origin
                    || reader.account_id != original.account_id
                    || reader.root_identity != original.root_identity
                {
                    return Err(invalid());
                }
                expired(value, source)
            }
            _ => Err(invalid()),
        }
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    schema_version: u32,
    operation_id: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    state_parent: PathBuf,
    root_identity: [String; 2],
    local_identity: authoring::Identity,
    created_at: String,
    expires_at: String,
    registry_schema_before: u32,
    registry_schema_after: u32,
    source: Checkpoint,
    original: Box<model::Plan>,
    reason: Reason,
    reader: Option<Reader>,
    settlement: Option<Value>,
}

impl Plan {
    pub fn state_parent(&self) -> &Path {
        &self.state_parent
    }

    fn evidence(&self, hash: String, settlement: Option<Value>) -> Evidence {
        Evidence {
            operation_id: self.operation_id.clone(),
            plan_digest: hash,
            source: self.source.clone(),
            reason: self.reason.clone(),
            reader: self.reader.as_ref().map(|reader| reader.account.clone()),
            settlement,
        }
    }

    pub fn digest(&self) -> Result<String> {
        self.local_identity.validate()?;
        self.original.digest()?;
        self.source.validate()?;
        if self.schema_version
            != if crate::store::has_checkout_unlinks(self.registry_schema_after) {
                2
            } else {
                1
            }
            || !passport::stable_id(&self.operation_id, "operation")
            || self.operation_id == self.source.operation_id
            || !self.state_parent.is_absolute()
            || self.state_parent != self.original.state_parent
            || self.root_identity != self.original.snapshot().account.root_identity
            || ![
                CHECKOUT_LINK_SCHEMA,
                CHECKOUT_RETIREMENT_SCHEMA,
                CHECKOUT_UNLINK_SCHEMA,
                BINDING_RETIREMENT_SCHEMA,
                CHECKOUT_LOCATION_SCHEMA,
                crate::store::MISSING_CHECKOUT_RETIREMENT_SCHEMA,
            ]
            .contains(&self.registry_schema_before)
            || self.registry_schema_after
                != if crate::store::has_checkout_unlinks(self.registry_schema_before) {
                    self.registry_schema_before
                } else {
                    CHECKOUT_RETIREMENT_SCHEMA
                }
            || authoring::expiry(&self.created_at)? != self.expires_at
        {
            return Err(invalid());
        }
        self.evidence(
            digest::sha256(b"retirement-plan-validation"),
            self.settlement.clone(),
        )
        .validate(&self.original)?;
        match (&self.reader, &self.reason) {
            (Some(reader), Reason::ExpiredConfirmation) => {
                reader.validate(&self.original)?;
                if reader.context.local_identity != self.local_identity
                    || self.settlement.as_ref().ok_or_else(invalid)?["authorization_revision"]
                        != reader.observation["capabilities"]["authorization_revision"]
                {
                    return Err(invalid());
                }
            }
            (None, Reason::UnknownRequest) => (),
            _ => return Err(invalid()),
        }
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        if canonical::bytes(&value)?.len() as u64 > LIMIT {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }
}

fn reserve_source(connection: &Connection, source: &Record) -> Result<()> {
    request_open(connection, request_id(&source.plan)?)?;
    if !matches!(source.state.as_str(), "applying" | "interrupted") {
        return Err(invalid());
    }
    match &source.plan.change {
        Change::Request { .. } => {
            if connection.query_row("SELECT EXISTS(SELECT 1 FROM native_checkout_reservation WHERE request_operation_id=?)",
                [&source.plan.operation_id], |r| r.get::<_,bool>(0)).map_err(database)? { return Err(invalid()); }
        }
        Change::Confirm { request_operation_id, .. } => {
            let physical = source.plan.snapshot().physical_root()?;
            let valid: bool = connection.query_row(
                "SELECT EXISTS(SELECT 1 FROM native_checkout_reservation WHERE request_operation_id=? AND local_project_id=? AND root_device=? AND root_inode=? AND confirmation_operation_id=? AND binding_operation_id IS NULL AND context_id IS NULL)",
                params![request_operation_id,source.plan.snapshot().project_id()?,physical[0],physical[1],source.plan.operation_id], |r| r.get(0)).map_err(database)?;
            let binding: bool = connection.query_row("SELECT EXISTS(SELECT 1 FROM project_link WHERE local_project_id=? AND state!='unlinked')",
                [source.plan.snapshot().project_id()?], |r| r.get(0)).map_err(database)?;
            if !valid || binding { return Err(invalid()); }
        }
        Change::Adopt { .. } => return Err(invalid()),
    }
    Ok(())
}

fn unknown(failure: Failure) -> Failure {
    if matches!(failure.kind, ErrorKind::NotFound) {
        Failure::new(
            ErrorKind::Unavailable,
            "the original confirmation settlement remains unknown; retain its reservation",
        )
    } else {
        failure
    }
}

pub fn plan(root: &Path, source_id: &str, context: Option<&str>, at: &str) -> Result<Plan> {
    let (owner, source) = workflow::load(root, source_id)?;
    let before = {
        let store = owner.planning()?;
        reserve_source(&store.connection, &source)?;
        store.version()?
    };
    let (reason, reader, settlement) = match &source.plan.change {
        Change::Request { .. } => {
            if context.is_some() {
                return Err(Failure::input(
                    "local request retirement does not select a remote reader",
                ));
            }
            (Reason::UnknownRequest, None, None)
        }
        Change::Confirm { server_plan, .. } => {
            let selected = contexts::resolve(
                root,
                Some(context.unwrap_or(&source.plan.snapshot().context.context_id)),
            )?;
            workflow::reader_matches(&selected, source.plan.snapshot())?;
            selected.require_current_native_identity(&owner)?;
            let observed = corporate::observe(
                root,
                Some(&selected.context_id),
                corporate::Request::LinkSettlement {
                    plan_id: server_plan.plan_id.clone(),
                },
            )
            .map_err(unknown)?;
            let observed = &observed["observation"];
            let reader = Reader {
                context: selected,
                account: serde_json::from_value(observed["account"].clone())
                    .map_err(|_| invalid())?,
                organization: observed["organization"].clone(),
                observation: observed["observation"].clone(),
            };
            reader.validate(&source.plan)?;
            if observed["context"]
                != serde_json::to_value(&reader.context).map_err(|_| invalid())?
            {
                return Err(invalid());
            }
            expired(&observed["data"], &source.plan)?;
            (
                Reason::ExpiredConfirmation,
                Some(reader),
                Some(observed["data"].clone()),
            )
        }
        Change::Adopt { .. } => return Err(invalid()),
    };
    let plan = Plan {
        schema_version: if crate::store::has_checkout_unlinks(before) {
            2
        } else {
            1
        },
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        state_parent: identity::root(root)?.0,
        root_identity: identity::root(root)?.1,
        local_identity: owner.clone(),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        registry_schema_before: before,
        registry_schema_after: if crate::store::has_checkout_unlinks(before) {
            before
        } else {
            CHECKOUT_RETIREMENT_SCHEMA
        },
        source: source.checkpoint()?,
        original: Box::new(source.plan),
        reason,
        reader,
        settlement,
    };
    plan.digest()?;
    let store = owner.planning()?;
    let current = Record::load(&store.connection, source_id)?.ok_or_else(invalid)?;
    if current.checkpoint()? != plan.source || store.version()? != before {
        return Err(invalid());
    }
    reserve_source(&store.connection, &current)?;
    Ok(plan)
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let value = canonical::parse(&files::read(path, LIMIT)?)?;
    let plan: Plan = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    if plan.digest()? != digest::canonical("ai-stp:plan:v1", &value)? {
        return Err(invalid());
    }
    Ok(plan)
}

fn receipt(connection: &Connection, plan: &Plan, hash: &str) -> Result<Option<Value>> {
    let row: Option<(String,String,String,String)> = connection.query_row(
        "SELECT kind,state,coalesce(detail,''),coalesce(finished_at,'') FROM operation WHERE operation_id=?",
        [&plan.operation_id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).optional().map_err(database)?;
    let Some((kind, state, digest, at)) = row else {
        return Ok(None);
    };
    if kind != KIND
        || state != "completed"
        || digest != hash
        || !passport::timestamp(&at)
        || at < plan.created_at
        || at >= plan.expires_at
    {
        return Err(invalid());
    }
    let mut query = connection.prepare("SELECT sequence,at,state_before,state_after,result,CASE WHEN length(CAST(evidence AS BLOB))<=262144 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? ORDER BY sequence LIMIT 2").map_err(database)?;
    let rows = query
        .query_map([&plan.operation_id], |r| {
            Ok((
                r.get::<_, i64>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, String>(3)?,
                r.get::<_, String>(4)?,
                r.get::<_, String>(5)?,
            ))
        })
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    let [row] = rows.as_slice() else {
        return Err(invalid());
    };
    let value = canonical::parse(row.5.as_bytes())?;
    if row.0 != 1
        || row.1 != at
        || row.2 != "planned"
        || row.3 != "completed"
        || row.4 != "completed"
        || value["plan"] != serde_json::to_value(plan).map_err(|_| invalid())?
    {
        return Err(invalid());
    }
    let evidence: Evidence =
        serde_json::from_value(value["effect"].clone()).map_err(|_| invalid())?;
    evidence.validate(&plan.original)?;
    if canonical::bytes(&value)? != canonical::bytes(&json!({"plan":plan,"effect":evidence}))? {
        return Err(invalid());
    }
    if evidence.operation_id != plan.operation_id
        || evidence.plan_digest != hash
        || evidence.source != plan.source
        || evidence.reason != plan.reason
        || evidence.reader != plan.reader.as_ref().map(|r| r.account.clone())
    {
        return Err(invalid());
    }
    let source = Record::load(connection, &plan.source.operation_id)?.ok_or_else(invalid)?;
    if source.state != "retired"
        || source.output()?["observed_at"] != at
        || source.plan.digest()? != plan.source.plan_digest
        || !matches!(&source.effect, Some(Effect::Retired { retirement }) if **retirement == evidence)
    {
        return Err(invalid());
    }
    let bound: bool = connection.query_row("SELECT EXISTS(SELECT 1 FROM native_checkout_retirement WHERE source_operation_id=? AND request_operation_id=? AND retirement_operation_id=?)",
        params![plan.source.operation_id,request_id(&plan.original)?,plan.operation_id], |r| r.get(0)).map_err(database)?;
    if !bound {
        return Err(invalid());
    }
    Ok(Some(output(plan, hash, &evidence, &at)))
}

fn output(plan: &Plan, hash: &str, evidence: &Evidence, at: &str) -> Value {
    json!({"schema_version":1,"operation_id":plan.operation_id,"plan_digest":hash,"state":"completed",
        "source_operation_id":plan.source.operation_id,"reason":evidence.reason,"completed_at":at,
        "remote_outcome":if evidence.reason==Reason::UnknownRequest {"unknown"}else{"expired_without_link"},
        "reservation_released":evidence.reason==Reason::ExpiredConfirmation,
        "online_verified":false,"installation_authority":false})
}

fn commit(
    t: &Transaction<'_>,
    plan: &Plan,
    hash: &str,
    settlement: Option<Value>,
    at: &str,
) -> Result<Value> {
    if let Some(known) = receipt(t, plan, hash)? {
        return Ok(known);
    }
    let mut source = Record::load(t, &plan.source.operation_id)?.ok_or_else(invalid)?;
    if source.checkpoint()? != plan.source {
        return Err(invalid());
    }
    reserve_source(t, &source)?;
    let evidence = plan.evidence(hash.into(), settlement);
    evidence.validate(&source.plan)?;
    t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'completed',?,?,?)",
        params![plan.operation_id,KIND,at,at,hash]).map_err(database)?;
    let bytes = canonical::bytes(&json!({"plan":plan,"effect":evidence}))?;
    if bytes.len() as u64 > LIMIT {
        return Err(invalid());
    }
    let text = String::from_utf8(bytes).map_err(|_| invalid())?;
    t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,1,?,'planned','completed','completed',?)",
        params![plan.operation_id,at,text]).map_err(database)?;
    source.save(
        t,
        Effect::Retired {
            retirement: Box::new(evidence),
        },
        at,
    )?;
    t.execute("INSERT INTO native_checkout_retirement(source_operation_id,request_operation_id,retirement_operation_id) VALUES (?,?,?)",
        params![plan.source.operation_id,request_id(&plan.original)?,plan.operation_id]).map_err(database)?;
    if plan.reason == Reason::ExpiredConfirmation {
        let changed = t.execute("DELETE FROM native_checkout_reservation WHERE confirmation_operation_id=? AND binding_operation_id IS NULL AND context_id IS NULL",
            [&plan.source.operation_id]).map_err(database)?;
        if changed != 1 {
            return Err(invalid());
        }
    }
    receipt(t, plan, hash)?.ok_or_else(invalid)
}

pub fn apply(root: &Path, plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    if plan.digest()? != expected || !passport::timestamp(at) || at < plan.created_at.as_str() {
        return Err(invalid());
    }
    let owner = runtime::owner(root)?;
    workflow::owned(root, &owner, &plan.original)?;
    if identity::root(root)? != (plan.state_parent.clone(), plan.root_identity.clone()) {
        return Err(invalid());
    }
    {
        let store = owner.planning()?;
        if let Some(known) = receipt(&store.connection, plan, expected)? {
            return Ok(known);
        }
    }
    if at >= plan.expires_at.as_str() || *owner != plan.local_identity {
        return Err(invalid());
    }
    let mut access = if let Some(reader) = &plan.reader {
        if contexts::resolve(root, Some(&reader.context.context_id))? != reader.context {
            return Err(invalid());
        }
        let access = Access::for_binding(root, &reader.account, false)?;
        if *access.binding() != reader.account {
            return Err(invalid());
        }
        Some(access)
    } else {
        None
    };
    let settlement = if let Some(access) = access.as_mut() {
        let reader = plan.reader.as_ref().ok_or_else(invalid)?;
        let organization = plan.original.snapshot().organization_id()?;
        let (current, observation) = contexts::remote(access, Some(organization))?;
        if corporate::authority(&current, &observation)
            != corporate::authority(&reader.organization, &reader.observation)
        {
            return Err(invalid());
        }
        let Change::Confirm { server_plan, .. } = &plan.original.change else {
            return Err(invalid());
        };
        let request = corporate::Request::LinkSettlement {
            plan_id: server_plan.plan_id.clone(),
        };
        let fresh = request.project(
            &access.corporate(&request, organization).map_err(unknown)?,
            organization,
            &reader.account.account_id,
        )?;
        expired(&fresh, &plan.original)?;
        let reviewed = plan.settlement.as_ref().ok_or_else(invalid)?;
        for field in ["plan", "state", "link", "authorization_revision"] {
            if reviewed[field] != fresh[field] {
                return Err(invalid());
            }
        }
        let (current, observation) = contexts::remote(access, Some(organization))?;
        if corporate::authority(&current, &observation)
            != corporate::authority(&reader.organization, &reader.observation)
            || fresh["authorization_revision"]
                != observation["capabilities"]["authorization_revision"]
        {
            return Err(invalid());
        }
        reader.context.bind()?.revalidate()?;
        access.revalidate()?;
        Some(fresh)
    } else {
        None
    };
    let mut store = owner.open(false)?;
    if store.version()? != plan.registry_schema_before {
        return Err(invalid());
    }
    // Access (when required) remains held before Store; no HTTP inside this transaction.
    store.checkout_retirement_transaction(|t| commit(t, plan, expected, settlement, at))
}
