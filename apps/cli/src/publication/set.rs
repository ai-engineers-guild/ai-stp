//! The group owns admission and terminal results; child journals own delivery.

use rusqlite::{Connection, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    interruption::{self, Checkpoint, Kind, Receipt},
    readback::Observation,
    runtime::{Intent, Member, Plan, encode, invalid},
};
use crate::{
    canonical, digest,
    error::{Failure, Result},
    passport,
    store::{database, journal},
};

const KIND: &str = "publication.set";

#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "state", rename_all = "snake_case", deny_unknown_fields)]
pub(super) enum Terminal {
    Published {
        catalogs: Vec<Observation>,
    },
    Refused {
        index: usize,
        catalogs: Vec<Observation>,
    },
    Interrupted {
        recovery: Receipt,
    },
}

#[derive(Deserialize, Serialize)]
#[serde(tag = "event", rename_all = "snake_case", deny_unknown_fields)]
enum Event {
    Confirmed { plan: Box<Plan> },
    Completed { result: Terminal },
}

pub(super) struct Run {
    sequence: i64,
    at: String,
    pub terminal: Option<Terminal>,
}

impl Terminal {
    fn validate(&self, connection: &Connection, intent: &Intent) -> Result<()> {
        let catalogs = match self {
            Self::Published { catalogs } if catalogs.len() == intent.members.len() => catalogs,
            Self::Refused { index, catalogs }
                if *index < intent.members.len() && catalogs.len() == *index =>
            {
                let Member::Publish { attempt } = &intent.members[*index] else {
                    return Err(invalid());
                };
                if attempt
                    .inspect(connection)?
                    .is_none_or(|v| v["state"] != "refused")
                {
                    return Err(invalid());
                }
                catalogs
            }
            Self::Interrupted { recovery } => {
                recovery.validate()?;
                if recovery.checkpoint.kind != Kind::Set
                    || recovery.checkpoint.operation_id != intent.operation_id
                    || recovery.checkpoint.request_digest != intent.digest()?
                    || recovery.replacement_device_id == intent.account.device_id
                {
                    return Err(invalid());
                }
                return Ok(());
            }
            _ => return Err(invalid()),
        };
        for (catalog, member) in catalogs.iter().zip(&intent.members) {
            catalog.validate(&member.snapshot()?, intent.visibility, &intent.account)?;
            if let Member::Publish { attempt } = member
                && attempt
                    .inspect(connection)?
                    .is_some_and(|v| v["state"] != "published")
            {
                return Err(invalid());
            }
        }
        Ok(())
    }
}

impl Run {
    pub fn unoccupied(connection: &Connection, target: &super::Snapshot) -> Result<()> {
        let mut query=connection.prepare("SELECT operation_id FROM operation WHERE kind='publication.set' AND finished_at IS NULL ORDER BY operation_id LIMIT 129").map_err(database)?;
        let ids = query
            .query_map([], |r| r.get::<_, String>(0))
            .map_err(database)?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(database)?;
        if ids.len() > 128 {
            return Err(invalid());
        }
        for id in ids {
            let held = Self::intent(connection, &id)?;
            let existing = held.members.last().ok_or_else(invalid)?.snapshot()?;
            if existing.passport["stable_id"] == target.passport["stable_id"]
                && existing.passport["version"] == target.passport["version"]
            {
                return Err(Failure::precondition(
                    "resume the admitted publication group before planning another",
                )
                .with_details([("operation_id".into(), id.into())]));
            }
        }
        Ok(())
    }

    pub fn intent(connection: &Connection, id: &str) -> Result<Intent> {
        if !passport::stable_id(id, "operation") {
            return Err(invalid());
        }
        let bytes: String = connection.query_row(
            "SELECT CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? AND sequence=1 AND result='confirmed'",
            [id], |r| r.get(0)).map_err(database)?;
        let Event::Confirmed { plan } =
            serde_json::from_value(canonical::parse(bytes.as_bytes())?).map_err(|_| invalid())?
        else {
            return Err(invalid());
        };
        plan.digest()?;
        if plan.intent.operation_id != id || plan.account != plan.intent.account {
            return Err(invalid());
        }
        Self::load(connection, &plan.intent)?.ok_or_else(invalid)?;
        Ok(plan.intent)
    }

