//! One durable parent admission and monotonic checkpoints for all child roots.

use std::path::Path;

use rusqlite::{Connection, OptionalExtension, params};
use serde_json::json;

use super::{Plan, Record, invalid};
use crate::{
    error::Result,
    files::OwnedDirectory,
    provider::configuration::set::{KIND, RECORD_LIMIT},
    provider::runtime::{
        configuration::{identity, reservations},
        target::Target,
    },
    store::{Store, database},
};

pub(super) fn read(connection: &Connection, plan: &Plan, digest: &str) -> Result<Option<Record>> {
    let row: Option<(String, String, String)> = connection
        .query_row(
            "SELECT kind,state,coalesce(detail,'') FROM operation WHERE operation_id=?",
            [&plan.operation_id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )
        .optional()
        .map_err(database)?;
    let Some((kind, state, detail)) = row else {
        return Ok(None);
    };
    if kind != KIND {
        return Err(invalid());
    }
    let (record, held) = Record::parse(&detail, &state)?;
    if record.plan_digest != digest || held.value()? != plan.value()? {
        return Err(invalid());
    }
    Ok(Some(record))
}

pub(in crate::provider::runtime::configuration) struct Journal {
    state: Target,
    operation: OwnedDirectory,
    pub(super) namespace: Option<OwnedDirectory>,
    pub(super) plan: Plan,
    pub(super) digest: String,
}

impl Journal {
    pub(super) fn state_path(&self) -> &Path {
        self.state.path()
    }
    pub(super) fn history(parent: &Path, plan: &Plan, digest: &str) -> Result<Option<Record>> {
        let first = plan.first()?;
        let state = Target::open(parent)?;
        if state.path().to_str() != Some(&first.state_parent)
            || identity(&state)? != first.state_identity
        {
            return Err(invalid());
        }
        let store = Store::planning(parent)?;
        let record = read(&store.connection, plan, digest)?;
        state.revalidate()?;
        Ok(record)
    }

    pub(super) fn open(parent: &Path, plan: Plan, digest: &str) -> Result<Self> {
        Self::history(parent, &plan, digest)?;
        let state = Target::open(parent)?;
        let namespace = reservations::namespace(&state.directory()?, true)?;
        let operation = OwnedDirectory::open_at(
            &namespace.directory,
            &plan.operation_id,
            format!(
                "ai-stp:configuration-set/v1\n{}\n{digest}\n",
                plan.operation_id
            )
            .as_bytes(),
            true,
        )?
        .ok_or_else(invalid)?;
        Ok(Self {
            state,
            operation,
            namespace: Some(namespace),
            plan,
            digest: digest.into(),
        })
    }

    pub(super) fn store(&self) -> Result<Store> {
        self.validate()?;
        Store::open(self.state.path(), true)
    }

    pub(super) fn validate(&self) -> Result<()> {
        self.state.revalidate()?;
        self.operation.validate_lock()?;
        if let Some(namespace) = &self.namespace {
            namespace.validate_lock()?;
        }
        Ok(())
    }

    pub(super) fn save(&self, record: &Record) -> Result<()> {
        let mut store = self.store()?;
        store.transaction(|connection| {
            write(connection, &self.plan, &self.digest, record)?;
            if record.phase == "verified" {
                super::project::completed(connection, &self.plan)?;
            }
            Ok(())
        })?;
        self.validate()
    }
}

pub(super) fn write(
    connection: &Connection,
    plan: &Plan,
    digest: &str,
    record: &Record,
) -> Result<()> {
    if record.plan_digest != digest || record.plan != plan.value()? {
        return Err(invalid());
    }
    let detail = serde_json::to_string(record).map_err(|_| invalid())?;
    if detail.len() > RECORD_LIMIT {
        return Err(invalid());
    }
    Record::parse(&detail, record.state())?;
    let previous = read(connection, plan, digest)?;
    let before = previous.as_ref().map_or("unseen", |r| r.phase.as_str());
    if let Some(previous) = &previous {
        if previous.state() != "applying"
            || !matches!(
                (before, record.phase.as_str()),
                (
                    "preparing",
                    "preparing" | "awaiting_exit" | "applying" | "cancelling"
                ) | ("awaiting_exit", "applying" | "cancelling")
                    | ("applying", "applying" | "awaiting_restart" | "verified")
                    | ("awaiting_restart", "verified")
                    | ("cancelling", "cancelling" | "cancelled")
            )
        {
            return Err(invalid());
        }
        match (&previous.handoff, &record.handoff) {
            (None, None) => (),
            (Some(old), Some(next))
                if old.sessions == next.sessions
                    && (old.published.is_none() || old.published == next.published)
                    && (old.confirmed.is_none() || old.confirmed == next.confirmed) => {}
            _ => return Err(invalid()),
        }
        for (old, next) in previous
            .prepared
            .iter()
            .zip(&record.prepared)
            .chain(previous.results.iter().zip(&record.results))
        {
            if old.is_some() && old != next {
                return Err(invalid());
            }
        }
    } else if !matches!(record.phase.as_str(), "preparing" | "cancelling")
        || record.results.iter().any(Option::is_some)
        || record.prepared.iter().any(Option::is_some)
    {
        return Err(invalid());
    }
    let now = jiff::Timestamp::now().to_string();
    let finished = (record.state() != "applying").then_some(&now);
    connection.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,?,?,?,?) \
        ON CONFLICT(operation_id) DO UPDATE SET state=excluded.state,finished_at=excluded.finished_at,detail=excluded.detail",
        params![plan.operation_id,KIND,record.state(),now,finished,detail]).map_err(database)?;
    let evidence = serde_json::to_string(&json!({"plan_digest":digest,"phase":record.phase}))
        .map_err(|_| invalid())?;
    connection.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence,global_sequence) \
        SELECT ?,coalesce((SELECT max(sequence) FROM operation_event WHERE operation_id=?),0)+1,?,?,?,?,?, \
        coalesce((SELECT max(global_sequence) FROM operation_event),0)+1",
        params![plan.operation_id,plan.operation_id,now,before,record.state(),"accepted",evidence]).map_err(database)?;
    Ok(())
}
