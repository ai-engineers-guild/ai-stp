//! Explicit same-account key replacement under account → registry → identity locks.

use std::{collections::BTreeSet, path::Path};

use serde_json::{Value, json};

use super::{
    Plan, Session, State, check_state, invalid,
    journal::{Journal, Pending},
    model::{Outcome, Receipt},
};
use crate::{
    identity::{
        self,
        recovery::{Intent, Replacement},
    },
    store::{Store, database},
};

fn quiescent(connection: &rusqlite::Connection, at: &str) -> crate::error::Result<()> {
    let unfinished: bool = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM operation WHERE finished_at IS NULL AND kind NOT IN ('sync.run','publication.run','publication.set')) OR EXISTS(SELECT 1 FROM proposal WHERE cancelled_at IS NULL AND confirmed_stable_id IS NULL AND expires_at>?) OR EXISTS(SELECT 1 FROM agent_task WHERE state IN ('planned','blocked','running'))",
        [at], |row| row.get(0)).map_err(database)?;
    if unfinished {
        return Err(crate::error::Failure::precondition(
            "finish or cancel outstanding local operations, proposals and tasks before replacing the device key",
        ));
    }
    Ok(())
}

fn account(journal: &Journal, state: &State) -> crate::error::Result<Option<String>> {
    if !matches!(&state.session, Session::Closed { reason } if reason == "device_revoked")
        || state.outcome != Outcome::Revoked
    {
        return Err(invalid());
    }
    let mut previous = state.plan.expected_revision.clone();
    let mut seen = BTreeSet::new();
    let mut at = state.plan.created_at.as_str().to_owned();
    while let Some(id) = previous {
        if seen.len() >= 4096 || !seen.insert(id.clone()) {
            return Err(invalid());
        }
        let held = journal.receipt_id(&id)?.ok_or_else(invalid)?;
        if held.plan.root != state.plan.root
            || held.plan.root_identity != state.plan.root_identity
            || held.plan.identity != state.plan.identity
            || held.plan.public_key != state.plan.public_key
            || held.plan.credential_store != state.plan.credential_store
            || held.plan.origin != state.plan.origin
            || held.completed_at > at
        {
            return Err(invalid());
        }
        if let Some(account) = held.account_id {
            return Ok(Some(account));
        }
        previous = held.plan.expected_revision;
        at = held.plan.created_at;
    }
    // A recovered identity already retains the exact previous account binding.
    Ok(state.plan.expected_account_id.clone())
}

pub(super) fn selection(
    device: &identity::Identity,
    journal: &Journal,
    state: &State,
    at: &str,
) -> crate::error::Result<Intent> {
    super::check_binding(device, &state.plan)?;
    let account_id = account(journal, state)?;
    let store = Store::planning_at(device.root_directory())?;
    device.revalidate()?;
    quiescent(&store.connection, at)?;
    let owner_id = super::attachment::effective(&store.connection, device)?.account_id;
    let intent = Intent {
        device_id: format!("device_{}", ulid::Ulid::generate()),
        interrupted_sync: crate::sync::interruption::capture(
            &store.connection,
            &state.plan,
            account_id.as_deref(),
        )?,
        interrupted_publications: crate::publication::interruption::capture(
            &store.connection,
            &state.plan,
            account_id.as_deref(),
        )?,
        account_id,
        owner_id,
        previous: device.recovery_tip()?,
    };
    intent.validate(&device.context())?;
    Ok(intent)
}

pub(super) fn pending(root: &Path) -> crate::error::Result<Option<Value>> {
    identity::recovery::pending_at(root)?.map(|plan| {
        let intent = plan.recovery.as_ref().ok_or_else(invalid)?;
        Ok(json!({"schema_version":1,"session":{"state":"closed","reason":"device_recovery_pending"},
            "owner_attached":intent.owner_id != plan.identity.account_id,"effective_owner_id":intent.owner_id,
            "online_verified":false,"pending_operation":{"plan_digest":plan.digest()?,"plan":plan}}))
    }).transpose()
}

