//! Original per-object intent and observed progress in the existing operation
//! journal. Each transaction ends before HTTP; an unknown reply stays retryable.

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    client::Client,
    contract::{Create, Visibility},
    interruption::{self, Checkpoint},
    readback::Observation,
    text,
};
use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    passport,
    store::{Store, database, journal, revisions},
};

const KIND: &str = "publication.run";
const MAX_BYTES: usize = 16 * 1024 * 1024;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Attempt {
    pub operation_id: String,
    pub request: Create,
    pub confirmation_key: String,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "state", rename_all = "snake_case", deny_unknown_fields)]
enum Outcome {
    Published { catalog: Observation },
    Refused,
    Interrupted { recovery: interruption::Receipt },
}

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Progress {
    plan: Option<Value>,
    outcome: Option<Outcome>,
}

struct Held {
    sequence: i64,
    at: String,
    progress: Progress,
}

fn invalid() -> Failure {
    Failure::precondition(
        "the retained publication differs from its exact request or observed progress",
    )
}

fn encode(value: &impl Serialize) -> Result<String> {
    let bytes = canonical::bytes(&serde_json::to_value(value).map_err(|_| invalid())?)?;
    if bytes.len() > MAX_BYTES {
        return Err(invalid());
    }
    String::from_utf8(bytes).map_err(|_| invalid())
}

impl Attempt {
    pub fn new(request: Create) -> Result<Self> {
        let attempt = Self {
            operation_id: format!("operation_{}", ulid::Ulid::generate()),
            request,
            confirmation_key: format!("publication-confirm-{}", ulid::Ulid::generate()),
        };
        attempt.digest()?;
        Ok(attempt)
    }

    pub fn digest(&self) -> Result<String> {
        self.request.validate()?;
        super::contract::confirmation_key(&self.confirmation_key)?;
        if !passport::stable_id(&self.operation_id, "operation") {
            return Err(invalid());
        }
        digest::bytes("ai-stp:plan:v1", encode(self)?.as_bytes())
    }

    pub fn load(connection: &Connection, id: &str) -> Result<Self> {
        if !passport::stable_id(id, "operation") {
            return Err(invalid());
        }
        let bytes:Option<String>=connection.query_row(
            "SELECT CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? AND sequence=1 AND result='admitted'",
            [id],|r|r.get(0)).optional().map_err(database)?;
        let value: Self =
            serde_json::from_value(canonical::parse(bytes.ok_or_else(invalid)?.as_bytes())?)
                .map_err(|_| invalid())?;
        if value.operation_id != id {
            return Err(invalid());
        }
        value.digest()?;
        value.held(connection)?.ok_or_else(invalid)?;
        Ok(value)
    }

    fn check_progress(&self, progress: &Progress) -> Result<()> {
        if let Some(plan) = &progress.plan {
            self.request.response(plan, None)?;
        }
        match &progress.outcome {
            Some(Outcome::Interrupted { recovery }) => {
                recovery.validate()?;
                if recovery.checkpoint.operation_id != self.operation_id
                    || recovery.checkpoint.request_digest != self.digest()?
                    || recovery.replacement_device_id == self.request.account.device_id
                {
                    return Err(invalid());
                }
            }
            Some(Outcome::Published { catalog }) => {
                if progress
                    .plan
                    .as_ref()
                    .is_none_or(|p| p["state"] != "published")
                {
                    return Err(invalid());
                }
                let visibility: Visibility =
                    serde_json::from_value(self.request.body()["visibility"].clone())
                        .map_err(|_| invalid())?;
                catalog.validate(&self.request.snapshot()?, visibility, &self.request.account)?;
            }
            Some(Outcome::Refused)
                if !matches!(
                    progress.plan.as_ref().and_then(|p| p["state"].as_str()),
                    Some("failed" | "cancelled" | "stale")
                ) =>
            {
                return Err(invalid());
            }
            Some(Outcome::Refused) | None => {}
        }
        Ok(())
    }

