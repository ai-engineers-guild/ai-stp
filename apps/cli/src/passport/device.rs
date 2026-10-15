//! Private device context derived from this runtime, never from caller claims.

use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

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
    pub expected_revision: Option<String>,
    pub passport: Value,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

fn invalid() -> Failure {
    Failure::precondition(
        "the device context must contain this runtime's exact private observations",
    )
}

fn conflict() -> Failure {
    Failure::new(
        ErrorKind::Conflict,
        "the device context changed after planning",
    )
}

fn current(connection: &Connection, identity: &Identity) -> Result<Option<Value>> {
    let mut query = connection
        .prepare("SELECT stable_id FROM entity WHERE kind='device' LIMIT 2")
        .map_err(database)?;
    let ids = query
        .query_map([], |r| r.get::<_, String>(0))
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if ids.len() > 1 || ids.first().is_some_and(|id| *id != identity.device_id) {
        return Err(invalid());
    }
    ids.first()
        .map(|id| {
            let objects = Objects { connection };
            objects.require_active(id)?;
            objects.head("device", id)
        })
        .transpose()
}

fn observations() -> Result<Value> {
    let os = match std::env::consts::OS {
        "linux" => "linux",
        "macos" => "macos",
        "windows" => "windows",
        _ => return Err(invalid()),
    };
    let arch = match std::env::consts::ARCH {
        "x86_64" => "x86_64",
        "aarch64" => "arm64",
        _ => return Err(invalid()),
    };
    // Execution platform, not a hardware inventory or evidence of installed
    // harnesses. In particular, translation layers may run a different ISA.
    Ok(json!({"operating_system":os,"architecture":arch,
        "tool_versions":[format!("ai-stp-cli-v2={}", env!("CARGO_PKG_VERSION"))]}))
}

fn build(before: Option<Value>, identity: &Identity, at: &str) -> Result<Value> {
    let fresh = observations()?;
    let new = before.is_none();
    let mut document = match before {
        Some(document) => {
            if document["stable_id"] != identity.device_id
                || document["owner_id"] != identity.account_id
                || document["visibility"] != "private"
            {
                return Err(invalid());
            }
            let facts = document["facts"].as_object().ok_or_else(invalid)?;
            if facts.iter().any(|(key, fact)| {
                fresh.get(key).is_none()
                    || fact["origin"] != "observed"
                    || fact["confirmation"] != "none"
                    || !fact["observed_at"]
                        .as_str()
                        .is_some_and(passport::timestamp)
            }) {
                return Err(invalid());
            }
            document
        }
        None => revisions::seal(&json!({"kind":"device","stable_id":identity.device_id,
            "owner_id":identity.account_id,"created_at":at,"visibility":"private","facts":{}}))?,
    };
    let previous_revision = document["revision_id"].clone();
    let mut changed = false;
    for (key, value) in fresh.as_object().ok_or_else(invalid)? {
        if document["facts"][key]["value"] != *value {
            document["facts"][key] = json!({"value":value,"origin":"observed",
                "confirmation":"none","observed_at":at});
            changed = true;
        }
    }
    if !changed {
        return Ok(document);
    }
    if !new {
        document["parent_revision_ids"] = json!([previous_revision]);
    }
    revisions::seal(&document)
}

pub fn plan(store: &mut Store, identity: Identity, at: &str) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    store.transaction(|t| {
        let before = current(t, &identity)?;
        let expected_revision = before
            .as_ref()
            .and_then(|p| p["revision_id"].as_str())
            .map(str::to_owned);
        let passport = build(before, &identity, at)?;
        Ok(Plan {
            schema_version: 1,
            action: "passport.device.record".into(),
            operation_id: format!("operation_{}", ulid::Ulid::generate()),
            created_at: at.into(),
            expires_at,
            identity,
            expected_revision,
            passport,
        })
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
        || plan.action != "passport.device.record"
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
            if state != "verified" {
                return Err(invalid());
            }
            let held = Objects { connection: t }.revision(
                plan.passport["revision_id"].as_str().ok_or_else(invalid)?,
            )?;
            if held != plan.passport {
                return Err(invalid());
            }
            return Ok(held);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
            return Err(Failure::precondition("the device context plan is outside its validity interval"));
        }
        let before = current(t, identity)?;
        if before.as_ref().and_then(|p| p["revision_id"].as_str()) != plan.expected_revision.as_deref() {
            return Err(conflict());
        }
        // Re-observe inside the write transaction. A freshly hashed plan file
        // cannot turn a caller's platform/version/inventory claims into facts.
        let after = build(before, identity, &plan.created_at)?;
        if after != plan.passport {
            return Err(invalid());
        }
        t.execute(
            "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id, plan.action, at, at, expected_digest],
        ).map_err(database)?;
        let heads: Vec<_> = plan.expected_revision.iter().cloned().collect();
        revisions::commit(
            t, &after, &identity.device_id, Some(&plan.operation_id),
            Write::Advance { expected_heads: &heads },
        )
    })
}
