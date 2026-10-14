//! A command's durable progress surrounds its existing outbox/page transactions.

use super::{ledger::Scope, runtime::Plan};
use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    passport,
    store::{database, journal},
};
use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

const KIND: &str = "sync.run";

fn invalid() -> Failure {
    Failure::precondition("the retained sync operation does not match its exact plan and progress")
}
fn encode(value: &impl Serialize) -> Result<String> {
    let bytes = canonical::bytes(&serde_json::to_value(value).map_err(|_| invalid())?)?;
    if bytes.len() > 16 * 1024 * 1024 {
        return Err(invalid());
    }
    String::from_utf8(bytes).map_err(|_| invalid())
}

pub(super) fn frontier(
    connection: &Connection,
    scope: &Scope,
    entity: Option<&str>,
) -> Result<String> {
    scope.inspect(connection)?;
    let mut query=connection.prepare("SELECT state,count(*),max(rowid) FROM sync_event WHERE account_id=? AND (? IS NULL OR entity_id=?) GROUP BY state ORDER BY state").map_err(database)?;
    let states = query
        .query_map(params![scope.account(), entity, entity], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, i64>(1)?,
                r.get::<_, i64>(2)?,
            ))
        })
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if states.iter().any(|(s, _, _)| {
        !matches!(
            s.as_str(),
            "accepted" | "pending" | "conflict" | "rejected" | "superseded" | "failed"
        )
    }) {
        return Err(invalid());
    }
    let mut query=connection.prepare("SELECT entity_id,remote_revision_id FROM sync_remote_head WHERE account_id=? AND (? IS NULL OR entity_id=?) ORDER BY entity_id LIMIT 16385").map_err(database)?;
    let heads = query
        .query_map(params![scope.account(), entity, entity], |r| {
            Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?))
        })
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if heads.len() > 16384 {
        return Err(invalid());
    }
    let cursor: Option<Option<String>> = connection
        .query_row(
            "SELECT cursor FROM sync_cursor WHERE account_id=?",
            [scope.account()],
            |r| r.get(0),
        )
        .optional()
        .map_err(database)?;
    let pending:i64=connection.query_row("SELECT count(*) FROM sync_pending_version WHERE account_id=? AND (? IS NULL OR stable_id=?)",params![scope.account(),entity,entity],|r|r.get(0)).map_err(database)?;
    let skipped: i64 = connection
        .query_row(
            "SELECT count(*) FROM sync_abandoned_event WHERE account_id=?",
            [scope.account()],
            |r| r.get(0),
        )
        .map_err(database)?;
    digest::canonical(
        "ai-stp:plan:v1",
        &json!({"states":states,"heads":heads,"cursor":cursor,"pending_versions":pending,"abandoned_events":skipped}),
    )
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Progress {
    plan_digest: String,
    frontier: String,
    result: Option<Value>,
    result_digest: Option<String>,
}

pub(super) struct Run {
    id: String,
    hash: String,
    entity: Option<String>,
    frontier: String,
    sequence: i64,
    pub result: Option<Value>,
    completed_at: Option<String>,
}

impl Run {
    pub(super) fn admitted(connection: &Connection, id: &str) -> Result<Plan> {
        let bytes: String = connection.query_row(
            "SELECT CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? AND sequence=1",
            [id], |r| r.get(0),
        ).map_err(database)?;
        let plan: Plan =
            serde_json::from_value(canonical::parse(bytes.as_bytes())?).map_err(|_| invalid())?;
        if plan.operation_id != id {
            return Err(invalid());
        }
        plan.digest()?;
        Ok(plan)
    }

