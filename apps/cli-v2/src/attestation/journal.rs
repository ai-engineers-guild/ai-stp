//! Existing operation/event storage retains the signed bytes before export.

use super::{Plan, contract, invalid};
use crate::{canonical, error::Result, passport, store::database};
use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Saved {
    plan: Plan,
    record: Value,
}

pub(super) struct Receipt {
    pub plan: Plan,
    pub record: Value,
    pub completed: bool,
    cleanup_pending: bool,
}

impl Receipt {
    pub fn matches(&self, plan: &Plan) -> Result<()> {
        if self.plan.digest()? != plan.digest()? {
            return Err(invalid());
        }
        Ok(())
    }
    pub fn report(&self) -> Result<Value> {
        Ok(
            json!({"schema_version":1,"operation_id":self.plan.operation_id,
            "plan_digest":self.plan.digest()?,"attestation_digest":contract::hash(&self.record)?,
            "attestation":self.record,"state":if self.completed {"completed"} else {"signed"},
            "output":serde_json::to_value(&self.plan).map_err(|_|invalid())?["output"],
            "staging_cleanup_pending":self.cleanup_pending}),
        )
    }
}

pub(super) fn load(connection: &Connection, id: &str) -> Result<Option<Receipt>> {
    let operation: Option<(String,String,String,Option<String>,String)> = connection.query_row(
        "SELECT kind,state,started_at,finished_at,coalesce(detail,'') FROM operation WHERE operation_id=?",
        [id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?))).optional().map_err(database)?;
    let Some((kind, state, started, finished, hash)) = operation else {
        return Ok(None);
    };
    if kind != "attestation.sign"
        || !matches!(state.as_str(), "applying" | "completed")
        || !passport::timestamp(&started)
        || (state == "completed") != finished.is_some()
        || finished
            .as_deref()
            .is_some_and(|v| !passport::timestamp(v) || v < started.as_str())
    {
        return Err(invalid());
    }
    let data: String = connection.query_row(
        "SELECT CASE WHEN length(CAST(evidence AS BLOB))<=1048576 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? AND sequence=1 AND at=? AND state_before='planned' AND state_after='applying' AND result='signed'",
        params![id,started],|r|r.get(0)).map_err(database)?;
    let saved: Saved =
        serde_json::from_value(canonical::parse(data.as_bytes())?).map_err(|_| invalid())?;
    if saved.plan.operation_id != id
        || saved.plan.digest()? != hash
        || contract::payload(&saved.record)? != contract::payload(&saved.plan.record)?
    {
        return Err(invalid());
    }
    contract::verify(&saved.record, &saved.plan.account.public_key)?;
    let count: i64 = connection
        .query_row(
            "SELECT count(*) FROM operation_event WHERE operation_id=?",
            [id],
            |r| r.get(0),
        )
        .map_err(database)?;
    if count != if finished.is_some() { 2 } else { 1 } {
        return Err(invalid());
    }
    let mut cleanup_pending = false;
    if let Some(at) = finished {
        let pending: String = connection.query_row("SELECT evidence FROM operation_event WHERE operation_id=? AND sequence=2 AND at=? AND state_before='applying' AND state_after='completed' AND result='exported'",params![id,at],|r|r.get(0)).map_err(database)?;
        cleanup_pending = match pending.as_str() {
            "true" => true,
            "false" => false,
            _ => return Err(invalid()),
        };
    }
    Ok(Some(Receipt {
        plan: saved.plan,
        record: saved.record,
        completed: state == "completed",
        cleanup_pending,
    }))
}

pub(super) fn retain(t: &Transaction<'_>, plan: &Plan, record: Value, at: &str) -> Result<()> {
    let data = canonical::bytes(
        &serde_json::to_value(Saved {
            plan: plan.clone(),
            record,
        })
        .map_err(|_| invalid())?,
    )?;
    let data = String::from_utf8(data).map_err(|_| invalid())?;
    t.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?,'attestation.sign','applying',?,?)",params![plan.operation_id,at,plan.digest()?]).map_err(database)?;
    t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,1,?,'planned','applying','signed',?)",params![plan.operation_id,at,data]).map_err(database)?;
    Ok(())
}

pub(super) fn finish(t: &Transaction<'_>, plan: &Plan, at: &str, pending: bool) -> Result<()> {
    if !passport::timestamp(at) {
        return Err(invalid());
    }
    let changed=t.execute("UPDATE operation SET state='completed',finished_at=? WHERE operation_id=? AND kind='attestation.sign' AND state='applying' AND detail=? AND started_at<=?",params![at,plan.operation_id,plan.digest()?,at]).map_err(database)?;
    if changed != 1 {
        return Err(invalid());
    }
    t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,2,?,'applying','completed','exported',?)",params![plan.operation_id,at,if pending{"true"}else{"false"}]).map_err(database)?;
    Ok(())
}
