//! Owned setup revisions retain their identity, harness and captured provenance.

use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::Request;
use crate::{
    authoring::{Identity, expiry},
    digest,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
    store::{
        Store, database, journal,
        revisions::{self, Write},
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
    pub request: Request,
    pub passport: Value,
}

fn invalid() -> Failure {
    Failure::input("the setup draft plan violates its exact composition contract")
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

pub(super) fn current(
    connection: &Connection,
    id: &str,
    expected: &str,
    identity: &Identity,
) -> Result<Value> {
    let objects = Objects { connection };
    let document = objects.head("setup", id)?;
    if document["revision_id"] != expected {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "the setup head changed after planning",
        ));
    }
    if document["owner_id"] != identity.account_id || document["visibility"] != "private" {
        return Err(Failure::precondition(
            "setup authoring requires an owned private draft",
        ));
    }
    objects.require_active(id)?;
    Ok(document)
}

pub(super) fn verify(connection: &Connection, document: &Value) -> Result<()> {
    let mut snapshot = document.clone();
    snapshot["parent_revision_ids"] = json!([]);
    super::verify(connection, &revisions::seal(&snapshot)?)
}

fn require_member_summaries(connection: &Connection, before: &Value) -> Result<()> {
    let mut aggregate = super::aggregate::Aggregate::default();
    for reference in before["components"].as_array().ok_or_else(invalid)? {
        let member = Objects { connection }.exact_version(
            reference["stable_id"].as_str().ok_or_else(invalid)?,
            reference["version"].as_str().ok_or_else(invalid)?,
            Some(reference["passport_digest"].as_str().ok_or_else(invalid)?),
        )?;
        aggregate.include(&member)?;
    }
    let mut expected = json!({});
    aggregate.apply(&mut expected);
    if expected
        .as_object()
        .ok_or_else(invalid)?
        .iter()
        .any(|(key, value)| before[key] != *value)
    {
        return Err(Failure::precondition(
            "this setup has additional requirement declarations; composition-only editing cannot replace them",
        ).with_details([("constraint".into(), "setup_requirements_not_derived".into())]));
    }
    Ok(())
}

fn build(
    connection: &Connection,
    before: Value,
    request: &Request,
    identity: &Identity,
    at: &str,
) -> Result<(Value, Vec<u8>)> {
    let harness = before
        .get("harness_id")
        .unwrap_or(&before["facts"]["harness_id"]["value"]);
    if harness != &request.harness_id {
        return Err(Failure::precondition(
            "a setup cannot change its harness; create an explicit recast",
        ));
    }
    let id = before["stable_id"].as_str().ok_or_else(invalid)?;
    if before.get("components").is_some() {
        verify(connection, &before)?;
        require_member_summaries(connection, &before)?;
    }
    let (mut after, _) = super::compile(connection, request, id, identity, at)?;
    // Preserve declarations and lineage, but never carry result/evidence records
    // across a changed composition. Member summaries are rebuilt by compile.
    for key in [
        "version",
        "tags",
        "source",
        "target_role",
        "posture",
        "supported_tasks",
        "execution_profile",
        "supported_harness_versions",
        "supported_os",
        "supported_arch",
        "ported_from",
        "related_setup_ids",
    ] {
        if let Some(value) = before.get(key) {
            after[key] = value.clone();
        }
    }
    let derived = after["facts"].as_object().ok_or_else(invalid)?.clone();
    after["facts"] = before["facts"].clone();
    after["facts"]
        .as_object_mut()
        .ok_or_else(invalid)?
        .extend(derived);
    // Creation-time harness and capture facts keep their original evidence.
    if let Some(fact) = before["facts"].get("harness_id") {
        after["facts"]["harness_id"] = fact.clone();
    }
    for (key, value) in [
        ("name", &request.name),
        ("description", &request.description),
        ("purpose", &request.purpose),
    ] {
        after["facts"][key] = json!({"value":value,"origin":"declared","confirmation":"user_confirmed","confirmed_at":at});
    }
    let (mut after, payload) = super::finish(after)?;
    after["parent_revision_ids"] = json!([before["revision_id"]]);
    Ok((revisions::seal(&after)?, payload))
}

pub fn plan(
    store: &mut Store,
    id: &str,
    expected_revision: &str,
    mut request: Request,
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    super::normalize(&mut request);
    let passport = store.transaction(|t| {
        build(
            t,
            current(t, id, expected_revision, &identity)?,
            &request,
            &identity,
            at,
        )
        .map(|(document, _)| document)
    })?;
    Ok(Plan {
        schema_version: 1,
        action: "setup.passport.update".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
        stable_id: id.into(),
        expected_revision: expected_revision.into(),
        request,
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
        || plan.action != "setup.passport.update"
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
            let held = Objects { connection:t }.revision(plan.passport["revision_id"].as_str().ok_or_else(invalid)?)?;
            if held != plan.passport { return Err(invalid()); }
            verify(t, &held)?;
            return Ok(held);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
            return Err(Failure::precondition("the setup draft plan is not within its validity interval"));
        }
        let before = current(t, &plan.stable_id, &plan.expected_revision, identity)?;
        let (after, payload) = build(t, before, &plan.request, identity, &plan.created_at)?;
        if after != plan.passport { return Err(invalid()); }
        revisions::content(t, &payload, at)?;
        let held = revisions::commit(t, &after, &identity.device_id, Some(&plan.operation_id), Write::Advance { expected_heads:std::slice::from_ref(&plan.expected_revision) })?;
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        Ok(held)
    })
}
