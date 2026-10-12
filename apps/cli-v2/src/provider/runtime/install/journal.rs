//! Short registry transactions; long component execution holds only its own lock.

use std::path::Path;

use rusqlite::OptionalExtension;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    super::target::Target,
    plan::{Identity, Plan, invalid},
};
use crate::{
    error::{ErrorKind, Failure, Result},
    files::OwnedDirectory,
    store::{Store, database},
};

const OWNER: &[u8] = b"ai-stp-cli-v2:installation-operations/v1\n";

#[derive(Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum Phase {
    Prepared,
    Staged,
    Publishing,
    Applying,
    Complete,
    Cancelling,
    Cancelled,
}

impl Phase {
    fn state(self) -> &'static str {
        match self {
            Self::Prepared => "prepared",
            Self::Staged => "staged",
            Self::Publishing => "publishing",
            Self::Applying => "applying",
            Self::Complete => "verified",
            Self::Cancelling => "cancelling",
            Self::Cancelled => "cancelled",
        }
    }

    pub fn terminal(self) -> bool {
        matches!(self, Self::Complete | Self::Cancelled)
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Record {
    pub schema_version: u32,
    pub plan_digest: String,
    pub plan: Value,
    pub phase: Phase,
    pub stage_parent: Option<Identity>,
    pub stage_root: Option<Identity>,
    pub result: Option<Value>,
}

impl Record {
    pub(super) fn parse(operation_id: &str, kind: &str, state: &str, detail: &str) -> Result<Self> {
        if detail.len() > 2 * 1024 * 1024 {
            return Err(invalid());
        }
        let record: Self = serde_json::from_value(crate::wire::parse(detail.as_bytes())?)
            .map_err(|_| conflict())?;
        if record.plan["action"] != kind || record.phase.state() != state {
            return Err(conflict());
        }
        record.validate(operation_id, &record.plan_digest)?;
        Ok(record)
    }

    fn validate(&self, operation_id: &str, digest: &str) -> Result<()> {
        let bytes = serde_json::to_vec(&self.plan).map_err(|_| invalid())?;
        let plan = Plan::parse(&bytes, digest)?;
        if self.schema_version != 1
            || self.plan_digest != digest
            || plan.operation_id != operation_id
            || self.stage_root.is_some() && self.stage_parent.is_none()
            || [&self.stage_parent, &self.stage_root]
                .into_iter()
                .flatten()
                .any(|value| !super::plan::valid_identity(value))
        {
            return Err(conflict());
        }
        let stage = self.stage_parent.is_some() && self.stage_root.is_some();
        if plan.action != "program.install" {
            if self.stage_parent.is_some() || self.stage_root.is_some() {
                return Err(conflict());
            }
            return match self.phase {
                Phase::Applying if self.result.is_none() => Ok(()),
                Phase::Complete => super::change::validate_outcome(
                    self.result.as_ref().ok_or_else(invalid)?,
                    &plan,
                    digest,
                ),
                Phase::Cancelled => super::change::cancellation::validate_outcome(
                    self.result.as_ref().ok_or_else(invalid)?,
                    &plan,
                    digest,
                ),
                _ => Err(conflict()),
            };
        }
        match self.phase {
            Phase::Prepared if self.stage_parent.is_none() && self.result.is_none() => Ok(()),
            Phase::Staged if stage && self.result.is_none() => Ok(()),
            Phase::Publishing | Phase::Complete if stage => {
                super::outcome::validate(self.result.as_ref().ok_or_else(invalid)?, &plan, digest)
            }
            Phase::Cancelling if self.result.is_none() => Ok(()),
            Phase::Cancelled
                if self.result
                    == Some(json!({
                        "operation_id":operation_id,"plan_digest":digest,
                        "state":"cancelled","installation_performed":false
                    })) =>
            {
                Ok(())
            }
            _ => Err(conflict()),
        }
    }
}

pub(super) struct Journal {
    state: Target,
    operation_id: String,
    digest: String,
    _lock: OwnedDirectory,
    _prefix_lock: OwnedDirectory,
}

fn conflict() -> Failure {
    Failure::new(
        ErrorKind::Conflict,
        "the installation operation is already bound to another plan or phase",
    )
}

pub(super) fn identity(target: &Target) -> Result<Identity> {
    let (dev, ino) = target.identity()?;
    Ok([dev.to_string(), ino.to_string()])
}

impl Journal {
    pub fn history(parent: &Path, plan: &Plan, digest: &str) -> Result<Option<Record>> {
        let state = Target::open(parent)?;
        if state.path().to_str() != Some(plan.state_parent.as_str())
            || identity(&state)? != plan.state_parent_identity
        {
            return Err(invalid());
        }
        let store = Store::planning(state.path())?;
        let record = read_store(&store, &plan.operation_id, digest)?;
        state.revalidate()?;
        Ok(record)
    }

    pub fn open(parent: &Path, plan: &Plan, digest: &str) -> Result<Self> {
        let state = Target::open(parent)?;
        if state.path().to_str() != Some(plan.state_parent.as_str())
            || identity(&state)? != plan.state_parent_identity
        {
            return Err(invalid());
        }
        let namespace =
            OwnedDirectory::open_at(&state.directory()?, "installation-operations", OWNER, true)?
                .ok_or_else(invalid)?;
        // Serialize observation, component execution and independent readback.
        // A process lock releases on interruption: an unadmitted expired request
        // must not permanently reserve a prefix. The component's own durable
        // admission remains authoritative across native states and processes.
        let key = crate::digest::sha256(plan.prefix.path.as_bytes());
        let name = format!(
            "prefix-{}",
            key.strip_prefix("sha256:").ok_or_else(invalid)?
        );
        let prefix_owner = format!("ai-stp:program-prefix/v1\n{}\n", plan.prefix.path);
        let prefix_lock =
            OwnedDirectory::open_at(&namespace.directory, &name, prefix_owner.as_bytes(), true)?
                .ok_or_else(invalid)?;
        let owner = format!(
            "ai-stp:{}/v1\n{}\n{digest}\n",
            plan.action, plan.operation_id
        );
        let lock = OwnedDirectory::open_at(
            &namespace.directory,
            &plan.operation_id,
            owner.as_bytes(),
            true,
        )?
        .ok_or_else(invalid)?;
        state.revalidate()?;
        Ok(Self {
            state,
            operation_id: plan.operation_id.clone(),
            digest: digest.into(),
            _lock: lock,
            _prefix_lock: prefix_lock,
        })
    }

    fn store(&self, create: bool) -> Result<Store> {
        self.state.revalidate()?;
        let store = Store::open(self.state.path(), create)?;
        self.state.revalidate()?;
        Ok(store)
    }

    pub fn read(&self) -> Result<Option<Record>> {
        let store = match self.store(false) {
            Err(error) if matches!(error.kind, ErrorKind::NotFound) => return Ok(None),
            value => value?,
        };
        let result = read_store(&store, &self.operation_id, &self.digest)?;
        self.state.revalidate()?;
        Ok(result)
    }

    pub fn write(&self, previous: Option<Phase>, record: &Record) -> Result<()> {
        record.validate(&self.operation_id, &self.digest)?;
        let mut store = self.store(true)?;
        let detail = serde_json::to_string(record).map_err(|_| invalid())?;
        if detail.len() > 2 * 1024 * 1024 || record.plan_digest != self.digest {
            return Err(invalid());
        }
        if !matches!(
            (previous, record.phase),
            (None, Phase::Prepared | Phase::Cancelled | Phase::Applying)
                | (Some(Phase::Prepared), Phase::Staged | Phase::Cancelling)
                | (Some(Phase::Staged), Phase::Publishing | Phase::Cancelling)
                | (Some(Phase::Publishing), Phase::Complete | Phase::Cancelling)
                | (Some(Phase::Cancelling), Phase::Cancelled)
                | (Some(Phase::Applying), Phase::Complete | Phase::Cancelled)
        ) {
            return Err(conflict());
        }
        let now = jiff::Timestamp::now().to_string();
        let finished = record.phase.terminal().then_some(&now);
        let action = record.plan["action"].as_str().ok_or_else(invalid)?;
        store.transaction(|tx| {
            let known: Option<(String, String)> = tx.query_row(
                "SELECT kind,state FROM operation WHERE operation_id=?",
                [&self.operation_id], |r| Ok((r.get(0)?,r.get(1)?)),
            ).optional().map_err(database)?;
            match (previous, known) {
                (None, None) => {
                    tx.execute(
                        "INSERT INTO operation(operation_id,kind,state,started_at,detail,finished_at) \
                         VALUES (?,?,?,?,?,?)",
                        rusqlite::params![self.operation_id,action,record.phase.state(),now,detail,finished],
                    ).map_err(database)?;
                }
                (Some(expected), Some((kind, state))) if kind == action && expected.state() == state => {
                    tx.execute(
                        "UPDATE operation SET state=?,detail=?,finished_at=? WHERE operation_id=?",
                        rusqlite::params![record.phase.state(),detail,finished,self.operation_id],
                    ).map_err(database)?;
                }
                _ => return Err(conflict()),
            }
            let evidence = serde_json::to_string(&json!({"plan_digest":self.digest,"phase":record.phase})).map_err(|_| invalid())?;
            tx.execute(
                "INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence,global_sequence) \
                 SELECT ?,coalesce((SELECT max(sequence) FROM operation_event WHERE operation_id=?),0)+1,?,?,?,?,?, \
                 coalesce((SELECT max(global_sequence) FROM operation_event),0)+1",
                rusqlite::params![self.operation_id,self.operation_id,now,previous.map_or("unseen",Phase::state),record.phase.state(),"accepted",evidence],
            ).map_err(database)?;
            Ok(())
        })?;
        self.state.revalidate()
    }
}

fn read_store(store: &Store, operation_id: &str, digest: &str) -> Result<Option<Record>> {
    let row: Option<(String, String, String)> = store
        .connection
        .query_row(
            "SELECT kind,state,coalesce(detail,'') FROM operation WHERE operation_id=?",
            [operation_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .map_err(database)?;
    row.map(|(kind, state, detail)| {
        let record = Record::parse(operation_id, &kind, &state, &detail)?;
        if record.plan_digest != digest {
            return Err(conflict());
        }
        Ok(record)
    })
    .transpose()
}
