//! Exact native admission and terminal receipts; only desired bundle bytes are retained.

use rusqlite::{Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;

use super::{identity, invalid, outcome, plan::Plan};
use crate::{
    digest,
    error::{ErrorKind, Result},
    files::OwnedDirectory,
    provider::runtime::target::Target,
    store::{Store, database},
    wire,
};

const OWNER: &[u8] = b"ai-stp-cli-v2:configuration-operations/v1\n";
const RECORD_LIMIT: usize = super::plan::LIMIT + 8 * 1024 * 1024;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Record {
    schema_version: u32,
    plan_digest: String,
    plan: Value,
    pub state: String,
    pub result: Option<Value>,
}

pub(super) struct Journal {
    state: Target,
    operation: OwnedDirectory,
    _target_lock: OwnedDirectory,
}

fn context(parent: &Path, plan: &Plan) -> Result<Target> {
    let state = Target::open(parent)?;
    if state.path().to_str() != Some(&plan.state_parent) || identity(&state)? != plan.state_identity
    {
        return Err(invalid());
    }
    Ok(state)
}

fn read(connection: &Connection, plan: &Plan, digest: &str) -> Result<Option<Record>> {
    let row: Option<(String, String, String)> = connection
        .query_row(
            "SELECT kind,state,coalesce(detail,'') FROM operation WHERE operation_id=?",
            [&plan.operation_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .map_err(database)?;
    let Some((kind, state, detail)) = row else {
        return Ok(None);
    };
    if detail.len() > RECORD_LIMIT {
        return Err(invalid());
    }
    let record: Record =
        serde_json::from_value(wire::parse(detail.as_bytes())?).map_err(|_| invalid())?;
    if record.schema_version != 1
        || record.plan_digest != digest
        || record.plan != plan.value()?
        || kind != plan.action
        || state != record.state
    {
        return Err(invalid());
    }
    match record.state.as_str() {
        "applying" if record.result.is_none() => (),
        "verified" => outcome::validate(record.result.as_ref().ok_or_else(invalid)?, plan, digest)?,
        _ => return Err(invalid()),
    }
    Ok(Some(record))
}

impl Journal {
    pub fn history(parent: &Path, plan: &Plan, digest: &str) -> Result<Option<Record>> {
        let state = context(parent, plan)?;
        let store = Store::planning(state.path())?;
        let record = read(&store.connection, plan, digest)?;
        state.revalidate()?;
        Ok(record)
    }

    pub fn open(parent: &Path, plan: &Plan, digest: &str) -> Result<Self> {
        let state = context(parent, plan)?;
        let namespace =
            OwnedDirectory::open_at(&state.directory()?, "configuration-operations", OWNER, true)?
                .ok_or_else(invalid)?;
        let target_key = digest::sha256(
            format!("{}:{}", plan.target_identity[0], plan.target_identity[1]).as_bytes(),
        );
        let target_lock = OwnedDirectory::open_at(
            &namespace.directory,
            &format!(
                "target-{}",
                target_key.strip_prefix("sha256:").ok_or_else(invalid)?
            ),
            format!("ai-stp:configuration-target/v1\n{target_key}\n").as_bytes(),
            true,
        )?
        .ok_or_else(invalid)?;
        let owner = format!(
            "ai-stp:configuration-operation/v1\n{}\n{digest}\n",
            plan.operation_id
        );
        let operation = OwnedDirectory::open_at(
            &namespace.directory,
            &plan.operation_id,
            owner.as_bytes(),
            true,
        )?
        .ok_or_else(invalid)?;
        state.revalidate()?;
        Ok(Self {
            state,
            operation,
            _target_lock: target_lock,
        })
    }

    fn store(&self, create: bool) -> Result<Store> {
        self.state.revalidate()?;
        self.operation.validate_lock()?;
        Store::open(self.state.path(), create)
    }

    pub fn read(&self, plan: &Plan, digest: &str) -> Result<Option<Record>> {
        let store = match self.store(false) {
            Err(error) if matches!(error.kind, ErrorKind::NotFound) => return Ok(None),
            result => result?,
        };
        let record = read(&store.connection, plan, digest)?;
        self.state.revalidate()?;
        Ok(record)
    }

    pub fn payload(&self, plan: &Plan, supplied: Option<&[u8]>, admitted: bool) -> Result<Vec<u8>> {
        self.state.revalidate()?;
        self.operation.validate_lock()?;
        let created = plan.created_at.parse().map_err(|_| invalid())?;
        let request = plan.request(created)?;
        if request.bundle.is_none() {
            if supplied.is_some() {
                return Err(invalid());
            }
            return Ok(Vec::new());
        }
        if let Some(bytes) = supplied {
            request.check_bundle(bytes, created)?;
        }
        if let Some(bytes) = self.operation.read_file("bundle.zip", 64 * 1024 * 1024)? {
            request.check_bundle(&bytes, created)?;
            return Ok(bytes);
        }
        if admitted {
            return Err(invalid());
        }
        let bytes = supplied.ok_or_else(invalid)?;
        self.operation.atomic("bundle.zip", bytes)?;
        let bytes = self
            .operation
            .read_file("bundle.zip", 64 * 1024 * 1024)?
            .ok_or_else(invalid)?;
        request.check_bundle(&bytes, created)?;
        Ok(bytes)
    }

    pub fn admit(&self, plan: &Plan, digest: &str) -> Result<()> {
        self.write(plan, digest, None)
    }

    pub fn complete(&self, plan: &Plan, digest: &str, result: &Value) -> Result<()> {
        outcome::validate(result, plan, digest)?;
        self.write(plan, digest, Some(result))?;
        self.cleanup()
    }

    fn write(&self, plan: &Plan, digest: &str, result: Option<&Value>) -> Result<()> {
        let state = if result.is_some() {
            "verified"
        } else {
            "applying"
        };
        let detail = serde_json::to_string(&Record {
            schema_version: 1,
            plan_digest: digest.into(),
            plan: plan.value()?,
            state: state.into(),
            result: result.cloned(),
        })
        .map_err(|_| invalid())?;
        if detail.len() > RECORD_LIMIT {
            return Err(invalid());
        }
        let mut store = self.store(true)?;
        let now = jiff::Timestamp::now().to_string();
        store.transaction(|transaction| {
            let previous = read(transaction, plan, digest)?;
            match (previous, result) {
                (None, None) => { transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?,?,?,?,?)",
                    rusqlite::params![plan.operation_id,plan.action,state,now,detail]).map_err(database)?; }
                (Some(record), Some(_)) if record.state == "applying" => {
                    transaction.execute("UPDATE operation SET state=?,detail=?,finished_at=? WHERE operation_id=?",
                        rusqlite::params![state,detail,now,plan.operation_id]).map_err(database)?;
                }
                _ => return Err(invalid()),
            }
            let evidence = serde_json::to_string(&json!({"plan_digest":digest})).map_err(|_| invalid())?;
            transaction.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence,global_sequence) \
                SELECT ?,coalesce((SELECT max(sequence) FROM operation_event WHERE operation_id=?),0)+1,?,?,?,?,?, \
                coalesce((SELECT max(global_sequence) FROM operation_event),0)+1",
                rusqlite::params![plan.operation_id,plan.operation_id,now,if result.is_some() {"applying"} else {"unseen"},state,"accepted",evidence]).map_err(database)?;
            Ok(())
        })?;
        self.state.revalidate()
    }

    pub fn cleanup(&self) -> Result<()> {
        self.state.revalidate()?;
        self.operation.validate_lock()?;
        for entry in self.operation.directory.entries().map_err(|_| invalid())? {
            let entry = entry.map_err(|_| invalid())?;
            let name = entry.file_name();
            let name = name.to_str().ok_or_else(invalid)?;
            if matches!(name, "lock" | "owner") {
                continue;
            }
            if name != "bundle.zip"
                && !name
                    .strip_prefix(".tmp-")
                    .is_some_and(|suffix| suffix.parse::<ulid::Ulid>().is_ok())
            {
                return Err(invalid());
            }
            self.operation
                .directory
                .remove_file(name)
                .map_err(|_| invalid())?;
        }
        self.operation.sync()
    }
}
