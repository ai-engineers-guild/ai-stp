//! Close only local pending intent; an active binding and its reservation remain.

use std::path::{Path, PathBuf};

use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    Binding, Checkpoint, Context, contexts, corporate, invalid,
    journal::Record,
    model::{Change, Effect, LIMIT, ServerPlan},
    workflow,
};
use crate::{
    authoring, canonical, digest,
    error::Result,
    files, passport,
    store::{database, has_checkout_unlinks, journal::checkout_unlink_epoch},
};

const KIND: &str = "corporate.project_unlink.retire";

#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "reason", rename_all = "snake_case", deny_unknown_fields)]
enum Decision {
    UnknownRequest,
    ExpiredConfirmation {
        context: Box<Context>,
        reader: Box<Binding>,
        settlement: Value,
    },
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub operation_id: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    state_parent: PathBuf,
    pub created_at: String,
    pub expires_at: String,
    pub registry_schema_before: u32,
    pub source: Checkpoint,
    decision: Decision,
}

impl Plan {
    pub fn state_parent(&self) -> &Path {
        &self.state_parent
    }

    pub fn digest(&self) -> Result<String> {
        self.source.validate()?;
        if self.schema_version != 1
            || !has_checkout_unlinks(self.registry_schema_before)
            || !passport::stable_id(&self.operation_id, "operation")
            || self.operation_id == self.source.operation_id
            || !self.state_parent.is_absolute()
            || self.expires_at != authoring::expiry(&self.created_at)?
        {
            return Err(invalid());
        }
        if let Decision::ExpiredConfirmation {
            context, reader, ..
        } = &self.decision
        {
            context.digest()?;
            reader.validate()?;
            if context.root != self.state_parent {
                return Err(invalid());
            }
        }
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        if canonical::bytes(&value)?.len() as u64 > LIMIT {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }

    pub(super) fn validate_source(&self, original: &super::Plan) -> Result<()> {
        self.digest()?;
        if self.source.operation_id != original.operation_id
            || self.source.plan_digest != original.digest()?
            || self.state_parent != original.state_parent()
        {
            return Err(invalid());
        }
        match (&self.decision, &original.change) {
            (Decision::UnknownRequest, Change::Request { .. }) => Ok(()),
            (
                Decision::ExpiredConfirmation {
                    context,
                    reader,
                    settlement,
                },
                Change::Confirm { server_plan, .. },
            ) => {
                workflow::reader_matches(context, original.snapshot())?;
                reader_matches(reader, original)?;
                validate_settlement(settlement, server_plan, original)
            }
            _ => Err(invalid()),
        }
    }

    pub(super) fn remote_outcome(&self) -> &'static str {
        match self.decision {
            Decision::UnknownRequest => "unknown",
            Decision::ExpiredConfirmation { .. } => "expired_unapplied",
        }
    }
}

fn reader_matches(reader: &Binding, original: &super::Plan) -> Result<()> {
    reader.validate()?;
    let old = &original.snapshot().account;
    if reader.origin != old.origin
        || reader.account_id != old.account_id
        || reader.root_identity != old.root_identity
    {
        return Err(invalid());
    }
    Ok(())
}

fn validate_settlement(value: &Value, server: &ServerPlan, original: &super::Plan) -> Result<()> {
    let request = corporate::Request::UnlinkSettlement {
        plan_id: server.plan_id.clone(),
    };
    if request.project(
        value,
        original.snapshot().organization_id()?,
        &original.snapshot().account.account_id,
    )? != *value
        || &ServerPlan::read(&value["plan"], original.snapshot())? != server
        || value["observed_at"]
            .as_str()
            .ok_or_else(invalid)?
            .parse::<jiff::Timestamp>()
            .map_err(|_| invalid())?
            < server
                .expires_at
                .parse::<jiff::Timestamp>()
                .map_err(|_| invalid())?
    {
        return Err(invalid());
    }
    if value["state"] != "expired" || !value["link"].is_null() {
        return Err(crate::error::Failure::precondition(
            "observe an exact expired and unapplied unlink plan before retiring this pending confirmation",
        ));
    }
    Ok(())
}

fn observe(
    root: &Path,
    source: &Record,
    context: Option<&str>,
) -> Result<(Context, Binding, Value)> {
    let Change::Confirm { server_plan, .. } = &source.plan.change else {
        return Err(invalid());
    };
    let selected = contexts::resolve(
        root,
        Some(context.unwrap_or(&source.plan.snapshot().context.context_id)),
    )?;
    workflow::reader_matches(&selected, source.plan.snapshot())?;
    let observed = corporate::observe(
        root,
        Some(&selected.context_id),
        corporate::Request::UnlinkSettlement {
            plan_id: server_plan.plan_id.clone(),
        },
    )?;
    let observed = &observed["observation"];
    let reader: Binding =
        serde_json::from_value(observed["account"].clone()).map_err(|_| invalid())?;
    if observed["context"] != serde_json::to_value(&selected).map_err(|_| invalid())? {
        return Err(invalid());
    }
    reader_matches(&reader, &source.plan)?;
    validate_settlement(&observed["data"], server_plan, &source.plan)?;
    Ok((selected, reader, observed["data"].clone()))
}

fn unknown(source: &Record) -> Result<()> {
    if !matches!(source.state.as_str(), "applying" | "interrupted") {
        return Err(invalid());
    }
    Ok(())
}

