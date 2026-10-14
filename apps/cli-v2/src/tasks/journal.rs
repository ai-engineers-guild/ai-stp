//! Native task records in the existing registry, protected by its lifetime writer lock.

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::service::{Input, Plan};
use crate::{
    authoring::Identity,
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    passport,
    store::database,
    wire::Schema,
};

const FORMAT: &str = "ai-stp-native-task/1";
static VIEW: Schema = Schema::new(include_str!("../../../../schemas/v1/cli-task.schema.json"));

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Payload {
    format: String,
    pub identity: Identity,
    pub input: Input,
    pub plan: Option<Plan>,
    pub plan_digest: Option<String>,
}

#[derive(Clone)]
pub(super) struct Row {
    pub id: String,
    pub revision: i64,
    pub state: String,
    pub key: String,
    pub original: String,
    pub payload: Payload,
    pub outcome: Option<Value>,
    pub created: String,
    pub updated: String,
}

fn invalid() -> Failure {
    Failure::precondition("the retained task does not match the native task contract")
}

pub(super) fn encode(value: &impl Serialize) -> Result<String> {
    // Filesystem spellings in child plans must survive journal storage exactly.
    let bytes = serde_json_canonicalizer::to_vec(value).map_err(|_| invalid())?;
    if bytes.len() > 48 * 1024 * 1024 {
        return Err(invalid());
    }
    String::from_utf8(bytes).map_err(|_| invalid())
}

impl Row {
    pub fn new(input: impl Into<Input>, identity: Identity, key: &str, at: &str) -> Result<Self> {
        let input = input.into();
        let original = encode(&input.value()?)?;
        Ok(Self {
            id: format!("task_{}", ulid::Ulid::generate()),
            revision: 1,
            state: "planned".into(),
            key: key.into(),
            original,
            payload: Payload {
                format: FORMAT.into(),
                identity,
                input,
                plan: None,
                plan_digest: None,
            },
            outcome: None,
            created: at.into(),
            updated: at.into(),
        })
    }
    pub fn settled(&self) -> bool {
        matches!(self.state.as_str(), "completed" | "cancelled" | "failed")
    }
    pub fn children(&self) -> Vec<String> {
        self.payload.plan.iter().flat_map(Plan::children).collect()
    }
    pub fn questions(&self) -> Result<Vec<Value>> {
        if self.state == "blocked" {
            Ok(self.payload.input.question()?.into_iter().collect())
        } else {
            Ok(Vec::new())
        }
    }
    pub fn view(&self) -> Result<Value> {
        let mut view = json!({"schema_version":1,"task_id":self.id,"revision":self.revision,"intent":self.payload.input.intent(), "state":self.state,
            "goal_satisfied":self.state=="completed","questions":self.questions()?,"outcome":self.outcome,"child_operation_ids":self.children()});
        if let Some(handoff) = self.payload.plan.as_ref().and_then(Plan::handoff) {
            view["handoff"] = handoff;
        }
        VIEW.validate(&view)?;
        Ok(view)
    }
    pub fn advance(&mut self, state: &str, at: &str) -> Result<()> {
        self.revision = self.revision.checked_add(1).ok_or_else(invalid)?;
        self.state = state.into();
        self.updated = at.into();
        Ok(())
    }
    fn validate(&self) -> Result<()> {
        super::valid_key(&self.key)?;
        if self.payload.format != FORMAT
            || !passport::stable_id(&self.id, "task")
            || self.revision < 1
            || !passport::timestamp(&self.created)
            || !passport::timestamp(&self.updated)
        {
            return Err(invalid());
        }
        self.payload.identity.validate()?;
        Input::stored(self.payload.input.intent(), self.payload.input.value()?)?;
        if let Some(plan) = &self.payload.plan {
            plan.validate(&self.payload.input, &self.payload.identity)?;
            if self.payload.plan_digest.as_deref() != Some(plan.digest()?.as_str()) {
                return Err(invalid());
            }
        } else if self.payload.plan_digest.is_some() || self.state == "running" {
            return Err(invalid());
        }
        if self.state == "completed" {
            let plan = self.payload.plan.as_ref().ok_or_else(invalid)?;
            if self.outcome.as_ref() != Some(&plan.outcome()?) {
                return Err(invalid());
            }
        }
        if self.state != "completed" && self.outcome.is_some() {
            return Err(invalid());
        }
        self.view()?;
        Ok(())
    }
}