    pub fn load(connection: &Connection, intent: &Intent) -> Result<Option<Self>> {
        let Some(state) =
            journal::state(connection, &intent.operation_id, KIND, &intent.digest()?)?
        else {
            return Ok(None);
        };
        if !matches!(state.as_str(), "applying" | "completed") {
            return Err(invalid());
        }
        let (started, finished): (String, Option<String>) = connection
            .query_row(
                "SELECT started_at,finished_at FROM operation WHERE operation_id=?",
                [&intent.operation_id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .map_err(database)?;
        let initial:String=connection.query_row("SELECT CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? AND sequence=1 AND at=? AND result='confirmed' AND state_before='planned' AND state_after='applying'",
            params![intent.operation_id,started],|r|r.get(0)).map_err(database)?;
        let Event::Confirmed { plan: original } =
            serde_json::from_value(canonical::parse(initial.as_bytes())?).map_err(|_| invalid())?
        else {
            return Err(invalid());
        };
        original.digest()?;
        if original.intent.digest()? != intent.digest()?
            || original.account != intent.account
            || !passport::timestamp(&started)
            || started < original.created_at
            || started > original.expires_at
        {
            return Err(invalid());
        }
        let (sequence,at,before,after,result,bytes):(i64,String,String,String,String,String)=connection.query_row(
            "SELECT sequence,at,state_before,state_after,result,CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? ORDER BY sequence DESC LIMIT 1",
            [&intent.operation_id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?))).map_err(database)?;
        if sequence < 1
            || !passport::timestamp(&at)
            || at < started
            || after != state
            || before != if sequence == 1 { "planned" } else { "applying" }
        {
            return Err(invalid());
        }
        let event: Event =
            serde_json::from_value(canonical::parse(bytes.as_bytes())?).map_err(|_| invalid())?;
        let terminal = match event {
            Event::Confirmed { plan }
                if state == "applying" && result == "confirmed" && finished.is_none() =>
            {
                plan.digest()?;
                if plan.intent.digest()? != intent.digest()?
                    || at < plan.created_at
                    || at > plan.expires_at
                {
                    return Err(invalid());
                }
                None
            }
            Event::Completed { result: terminal }
                if state == "completed"
                    && result == "completed"
                    && finished.as_deref() == Some(&at)
                    && sequence > 1 =>
            {
                terminal.validate(connection, intent)?;
                if let Terminal::Interrupted { recovery } = &terminal
                    && interruption::progress_digest(
                        connection,
                        &intent.operation_id,
                        sequence - 1,
                    )? != recovery.checkpoint.progress_digest
                {
                    return Err(invalid());
                }
                Some(terminal)
            }
            _ => return Err(invalid()),
        };
        Ok(Some(Self {
            sequence,
            at,
            terminal,
        }))
    }

    pub fn position(connection: &Connection, intent: &Intent) -> Result<String> {
        let parent = Self::load(connection, intent)?
            .map(|r| interruption::progress_digest(connection, &intent.operation_id, r.sequence))
            .transpose()?;
        let mut children = Vec::new();
        for member in &intent.members {
            if let Member::Publish { attempt } = member {
                children.push(json!({"operation_id":attempt.operation_id,"position":attempt.position(connection)?}));
            }
        }
        digest::canonical(
            "ai-stp:plan:v1",
            &json!({"parent":parent,"children":children}),
        )
    }

    pub fn confirm(t: &Transaction<'_>, plan: &Plan, at: &str) -> Result<Self> {
        plan.digest()?;
        let intent = &plan.intent;
        if Self::position(t, intent)? != plan.position {
            return Err(invalid());
        }
        let held = Self::load(t, intent)?;
        if held
            .as_ref()
            .is_some_and(|r| r.terminal.is_some() || at < r.at.as_str())
        {
            return Err(invalid());
        }
        let sequence = held.as_ref().map_or(1, |r| r.sequence + 1);
        if held.is_none() {
            if plan.account != intent.account {
                return Err(invalid());
            }
            Self::unoccupied(t, &intent.members.last().ok_or_else(invalid)?.snapshot()?)?;
            // Reserve room for the group's one active child in device recovery.
            journal::recovery_capacity(t, 2)?;
            t.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?,?,'applying',?,?)",
                params![intent.operation_id,KIND,at,intent.digest()?]).map_err(database)?;
        }
        t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,?,?,?,'applying','confirmed',?)",
            params![intent.operation_id,sequence,at,if sequence==1 {"planned"}else{"applying"},encode(&Event::Confirmed {plan:Box::new(plan.clone())})?]).map_err(database)?;
        Ok(Self {
            sequence,
            at: at.into(),
            terminal: None,
        })
    }

    pub fn finish(&mut self, t: &Transaction<'_>, intent: &Intent, result: Terminal) -> Result<()> {
        result.validate(t, intent)?;
        let held = Self::load(t, intent)?.ok_or_else(invalid)?;
        if held.sequence != self.sequence || held.terminal.is_some() {
            return Err(invalid());
        }
        let at = format!("{:.3}", jiff::Timestamp::now());
        if at < self.at {
            return Err(invalid());
        }
        t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,?,?,'applying','completed','completed',?)",
            params![intent.operation_id,self.sequence+1,at,encode(&Event::Completed {result:result.clone()})?]).map_err(database)?;
        t.execute(
            "UPDATE operation SET state='completed',finished_at=? WHERE operation_id=?",
            params![at, intent.operation_id],
        )
        .map_err(database)?;
        self.sequence += 1;
        self.at = at;
        self.terminal = Some(result);
        Ok(())
    }

    pub fn checkpoint(&self, connection: &Connection, intent: &Intent) -> Result<Checkpoint> {
        if self.terminal.is_some() {
            return Err(invalid());
        }
        Ok(Checkpoint {
            kind: Kind::Set,
            operation_id: intent.operation_id.clone(),
            request_digest: intent.digest()?,
            progress_digest: interruption::progress_digest(
                connection,
                &intent.operation_id,
                self.sequence,
            )?,
        })
    }

    pub fn interrupt(
        &mut self,
        t: &Transaction<'_>,
        intent: &Intent,
        receipt: &Receipt,
    ) -> Result<()> {
        if let Some(Terminal::Interrupted { recovery }) = &self.terminal {
            return if recovery == receipt {
                Ok(())
            } else {
                Err(invalid())
            };
        }
        if self.checkpoint(t, intent)? != receipt.checkpoint {
            return Err(invalid());
        }
        self.finish(
            t,
            intent,
            Terminal::Interrupted {
                recovery: receipt.clone(),
            },
        )
    }

    pub fn view(&self, intent: &Intent) -> Result<Value> {
        let terminal = self.terminal.as_ref().ok_or_else(invalid)?;
        let state = match terminal {
            Terminal::Published { .. } => "published",
            Terminal::Refused { .. } => "refused",
            Terminal::Interrupted { .. } => "interrupted",
        };
        let mut value = json!({"schema_version":1,"operation_id":intent.operation_id,"intent_digest":intent.digest()?,"state":state,"outcome":terminal});
        if state == "interrupted" {
            value["remote_outcome"] = "unknown".into();
        }
        Ok(value)
    }
}
