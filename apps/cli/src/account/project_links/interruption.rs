//! Retire only the original actor while retaining unknown confirmation reservations.

use rusqlite::{Connection, Transaction};

use super::{
    invalid,
    journal::{Checkpoint, Record},
    model::{Effect, Interruption, KIND, RetirementKind},
};
use crate::{account, error::Result, store::database};

fn active(connection: &Connection) -> Result<Vec<Record>> {
    let mut query = connection.prepare(
        "SELECT operation_id FROM operation WHERE kind=? AND finished_at IS NULL ORDER BY operation_id LIMIT 129"
    ).map_err(database)?;
    let ids = query
        .query_map([KIND], |row| row.get::<_, String>(0))
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if ids.len() > 128 {
        return Err(invalid());
    }
    ids.iter()
        .map(|id| Record::load(connection, id)?.ok_or_else(invalid))
        .collect()
}

fn named_receipt(
    checkpoint: &Checkpoint,
    recovery: &account::enrollment_recovery::Plan,
) -> Result<Interruption> {
    if !recovery.interrupted_checkout_links.contains(checkpoint) {
        return Err(invalid());
    }
    let receipt = Interruption {
        kind: RetirementKind::Enrollment,
        checkpoint: checkpoint.clone(),
        recovery_operation_id: recovery.operation_id.clone(),
        recovery_plan_digest: recovery.digest()?,
        replacement_device_id: recovery.replacement.device_id.clone(),
    };
    receipt.validate()?;
    Ok(receipt)
}

fn root_receipt(checkpoint: &Checkpoint, recovery: &account::Plan) -> Result<Interruption> {
    let intent = recovery.recovery.as_ref().ok_or_else(invalid)?;
    if recovery.action != account::Action::Recover
        || !intent.interrupted_checkout_links.contains(checkpoint)
    {
        return Err(invalid());
    }
    let receipt = Interruption {
        kind: RetirementKind::Root,
        checkpoint: checkpoint.clone(),
        recovery_operation_id: recovery.operation_id.clone(),
        recovery_plan_digest: recovery.digest()?,
        replacement_device_id: intent.device_id.clone(),
    };
    receipt.validate()?;
    Ok(receipt)
}

pub(crate) fn capture_named(
    connection: &Connection,
    recovery: &account::enrollment_recovery::Plan,
) -> Result<Vec<Checkpoint>> {
    let mut checkpoints = Vec::new();
    for record in active(connection)? {
        let binding = &record.plan.snapshot().account;
        if binding
            .connection
            .as_ref()
            .is_some_and(|c| c.connection_id == recovery.previous.connection_id)
        {
            recovery.check_previous_binding(binding)?;
            if record.plan.state_parent != recovery.replacement.root {
                return Err(invalid());
            }
            checkpoints.push(record.checkpoint()?);
        }
    }
    Ok(checkpoints)
}

pub(crate) fn validate_named(
    connection: &Connection,
    recovery: &account::enrollment_recovery::Plan,
) -> Result<()> {
    let current = capture_named(connection, recovery)?;
    if current
        .iter()
        .any(|checkpoint| !recovery.interrupted_checkout_links.contains(checkpoint))
    {
        return Err(invalid());
    }
    for checkpoint in &recovery.interrupted_checkout_links {
        let record = Record::load(connection, &checkpoint.operation_id)?.ok_or_else(invalid)?;
        recovery.check_previous_binding(&record.plan.snapshot().account)?;
        if record.plan.state_parent != recovery.replacement.root
            || record.plan.digest()? != checkpoint.plan_digest
            || !current.contains(checkpoint)
                && record.interruption != Some(named_receipt(checkpoint, recovery)?)
        {
            return Err(invalid());
        }
    }
    Ok(())
}

pub(crate) fn apply_named(
    transaction: &Transaction<'_>,
    recovery: &account::enrollment_recovery::Plan,
    at: &str,
) -> Result<()> {
    validate_named(transaction, recovery)?;
    for checkpoint in &recovery.interrupted_checkout_links {
        let mut record =
            Record::load(transaction, &checkpoint.operation_id)?.ok_or_else(invalid)?;
        if record.interruption.is_none() {
            record.save(
                transaction,
                Effect::Interrupted {
                    retirement: named_receipt(checkpoint, recovery)?,
                },
                at,
            )?;
        }
    }
    Ok(())
}

pub(crate) fn capture(
    connection: &Connection,
    recovery: &account::Plan,
    account_id: Option<&str>,
) -> Result<Vec<Checkpoint>> {
    let mut checkpoints = Vec::new();
    for record in active(connection)? {
        let binding = &record.plan.snapshot().account;
        if binding.connection.is_none()
            && binding.device_id == recovery.identity.device_id
            && binding.origin == recovery.origin
        {
            crate::publication::interruption::belongs(binding, recovery)?;
            if record.plan.state_parent != recovery.root
                || Some(binding.account_id.as_str()) != account_id
            {
                return Err(invalid());
            }
            checkpoints.push(record.checkpoint()?);
        }
    }
    Ok(checkpoints)
}

pub(crate) fn validate(connection: &Connection, recovery: &account::Plan) -> Result<()> {
    let intent = recovery.recovery.as_ref().ok_or_else(invalid)?;
    let current = capture(connection, recovery, intent.account_id.as_deref())?;
    if current
        .iter()
        .any(|checkpoint| !intent.interrupted_checkout_links.contains(checkpoint))
    {
        return Err(invalid());
    }
    for checkpoint in &intent.interrupted_checkout_links {
        let record = Record::load(connection, &checkpoint.operation_id)?.ok_or_else(invalid)?;
        crate::publication::interruption::belongs(&record.plan.snapshot().account, recovery)?;
        if record.plan.state_parent != recovery.root
            || record.plan.digest()? != checkpoint.plan_digest
            || !current.contains(checkpoint)
                && record.interruption != Some(root_receipt(checkpoint, recovery)?)
        {
            return Err(invalid());
        }
    }
    Ok(())
}

pub(crate) fn apply(
    transaction: &Transaction<'_>,
    recovery: &account::Plan,
    at: &str,
) -> Result<()> {
    validate(transaction, recovery)?;
    for checkpoint in &recovery
        .recovery
        .as_ref()
        .ok_or_else(invalid)?
        .interrupted_checkout_links
    {
        let mut record =
            Record::load(transaction, &checkpoint.operation_id)?.ok_or_else(invalid)?;
        if record.interruption.is_none() {
            record.save(
                transaction,
                Effect::Interrupted {
                    retirement: root_receipt(checkpoint, recovery)?,
                },
                at,
            )?;
        }
    }
    Ok(())
}
