//! Device-signed author evidence over immutable local objects. Signing does not
//! execute a check, invoke a harness or grant a verification badge.

pub mod contract;
mod journal;

use crate::{
    account::access::{Access, Binding},
    authoring, canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, identity, passport, publication,
    store::Store,
};
use base64::{Engine, engine::general_purpose::STANDARD};
use contract::invalid;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub stable_id: String,
    pub version: String,
    pub evidence: Value,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    schema_version: u32,
    action: String,
    operation_id: String,
    created_at: String,
    expires_at: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    state_parent: PathBuf,
    account: Binding,
    #[serde(
        serialize_with = "files::serialize_location",
        deserialize_with = "files::deserialize_location"
    )]
    output: String,
    parent_identity: [String; 2],
    record: Value,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        self.account.validate()?;
        contract::hash(&self.record)?;
        claims(&self.record)?;
        if self.schema_version != 1
            || self.action != "attestation.sign"
            || !passport::stable_id(&self.operation_id, "operation")
            || !self.state_parent.is_absolute()
            || !Path::new(&self.output).is_absolute()
            || self.record["signature"] != STANDARD.encode([0u8; 64])
            || self.record["account_id"] != self.account.account_id
            || self.record["device_id"] != self.account.device_id
            || authoring::expiry(&self.created_at)? != self.expires_at
            || !passport::timestamp(self.record["attested_at"].as_str().ok_or_else(invalid)?)
            || self.record["attested_at"].as_str().ok_or_else(invalid)? > self.created_at.as_str()
        {
            return Err(invalid());
        }
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        if canonical::bytes(&value)?.len() > 512 * 1024 {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }

    fn root(&self) -> Result<identity::Identity> {
        let owner = identity::current(&self.state_parent)?.ok_or_else(invalid)?;
        if owner.root_binding() != (self.state_parent.as_path(), &self.account.root_identity) {
            return Err(invalid());
        }
        owner.revalidate()?;
        Ok(owner)
    }

    fn subject(&self, store: &mut Store) -> Result<()> {
        let subject = &self.record["subject"];
        let snapshot = subject_at(
            store,
            subject["stable_id"].as_str().ok_or_else(invalid)?,
            subject["version"].as_str().ok_or_else(invalid)?,
            Some(subject["passport_digest"].as_str().ok_or_else(invalid)?),
        )?;
        snapshot.require_owner(&self.account.account_id)?;
        contract::bind(&self.record, &snapshot.passport, &self.account)?;
        contract::coordinates(&self.record, &snapshot.passport)
    }
}

fn subject_at(
    store: &mut Store,
    id: &str,
    version: &str,
    expected: Option<&str>,
) -> Result<publication::Snapshot> {
    publication::prepare(store, id, version, expected, None)?
        .pop()
        .ok_or_else(invalid)
}

fn evidence(value: &Value) -> Result<()> {
    let fields = value.as_object().ok_or_else(invalid)?;
    let keys = [
        "check_id",
        "policy_version",
        "tool_versions",
        "harness_id",
        "harness_version",
        "provider_version",
        "test_case_ids",
        "result",
        "attested_at",
    ];
    if fields
        .keys()
        .any(|key| !keys.contains(&key.as_str()) && !contract::TARGETS.contains(&key.as_str()))
    {
        return Err(invalid());
    }
    claims(value)
}

fn claims(value: &Value) -> Result<()> {
    if value.get("tool_versions").is_some_and(|tools| {
        tools.as_object().is_none_or(|tools| {
            tools.iter().any(|(key, value)| {
                key.trim().is_empty()
                    || value.as_str().is_none_or(|v| v.trim().is_empty())
                    || ["secret", "token", "password", "key"]
                        .iter()
                        .any(|part| key.to_lowercase().contains(part))
            })
        })
    }) {
        return Err(invalid());
    }
    let cases = value["test_case_ids"].as_array().ok_or_else(invalid)?;
    let mut seen = std::collections::BTreeSet::new();
    for case in cases {
        let case = case
            .as_str()
            .filter(|v| !v.trim().is_empty())
            .ok_or_else(invalid)?;
        if !seen.insert(case) {
            return Err(invalid());
        }
    }
    Ok(())
}

pub fn plan(
    root: &Path,
    origin: Option<&str>,
    request: Request,
    output: &Path,
    at: &str,
) -> Result<Plan> {
    plan_for_connection(root, origin, None, request, output, at)
}

