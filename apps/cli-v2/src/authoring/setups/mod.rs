//! Exact private compositions. A frozen graph is not an installation approval.

mod aggregate;
pub mod copies;
pub(crate) mod definition;
pub mod drafts;
pub mod export;
pub mod releases;
mod requirements;

pub use requirements::Requirements;

use rusqlite::{Connection, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Identity, expiry, freezing};
use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    harnesses,
    objects::Objects,
    passport,
    selection::graph,
    store::{
        Store, database, journal,
        revisions::{self, Write},
        versions,
    },
};

use definition::FORMAT;

/// Exact immutable setup coordinate, independently verified before use.
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub stable_id: String,
    pub version: String,
    pub passport_digest: String,
}

fn exact(connection: &Connection, reference: &Source) -> Result<Value> {
    if !passport::stable_id(&reference.stable_id, "setup") {
        return Err(invalid());
    }
    let document = Objects { connection }.exact_version(
        &reference.stable_id,
        &reference.version,
        Some(&reference.passport_digest),
    )?;
    verify(connection, &document)?;
    Ok(document)
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Member {
    pub stable_id: String,
    pub version: String,
    pub passport_digest: String,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub harness_id: String,
    pub name: String,
    pub description: String,
    pub purpose: String,
    pub members: Vec<Member>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub requirements: Option<Requirements>,
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
    pub request: Request,
    pub passport: Value,
}

fn invalid() -> Failure {
    Failure::input("the setup composition plan violates its exact graph or result contract")
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

fn member(connection: &Connection, reference: &Value, harness: &str) -> Result<Value> {
    let document = Objects { connection }.exact_version(
        reference["stable_id"].as_str().ok_or_else(invalid)?,
        reference["version"].as_str().ok_or_else(invalid)?,
        Some(reference["passport_digest"].as_str().ok_or_else(invalid)?),
    )?;
    if document["kind"] != "component"
        || !document["adaptations"]
            .as_array()
            .is_some_and(|items| items.iter().any(|item| item["harness_id"] == harness))
    {
        return Err(Failure::precondition(
            "a setup member has no explicit adaptation for its harness",
        ));
    }
    freezing::verify(connection, &document)?;
    Ok(document)
}

pub(crate) fn compile(
    connection: &Connection,
    request: &Request,
    id: &str,
    identity: &Identity,
    at: &str,
) -> Result<(Value, Vec<u8>)> {
    let input = serde_json::to_value(request).map_err(|_| invalid())?;
    if !passport::stable_id(id, "setup")
        || request.harness_id == "undefined"
        || request.name.trim().is_empty()
        || request.name.len() > 1024
        || request.purpose.trim().is_empty()
        || request.purpose.len() > 16384
        || [&request.name, &request.description, &request.purpose]
            .iter()
            .any(|value| value.contains("TODO(ai-stp-scaffold)"))
        || request.members.len() > 512
        || canonical::bytes(&input)?.len() > 256 * 1024
        || request
            .members
            .iter()
            .any(|item| !passport::stable_id(&item.stable_id, "component"))
    {
        return Err(invalid());
    }
    harnesses::definition(&request.harness_id)?;
    passport::markdown::validate(&request.description)?;
    let roots = input["members"].as_array().ok_or_else(invalid)?;
    let closure = graph::exact(connection, roots)?;
    if closure["resolved"] != true {
        let reasons = closure["refusals"]
            .as_array()
            .ok_or_else(invalid)?
            .iter()
            .filter_map(|item| item["code"].as_str())
            .collect::<Vec<_>>()
            .join(", ");
        return Err(Failure::precondition(format!(
            "the setup dependency graph was refused: {reasons}"
        )));
    }
    let mut refs: Vec<Value> = closure["nodes"].as_array().ok_or_else(invalid)?.iter()
        .map(|node| json!({"stable_id":node["stable_id"],"version":node["version"],"passport_digest":node["passport_digest"]})).collect();
    refs.sort_by(|a, b| a["stable_id"].as_str().cmp(&b["stable_id"].as_str()));
    let mut aggregate = aggregate::Aggregate::default();
    for reference in &refs {
        let document = member(connection, reference, &request.harness_id)?;
        if document["lifecycle_state"] == "conflict"
            || document["description"]
                .as_str()
                .is_some_and(|text| text.contains("TODO(ai-stp-scaffold)"))
        {
            return Err(Failure::precondition(
                "a setup cannot freeze a conflicted or scaffold draft member",
            ));
        }
        aggregate.include(&document)?;
    }
    if let Some(declarations) = &request.requirements {
        declarations.include(&mut aggregate)?;
    }
    let fact = |value: Value| json!({"value":value,"origin":"derived","confirmation":"none","observed_at":at});
    let mut document = json!({"kind":"setup","stable_id":id,"owner_id":identity.account_id,
        "created_at":at,"visibility":"private","parent_revision_ids":[],
        "facts":{"harness_id":fact(request.harness_id.clone().into()),"members":fact(json!(refs)),
            "snapshot":fact(digest::canonical("ai-stp:plan:v1", &input)?.into()),"member_metadata_complete":fact(true.into())},
        "name":request.name,"description":request.description,"version":"1.0","tags":["local-setup"],
        "source":null,"harness_id":request.harness_id,"components":refs,"purpose":request.purpose,
        "target_role":null,"posture":null,"supported_tasks":[],"ported_from":null,"related_setup_ids":[],
        "execution_profile":"full-auto","supported_harness_versions":[],"supported_os":[],"supported_arch":[],
        "composition_report_ref":null,"conversion_report_ref":null,"install_evidence_ref":null,"launch_evidence_ref":null,
        "compatibility_evidence_refs":[],"artifact_format":FORMAT,"member_metadata_complete":true});
    aggregate.apply(&mut document);
    if let Some(declarations) = &request.requirements {
        document["facts"]["setup_requirements"] = json!({
            "value": declarations, "origin":"declared", "confirmation":"user_confirmed", "confirmed_at":at
        });
    }
    finish(document)
}

pub(crate) fn finish(mut document: Value) -> Result<(Value, Vec<u8>)> {
    passport::versions::normalize_component_refs(&mut document["components"])?;
    let payload = canonical::bytes(&definition::document(&document))?;
    document["artifact"] =
        json!({"digest":digest::bytes("ai-stp:artifact:v1", &payload)?,"size_bytes":payload.len()});
    let document = revisions::seal(&document)?;
    passport::versions::validate_document(&document)?;
    if canonical::bytes(&document)?.len() > 1024 * 1024 {
        return Err(Failure::precondition(
            "the aggregated setup metadata exceeds one MiB",
        ));
    }
    Ok((document, payload))
}

pub(crate) fn verify(connection: &Connection, document: &Value) -> Result<()> {
    passport::versions::validate_document(document)?;
    let payload = revisions::read_content(
        connection,
        document["artifact"]["digest"]
            .as_str()
            .ok_or_else(invalid)?,
    )?;
    verify_definition(document, &payload)?;
    for reference in document["components"].as_array().ok_or_else(invalid)? {
        member(
            connection,
            reference,
            document["harness_id"].as_str().ok_or_else(invalid)?,
        )?;
    }
    Ok(())
}

pub(crate) fn verify_definition(document: &Value, payload: &[u8]) -> Result<()> {
    definition::verify(document, payload).map(|_| ())
}

fn normalize(request: &mut Request) {
    // Input ordering must not change the composition snapshot or its aggregate.
    request.members.sort_by(|a, b| {
        (&a.stable_id, &a.version, &a.passport_digest).cmp(&(
            &b.stable_id,
            &b.version,
            &b.passport_digest,
        ))
    });
    request.members.dedup_by(|a, b| {
        a.stable_id == b.stable_id
            && a.version == b.version
            && a.passport_digest == b.passport_digest
    });
}

pub fn plan(store: &mut Store, mut request: Request, identity: Identity, at: &str) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    normalize(&mut request);
    let id = format!("setup_{}", ulid::Ulid::generate());
    let passport = store
        .transaction(|t| compile(t, &request, &id, &identity, at).map(|(document, _)| document))?;
    Ok(Plan {
        schema_version: 1,
        action: "setup.compose".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
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
        || plan.action != "setup.compose"
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
            let held = Objects {connection:t}.exact_version(id,"1.0",None)?;
            if held != plan.passport { return Err(invalid()); }
            verify(t,&held)?;
            return Ok(held);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() { return Err(Failure::precondition("the composition plan is not within its validity interval")); }
        let exists: bool = t.query_row("SELECT EXISTS(SELECT 1 FROM entity WHERE stable_id=?)",[id],|r|r.get(0)).map_err(database)?;
        if exists { return Err(Failure::new(ErrorKind::Conflict,"the planned setup identity already exists")); }
        let (document,payload) = compile(t,&plan.request,id,identity,&plan.created_at)?;
        if document != plan.passport { return Err(invalid()); }
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        persist(t, &document, &payload, identity, &plan.operation_id, at)
    })
}

pub(crate) fn persist(
    transaction: &Transaction<'_>,
    document: &Value,
    payload: &[u8],
    identity: &Identity,
    operation_id: &str,
    at: &str,
) -> Result<Value> {
    revisions::content(transaction, payload, at)?;
    revisions::commit(
        transaction,
        document,
        &identity.device_id,
        Some(operation_id),
        Write::Advance {
            expected_heads: &[],
        },
    )?;
    versions::record(
        transaction,
        document,
        &identity.device_id,
        Some(operation_id),
        at,
    )
}