pub(super) fn apply(plan: &Plan, at: &str) -> crate::error::Result<Value> {
    let intent = plan.recovery.as_ref().ok_or_else(invalid)?;
    let (path, physical) = identity::root(&plan.root)?;
    if path != plan.root || physical != plan.root_identity {
        return Err(invalid());
    }
    let root = cap_std::fs::Dir::open_ambient_dir(&path, cap_std::ambient_authority())
        .map_err(|_| invalid())?;
    if identity::physical_root(&root)? != plan.root_identity {
        return Err(invalid());
    }
    let journal = Journal::at(
        &root,
        plan.credential_store,
        &plan.identity.device_id,
        false,
    )?
    .ok_or_else(invalid)?;
    if let Some(receipt) = journal.receipt(plan)? {
        let replacement = Replacement::open(plan)?;
        let entry = replacement.history.entry(plan)?.ok_or_else(invalid)?;
        if receipt.outcome != Outcome::DeviceReplaced
            || receipt.completed_at != entry.completed_at
            || receipt.account_id != intent.account_id
        {
            return Err(invalid());
        }
        if identity::recovery::pending(&replacement.directory)?.as_ref() == Some(plan) {
            journal.clear_pending(plan)?;
            replacement.finish(plan)?;
        }
        return Ok(receipt.public());
    }
    let pending = journal.pending()?;
    if pending.as_ref().is_some_and(|held| held.plan != *plan) {
        return Err(invalid());
    }
    if pending.is_none() && (at < plan.created_at.as_str() || at > plan.expires_at.as_str()) {
        return Err(crate::error::Failure::precondition(
            "the device recovery plan expired before admission",
        ));
    }
    let mut store = Store::open_at(&root, true)?;
    let mut replacement = Replacement::open(plan)?;
    replacement.validate(plan)?;
    let retained = identity::recovery::pending(&replacement.directory)?;
    if retained.as_ref().is_some_and(|p| p != plan) {
        return Err(invalid());
    }
    if retained.is_none() {
        quiescent(&store.connection, at)?;
        crate::sync::interruption::validate(&store.connection, plan)?;
        crate::publication::interruption::validate(&store.connection, plan)?;
    }
    let owner_id = match super::attachment::owner_binding(&store.connection)? {
        Some((original, account)) if replacement.knows_original(&original) => account,
        Some(_) => return Err(invalid()),
        None => plan.identity.account_id.clone(),
    };
    if owner_id != intent.owner_id {
        return Err(invalid());
    }
    match journal.state()? {
        Some(state) => {
            check_state(&state, plan)?;
            if plan.expected_revision.as_deref() != Some(&state.revision)
                || account(&journal, &state)? != intent.account_id
                || at < state.completed_at.as_str()
            {
                return Err(invalid());
            }
        }
        None if retained.as_ref() == Some(plan) && replacement.history.entry(plan)?.is_some() => {}
        None => return Err(invalid()),
    }
    if pending.is_none() {
        journal.admit(&Pending {
            plan: plan.clone(),
            requested_at: at.into(),
        })?;
    }
    // Drain all old registry/account users before removing their credential.
    // These monotonic markers stay compatible if the process stops here.
    store.fence_retired_devices()?;
    journal.fence()?;
    store.transaction(|t| {
        crate::sync::interruption::apply(t, plan, &super::now_after(at))?;
        crate::publication::interruption::apply(t, plan)
    })?;
    replacement.admit(plan)?;
    replacement.replace(plan, &super::now_after(at))?;
    journal.retire()?;
    let entry = replacement.completed(plan, &super::now_after(at))?;
    let receipt = Receipt {
        plan: plan.clone(),
        plan_digest: plan.digest()?,
        outcome: Outcome::DeviceReplaced,
        completed_at: entry.completed_at,
        account_id: intent.account_id.clone(),
    };
    if identity::root(&plan.root)? != (plan.root.clone(), plan.root_identity.clone()) {
        return Err(invalid());
    }
    journal.complete_receipt(&receipt)?;
    replacement.finish(plan)?;
    Ok(receipt.public())
}
