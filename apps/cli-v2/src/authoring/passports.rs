//! Confirmed draft facts, bound to one exact head and an atomic journal receipt.

use std::path::Path;

use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Identity, expiry};
use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files,
    objects::Objects,
    passport,
    store::{
        Store, database, journal,
        revisions::{self, Write},
    },
    wire::Schema,
};

const MAX_PATCH: usize = 256 * 1024;
static PATCH: Schema = Schema::new(include_str!(
    "../../../../schemas/v1/cli-component-passport-patch.schema.json"
));

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(try_from = "Value", into = "Value")]
pub struct Patch(Value);

fn invalid() -> Failure {
    Failure::input("the component passport patch violates its closed contract")
}

fn secret_fields(value: &Value) -> bool {
    match value {
        Value::Object(object) => object.iter().any(|(key, value)| {
            matches!(
                key.to_lowercase().replace('-', "_").as_str(),
                "api_key"
                    | "apikey"
                    | "access_token"
                    | "auth_token"
                    | "credential_value"
                    | "password"
                    | "private_key"
                    | "secret"
                    | "secret_value"
                    | "token"
            ) || secret_fields(value)
        }),
        Value::Array(items) => items.iter().any(secret_fields),
        _ => false,
    }
}

impl TryFrom<Value> for Patch {
    type Error = Failure;

    fn try_from(value: Value) -> Result<Self> {
        let encoded = canonical::bytes(&value)?;
        if encoded.len() > MAX_PATCH {
            return Err(invalid());
        }
        let value = canonical::parse(&encoded)?;
        let object = value.as_object().ok_or_else(invalid)?;
        if object.is_empty() || object.values().any(Value::is_null) || secret_fields(&value) {
            return Err(invalid());
        }
        PATCH.validate(&value)?;
        if let Some(description) = value.get("description").and_then(Value::as_str) {
            passport::markdown::validate(description)?;
        }
        if let Some(source) = value.get("source") {
            let repository = source["repository"].as_str().ok_or_else(invalid)?;
            let url = url::Url::parse(repository).map_err(|_| invalid())?;
            if url.scheme() != "https"
                || url.host_str().is_none()
                || !url.username().is_empty()
                || url.password().is_some()
                || url.query().is_some()
                || url.fragment().is_some()
                || repository.contains('\\')
                || repository.chars().any(char::is_control)
            {
                return Err(invalid());
            }
            let path = source["path"].as_str().ok_or_else(invalid)?;
            if path.is_empty() || path.starts_with('/') || path.split('/').any(|part| part == "..")
            {
                return Err(invalid());
            }
        }
        for path in value["managed_paths"].as_array().into_iter().flatten() {
            let path = path.as_str().ok_or_else(invalid)?;
            if path.starts_with(['/', '\\'])
                || path == ".."
                || ["../", "/..", "\\..", "..\\"]
                    .iter()
                    .any(|part| path.contains(part))
            {
                return Err(invalid());
            }
        }
        Ok(Self(value))
    }
}

impl From<Patch> for Value {
    fn from(patch: Patch) -> Self {
        patch.0
    }
}

impl Patch {
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        if bytes.len() > MAX_PATCH {
            return Err(invalid());
        }
        Self::try_from(canonical::parse(bytes)?)
    }

    pub fn read(path: &Path) -> Result<Self> {
        Self::parse(&files::read(path, MAX_PATCH as u64)?)
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
    pub expected_revision: String,
    pub patch: Patch,
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

pub(super) fn current(
    connection: &Connection,
    id: &str,
    expected: &str,
    identity: &Identity,
) -> Result<Value> {
    if !passport::stable_id(id, "component") {
        return Err(invalid());
    }
    let document = Objects { connection }.head("component", id)?;
    if document["revision_id"] != expected {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "the component head changed after planning",
        ));
    }
    if document["owner_id"] != identity.account_id {
        return Err(Failure::precondition(
            "the authoring identity does not own this component",
        ));
    }
    Ok(document)
}

fn edit(mut document: Value, patch: &Patch, at: &str) -> Result<Value> {
    let patch = patch.0.as_object().ok_or_else(invalid)?;
    let complete = document.get("adaptations").is_some();
    if complete
        && patch.keys().any(|key| {
            !matches!(
                key.as_str(),
                "name"
                    | "description"
                    | "tags"
                    | "source"
                    | "license"
                    | "provides_capabilities"
                    | "requires_components"
                    | "requires_capabilities"
                    | "conflicts"
                    | "required_env"
                    | "requires_credentials"
                    | "requires_authorization"
                    | "external_endpoints"
                    | "runtime_requirements"
            )
        })
    {
        return Err(Failure::precondition(
            "native facts of a complete passport require an explicit adaptation edit",
        ));
    }
    if patch.iter().all(|(key, value)| {
        document["facts"][key]["value"] == *value
            && document["facts"][key]["confirmation"] == "user_confirmed"
            && (!complete || document[key] == *value)
    }) {
        return Ok(document);
    }
    document["parent_revision_ids"] = json!([document["revision_id"]]);
    document["created_at"] = at.into();
    for (key, value) in patch {
        if complete {
            document[key] = value.clone();
        }
        document["facts"][key] = json!({"value":value,"origin":"declared",
            "confirmation":"user_confirmed","confirmed_at":at});
    }
    revisions::seal(&document)
}

pub fn plan(
    store: &mut Store,
    id: &str,
    expected_revision: &str,
    patch: Patch,
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    if !passport::timestamp(at) {
        return Err(invalid());
    }
    let passport = store.transaction(|transaction| {
        edit(
            current(transaction, id, expected_revision, &identity)?,
            &patch,
            at,
        )
    })?;
    Ok(Plan {
        schema_version: 1,
        action: "component.passport.update".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at: expiry(at)?,
        identity,
        stable_id: id.into(),
        expected_revision: expected_revision.into(),
        patch,
        passport,
    })
}

/// Database-only work has no external applying phase: effect and receipt share one commit.
pub fn apply(
    store: &mut Store,
    plan: &Plan,
    expected_digest: &str,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    identity.validate()?;
    if plan.schema_version != 1
        || plan.action != "component.passport.update"
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || !passport::timestamp(&plan.created_at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected_digest
    {
        return Err(invalid());
    }
    store.transaction(|transaction| {
        if let Some(state) = journal::state(transaction,&plan.operation_id,&plan.action,expected_digest)? {
            if state != "verified" { return Err(invalid()); }
            let held = Objects { connection:transaction }.revision(plan.passport["revision_id"].as_str().ok_or_else(invalid)?)?;
            if held != plan.passport { return Err(invalid()); }
            return Ok(held);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
            return Err(Failure::precondition("the passport plan is not within its validity interval"));
        }
        let before = current(transaction,&plan.stable_id,&plan.expected_revision,identity)?;
        let after = edit(before,&plan.patch,&plan.created_at)?;
        if after != plan.passport { return Err(invalid()); }
        transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        revisions::commit(transaction,&after,&identity.device_id,Some(&plan.operation_id),
            Write::Advance {expected_heads:std::slice::from_ref(&plan.expected_revision)})
    })
}