pub fn plan(root: &Path, id: &str, context: Option<&str>, at: &str) -> Result<Plan> {
    let (owner, source) = workflow::load(root, id)?;
    unknown(&source)?;
    let decision = match &source.plan.change {
        Change::Request { .. } => {
            if context.is_some() {
                return Err(invalid());
            }
            Decision::UnknownRequest
        }
        Change::Confirm { .. } => {
            let (context, reader, settlement) = observe(root, &source, context)?;
            Decision::ExpiredConfirmation {
                context: Box::new(context),
                reader: Box::new(reader),
                settlement,
            }
        }
    };
    let plan = Plan {
        schema_version: 1,
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        state_parent: source.plan.state_parent().into(),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        registry_schema_before: owner.planning()?.version()?,
        source: source.checkpoint()?,
        decision,
    };
    plan.validate_source(&source.plan)?;
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

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    plan: Plan,
    plan_digest: String,
    completed_at: String,
}

struct ReceiptRow {
    kind: String,
    state: String,
    started: String,
    finished: Option<String>,
    detail: Option<String>,
}

fn read_receipt(connection: &Connection, plan: &Plan) -> Result<Option<Receipt>> {
    let row:Option<ReceiptRow>=connection.query_row(
        "SELECT kind,state,started_at,finished_at,CASE WHEN length(CAST(detail AS BLOB))<=262144 THEN detail ELSE NULL END FROM operation WHERE operation_id=?",
        [&plan.operation_id],|row|Ok(ReceiptRow{kind:row.get(0)?,state:row.get(1)?,started:row.get(2)?,finished:row.get(3)?,detail:row.get(4)?})).optional().map_err(database)?;
    let Some(ReceiptRow {
        kind,
        state,
        started,
        finished,
        detail,
    }) = row
    else {
        return Ok(None);
    };
    let raw = canonical::parse(detail.as_ref().ok_or_else(invalid)?.as_bytes())?;
    let receipt: Receipt = serde_json::from_value(raw.clone()).map_err(|_| invalid())?;
    if kind != KIND
        || state != "verified"
        || receipt.plan_digest != plan.digest()?
        || receipt.plan.digest()? != plan.digest()?
        || canonical::bytes(&raw)?
            != canonical::bytes(&serde_json::to_value(&receipt).map_err(|_| invalid())?)?
        || !passport::timestamp(&started)
        || started < plan.created_at
        || started >= plan.expires_at
        || !passport::timestamp(&receipt.completed_at)
        || receipt.completed_at < started
        || finished.as_deref() != Some(receipt.completed_at.as_str())
    {
        return Err(invalid());
    }
    Ok(Some(receipt))
}

fn output(receipt: &Receipt) -> Result<Value> {
    Ok(
        json!({"schema_version":1,"operation_id":receipt.plan.operation_id,"plan_digest":receipt.plan_digest,"plan":receipt.plan,
        "retired_operation_id":receipt.plan.source.operation_id,"state":"verified","outcome":"local_intent_retired",
        "remote_outcome":receipt.plan.remote_outcome(),"local_binding_retired":false,"installation_authority":false}),
    )
}

fn settlement_coordinates(value: &Value) -> Value {
    json!([
        value["plan"],
        value["state"],
        value["link"],
        value["authorization_revision"]
    ])
}

fn checked_output(connection: &Connection, receipt: &Receipt) -> Result<Value> {
    let current =
        Record::load(connection, &receipt.plan.source.operation_id)?.ok_or_else(invalid)?;
    let Some(Effect::Retired { retirement }) = &current.effect else {
        return Err(invalid());
    };
    if retirement.digest()? != receipt.plan_digest {
        return Err(invalid());
    }
    output(receipt)
}

pub fn apply(root: &Path, plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    if plan.digest()? != expected || !passport::timestamp(at) || at < plan.created_at.as_str() {
        return Err(invalid());
    }
    let (owner, source) = workflow::load(root, &plan.source.operation_id)?;
    plan.validate_source(&source.plan)?;
    {
        let store = owner.planning()?;
        if let Some(receipt) = read_receipt(&store.connection, plan)? {
            return checked_output(&store.connection, &receipt);
        }
    }
    if at >= plan.expires_at.as_str() {
        return Err(invalid());
    }
    unknown(&source)?;
    if source.checkpoint()? != plan.source {
        return Err(invalid());
    }
    if let Decision::ExpiredConfirmation {
        context,
        reader,
        settlement,
    } = &plan.decision
    {
        let (fresh_context, fresh_reader, fresh) =
            observe(root, &source, Some(&context.context_id))?;
        if &fresh_context != context.as_ref()
            || &fresh_reader != reader.as_ref()
            || settlement_coordinates(&fresh) != settlement_coordinates(settlement)
        {
            return Err(invalid());
        }
    }
    let mut store = owner.open(false)?;
    if store.version()? != plan.registry_schema_before {
        return Err(invalid());
    }
    store.transaction(|transaction|{
        if !checkout_unlink_epoch(transaction)? {return Err(invalid());}
        if let Some(receipt)=read_receipt(transaction,plan)? {return checked_output(transaction,&receipt);}
        let mut current=Record::load(transaction,&plan.source.operation_id)?.ok_or_else(invalid)?;
        unknown(&current)?;
        if current.checkpoint()?!=plan.source {return Err(invalid());}
        let receipt=Receipt{plan:plan.clone(),plan_digest:expected.into(),completed_at:super::super::now_after(at)};
        let detail=canonical::bytes(&serde_json::to_value(&receipt).map_err(|_|invalid())?)?;
        if detail.len() as u64>LIMIT {return Err(invalid());}
        transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,KIND,at,receipt.completed_at,String::from_utf8(detail).map_err(|_|invalid())?]).map_err(database)?;
        current.save(transaction,Effect::Retired{retirement:Box::new(plan.clone())},&receipt.completed_at)?;
        output(&receipt)
    })
}