pub fn plan_for_connection(
    root: &Path,
    origin: Option<&str>,
    connection: Option<&str>,
    request: Request,
    output: &Path,
    at: &str,
) -> Result<Plan> {
    evidence(&request.evidence)?;
    let mut account = Access::for_connection(root, origin, connection, false)?;
    account.verify()?;
    let state_parent = PathBuf::from(files::location(root)?);
    let (output, parent_identity) = files::tree::destination(output)?;
    files::document::unused(&output, &parent_identity)?;
    let owner = identity::current(&state_parent)?.ok_or_else(invalid)?;
    let mut store = Store::planning_at(owner.root_directory())?;
    account.check_registry_owner(&store.connection)?;
    let snapshot = subject_at(&mut store, &request.stable_id, &request.version, None)?;
    snapshot.require_owner(&account.binding().account_id)?;
    let mut record = request.evidence;
    let fields = record.as_object_mut().ok_or_else(invalid)?;
    fields.extend(json!({"schema_version":1, "object_digest":snapshot.artifact.digest,
        "subject":{"stable_id":request.stable_id,"version":request.version,"passport_digest":snapshot.passport_digest},
        "account_id":account.binding().account_id,"device_id":account.binding().device_id,
        "signature":STANDARD.encode([0u8;64])}).as_object().ok_or_else(invalid)?.clone());
    // Normalize exactly as the shared model before exposing the reviewed plan.
    let mut record = contract::payload(&record)?;
    record["signature"] = STANDARD.encode([0u8; 64]).into();
    contract::coordinates(&record, &snapshot.passport)?;
    let plan = Plan {
        schema_version: 1,
        action: "attestation.sign".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        state_parent,
        account: account.binding().clone(),
        output,
        parent_identity,
        record,
    };
    plan.root()?;
    plan.digest()?;
    account.revalidate()?;
    Ok(plan)
}

pub fn read_request(path: &Path) -> Result<Request> {
    serde_json::from_value(canonical::parse(&files::read(path, contract::LIMIT)?)?)
        .map_err(|_| invalid())
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    serde_json::from_value(canonical::parse(&files::read(path, 512 * 1024)?)?)
        .map_err(|_| invalid())
}

pub fn status(root: &Path, operation: &str) -> Result<Value> {
    if !passport::stable_id(operation, "operation") {
        return Err(invalid());
    }
    let owner = identity::current(root)?.ok_or_else(invalid)?;
    let store = Store::planning_at(owner.root_directory())?;
    let receipt = journal::load(&store.connection, operation)?.ok_or_else(|| {
        Failure::new(
            ErrorKind::NotFound,
            "the attestation operation has not been signed",
        )
    })?;
    receipt.plan.root()?;
    if receipt.plan.state_parent != Path::new(&files::location(root)?) {
        return Err(invalid());
    }
    receipt.report()
}

pub fn apply(plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    if plan.digest()? != expected {
        return Err(invalid());
    }
    execute(plan, expected, at).map_err(|error| {
        error.with_details([("operation_id".into(), plan.operation_id.clone().into())])
    })
}

fn execute(plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    let owner = plan.root()?;
    let observed = {
        let store = Store::planning_at(owner.root_directory())?;
        journal::load(&store.connection, &plan.operation_id)?
    };
    if let Some(receipt) = &observed {
        receipt.matches(plan)?;
        if receipt.completed {
            return receipt.report();
        }
    }
    if observed.is_none() {
        if !passport::timestamp(at)
            || at < plan.created_at.as_str()
            || at > plan.expires_at.as_str()
        {
            return Err(Failure::precondition(
                "the attestation signing plan has expired",
            ));
        }
        let mut account = Access::for_binding(&plan.state_parent, &plan.account, false)?;
        if *account.binding() != plan.account {
            return Err(invalid());
        }
        account.verify()?;
        let mut store = account.owned_registry()?;
        if let Some(receipt) = journal::load(&store.connection, &plan.operation_id)? {
            receipt.matches(plan)?;
        } else {
            plan.subject(&mut store)?;
            files::document::unused(&plan.output, &plan.parent_identity)?;
            let mut record = plan.record.clone();
            record["signature"] = STANDARD.encode(account.sign_attestation(&record)?).into();
            contract::verify(&record, &plan.account.public_key)?;
            store.transaction(|t| journal::retain(t, plan, record, at))?;
        }
    }
    // Signing has been durably retained. Exporting that exact evidence never
    // acquires former credentials or signs again, including after logout.
    let mut store = Store::open_at(owner.root_directory(), false)?;
    let mut receipt = journal::load(&store.connection, &plan.operation_id)?.ok_or_else(invalid)?;
    receipt.matches(plan)?;
    if !receipt.completed {
        owner.revalidate()?;
        let pending = files::document::publish(
            &plan.output,
            &plan.parent_identity,
            &canonical::bytes(&receipt.record)?,
            expected,
        )?;
        plan.root()?;
        store.transaction(|t| journal::finish(t, plan, at, pending))?;
        receipt = journal::load(&store.connection, &plan.operation_id)?.ok_or_else(invalid)?;
    }
    receipt.report()
}
