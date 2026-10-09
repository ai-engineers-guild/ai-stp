//! Add a conservative target adaptation to an exact owned complete draft.

mod mcp;

use std::collections::BTreeMap;

use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Identity, contribution::Format, expiry, freezing, passports};
use crate::{
    artifacts, canonical, digest,
    error::{Failure, Result},
    harnesses::Shape,
    objects::Objects,
    passport,
    projection::{self, Scope, artifact},
    provider::Info,
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
    pub source_harness: String,
    pub provider: Value,
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
    Failure::precondition("this exact component cannot be derived without losing native controls, scopes or constraints")
        .with_details([("constraint".into(), "native_derivation_unsupported".into())])
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(invalid)
}

fn verify(connection: &Connection, document: &Value) -> Result<()> {
    let mut version = document.clone();
    version["parent_revision_ids"] = json!([]);
    freezing::verify(connection, &revisions::seal(&version)?)
}

pub(super) struct Built {
    pub document: Value,
    pub artifacts: BTreeMap<String, Vec<u8>>,
}

pub(super) fn build(
    connection: &Connection,
    before: Value,
    source_harness: &str,
    provider: &Info,
    at: &str,
) -> Result<Built> {
    verify(connection, &before)?;
    let target = text(provider.document(), "harness_id")?;
    let adaptations = before["adaptations"].as_array().ok_or_else(invalid)?;
    if before["component_type"] != "mcp"
        || target == source_harness
        || adaptations.iter().any(|a| a["harness_id"] == target)
    {
        return Err(invalid());
    }
    let source = adaptations
        .iter()
        .find(|a| a["harness_id"] == source_harness)
        .ok_or_else(invalid)?;
    if source["implementation_mode"] != "native" {
        return Err(invalid());
    }
    let source_bytes =
        canonical::bytes(&json!({"source_revision_id":before["revision_id"],"adaptation":source}))?;
    let source_address = digest::bytes("ai-stp:artifact:v1", &source_bytes)?;
    let source_artifact = json!({"digest":source_address,"size_bytes":source_bytes.len()});
    let mut artifacts = BTreeMap::from([(source_address, source_bytes)]);
    let mut scopes = Vec::new();
    for scope in source["scope_adaptations"].as_array().ok_or_else(invalid)? {
        if scope["technical_support"] == "unsupported"
            || scope["supported_harness_versions"]
                .as_array()
                .is_none_or(|a| !a.is_empty())
            || scope["semantic_losses"]
                .as_array()
                .is_none_or(|a| !a.is_empty())
        {
            return Err(invalid());
        }
        let requested: Scope =
            serde_json::from_value(scope["scope"].clone()).map_err(|_| invalid())?;
        let from = projection::route("mcp", source_harness, requested)?
            .filter(|r| r.target_scope == requested && r.shape == Shape::File)
            .ok_or_else(invalid)?;
        let to = projection::route("mcp", target, requested)?
            .filter(|r| r.target_scope == requested && r.shape == Shape::File)
            .ok_or_else(invalid)?;
        let payload =
            revisions::read_content(connection, text(&scope["projection_artifact"], "digest")?)?;
        let files = artifact::verify(scope, &payload)?;
        let members = scope["members"].as_array().ok_or_else(invalid)?;
        if files.len() != 1
            || members.len() != 1
            || files[0].path != from.relative
            || (from.declared_key.is_empty() && members[0]["ownership"] != "whole")
            || (!from.declared_key.is_empty()
                && (members[0]["ownership"] != "contribution"
                    || members[0]["ownership_key"] != from.declared_key))
        {
            return Err(invalid());
        }
        let servers = mcp::decode(
            &files[0].bytes,
            source_harness,
            Format::for_path(&from.relative)?,
            from.declared_key.is_empty(),
        )?;
        let bytes = mcp::encode(
            &servers,
            target,
            Format::for_path(&to.relative)?,
            to.declared_key.is_empty(),
        )?;
        let values = json!({"harness_id":target,"scope":requested,"projection_kind":to.projection_kind,
            "managed_paths":[to.relative],"declared_key":to.declared_key,"source_locator":format!("{}#{}",to.relative,to.declared_key),
            "content_format":artifacts::FILE_FORMAT,"source_mode":files[0].mode,"native_ids":members[0]["native_ids"],
            "permissions":scope["permissions"],"supported_os":scope["supported_os"],"supported_arch":scope["supported_arch"],"supported_harness_versions":[]});
        let (adaptation, bytes) =
            freezing::project(&before, &values, bytes, std::slice::from_ref(provider))?;
        let mut derived = adaptation["scope_adaptations"][0].clone();
        derived["technical_support_reason"] = "literal stdio configuration converted for this provider profile; harness execution not assessed".into();
        artifacts.insert(
            text(&derived["projection_artifact"], "digest")?.into(),
            bytes,
        );
        scopes.push(derived);
    }
    scopes.sort_by(|a, b| a["scope"].as_str().cmp(&b["scope"].as_str()));
    let transform = json!({"transform_id":"literal-stdio","version":"1.0","source":source_artifact,"target_harness":target,"scopes":scopes});
    let adaptation = passport::versions::seal_adaptation(
        &json!({"harness_id":target,"implementation_mode":"derived",
        "source_artifact":source_artifact,"transform":{"transform_id":"literal-stdio","version":"1.0","digest":digest::canonical("ai-stp:component-adaptation:v1",&transform)?},
        "logical_component_type":"mcp","scope_adaptations":scopes}),
    )?;
    let mut all = adaptations.clone();
    all.push(adaptation);
    all.sort_by(|a, b| a["harness_id"].as_str().cmp(&b["harness_id"].as_str()));
    let mut document = before.clone();
    document["artifact"] = all[0]["scope_adaptations"][0]["projection_artifact"].clone();
    document["adaptations"] = all.into();
    document["parent_revision_ids"] = json!([before["revision_id"]]);
    document["created_at"] = at.into();
    let document = revisions::seal(&document)?;
    let mut complete = document.clone();
    complete["parent_revision_ids"] = json!([]);
    passport::versions::validate_document(&revisions::seal(&complete)?)?;
    Ok(Built {
        document,
        artifacts,
    })
}

