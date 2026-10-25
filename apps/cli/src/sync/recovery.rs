//! Explicit local retirement is not a claim about the unknown remote outcome.

use super::{
    event::Event,
    ledger::{self, Scope},
    run::Run,
};
use crate::{
    authoring::{Identity, runtime::Owner},
    canonical,
    error::{Failure, Result},
    store::database,
};
use rusqlite::{Connection, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(super) struct Capture {
    pub request: Value,
    pub replacement_device_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub enrollment_recovery: Option<EnrollmentRecovery>,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(super) struct EnrollmentRecovery {
    pub operation_id: String,
    pub plan_digest: String,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Retirement {
    kind: String,
    operation_id: String,
    plan_digest: String,
}

fn invalid() -> Failure {
    Failure::precondition("the retained request does not have exact local retirement evidence")
}

impl Capture {
    pub fn entity(&self) -> Option<&str> {
        self.request["entity_id"].as_str()
    }
    pub fn outcome(&self) -> Value {
        json!({"schema_version":1,"state":"retired_device","remote_outcome":"unknown",
            "event_id":self.request["event_id"],"entity_id":self.request["entity_id"],
            "retired_device_id":self.request["device_id"],"replacement_device_id":self.replacement_device_id})
    }
}

pub(super) fn capture(
    connection: &Connection,
    scope: &Scope,
    owner: &Owner,
    binding: &crate::account::access::Binding,
    event_id: &str,
) -> Result<Capture> {
    let held = ledger::recorded(connection, scope, event_id)?;
    let event = Event::push(&held.request, scope.account())?;
    if held.state != "pending" || event.device_id == binding.device_id {
        return Err(invalid());
    }
    let enrollment_recovery = if binding.connection.is_some() {
        let plan = crate::account::enrollment_recovery::completed_retirement(
            connection,
            binding,
            &event.device_id,
        )?;
        Some(EnrollmentRecovery {
            operation_id: plan.operation_id.clone(),
            plan_digest: plan.digest()?,
        })
    } else {
        if binding.device_id != owner.device_id
            || !owner.historical(&Identity {
                account_id: owner.account_id.clone(),
                device_id: event.device_id.clone(),
            })
        {
            return Err(Failure::precondition(
                "only a pending request from this installation's verified retired device can be recovered",
            ));
        }
        None
    };
    Ok(Capture {
        request: held.request,
        replacement_device_id: binding.device_id.clone(),
        enrollment_recovery,
    })
}

/// This update and the enclosing command's completed result share a transaction.
pub(super) fn retire(
    t: &Transaction<'_>,
    scope: &Scope,
    capture: &Capture,
    binding: &crate::account::access::Binding,
    operation_id: &str,
    plan_digest: &str,
) -> Result<Value> {
    let event = Event::push(&capture.request, scope.account())?;
    let held = ledger::recorded(t, scope, &event.event_id)?;
    if held.state != "pending"
        || held.request != capture.request
        || event.device_id == capture.replacement_device_id
    {
        return Err(invalid());
    }
    if let Some(expected) = &capture.enrollment_recovery {
        let plan = crate::account::enrollment_recovery::completed_retirement(
            t,
            binding,
            &event.device_id,
        )?;
        if expected.operation_id != plan.operation_id || expected.plan_digest != plan.digest()? {
            return Err(invalid());
        }
    } else if binding.connection.is_some() {
        return Err(invalid());
    }
    let evidence = Retirement {
        kind: "retired_device".into(),
        operation_id: operation_id.into(),
        plan_digest: plan_digest.into(),
    };
    let bytes = canonical::bytes(&serde_json::to_value(evidence).map_err(|_| invalid())?)?;
    let changed=t.execute("UPDATE sync_event SET state='failed',receipt_json=? WHERE account_id=? AND event_id=? AND direction='push' AND state='pending' AND receipt_json IS NULL",params![std::str::from_utf8(&bytes).map_err(|_|invalid())?,scope.account(),event.event_id]).map_err(database)?;
    if changed != 1 {
        return Err(invalid());
    }
    Ok(capture.outcome())
}

/// Local evidence is tied to a completed exact command, never parsed as a server receipt.
pub(super) fn validate(
    connection: &Connection,
    account: &str,
    request: &Value,
    evidence: &Value,
) -> Result<()> {
    let evidence: Retirement = serde_json::from_value(evidence.clone()).map_err(|_| invalid())?;
    let plan = Run::admitted(connection, &evidence.operation_id)?;
    let run = Run::load(connection, &plan)?.ok_or_else(invalid)?;
    let capture = plan.retirement.as_ref().ok_or_else(invalid)?;
    if evidence.kind != "retired_device"
        || plan.digest()? != evidence.plan_digest
        || plan.account.account_id != account
        || capture.request != *request
        || capture.replacement_device_id != plan.account.device_id
        || run.result != Some(capture.outcome())
    {
        return Err(invalid());
    }
    if let Some(expected) = &capture.enrollment_recovery {
        let recovery = crate::account::enrollment_recovery::completed_retirement(
            connection,
            &plan.account,
            request["device_id"].as_str().ok_or_else(invalid)?,
        )?;
        if recovery.operation_id != expected.operation_id
            || recovery.digest()? != expected.plan_digest
        {
            return Err(invalid());
        }
    } else if plan.account.connection.is_some() {
        return Err(invalid());
    }
    Scope::new(account, &plan.account.origin)?.require(connection)
}