    fn held(&self, connection: &Connection) -> Result<Option<Held>> {
        let Some(state) = journal::state(connection, &self.operation_id, KIND, &self.digest()?)?
        else {
            return Ok(None);
        };
        if !matches!(state.as_str(), "applying" | "completed") {
            return Err(invalid());
        }
        let admission:String=connection.query_row(
            "SELECT evidence FROM operation_event WHERE operation_id=? AND sequence=1 AND state_before='planned' AND state_after='applying' AND result='admitted' AND length(CAST(evidence AS BLOB))<=16777216",
            [&self.operation_id],|r|r.get(0)).map_err(database)?;
        if admission != encode(self)? {
            return Err(invalid());
        }
        let (started, finished): (String, Option<String>) = connection
            .query_row(
                "SELECT started_at,finished_at FROM operation WHERE operation_id=?",
                [&self.operation_id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .map_err(database)?;
        let (sequence,at,result,bytes):(i64,String,String,Option<String>)=connection.query_row(
            "SELECT sequence,at,result,CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? ORDER BY sequence DESC LIMIT 1",
            [&self.operation_id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).map_err(database)?;
        if !passport::timestamp(&at) || !passport::timestamp(&started) || at < started {
            return Err(invalid());
        }
        let progress = if sequence == 1 {
            if result != "admitted" || at != started {
                return Err(invalid());
            }
            Progress::default()
        } else {
            if !matches!(result.as_str(), "observed" | "settled") {
                return Err(invalid());
            }
            serde_json::from_value(canonical::parse(bytes.ok_or_else(invalid)?.as_bytes())?)
                .map_err(|_| invalid())?
        };
        self.check_progress(&progress)?;
        if sequence > 1
            && progress.plan.is_none()
            && !matches!(progress.outcome, Some(Outcome::Interrupted { .. }))
        {
            return Err(invalid());
        }
        if (state == "completed") != progress.outcome.is_some()
            || (result == "settled") != progress.outcome.is_some()
            || finished.as_deref() != progress.outcome.as_ref().map(|_| at.as_str())
        {
            return Err(invalid());
        }
        if progress.plan.is_some() {
            let first:String=connection.query_row("SELECT evidence FROM operation_event WHERE operation_id=? AND sequence=2 AND result='observed' AND length(CAST(evidence AS BLOB))<=16777216",[&self.operation_id],|r|r.get(0)).map_err(database)?;
            let first: Progress = serde_json::from_value(canonical::parse(first.as_bytes())?)
                .map_err(|_| invalid())?;
            if first.outcome.is_some() {
                return Err(invalid());
            }
            self.request.response(
                progress.plan.as_ref().ok_or_else(invalid)?,
                Some(first.plan.as_ref().ok_or_else(invalid)?),
            )?;
        }
        if let Some(Outcome::Interrupted { recovery }) = &progress.outcome {
            if sequence < 2
                || interruption::progress_digest(connection, &self.operation_id, sequence - 1)?
                    != recovery.checkpoint.progress_digest
            {
                return Err(invalid());
            }
            let prior = if sequence == 2 {
                Progress::default()
            } else {
                let bytes: String = connection.query_row(
                    "SELECT CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? AND sequence=?",
                    params![self.operation_id,sequence-1], |r| r.get(0)).map_err(database)?;
                serde_json::from_value(canonical::parse(bytes.as_bytes())?)
                    .map_err(|_| invalid())?
            };
            let mut preserved = progress.clone();
            preserved.outcome = None;
            if encode(&prior)? != encode(&preserved)? {
                return Err(invalid());
            }
        }
        Ok(Some(Held {
            sequence,
            at,
            progress,
        }))
    }

    fn admit(&self, store: &mut Store) -> Result<Held> {
        store.transaction(|t| {
            if let Some(held)=self.held(t)? {return Ok(held);}
            let at=format!("{:.3}",jiff::Timestamp::now());
            t.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?,?,'applying',?,?)",
                params![self.operation_id,KIND,at,self.digest()?]).map_err(database)?;
            t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,1,?,'planned','applying','admitted',?)",
                params![self.operation_id,at,encode(self)?]).map_err(database)?;
            Ok(Held {sequence:1,at,progress:Progress::default()})
        })
    }

    fn save(&self, t: &Transaction<'_>, held: &mut Held) -> Result<()> {
        self.check_progress(&held.progress)?;
        let current = self.held(t)?.ok_or_else(invalid)?;
        if current.sequence != held.sequence || current.progress.outcome.is_some() {
            return Err(invalid());
        }
        if encode(&current.progress)? == encode(&held.progress)? {
            return Ok(());
        }
        if let Some(previous) = &current.progress.plan {
            self.request.response(
                held.progress.plan.as_ref().ok_or_else(invalid)?,
                Some(previous),
            )?;
        }
        let at = format!("{:.3}", jiff::Timestamp::now());
        if at < current.at {
            return Err(invalid());
        }
        let done = held.progress.outcome.is_some();
        let state = if done { "completed" } else { "applying" };
        t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,?,?,'applying',?,?,?)",
            params![self.operation_id,held.sequence+1,at,state,if done {"settled"}else{"observed"},encode(&held.progress)?]).map_err(database)?;
        t.execute(
            "UPDATE operation SET state=?,finished_at=? WHERE operation_id=?",
            params![
                state,
                if done { Some(&at) } else { None },
                self.operation_id
            ],
        )
        .map_err(database)?;
        held.sequence += 1;
        held.at = at;
        Ok(())
    }

    fn view(&self, held: &Held) -> Result<Value> {
        let state = match &held.progress.outcome {
            Some(Outcome::Published { .. }) => "published",
            Some(Outcome::Refused) => "refused",
            Some(Outcome::Interrupted { .. }) => "interrupted",
            None => "waiting",
        };
        let mut value = json!({"schema_version":1,"operation_id":self.operation_id,"request_digest":self.digest()?,
            "state":state,"plan":held.progress.plan,"outcome":held.progress.outcome});
        if state == "interrupted" {
            value["remote_outcome"] = "unknown".into();
        }
        Ok(value)
    }

    pub(super) fn checkpoint(&self, connection: &Connection) -> Result<Checkpoint> {
        let held = self.held(connection)?.ok_or_else(invalid)?;
        if held.progress.outcome.is_some() {
            return Err(invalid());
        }
        Ok(Checkpoint {
            operation_id: self.operation_id.clone(),
            request_digest: self.digest()?,
            progress_digest: interruption::progress_digest(
                connection,
                &self.operation_id,
                held.sequence,
            )?,
        })
    }

    pub(super) fn interruption(
        &self,
        connection: &Connection,
    ) -> Result<Option<interruption::Receipt>> {
        Ok(
            match self.held(connection)?.ok_or_else(invalid)?.progress.outcome {
                Some(Outcome::Interrupted { recovery }) => Some(recovery),
                _ => None,
            },
        )
    }

    pub(super) fn interrupt(
        &self,
        t: &Transaction<'_>,
        receipt: &interruption::Receipt,
    ) -> Result<()> {
        let mut held = self.held(t)?.ok_or_else(invalid)?;
        if let Some(Outcome::Interrupted { recovery }) = &held.progress.outcome {
            return if recovery == receipt {
                Ok(())
            } else {
                Err(invalid())
            };
        }
        if self.checkpoint(t)? != receipt.checkpoint {
            return Err(invalid());
        }
        held.progress.outcome = Some(Outcome::Interrupted {
            recovery: receipt.clone(),
        });
        self.save(t, &mut held)
    }

    /// Fresh read-only evidence after completed key replacement. This never
    /// changes the stopped attempt or sends create/bind/confirm as the old device.
    pub fn reconcile(&self, client: &mut Client) -> Result<Value> {
        let store = client.registry()?;
        let held = self.held(&store.connection)?.ok_or_else(invalid)?;
        let Some(Outcome::Interrupted { recovery }) = &held.progress.outcome else {
            return Err(Failure::precondition(
                "only a retained interrupted publication can be reconciled",
            ));
        };
        client.recovered(&self.request, recovery)?;
        let plan = held
            .progress
            .plan
            .as_ref()
            .map(|plan| client.status(&self.request, plan))
            .transpose()?;
        let visibility: Visibility =
            serde_json::from_value(self.request.body()["visibility"].clone())
                .map_err(|_| invalid())?;
        let catalog = client.catalog(&self.request.snapshot()?, visibility)?;
        Ok(
            json!({"schema_version":1,"operation_id":self.operation_id,"request_digest":self.digest()?,
            "remote_outcome":plan.as_ref().map_or("unknown", |p|p["state"].as_str().unwrap_or("unknown")),
            "plan":plan,"catalog":catalog}),
        )
    }

    /// Historical receipt validation is local and does not load a session.
    pub fn completed(&self, store: &Store) -> Result<Option<Value>> {
        self.held(&store.connection)?
            .filter(|h| h.progress.outcome.is_some())
            .map(|h| self.view(&h))
            .transpose()
    }

    pub fn advance(&self, client: &mut Client) -> Result<Value> {
        self.digest()?;
        let mut store = client.registry()?;
        if let Some(value) = self.completed(&store)? {
            return Ok(value);
        }
        // One fresh account observation precedes local admission. The request's
        // original device may read history, but only it can advance an attempt.
        client.authorize(&self.request, true)?;
        let existing = self.held(&store.connection)?;
        if existing.is_none() {
            self.local(&mut store)?;
        }
        let mut held = self.admit(&mut store)?;
        let observed = match &held.progress.plan {
            Some(plan) => client.status(&self.request, plan)?,
            None => client.create(&self.request)?,
        };
        held.progress.plan = Some(observed);
        store.transaction(|t| self.save(t, &mut held))?;
        let mut plan = held.progress.plan.clone().ok_or_else(invalid)?;
        if matches!(plan["state"].as_str(), Some("draft" | "ready")) {
            self.local(&mut store)?;
            for (address, _) in self.request.artifacts()? {
                if !matches!(plan["state"].as_str(), Some("draft" | "ready")) {
                    break;
                }
                let bytes = store.transaction(|t| revisions::read_content(t, &address))?;
                let projection = (address != text(self.request.body(), "content_digest")?)
                    .then_some(address.as_str());
                plan = client.bind(&self.request, &plan, projection, &bytes)?;
                held.progress.plan = Some(plan.clone());
                store.transaction(|t| self.save(t, &mut held))?;
            }
            if matches!(plan["state"].as_str(), Some("draft" | "ready")) {
                plan = client.confirm(&self.request, &plan, &self.confirmation_key)?;
                held.progress.plan = Some(plan.clone());
                store.transaction(|t| self.save(t, &mut held))?;
            }
        }
        match plan["state"].as_str() {
            Some("published") => {
                let visibility: Visibility =
                    serde_json::from_value(self.request.body()["visibility"].clone())
                        .map_err(|_| invalid())?;
                let catalog = client
                    .catalog(&self.request.snapshot()?, visibility)?
                    .ok_or_else(|| {
                        Failure::new(
                            ErrorKind::Unavailable,
                            "published version is not yet readable in the required catalog",
                        )
                    })?;
                held.progress.outcome = Some(Outcome::Published { catalog });
            }
            Some("failed" | "cancelled" | "stale") => {
                held.progress.outcome = Some(Outcome::Refused)
            }
            Some("validating" | "publish_planned") => {}
            _ => return Err(invalid()),
        }
        store.transaction(|t| self.save(t, &mut held))?;
        self.view(&held)
    }

    fn local(&self, store: &mut Store) -> Result<()> {
        let expected = self.request.snapshot()?;
        let prepared = super::prepare(
            store,
            text(&expected.passport, "stable_id")?,
            text(&expected.passport, "version")?,
            Some(&expected.passport_digest),
            None,
        )?;
        if prepared.last().is_none_or(|s| {
            s.passport != expected.passport || s.artifact_inventory != expected.artifact_inventory
        }) {
            return Err(invalid());
        }
        Ok(())
    }
}
