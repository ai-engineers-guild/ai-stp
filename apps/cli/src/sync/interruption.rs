//! Key replacement stops exact command attempts without settling their outbox.

use super::{ledger::Scope, run::Run};
use crate::{
    account, canonical, digest,
    error::{Failure, Result},
    passport,
    store::database,
};
use rusqlite::{Connection, Transaction};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Checkpoint {
    pub operation_id: String,
    pub plan_digest: String,
    pub progress_digest: String,
}

fn invalid() -> Failure {
    Failure::precondition(
        "the interrupted sync commands differ from the exact device recovery plan",
    )
}

impl Checkpoint {
    pub(crate) fn validate(&self) -> Result<()> {
        let hash = |v: &str| {
            v.strip_prefix("sha256:").is_some_and(|v| {
                v.len() == 64
                    && v.bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            })
        };
        if !passport::stable_id(&self.operation_id, "operation")
            || !hash(&self.plan_digest)
            || !hash(&self.progress_digest)
        {
            return Err(invalid());
        }
        Ok(())
    }

    fn read(connection: &Connection, id: &str) -> Result<Self> {
        let plan = Run::admitted(connection, id)?;
        let run = Run::load(connection, &plan)?.ok_or_else(invalid)?;
        if run.result.is_some() {
            return Err(invalid());
        }
        let (sequence, bytes): (i64, String) = connection.query_row(
            "SELECT sequence,CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? ORDER BY sequence DESC LIMIT 1",
            [id], |r| Ok((r.get(0)?,r.get(1)?)),
        ).map_err(database)?;
        Ok(Self {
            operation_id: id.into(),
            plan_digest: plan.digest()?,
            progress_digest: digest::canonical(
                "ai-stp:plan:v1",
                &json!({"sequence":sequence,"evidence":canonical::parse(bytes.as_bytes())?}),
            )?,
        })
    }

    fn outcome(&self, recovery: &account::Plan) -> Result<Value> {
        let intent = recovery.recovery.as_ref().ok_or_else(invalid)?;
        Ok(
            json!({"schema_version":1,"state":"interrupted","reason":"device_replacement_admitted",
            "account_recovery_operation_id":recovery.operation_id,"account_recovery_plan_digest":recovery.digest()?,
            "replacement_device_id":intent.device_id,"checkpoint":self,"remote_outcome":"unknown"}),
        )
    }
}

pub(crate) fn capture(
    connection: &Connection,
    original: &account::Plan,
    account_id: Option<&str>,
) -> Result<Vec<Checkpoint>> {
    let mut query = connection.prepare("SELECT operation_id FROM operation WHERE kind='sync.run' AND finished_at IS NULL ORDER BY operation_id LIMIT 129").map_err(database)?;
    let ids = query
        .query_map([], |r| r.get::<_, String>(0))
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if ids.len() > 128 {
        return Err(invalid());
    }
    ids.iter()
        .map(|id| {
            let plan = Run::admitted(connection, id)?;
            let binding = &plan.account;
            if plan.state_parent != original.root
                || binding.root_identity != original.root_identity
                || binding.device_id != original.identity.device_id
                || binding.public_key != original.public_key
                || binding.credential_store != original.credential_store
                || binding.origin != original.origin
                || Some(binding.account_id.as_str()) != account_id
            {
                return Err(invalid());
            }
            Checkpoint::read(connection, id)
        })
        .collect()
}

pub(crate) fn pending_enrollment(connection: &Connection, enrollment: &str) -> Result<bool> {
    let mut query=connection.prepare("SELECT operation_id FROM operation WHERE kind='sync.run' AND finished_at IS NULL ORDER BY operation_id LIMIT 129").map_err(database)?;
    let ids = query
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if ids.len() > 128 {
        return Err(invalid());
    }
    for id in ids {
        let plan = Run::admitted(connection, &id)?;
        if plan
            .account
            .connection
            .as_ref()
            .is_some_and(|value| value.connection_id == enrollment)
        {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Replays only the exact interruptions already admitted by this recovery.
pub(crate) fn validate(connection: &Connection, recovery: &account::Plan) -> Result<()> {
    let intent = recovery.recovery.as_ref().ok_or_else(invalid)?;
    let current = capture(connection, recovery, intent.account_id.as_deref())?;
    if current.iter().any(|c| !intent.interrupted_sync.contains(c)) {
        return Err(invalid());
    }
    for checkpoint in &intent.interrupted_sync {
        if current.contains(checkpoint) {
            continue;
        }
        let plan = Run::admitted(connection, &checkpoint.operation_id)?;
        let run = Run::load(connection, &plan)?.ok_or_else(invalid)?;
        if plan.digest()? != checkpoint.plan_digest
            || run.result != Some(checkpoint.outcome(recovery)?)
        {
            return Err(invalid());
        }
    }
    Ok(())
}

pub(crate) fn apply(t: &Transaction<'_>, recovery: &account::Plan, at: &str) -> Result<()> {
    validate(t, recovery)?;
    for checkpoint in &recovery
        .recovery
        .as_ref()
        .ok_or_else(invalid)?
        .interrupted_sync
    {
        let plan = Run::admitted(t, &checkpoint.operation_id)?;
        let mut run = Run::load(t, &plan)?.ok_or_else(invalid)?;
        if run.result.is_none() {
            let scope = Scope::new(&plan.account.account_id, &plan.account.origin)?;
            run.save(t, &scope, Some(checkpoint.outcome(recovery)?), at)?;
        }
    }
    Ok(())
}
