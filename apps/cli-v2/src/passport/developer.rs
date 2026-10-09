//! One private developer context with explicit declarations and exact head plans.

use std::{collections::BTreeSet, path::Path};

use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{
    authoring::{Identity, expiry},
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files,
    objects::Objects,
    passport,
    store::{
        Store, database, journal,
        revisions::{self, Write},
    },
};

const MAX_PATCH: usize = 16 * 1024;

fn invalid() -> Failure {
    Failure::input("the developer passport plan or declaration violates its closed contract")
}

fn conflict() -> Failure {
    Failure::new(
        ErrorKind::Conflict,
        "the developer context changed after planning",
    )
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(try_from = "Value", into = "Value")]
pub struct Patch(Value);

fn validate_values(value: &Value) -> Result<()> {
    let object = value.as_object().ok_or_else(invalid)?;
    for (key, value) in object {
        let text = |value: &Value, limit| {
            value.as_str().is_some_and(|s| {
                s.len() <= limit && !s.chars().any(|c| c.is_control() && c != '\n' && c != '\t')
            })
        };
        let valid = match key.as_str() {
            "role" | "autonomy" => text(value, 4096),
            "typical_tasks" | "priorities" | "preferred_languages" | "preferred_harnesses" => {
                value.as_array().is_some_and(|items| {
                    items.len() <= 64
                        && items.iter().all(|v| {
                            text(v, 1024) && v.as_str().is_some_and(|s| !s.trim().is_empty())
                        })
                        && items
                            .iter()
                            .filter_map(Value::as_str)
                            .collect::<BTreeSet<_>>()
                            .len()
                            == items.len()
                })
            }
            _ => false,
        };
        if !valid {
            return Err(invalid());
        }
    }
    Ok(())
}

impl TryFrom<Value> for Patch {
    type Error = Failure;
    fn try_from(value: Value) -> Result<Self> {
        let bytes = canonical::bytes(&value)?;
        if bytes.len() > MAX_PATCH {
            return Err(invalid());
        }
        let value = canonical::parse(&bytes)?;
        validate_values(&value)?;
        if value.as_object().is_none_or(|object| object.is_empty()) {
            return Err(invalid());
        }
        Ok(Self(value))
    }
}

impl From<Patch> for Value {
    fn from(value: Patch) -> Self {
        value.0
    }
}

impl Patch {
    pub fn read(path: &Path) -> Result<Self> {
        Self::parse(&files::read(path, MAX_PATCH as u64)?)
    }
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        if bytes.len() > MAX_PATCH {
            return Err(invalid());
        }
        Self::try_from(canonical::parse(bytes)?)
    }
}

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
    pub expected_revision: Option<String>,
    pub patch: Option<Patch>,
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

/// Ambiguous state must never silently choose the oldest profile.
pub(crate) fn current(connection: &Connection) -> Result<Option<Value>> {
    let mut query = connection
        .prepare("SELECT stable_id FROM entity WHERE kind='developer' LIMIT 2")
        .map_err(database)?;
    let ids = query
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if ids.len() > 1 {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "the registry contains multiple developer contexts",
        ));
    }
    ids.first()
        .map(|id| {
            let objects = Objects { connection };
            objects.require_active(id)?;
            objects.head("developer", id)
        })
        .transpose()
}

fn build(
    before: Option<Value>,
    id: &str,
    patch: Option<&Patch>,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    if !passport::stable_id(id, "developer") {
        return Err(invalid());
    }
    let mut document = match before {
        Some(document) => {
            if document["stable_id"] != id
                || document["owner_id"] != identity.account_id
                || document["visibility"] != "private"
            {
                return Err(Failure::precondition(
                    "the developer context must be private and owned by this local identity",
                ));
            }
            let facts = document["facts"].as_object().ok_or_else(invalid)?;
            let values = Value::Object(
                facts
                    .iter()
                    .map(|(k, v)| (k.clone(), v["value"].clone()))
                    .collect(),
            );
            validate_values(&values)?;
            if facts.values().any(|v| v["origin"] != "declared") {
                return Err(invalid());
            }
            document
        }
        None if patch.is_none() => {
            return revisions::seal(&json!({"kind":"developer","stable_id":id,
            "owner_id":identity.account_id,"created_at":at,"visibility":"private","facts":{}}));
        }
        None => {
            return Err(Failure::new(
                ErrorKind::NotFound,
                "initialize the developer passport before declaring preferences",
            ));
        }
    };
    let Some(patch) = patch else {
        return Ok(document);
    };
    let mut changed = false;
    for (key, value) in patch.0.as_object().ok_or_else(invalid)? {
        let held = &document["facts"][key];
        if held["value"] == *value && held["confirmation"] == "user_confirmed" {
            continue;
        }
        document["facts"][key] = json!({"value":value,"origin":"declared","confirmation":"user_confirmed","confirmed_at":at});
        changed = true;
    }
    if !changed {
        return Ok(document);
    }
    document["parent_revision_ids"] = json!([document["revision_id"]]);
    revisions::seal(&document)
}

pub fn plan(
    store: &mut Store,
    expected_revision: Option<&str>,
    patch: Option<Patch>,
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    if expected_revision.is_some() != patch.is_some() {
        return Err(invalid());
    }
    store.transaction(|t| {
        let before = current(t)?;
        let expected = before
            .as_ref()
            .and_then(|p| p["revision_id"].as_str())
            .map(str::to_owned);
        if patch.is_some() && expected.as_deref() != expected_revision {
            return Err(conflict());
        }
        let id = before
            .as_ref()
            .and_then(|p| p["stable_id"].as_str())
            .map(str::to_owned)
            .unwrap_or_else(|| format!("developer_{}", ulid::Ulid::generate()));
        let passport = build(before, &id, patch.as_ref(), &identity, at)?;
        Ok(Plan {
            schema_version: 1,
            action: "passport.developer.record".into(),
            operation_id: format!("operation_{}", ulid::Ulid::generate()),
            created_at: at.into(),
            expires_at,
            identity,
            stable_id: id,
            expected_revision: expected,
            patch,
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
        || plan.action != "passport.developer.record"
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected_digest
        || (plan.patch.is_some() && plan.expected_revision.is_none())
    {
        return Err(invalid());
    }
    store.transaction(|t| {
        if let Some(state) = journal::state(t,&plan.operation_id,&plan.action,expected_digest)? {
            if state != "verified" { return Err(invalid()); }
            let held = Objects { connection:t }.revision(plan.passport["revision_id"].as_str().ok_or_else(invalid)?)?;
            if held != plan.passport { return Err(invalid()); }
            return Ok(held);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
            return Err(Failure::precondition("the developer passport plan is outside its validity interval"));
        }
        let before = current(t)?;
        if before.as_ref().and_then(|p|p["revision_id"].as_str()) != plan.expected_revision.as_deref() { return Err(conflict()); }
        let after = build(before,&plan.stable_id,plan.patch.as_ref(),identity,&plan.created_at)?;
        if after != plan.passport { return Err(invalid()); }
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        let heads: Vec<_> = plan.expected_revision.iter().cloned().collect();
        revisions::commit(t,&after,&identity.device_id,Some(&plan.operation_id),Write::Advance {expected_heads:&heads})
    })
}

pub fn show(store: &mut Store) -> Result<Value> {
    store.transaction(|t| {
        current(t)?.map(|p| passport::view(&p)).ok_or_else(|| {
            Failure::new(ErrorKind::NotFound, "the developer passport does not exist")
        })
    })
}
