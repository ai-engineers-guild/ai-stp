//! Durable original intent, append-only observations and recovery interruption.

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    invalid,
    model::{self, Effect, Interruption, KIND, LIMIT, Plan},
};
use crate::{
    canonical, digest,
    error::Result,
    passport,
    store::{database, journal},
};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Checkpoint {
    pub operation_id: String,
    pub plan_digest: String,
    pub progress_digest: String,
}

impl Checkpoint {
    pub(crate) fn validate(&self) -> Result<()> {
        if !passport::stable_id(&self.operation_id, "operation")
            || !model::hash(&self.plan_digest)
            || !model::hash(&self.progress_digest)
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Evidence {
    plan_digest: String,
    effect: Effect,
}

fn encode(value: &impl Serialize) -> Result<String> {
    let bytes = canonical::bytes(&serde_json::to_value(value).map_err(|_| invalid())?)?;
    if bytes.len() as u64 > LIMIT {
        return Err(invalid());
    }
    String::from_utf8(bytes).map_err(|_| invalid())
}

fn progress(sequence: i64, evidence: &Value) -> Result<String> {
    digest::canonical(
        "ai-stp:plan:v1",
        &json!({"sequence":sequence,"evidence":evidence}),
    )
}

pub(super) struct Record {
    pub plan: Plan,
    pub effect: Option<Effect>,
    pub interruption: Option<Interruption>,
    pub state: String,
    sequence: i64,
    at: String,
    progress: String,
}

impl Record {
    pub fn load(connection: &Connection, id: &str) -> Result<Option<Self>> {
        if !passport::stable_id(id, "operation") {
            return Err(invalid());
        }
        let row: Option<(String, String, String, Option<String>, String)> = connection.query_row(
            "SELECT kind,state,started_at,finished_at,coalesce(detail,'') FROM operation WHERE operation_id=?",
            [id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?))).optional().map_err(database)?;
        let Some((kind, state, started, finished, hash)) = row else {
            return Ok(None);
        };
        if kind != KIND || !model::hash(&hash) {
            return Err(invalid());
        }
        let mut query = connection.prepare(
            "SELECT sequence,at,state_before,state_after,result,CASE WHEN length(CAST(evidence AS BLOB))<=262144 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? ORDER BY sequence LIMIT 1025"
        ).map_err(database)?;
        let events = query
            .query_map([id], |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, String>(3)?,
                    r.get::<_, String>(4)?,
                    r.get::<_, String>(5)?,
                ))
            })
            .map_err(database)?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(database)?;
        if events.is_empty() || events.len() > 1024 {
            return Err(invalid());
        }
        let first = &events[0];
        let original = canonical::parse(first.5.as_bytes())?;
        let plan: Plan = serde_json::from_value(original.clone()).map_err(|_| invalid())?;
        if first.0 != 1
            || first.1 != started
            || first.2 != "planned"
            || first.3 != "applying"
            || first.4 != "admitted"
            || plan.operation_id != id
            || plan.digest()? != hash
            || digest::canonical("ai-stp:plan:v1", &original)? != hash
            || !passport::timestamp(&started)
            || started < plan.created_at
            || started >= plan.expires_at
        {
            return Err(invalid());
        }
        let mut held = Self {
            plan,
            effect: None,
            interruption: None,
            state: "applying".into(),
            sequence: 1,
            at: started,
            progress: progress(1, &original)?,
        };
        for event in events.iter().skip(1) {
            let raw = canonical::parse(event.5.as_bytes())?;
            let evidence: Evidence = serde_json::from_value(raw.clone()).map_err(|_| invalid())?;
            if event.0 != held.sequence + 1
                || event.1 < held.at
                || !passport::timestamp(&event.1)
                || event.2 != held.state
                || evidence.plan_digest != hash
                || canonical::bytes(&raw)?
                    != canonical::bytes(&serde_json::to_value(&evidence).map_err(|_| invalid())?)?
                || !matches!(held.state.as_str(), "applying" | "interrupted")
            {
                return Err(invalid());
            }
            evidence.effect.validate(&held.plan)?;
            let after = if let Effect::Retired { retirement } = &evidence.effect {
                if retirement.source != held.checkpoint()? {
                    return Err(invalid());
                }
                "retired"
            } else if let Effect::Interrupted { retirement } = &evidence.effect {
                if held.state != "applying"
                    || held.interruption.is_some()
                    || retirement.checkpoint.progress_digest != held.progress
                {
                    return Err(invalid());
                }
                held.interruption = Some(retirement.clone());
                "interrupted"
            } else {
                "completed"
            };
            if event.3 != after || event.4 != after {
                return Err(invalid());
            }
            held.sequence = event.0;
            held.at = event.1.clone();
            held.state = after.into();
            held.progress = progress(event.0, &raw)?;
            held.effect = Some(evidence.effect);
        }
        if held.state != state
            || finished.as_deref()
                != if state == "applying" {
                    None
                } else {
                    Some(held.at.as_str())
                }
        {
            return Err(invalid());
        }
        Ok(Some(held))
    }

    pub fn checkpoint(&self) -> Result<Checkpoint> {
        let checkpoint = Checkpoint {
            operation_id: self.plan.operation_id.clone(),
            plan_digest: self.plan.digest()?,
            progress_digest: self.progress.clone(),
        };
        checkpoint.validate()?;
        Ok(checkpoint)
    }

    pub fn admit(t: &Transaction<'_>, plan: &Plan, at: &str) -> Result<Self> {
        let hash = plan.digest()?;
        if let Some(held) = Self::load(t, &plan.operation_id)? {
            if held.plan.digest()? != hash {
                return Err(invalid());
            }
            return Ok(held);
        }
        if !passport::timestamp(at)
            || at < plan.created_at.as_str()
            || at >= plan.expires_at.as_str()
        {
            return Err(invalid());
        }
        journal::recovery_capacity(t, 1)?;
        let evidence = encode(plan)?;
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?,?,'applying',?,?)", params![plan.operation_id,KIND,at,hash]).map_err(database)?;
        t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,1,?,'planned','applying','admitted',?)", params![plan.operation_id,at,evidence]).map_err(database)?;
        Self::load(t, &plan.operation_id)?.ok_or_else(invalid)
    }

    pub fn save(&mut self, t: &Transaction<'_>, effect: Effect, at: &str) -> Result<()> {
        effect.validate(&self.plan)?;
        if matches!(self.state.as_str(), "completed" | "retired")
            || !passport::timestamp(at)
            || at < self.at.as_str()
        {
            return Err(invalid());
        }
        if self.state == "interrupted"
            && !matches!(
                &effect,
                Effect::Requested {
                    outcome_reader: Some(_),
                    ..
                } | Effect::Confirmed {
                    outcome_reader: Some(_),
                    ..
                } | Effect::Retired { .. }
            )
        {
            return Err(invalid());
        }
        if let Effect::Interrupted { retirement } = &effect
            && (self.state != "applying" || retirement.checkpoint != self.checkpoint()?)
        {
            return Err(invalid());
        }
        if let Effect::Retired { retirement } = &effect
            && retirement.source != self.checkpoint()?
        {
            return Err(invalid());
        }
        let after = if matches!(&effect, Effect::Retired { .. }) {
            "retired"
        } else if matches!(&effect, Effect::Interrupted { .. }) {
            "interrupted"
        } else {
            "completed"
        };
        let hash = self.plan.digest()?;
        let evidence = Evidence {
            plan_digest: hash.clone(),
            effect,
        };
        let text = encode(&evidence)?;
        let sequence = self.sequence.checked_add(1).ok_or_else(invalid)?;
        if sequence > 1024 {
            return Err(invalid());
        }
        let changed = t.execute("UPDATE operation SET state=?,finished_at=? WHERE operation_id=? AND kind=? AND detail=? AND state=?", params![after,at,self.plan.operation_id,KIND,hash,self.state]).map_err(database)?;
        if changed != 1 {
            return Err(invalid());
        }
        t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,?,?,?,?,?,?)", params![self.plan.operation_id,sequence,at,self.state,after,after,text]).map_err(database)?;
        *self = Self::load(t, &self.plan.operation_id)?.ok_or_else(invalid)?;
        Ok(())
    }

    pub fn output(&self) -> Result<Value> {
        Ok(
            json!({"schema_version":1,"operation_id":self.plan.operation_id,"plan_digest":self.plan.digest()?,
            "plan":self.plan,"state":self.state,"effect":self.effect,"interrupted":self.interruption.is_some(),
            "observed_at":self.at,"online_verified":false,"installation_authority":false,
            "original_request_key":if matches!(self.plan.change, model::Change::Request { .. }) {Some(self.plan.request_key())} else {None}}),
        )
    }
}
