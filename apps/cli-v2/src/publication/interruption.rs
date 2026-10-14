//! Exact device replacement stops local delivery, retaining unknown remote effects.

use rusqlite::{Connection, Transaction};
use serde::{Deserialize, Serialize};
use serde_json::json;

use super::{
    journal::Attempt,
    runtime::Intent,
    set::{Run, Terminal},
};
use crate::{
    account, canonical, digest,
    error::{Failure, Result},
    passport,
    store::database,
};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Checkpoint {
    #[serde(default, skip_serializing_if = "Kind::is_attempt")]
    pub(crate) kind: Kind,
    pub operation_id: String,
    pub request_digest: String,
    pub progress_digest: String,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Receipt {
    pub checkpoint: Checkpoint,
    pub recovery_operation_id: String,
    pub recovery_plan_digest: String,
    pub replacement_device_id: String,
}

fn invalid() -> Failure {
    Failure::precondition("publication interruption differs from the exact device recovery intent")
}

#[derive(Clone, Copy, Default, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Kind {
    #[default]
    Attempt,
    Set,
}

impl Kind {
    fn is_attempt(&self) -> bool {
        *self == Self::Attempt
    }
}

pub(super) fn hash(value: &str) -> bool {
    value.strip_prefix("sha256:").is_some_and(|v| {
        v.len() == 64
            && v.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}

impl Checkpoint {
    pub(crate) fn validate(&self) -> Result<()> {
        if !passport::stable_id(&self.operation_id, "operation")
            || !hash(&self.request_digest)
            || !hash(&self.progress_digest)
        {
            return Err(invalid());
        }
        Ok(())
    }
}

impl Receipt {
    pub(crate) fn for_plan(checkpoint: &Checkpoint, recovery: &account::Plan) -> Result<Self> {
        let intent = recovery.recovery.as_ref().ok_or_else(invalid)?;
        if recovery.action != account::Action::Recover
            || !intent.interrupted_publications.contains(checkpoint)
        {
            return Err(invalid());
        }
        let receipt = Self {
            checkpoint: checkpoint.clone(),
            recovery_operation_id: recovery.operation_id.clone(),
            recovery_plan_digest: recovery.digest()?,
            replacement_device_id: intent.device_id.clone(),
        };
        receipt.validate()?;
        Ok(receipt)
    }

    pub(super) fn validate(&self) -> Result<()> {
        self.checkpoint.validate()?;
        if !passport::stable_id(&self.recovery_operation_id, "operation")
            || !hash(&self.recovery_plan_digest)
            || !passport::stable_id(&self.replacement_device_id, "device")
        {
            return Err(invalid());
        }
        Ok(())
    }
}

pub(super) fn progress_digest(connection: &Connection, id: &str, sequence: i64) -> Result<String> {
    let bytes: String = connection.query_row(
        "SELECT CASE WHEN length(CAST(evidence AS BLOB))<=16777216 THEN evidence ELSE NULL END FROM operation_event WHERE operation_id=? AND sequence=?",
        rusqlite::params![id,sequence], |r| r.get(0)).map_err(database)?;
    digest::canonical(
        "ai-stp:plan:v1",
        &json!({"sequence":sequence,"evidence":canonical::parse(bytes.as_bytes())?}),
    )
}

pub(crate) fn belongs(binding: &account::access::Binding, recovery: &account::Plan) -> Result<()> {
    let intent = recovery.recovery.as_ref().ok_or_else(invalid)?;
    if binding.root_identity != recovery.root_identity
        || binding.device_id != recovery.identity.device_id
        || binding.public_key != recovery.public_key
        || binding.credential_store != recovery.credential_store
        || binding.origin != recovery.origin
        || Some(binding.account_id.as_str()) != intent.account_id.as_deref()
    {
        return Err(invalid());
    }
    Ok(())
}

enum Subject {
    Attempt(Attempt),
    Set(Box<Intent>, Run),
}

impl Subject {
    fn load(connection: &Connection, id: &str) -> Result<Self> {
        let kind: String = connection
            .query_row(
                "SELECT kind FROM operation WHERE operation_id=?",
                [id],
                |r| r.get(0),
            )
            .map_err(database)?;
        match kind.as_str() {
            "publication.run" => Ok(Self::Attempt(Attempt::load(connection, id)?)),
            "publication.set" => {
                let intent = Run::intent(connection, id)?;
                let run = Run::load(connection, &intent)?.ok_or_else(invalid)?;
                Ok(Self::Set(Box::new(intent), run))
            }
            _ => Err(invalid()),
        }
    }

    fn binding(&self) -> &account::access::Binding {
        match self {
            Self::Attempt(a) => &a.request.account,
            Self::Set(i, _) => &i.account,
        }
    }

    fn checkpoint(&self, connection: &Connection) -> Result<Checkpoint> {
        match self {
            Self::Attempt(a) => a.checkpoint(connection),
            Self::Set(i, r) => r.checkpoint(connection, i),
        }
    }

    fn receipt(&self, connection: &Connection) -> Result<Option<Receipt>> {
        match self {
            Self::Attempt(a) => a.interruption(connection),
            Self::Set(_, r) => Ok(match &r.terminal {
                Some(Terminal::Interrupted { recovery }) => Some(recovery.clone()),
                _ => None,
            }),
        }
    }

    fn interrupt(&mut self, t: &Transaction<'_>, receipt: &Receipt) -> Result<()> {
        match self {
            Self::Attempt(a) => a.interrupt(t, receipt),
            Self::Set(i, r) => r.interrupt(t, i, receipt),
        }
    }
}

pub(crate) fn capture(
    connection: &Connection,
    original: &account::Plan,
    account_id: Option<&str>,
) -> Result<Vec<Checkpoint>> {
    let mut query = connection.prepare(
        "SELECT operation_id FROM operation WHERE kind IN ('publication.run','publication.set') AND finished_at IS NULL ORDER BY operation_id LIMIT 129",
    ).map_err(database)?;
    let ids = query
        .query_map([], |r| r.get::<_, String>(0))
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if ids.len() > 128 {
        return Err(invalid());
    }
    ids.iter()
        .map(|id| {
            let subject = Subject::load(connection, id)?;
            let binding = subject.binding();
            if binding.root_identity != original.root_identity
                || binding.device_id != original.identity.device_id
                || binding.public_key != original.public_key
                || binding.credential_store != original.credential_store
                || binding.origin != original.origin
                || Some(binding.account_id.as_str()) != account_id
            {
                return Err(invalid());
            }
            subject.checkpoint(connection)
        })
        .collect()
}

pub(crate) fn validate(connection: &Connection, recovery: &account::Plan) -> Result<()> {
    let intent = recovery.recovery.as_ref().ok_or_else(invalid)?;
    let current = capture(connection, recovery, intent.account_id.as_deref())?;
    if current
        .iter()
        .any(|c| !intent.interrupted_publications.contains(c))
    {
        return Err(invalid());
    }
    for checkpoint in &intent.interrupted_publications {
        if current.contains(checkpoint) {
            continue;
        }
        let subject = Subject::load(connection, &checkpoint.operation_id)?;
        belongs(subject.binding(), recovery)?;
        if subject.receipt(connection)? != Some(Receipt::for_plan(checkpoint, recovery)?) {
            return Err(invalid());
        }
    }
    Ok(())
}

pub(crate) fn apply(t: &Transaction<'_>, recovery: &account::Plan) -> Result<()> {
    validate(t, recovery)?;
    for checkpoint in &recovery
        .recovery
        .as_ref()
        .ok_or_else(invalid)?
        .interrupted_publications
    {
        let mut subject = Subject::load(t, &checkpoint.operation_id)?;
        subject.interrupt(t, &Receipt::for_plan(checkpoint, recovery)?)?;
    }
    Ok(())
}