pub(super) fn load(connection: &Connection, id: &str) -> Result<Row> {
    if !passport::stable_id(id, "task") {
        return Err(Failure::input("task identity is invalid"));
    }
    let mut statement = connection
        .prepare(
            "SELECT * FROM agent_task WHERE task_id=?
         AND length(CAST(payload_json AS BLOB))<=50331648 AND length(CAST(original_request_json AS BLOB))<=16384
         AND length(CAST(coalesce(outcome_json,'') AS BLOB))<=16384 AND length(CAST(questions_json AS BLOB))<=16384
         AND length(CAST(child_operation_ids_json AS BLOB))<=4096 AND length(CAST(idempotency_key AS BLOB))<=128",
        )
        .map_err(database)?;
    let mut rows = statement.query([id]).map_err(database)?;
    let raw = rows.next().map_err(database)?.ok_or_else(|| {
        Failure::new(
            ErrorKind::NotFound,
            "the task is absent or exceeds native record bounds",
        )
    })?;
    let text = |name: &str| raw.get::<_, String>(name).map_err(database);
    let payload: Payload =
        serde_json::from_value(crate::wire::parse(text("payload_json")?.as_bytes())?)
            .map_err(|_| invalid())?;
    let outcome: Option<String> = raw.get("outcome_json").map_err(database)?;
    let value = Row {
        id: id.into(),
        revision: raw.get("revision").map_err(database)?,
        state: text("state")?,
        key: text("idempotency_key")?,
        original: text("original_request_json")?,
        payload,
        outcome: outcome
            .map(|v| canonical::parse(v.as_bytes()))
            .transpose()?,
        created: text("created_at")?,
        updated: text("updated_at")?,
    };
    value.validate()?;
    if text("intent")? != value.payload.input.intent()
        || text("account_id")? != value.payload.identity.account_id
        || text("precondition_digest")?
            != digest::canonical(
                "ai-stp:plan:v1",
                &serde_json::to_value(&value.payload).map_err(|_| invalid())?,
            )?
        || raw.get::<_, bool>("goal_satisfied").map_err(database)? != (value.state == "completed")
        || canonical::parse(text("questions_json")?.as_bytes())? != json!(value.questions()?)
        || canonical::parse(text("child_operation_ids_json")?.as_bytes())?
            != json!(value.children())
        || text("harness_id")? != value.payload.input.harness()
        || text("project_root")? != value.payload.input.project()
        || text("scope")? != value.payload.input.scope()
    {
        return Err(invalid());
    }
    Ok(value)
}

pub(super) fn key(connection: &Connection, key: &str) -> Result<Option<Row>> {
    let id: Option<String> = connection
        .query_row(
            "SELECT task_id FROM agent_task WHERE idempotency_key=?",
            [key],
            |row| row.get(0),
        )
        .optional()
        .map_err(database)?;
    id.map(|id| load(connection, &id)).transpose()
}

pub(super) fn save(t: &Transaction<'_>, row: &Row, previous: Option<i64>) -> Result<()> {
    row.validate()?;
    let payload = encode(&row.payload)?;
    let digest = digest::canonical(
        "ai-stp:plan:v1",
        &serde_json::to_value(&row.payload).map_err(|_| invalid())?,
    )?;
    let questions = encode(&row.questions()?)?;
    let children = encode(&row.children())?;
    let outcome = row.outcome.as_ref().map(encode).transpose()?;
    if let Some(previous) = previous {
        let changed=t.execute("UPDATE agent_task SET revision=?,state=?,goal_satisfied=?,payload_json=?,outcome_json=?,questions_json=?,child_operation_ids_json=?,updated_at=?,harness_id=?,precondition_digest=? WHERE task_id=? AND revision=?",
            params![row.revision,row.state,row.state=="completed",payload,outcome,questions,children,row.updated,row.payload.input.harness(),digest,row.id,previous]).map_err(database)?;
        if changed != 1 {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "the task revision changed",
            ));
        }
    } else {
        t.execute("INSERT INTO agent_task(task_id,revision,intent,state,goal_satisfied,idempotency_key,payload_json,outcome_json,questions_json,child_operation_ids_json,created_at,updated_at,harness_id,project_root,scope,account_id,precondition_digest,original_request_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            params![row.id,row.revision,row.payload.input.intent(),row.state,row.state=="completed",row.key,payload,outcome,questions,children,row.created,row.updated,row.payload.input.harness(),row.payload.input.project(),row.payload.input.scope(),row.payload.identity.account_id,digest,row.original]).map_err(database)?;
    }
    Ok(())
}

pub(super) fn unsettled(connection: &Connection) -> Result<Vec<Row>> {
    let mut query=connection.prepare("SELECT task_id FROM agent_task WHERE state IN ('planned','blocked','running') ORDER BY updated_at DESC,task_id LIMIT 1001").map_err(database)?;
    let ids = query
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if ids.len() > 1000 {
        return Err(Failure::precondition(
            "the unsettled task list exceeds 1000 records",
        ));
    }
    ids.iter().map(|id| load(connection, id)).collect()
}

/// Completed Python receipts remain readable after the in-place transfer.
/// Their opaque execution payload is never interpreted as a native continuation.
pub(super) fn legacy_view(connection: &Connection, id: &str) -> Result<Option<Value>> {
    if connection
        .query_row("PRAGMA user_version", [], |row| row.get::<_, u32>(0))
        .map_err(database)?
        != 54
    {
        return Ok(None);
    }
    let native: Option<Option<String>> = connection
        .query_row(
            "SELECT json_extract(payload_json,'$.format') FROM agent_task WHERE task_id=?",
            [id],
            |row| row.get(0),
        )
        .optional()
        .map_err(database)?;
    if native.is_none() || native.flatten().as_deref() == Some(FORMAT) {
        return Ok(None);
    }
    let (revision,intent,state,goal,outcome,children):(i64,String,String,bool,Option<String>,String)=connection.query_row(
        "SELECT revision,intent,state,goal_satisfied,outcome_json,child_operation_ids_json FROM agent_task WHERE task_id=?",[id],|row|Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?,row.get(4)?,row.get(5)?))).map_err(database)?;
    if !matches!(state.as_str(), "completed" | "failed" | "cancelled")
        || outcome.as_ref().is_some_and(|v| v.len() > 1024 * 1024)
        || children.len() > 65536
    {
        return Err(invalid());
    }
    let outcome = outcome
        .map(|body| canonical::parse(body.as_bytes()))
        .transpose()?;
    let children = canonical::parse(children.as_bytes())?;
    let view = json!({"schema_version":1,"task_id":id,"revision":revision,"intent":intent,"state":state,"goal_satisfied":goal,"questions":[],"outcome":outcome,"child_operation_ids":children,"legacy_read_only":true});
    VIEW.validate(&view)?;
    Ok(Some(view))
}