    pub fn load(connection: &Connection, plan: &Plan) -> Result<Option<Self>> {
        let hash = plan.digest()?;
        let Some(state) = journal::state(connection, &plan.operation_id, KIND, &hash)? else {
            return Ok(None);
        };
        if !matches!(state.as_str(), "applying" | "completed") {
            return Err(invalid());
        }
        let (started, finished): (String, Option<String>) = connection
            .query_row(
                "SELECT started_at,finished_at FROM operation WHERE operation_id=?",
                [&plan.operation_id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .map_err(database)?;
        let admission:String=connection.query_row("SELECT CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? AND sequence=1 AND state_before='planned' AND state_after='applying' AND result='admitted' AND at=?",params![plan.operation_id,started],|r|r.get(0)).map_err(database)?;
        let admitted: Plan = serde_json::from_value(canonical::parse(admission.as_bytes())?)
            .map_err(|_| invalid())?;
        if admitted.digest()? != hash
            || !passport::timestamp(&started)
            || started < plan.created_at
            || started > plan.expires_at
        {
            return Err(invalid());
        }
        let (sequence,at,before,after,result,evidence):(i64,String,String,String,String,String)=connection.query_row("SELECT sequence,at,state_before,state_after,result,CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? ORDER BY sequence DESC LIMIT 1",[&plan.operation_id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?))).map_err(database)?;
        if !passport::timestamp(&at)
            || at < started
            || after != state
            || (sequence > 1
                && (before != "applying"
                    || result
                        != if state == "completed" {
                            "completed"
                        } else {
                            "progress"
                        }))
        {
            return Err(invalid());
        }
        let progress = if sequence == 1 {
            Progress {
                plan_digest: hash.clone(),
                frontier: plan.frontier.clone(),
                result: None,
                result_digest: None,
            }
        } else {
            serde_json::from_value(canonical::parse(evidence.as_bytes())?).map_err(|_| invalid())?
        };
        let actual = progress
            .result
            .as_ref()
            .map(|r| digest::canonical("ai-stp:plan:v1", &json!({"plan_digest":hash,"result":r})))
            .transpose()?;
        if progress.plan_digest != hash
            || actual != progress.result_digest
            || (state == "completed") != progress.result.is_some()
            || (state == "completed" && finished.as_deref() != Some(&at))
            || (state == "applying" && finished.is_some())
        {
            return Err(invalid());
        }
        Ok(Some(Self {
            id: plan.operation_id.clone(),
            hash,
            entity: plan.entity(),
            frontier: progress.frontier,
            sequence,
            result: progress.result,
            completed_at: finished,
        }))
    }

    pub fn prepare(
        connection: &Connection,
        plan: &Plan,
        scope: &Scope,
        at: &str,
    ) -> Result<Option<Self>> {
        if let Some(run) = Self::load(connection, plan)? {
            run.check(connection, scope)?;
            return Ok(Some(run));
        }
        if !passport::timestamp(at)
            || at < plan.created_at.as_str()
            || at > plan.expires_at.as_str()
        {
            return Err(invalid());
        }
        if frontier(connection, scope, plan.entity().as_deref())? != plan.frontier {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "the private sync position changed after planning",
            ));
        }
        Ok(None)
    }

    pub fn admit(t: &Transaction<'_>, plan: &Plan, scope: &Scope, at: &str) -> Result<Self> {
        if let Some(run) = Self::prepare(t, plan, scope, at)? {
            return Ok(run);
        }
        let hash = plan.digest()?;
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'applying',?,NULL,?)",params![plan.operation_id,KIND,at,hash]).map_err(database)?;
        t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,1,?,'planned','applying','admitted',?)",params![plan.operation_id,at,encode(plan)?]).map_err(database)?;
        Ok(Self {
            id: plan.operation_id.clone(),
            hash,
            entity: plan.entity(),
            frontier: plan.frontier.clone(),
            sequence: 1,
            result: None,
            completed_at: None,
        })
    }

    pub fn check(&self, connection: &Connection, scope: &Scope) -> Result<()> {
        if self.result.is_some()
            || frontier(connection, scope, self.entity.as_deref())? != self.frontier
        {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "the private sync operation changed; create a new plan while preserving its retained requests",
            ));
        }
        Ok(())
    }

    /// Call inside the same transaction as retention, receipt, or page mutation.
    pub fn save(
        &mut self,
        t: &Transaction<'_>,
        scope: &Scope,
        result: Option<Value>,
        at: &str,
    ) -> Result<()> {
        if !passport::timestamp(at) || self.result.is_some() {
            return Err(invalid());
        }
        let next = self.sequence.checked_add(1).ok_or_else(invalid)?;
        let current = frontier(t, scope, self.entity.as_deref())?;
        let finished = result.is_some();
        let progress = Progress {
            plan_digest: self.hash.clone(),
            frontier: current.clone(),
            result_digest: result
                .as_ref()
                .map(|r| {
                    digest::canonical(
                        "ai-stp:plan:v1",
                        &json!({"plan_digest":self.hash,"result":r}),
                    )
                })
                .transpose()?,
            result: result.clone(),
        };
        let changed=t.execute("UPDATE operation SET state=?,finished_at=? WHERE operation_id=? AND kind=? AND detail=? AND state='applying'",
            params![if finished {"completed"} else {"applying"},if finished {Some(at)} else {None},self.id,KIND,self.hash]).map_err(database)?;
        if changed != 1 {
            return Err(invalid());
        }
        t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?, ?,?,'applying',?,?,?)",
            params![self.id,next,at,if finished {"completed"} else {"applying"},if finished {"completed"} else {"progress"},encode(&progress)?]).map_err(database)?;
        self.sequence = next;
        self.frontier = current;
        self.result = result;
        self.completed_at = finished.then(|| at.into());
        Ok(())
    }

    pub fn output(&self, plan: &Plan) -> Result<Value> {
        let result = self.result.as_ref().ok_or_else(invalid)?;
        Ok(
            json!({"schema_version":1,"operation_id":self.id,"plan_digest":self.hash,
            "account_id":plan.account.account_id,"api_origin":plan.account.origin,
            "completed_at":self.completed_at,"result":result}),
        )
    }
}
