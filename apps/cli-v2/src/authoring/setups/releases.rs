//! Setup snapshots freeze an owned complete draft without advancing its head.

use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{
    authoring::{Identity, expiry},
    digest,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
    selection::graph,
    store::{
        Store, database, journal, revisions,
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
    Failure::input("the setup release plan violates its exact draft or version contract")
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

fn build(connection: &Connection, mut draft: Value, version: &str) -> Result<(Value, Vec<u8>)> {
    if draft.get("components").is_none() {
        return Err(Failure::precondition(
            "complete the setup draft with exact released members before release",
        ));
    }
    super::drafts::verify(connection, &draft)?;
    let members = draft["components"].as_array().ok_or_else(invalid)?;
    let closure = graph::exact(connection, members)?;
    if closure["resolved"] != true
        || closure["nodes"].as_array().ok_or_else(invalid)?.len() != members.len()
    {
        return Err(Failure::precondition(
            "the setup's complete exact graph is no longer eligible for release",
        ));
    }
    draft["version"] = version.into();
    draft["parent_revision_ids"] = json!([]);
    super::finish(draft)
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
    let passport = store.transaction(|t| {
        let draft = super::drafts::current(t, id, expected_revision, &identity)?;
        build(t, draft, &versions::next(t, id, increment)?).map(|(document, _)| document)
    })?;
    Ok(Plan {
        schema_version: 1,
        action: "setup.version.release".into(),
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
        || plan.action != "setup.version.release"
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected_digest
    {
        return Err(invalid());
    }
    store.transaction(|t| {
        if let Some(state) = journal::state(t, &plan.operation_id, &plan.action, expected_digest)? {
            if state != "verified" { return Err(invalid()); }
            let held = Objects { connection:t }.exact_version(&plan.stable_id, plan.passport["version"].as_str().ok_or_else(invalid)?, None)?;
            if held != plan.passport { return Err(invalid()); }
            super::verify(t, &held)?;
            return Ok(held);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
            return Err(Failure::precondition("the setup release plan is not within its validity interval"));
        }
        let draft = super::drafts::current(t, &plan.stable_id, &plan.expected_revision, identity)?;
        let version = versions::next(t, &plan.stable_id, plan.increment)?;
        if plan.passport["version"] != version {
            return Err(Failure::new(ErrorKind::Conflict, "the next immutable setup version changed after planning"));
        }
        let (document, payload) = build(t, draft, &version)?;
        if document != plan.passport { return Err(invalid()); }
        revisions::content(t, &payload, at)?;
        let held = versions::record(t, &document, &identity.device_id, Some(&plan.operation_id), at)?;
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        Ok(held)
    })
}
