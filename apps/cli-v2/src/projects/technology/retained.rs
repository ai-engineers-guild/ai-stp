//! Atomic, identity-bound local observations. A receipt is historical evidence.

mod storage;

use std::path::{Path, PathBuf};

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{
    authoring::{Identity, expiry},
    digest,
    error::{Failure, Result},
    files, identity,
    objects::Objects,
    passport,
    projects::passports::{self, Registered},
    store::{Store, database},
};

const ACTION: &str = "project.technology.record";
const DETECTOR: &str = "native-technology/1";
const MAX_BYTES: usize = 16 * 1024 * 1024;

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub identity: Identity,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub root: PathBuf,
    pub root_identity: [String; 2],
    pub project_id: String,
    pub expected_revision: String,
    pub scope: String,
    pub expected_findings_digest: String,
    pub observation_digest: String,
}

fn invalid() -> Failure {
    Failure::precondition("the technology observation, registration or retained evidence changed")
}

fn hash(value: &impl Serialize) -> Result<String> {
    // Evidence paths are exact UTF-8. Domain canonicalization normalizes strings.
    let bytes = serde_json_canonicalizer::to_vec(value).map_err(|_| invalid())?;
    if bytes.len() > MAX_BYTES {
        return Err(invalid());
    }
    Ok(digest::sha256(&bytes))
}

fn sha256(value: &str) -> bool {
    value.strip_prefix("sha256:").is_some_and(|v| {
        v.len() == 64
            && v.bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    })
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }

    fn scan_id(&self) -> String {
        self.operation_id.replacen("operation_", "scan_", 1)
    }

    fn validate(&self, identity: &Identity) -> Result<()> {
        identity.validate()?;
        if self.schema_version != 1
            || self.action != ACTION
            || self.identity != *identity
            || !passport::stable_id(&self.operation_id, "operation")
            || !passport::stable_id(&self.project_id, "project")
            || !self
                .expected_revision
                .strip_prefix("revision_")
                .is_some_and(|v| sha256(&format!("sha256:{v}")))
            || self.scope != "repository"
            || !self.root.is_absolute()
            || !sha256(&self.expected_findings_digest)
            || !sha256(&self.observation_digest)
            || self.expires_at != expiry(&self.created_at)?
        {
            return Err(invalid());
        }
        Ok(())
    }
}

fn owned(connection: &Connection, id: &str, identity: &Identity) -> Result<Value> {
    let objects = Objects { connection };
    let project = objects.head("project", id)?;
    objects.require_active(id)?;
    if project["owner_id"] != identity.account_id || project["visibility"] != "private" {
        return Err(invalid());
    }
    Ok(project)
}

fn local_mapping(connection: &Connection, id: &str) -> Result<()> {
    // Organization mappings have a separate authority. Never replace one with
    // the bundled seed while connected detection remains unimplemented.
    let linked: bool = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM project_link WHERE local_project_id=? AND state!='unlinked')",
        [id], |row| row.get(0),
    ).map_err(database)?;
    if linked {
        return Err(Failure::precondition(
            "linked project technology requires an organization mapping",
        ));
    }
    Ok(())
}

fn registered(connection: &Connection, plan: &Plan) -> Result<Registered> {
    local_mapping(connection, &plan.project_id)?;
    let root = passports::registered(connection, &plan.root, &plan.identity)?;
    if root.path != plan.root
        || root.identity != plan.root_identity
        || root.project["stable_id"] != plan.project_id
        || owned(connection, &plan.project_id, &plan.identity)?["revision_id"]
            != plan.expected_revision
    {
        return Err(invalid());
    }
    Ok(root)
}

pub fn plan(store: &mut Store, root: &Path, identity: Identity, at: &str) -> Result<Plan> {
    identity.validate()?;
    let root = passports::registered(&store.connection, root, &identity)?;
    let id = root.project["stable_id"].as_str().ok_or_else(invalid)?;
    owned(&store.connection, id, &identity)?;
    local_mapping(&store.connection, id)?;
    let prior = storage::read(&store.connection, id)?;
    let observation = super::inspect_at(&root.path, &root.directory)?;
    let result = Plan {
        schema_version: 1,
        action: ACTION.into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at: expiry(at)?,
        identity,
        root: root.path,
        root_identity: root.identity,
        project_id: id.into(),
        expected_revision: root.project["revision_id"]
            .as_str()
            .ok_or_else(invalid)?
            .into(),
        scope: "repository".into(),
        expected_findings_digest: storage::state_digest(&store.connection, id, &prior)?,
        observation_digest: hash(&observation)?,
    };
    result.validate(&result.identity)?;
    registered(&store.connection, &result)?;
    storage::merge(prior, &observation, &result.scan_id(), at)?;
    Ok(result)
}

pub fn apply(
    store: &mut Store,
    plan: &Plan,
    expected_digest: &str,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    plan.validate(identity)?;
    if plan.digest()? != expected_digest || !passport::timestamp(at) {
        return Err(invalid());
    }
    if let Some(receipt) = storage::replay(&store.connection, plan, expected_digest)? {
        return Ok(receipt);
    }
    if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        return Err(invalid());
    }
    let root = registered(&store.connection, plan)?;
    let observation = super::inspect_at(&root.path, &root.directory)?;
    if hash(&observation)? != plan.observation_digest {
        return Err(invalid());
    }
    store.transaction(|transaction| {
        registered(transaction, plan)?;
        let prior = storage::read(transaction, &plan.project_id)?;
        if storage::state_digest(transaction, &plan.project_id, &prior)?
            != plan.expected_findings_digest
        {
            return Err(invalid());
        }
        let findings = storage::merge(prior, &observation, &plan.scan_id(), at)?;
        storage::write(
            transaction,
            plan,
            expected_digest,
            &observation,
            &findings,
            at,
        )?;
        storage::replay(transaction, plan, expected_digest)?.ok_or_else(invalid)
    })
}

/// Stored local evidence is available without reopening the observed filesystem.
pub fn findings(parent: &Path, id: &str) -> Result<Value> {
    let identity = identity::current(parent)?.ok_or_else(invalid)?.context();
    let mut store = Store::planning(parent)?;
    store.transaction(|transaction| {
        owned(transaction, id, &identity)?;
        let findings = storage::read(transaction, id)?;
        let digest = storage::state_digest(transaction, id, &findings)?;
        Ok(
            json!({"schema_version":1,"project_id":id,"scope":"repository",
            "findings":findings,"findings_digest":digest,"installed_software_verified":false,
            "publication":"not_performed"}),
        )
    })
}
