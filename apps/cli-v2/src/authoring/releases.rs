//! Planned component releases: exact draft, number and artifacts in one commit.

use rusqlite::params;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{Identity, expiry, freezing, passports};
use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
    store::{
        Store, database, journal,
        versions::{self, Increment},
    },
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub identity: Identity,
    pub stable_id: String,
    pub expected_revision: String,
    pub increment: Increment,
    pub passport: Value,
}

fn invalid() -> Failure {
    Failure::input("the component release plan violates its identity or result contract")
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

pub fn plan(
    store: &mut Store,
    id: &str,
    expected_revision: &str,
    increment: Increment,
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    let passport = store.transaction(|transaction| {
        let draft = passports::current(transaction, id, expected_revision, &identity)?;
        let version = versions::next(transaction, id, increment)?;
        freezing::compile(transaction, draft, &version, None)
    })?;
    Ok(Plan {
        schema_version: 1,
        action: "component.version.release".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
        stable_id: id.into(),
        expected_revision: expected_revision.into(),
        increment,
        passport,
    })
}

pub fn apply(
    store: &mut Store,
    plan: &Plan,
    expected_digest: &str,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    identity.validate()?;
    if plan.schema_version != 1
        || plan.action != "component.version.release"
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected_digest
    {
        return Err(invalid());
    }
    store.transaction(|transaction| {
        if let Some(state) = journal::state(transaction,&plan.operation_id,&plan.action,expected_digest)? {
            if state != "verified" { return Err(invalid()); }
            let document = Objects { connection:transaction }.exact_version(&plan.stable_id,
                plan.passport["version"].as_str().ok_or_else(invalid)?,None)?;
            if document != plan.passport { return Err(invalid()); }
            freezing::verify(transaction,&document)?;
            return Ok(document);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
            return Err(Failure::precondition("the release plan is not within its validity interval"));
        }
        let draft = passports::current(transaction,&plan.stable_id,&plan.expected_revision,identity)?;
        let version = versions::next(transaction,&plan.stable_id,plan.increment)?;
        if plan.passport["version"] != version {
            return Err(Failure::new(ErrorKind::Conflict,"the next immutable version changed after planning"));
        }
        let document = freezing::compile(transaction,draft,&version,Some(at))?;
        if document != plan.passport { return Err(invalid()); }
        transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        versions::record(transaction,&document,&identity.device_id,Some(&plan.operation_id),at)
    })
}