pub fn plan(
    store: &mut Store,
    id: &str,
    expected: &str,
    source_harness: &str,
    provider: &Info,
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    let built = store.transaction(|t| {
        build(
            t,
            passports::current(t, id, expected, &identity)?,
            source_harness,
            provider,
            at,
        )
    })?;
    Ok(Plan {
        schema_version: 1,
        action: "component.adaptation.derive".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
        stable_id: id.into(),
        expected_revision: expected.into(),
        source_harness: source_harness.into(),
        provider: provider.document().clone(),
        passport: built.document,
    })
}

fn replay(connection: &Connection, plan: &Plan) -> Result<Value> {
    let held = Objects { connection }.revision(text(&plan.passport, "revision_id")?)?;
    if held != plan.passport {
        return Err(invalid());
    }
    verify(connection, &held)?;
    Ok(held)
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
        || plan.action != "component.adaptation.derive"
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected_digest
    {
        return Err(invalid());
    }
    store.transaction(|t| {
        if let Some(state) = journal::state(t,&plan.operation_id,&plan.action,expected_digest)? {
            if state != "verified" { return Err(invalid()); }
            return replay(t,plan);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() { return Err(invalid()); }
        let provider = Info::parse(&canonical::bytes(&plan.provider)?)?;
        let before = passports::current(t,&plan.stable_id,&plan.expected_revision,identity)?;
        let built = build(t,before,&plan.source_harness,&provider,&plan.created_at)?;
        if built.document != plan.passport { return Err(invalid()); }
        for bytes in built.artifacts.values() { revisions::content(t,bytes,at)?; }
        verify(t,&built.document)?;
        let document = revisions::commit(t,&built.document,&identity.device_id,Some(&plan.operation_id),Write::Advance { expected_heads:std::slice::from_ref(&plan.expected_revision) })?;
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        Ok(document)
    })
}
