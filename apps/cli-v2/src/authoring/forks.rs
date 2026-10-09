//! Exact component copies with atomic draft, lineage and operation receipts.

use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Identity, expiry, freezing};
use crate::{
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
pub struct Source {
    pub stable_id: String,
    pub version: String,
    pub passport_digest: String,
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
    pub source: Source,
    pub passport: Value,
}

fn invalid() -> Failure {
    Failure::input("the component fork plan violates its source or copy contract")
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

fn seed(
    connection: &Connection,
    source: &Source,
    id: &str,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    if !passport::stable_id(&source.stable_id, "component")
        || !passport::stable_id(id, "component")
        || source.stable_id == id
    {
        return Err(invalid());
    }
    let mut document = Objects { connection }.exact_version(
        &source.stable_id,
        &source.version,
        Some(&source.passport_digest),
    )?;
    freezing::verify(connection, &document)?;
    document["stable_id"] = id.into();
    document["owner_id"] = identity.account_id.clone().into();
    document["created_at"] = at.into();
    document["visibility"] = "private".into();
    document["parent_revision_ids"] = json!([]);
    revisions::seal(&document)
}

pub fn plan(store: &mut Store, source: Source, identity: Identity, at: &str) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    let id = format!("component_{}", ulid::Ulid::generate());
    let passport = store.transaction(|t| seed(t, &source, &id, &identity, at))?;
    Ok(Plan {
        schema_version: 1,
        action: "component.fork".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
        source,
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
        || plan.action != "component.fork"
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected_digest
    {
        return Err(invalid());
    }
    let id = plan.passport["stable_id"].as_str().ok_or_else(invalid)?;
    store.transaction(|t| {
        if let Some(state) = journal::state(t,&plan.operation_id,&plan.action,expected_digest)? {
            if state != "verified" { return Err(invalid()); }
            let document = Objects {connection:t}.revision(plan.passport["revision_id"].as_str().ok_or_else(invalid)?)?;
            let origin: Option<(String,String,String,String)> = t.query_row(
                "SELECT source_stable_id,source_version,source_digest,created_at FROM fork_origin WHERE stable_id=?",
                [id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).optional().map_err(database)?;
            let expected = (plan.source.stable_id.clone(),plan.source.version.clone(),plan.source.passport_digest.clone(),plan.created_at.clone());
            if document != plan.passport || origin.as_ref() != Some(&expected) { return Err(invalid()); }
            freezing::verify(t,&document)?;
            return Ok(document);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() { return Err(Failure::precondition("the fork plan is not within its validity interval")); }
        let exists: bool = t.query_row("SELECT EXISTS(SELECT 1 FROM entity WHERE stable_id=?)",[id],|r|r.get(0)).map_err(database)?;
        if exists { return Err(Failure::new(ErrorKind::Conflict,"the planned fork identity already exists")); }
        let document = seed(t,&plan.source,id,identity,&plan.created_at)?;
        if document != plan.passport { return Err(invalid()); }
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        let document = revisions::commit(t,&document,&identity.device_id,Some(&plan.operation_id),Write::Advance {expected_heads:&[]})?;
        t.execute("INSERT INTO fork_origin(stable_id,source_stable_id,source_version,source_digest,created_at) VALUES (?,?,?,?,?)",
            params![id,plan.source.stable_id,plan.source.version,plan.source.passport_digest,plan.created_at]).map_err(database)?;
        Ok(document)
    })
}
