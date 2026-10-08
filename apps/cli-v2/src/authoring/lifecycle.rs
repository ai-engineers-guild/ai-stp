//! Planned local tombstones retain history and never mutate a harness or account.

use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Identity, expiry, passports};
use crate::{
    digest,
    error::{Failure, Result},
    objects::Objects,
    passport,
    store::{Store, database, journal},
};

const REASON: &str = "forgotten_by_owner";

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
}

fn invalid() -> Failure {
    Failure::precondition("the component forget plan or its retained receipt is invalid")
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
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    store.transaction(|t| passports::current(t, id, expected_revision, &identity))?;
    Ok(Plan {
        schema_version: 1,
        action: "component.forget".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
        stable_id: id.into(),
        expected_revision: expected_revision.into(),
    })
}

fn receipt(connection: &Connection, plan: &Plan) -> Result<Value> {
    let document = Objects { connection }.revision(&plan.expected_revision)?;
    let held: Option<(String, String)> = connection
        .query_row(
            "SELECT reason,created_at FROM tombstone WHERE stable_id=?",
            [&plan.stable_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()
        .map_err(database)?;
    if document["kind"] != "component"
        || document["stable_id"] != plan.stable_id
        || document["owner_id"] != plan.identity.account_id
        || held
            .as_ref()
            .is_none_or(|(reason, at)| reason != REASON || at != &plan.created_at)
    {
        return Err(invalid());
    }
    Ok(json!({"schema_version":1,"stable_id":plan.stable_id,
        "revision_id":plan.expected_revision,"state":"forgotten"}))
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
        || plan.action != "component.forget"
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::stable_id(&plan.stable_id, "component")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected_digest
    {
        return Err(invalid());
    }
    store.transaction(|t| {
        if let Some(state) = journal::state(t, &plan.operation_id, &plan.action, expected_digest)? {
            if state != "verified" {
                return Err(invalid());
            }
            return receipt(t, plan);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
            return Err(Failure::precondition(
                "the forget plan is not within its validity interval",
            ));
        }
        passports::current(t, &plan.stable_id, &plan.expected_revision, identity)?;
        t.execute(
            "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id, plan.action, at, at, expected_digest],
        ).map_err(database)?;
        t.execute(
            "INSERT INTO tombstone(stable_id,reason,created_at) VALUES (?,?,?)",
            params![plan.stable_id, REASON, plan.created_at],
        ).map_err(database)?;
        receipt(t, plan)
    })
}
