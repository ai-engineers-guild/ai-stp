//! Explicit cancellation discards only a recorded, unpublished generated stage.

use super::{
    context,
    journal::{Journal, Phase, Record},
    plan::{Plan, invalid},
    stage,
};
use crate::error::{Failure, Result};
use serde_json::{Value, json};
use std::path::Path;

fn outcome(record: &Record) -> Result<Option<Value>> {
    match record.phase {
        Phase::Cancelled => Ok(Some(record.result.clone().ok_or_else(invalid)?)),
        Phase::Complete => Err(Failure::precondition(
            "the program installation already completed; cancellation cannot remove it",
        )),
        _ => Ok(None),
    }
}

pub(in crate::provider::runtime) fn cancel(
    parent: &Path,
    bytes: &[u8],
    digest: &str,
) -> Result<Value> {
    let plan = Plan::parse(bytes, digest)?;
    let previous = Journal::history(parent, &plan, digest)?;
    if let Some(record) = &previous {
        if let Some(result) = outcome(record)? {
            return Ok(result);
        }
    } else {
        // First cancellation has no stored ownership to rely on. Validate the
        // declared separation before writing any new operation state.
        context(&plan)?;
    }
    let journal = Journal::open(parent, &plan, digest)?;
    let previous = journal.read()?;
    if let Some(record) = &previous
        && let Some(result) = outcome(record)?
    {
        return Ok(result);
    }
    let result = json!({"operation_id":plan.operation_id,"plan_digest":digest,"state":"cancelled","installation_performed":false});
    let mut record = match previous {
        None => {
            let record = Record {
                schema_version: 1,
                plan_digest: digest.into(),
                plan: plan.value()?,
                phase: Phase::Cancelled,
                stage_parent: None,
                stage_root: None,
                result: Some(result.clone()),
            };
            journal.write(None, &record)?;
            return Ok(result);
        }
        Some(record) => record,
    };
    if record.phase != Phase::Cancelling {
        stage::prepare_cancellation(&plan, &mut record)?;
        let before = record.phase;
        record.phase = Phase::Cancelling;
        record.result = None;
        journal.write(Some(before), &record)?;
    }
    stage::discard(&plan, &record)?;
    record.phase = Phase::Cancelled;
    record.result = Some(result.clone());
    journal.write(Some(Phase::Cancelling), &record)?;
    Ok(result)
}
