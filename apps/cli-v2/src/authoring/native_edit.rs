//! Exact native source replacement within an owned complete component draft.

use std::{collections::BTreeMap, path::PathBuf};

use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Identity, adoption, expiry, freezing, passports};
use crate::{
    canonical, digest,
    error::{Failure, Result},
    files,
    objects::Objects,
    passport, projection,
    provider::Info,
    store::{
        Store, database, journal,
        revisions::{self, Write},
    },
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub scope: projection::Scope,
    pub source: adoption::Source,
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
    pub sources: Vec<Source>,
    pub provider: Value,
    pub source_digests: Vec<String>,
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
        "the native adaptation edit violates its exact source or complete draft contract",
    )
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(invalid)
}

struct Captured {
    scope: projection::Scope,
    values: Value,
    bytes: Vec<u8>,
}

fn capture(sources: &[Source], provider: &Info) -> Result<Vec<Captured>> {
    if sources.is_empty() || sources.len() > 3 {
        return Err(invalid());
    }
    let harness = text(provider.document(), "harness_id")?;
    let mut scopes = std::collections::BTreeSet::new();
    sources
        .iter()
        .map(|source| {
            if (source.source.harness_id != harness && source.source.harness_id != "undefined")
                || !scopes.insert(source.scope.as_str())
            {
                return Err(invalid());
            }
            let captured = adoption::prepare_for(&source.source, harness)?;
            let mut values = adoption::source_values(&captured)?;
            // Shared skills have neutral discovery identity; their bytes are explicitly
            // supplied as native content for this concrete harness, without a transform.
            if values["harness_id"] != harness {
                return Err(invalid());
            }
            let kind = text(&values, "component_type")?;
            let route = projection::route(kind, harness, source.scope)?
                .filter(|r| r.target_scope == source.scope)
                .ok_or_else(invalid)?;
            let paths =
                projection::covers(kind, harness, text(&values, "source_name")?, source.scope)?;
            values["harness_id"] = harness.into();
            values["scope"] = serde_json::to_value(source.scope).map_err(|_| invalid())?;
            values["managed_paths"] = json!(paths);
            values["source_locator"] = if route.declared_key.is_empty() {
                "".into()
            } else {
                format!("{}#{}", route.relative, route.declared_key).into()
            };
            Ok(Captured {
                scope: source.scope,
                values,
                bytes: captured.content.bytes,
            })
        })
        .collect()
}

fn verify(connection: &Connection, document: &Value) -> Result<()> {
    let mut version = document.clone();
    version["parent_revision_ids"] = json!([]);
    freezing::verify(connection, &revisions::seal(&version)?)
}

struct Built {
    document: Value,
    artifacts: BTreeMap<String, Vec<u8>>,
    source_digests: Vec<String>,
}

fn build(before: Value, sources: &[Captured], provider: &Info, at: &str) -> Result<Built> {
    let harness = text(provider.document(), "harness_id")?;
    let adaptations = before["adaptations"].as_array().ok_or_else(|| Failure::precondition(
        "native adaptation editing requires a complete owned draft; bind a source project or fork an exact released version"
    ))?;
    let old = adaptations.iter().find(|a| a["harness_id"] == harness);
    let old_native = old.is_some_and(|a| a["implementation_mode"] == "native");
    let old_scopes = old
        .map(|a| a["scope_adaptations"].as_array().ok_or_else(invalid))
        .transpose()?;
    if old_scopes.is_some_and(|scopes| {
        scopes
            .iter()
            .any(|scope| !sources.iter().any(|s| scope["scope"] == s.scope.as_str()))
    }) {
        return Err(Failure::precondition(
            "an adaptation replacement must include every existing scope",
        ));
    }
    let mut scopes = Vec::new();
    let mut artifacts = BTreeMap::new();
    let mut source_digests = Vec::new();
    let mut total = 0usize;
    for source in sources {
        if source.values["component_type"] != before["component_type"] {
            return Err(invalid());
        }
        let mut values = source.values.clone();
        let old_scope = old_scopes
            .and_then(|scopes| scopes.iter().find(|s| s["scope"] == source.scope.as_str()));
        for field in [
            "permissions",
            "supported_os",
            "supported_arch",
            "supported_harness_versions",
        ] {
            if let Some(scope) = old_scope {
                values[field] = scope[field].clone();
            }
        }
        let (adaptation, bytes) = freezing::project(
            &before,
            &values,
            source.bytes.clone(),
            std::slice::from_ref(provider),
        )?;
        let mut scope = adaptation["scope_adaptations"][0].clone();
        if let Some(old) = old_scope {
            scope["semantic_losses"] = old["semantic_losses"].clone();
            if old["technical_support"] == "unsupported" {
                scope["technical_support"] = old["technical_support"].clone();
                scope["technical_support_reason"] = old["technical_support_reason"].clone();
            }
            // Preserve an existing native assessment only when all its inputs,
            // including bytes and the exact provider surface, are unchanged.
            if old_native {
                let mut comparable = old.clone();
                comparable["technical_support"] = scope["technical_support"].clone();
                comparable["technical_support_reason"] = scope["technical_support_reason"].clone();
                if comparable == scope {
                    scope = old.clone();
                }
            }
        }
        let address = text(&scope["projection_artifact"], "digest")?.to_owned();
        if let std::collections::btree_map::Entry::Vacant(entry) = artifacts.entry(address) {
            total = total.checked_add(bytes.len()).ok_or_else(invalid)?;
            if total > 128 * 1024 * 1024 {
                return Err(invalid());
            }
            entry.insert(bytes);
        }
        source_digests.push(digest::canonical(
            "ai-stp:component-adaptation:v1",
            &source.values,
        )?);
        scopes.push(scope);
    }
    scopes.sort_by(|a, b| a["scope"].as_str().cmp(&b["scope"].as_str()));
    let adaptation = passport::versions::seal_adaptation(&json!({"harness_id":harness,
        "implementation_mode":"native","transform":null,"source_artifact":null,
        "logical_component_type":before["component_type"],"scope_adaptations":scopes}))?;
    let mut built = Built {
        document: before.clone(),
        artifacts,
        source_digests,
    };
    if old == Some(&adaptation) {
        return Ok(built);
    }
    let mut adaptations: Vec<_> = adaptations
        .iter()
        .filter(|a| a["harness_id"] != harness)
        .cloned()
        .collect();
    adaptations.push(adaptation);
    adaptations.sort_by(|a, b| a["harness_id"].as_str().cmp(&b["harness_id"].as_str()));
    built.document["artifact"] =
        adaptations[0]["scope_adaptations"][0]["projection_artifact"].clone();
    built.document["adaptations"] = adaptations.into();
    built.document["parent_revision_ids"] = json!([before["revision_id"]]);
    built.document["created_at"] = at.into();
    built.document = revisions::seal(&built.document)?;
    let mut version = built.document.clone();
    version["parent_revision_ids"] = json!([]);
    passport::versions::validate_document(&revisions::seal(&version)?)?;
    Ok(built)
}

pub fn plan(
    store: &mut Store,
    id: &str,
    expected: &str,
    mut sources: Vec<Source>,
    provider: &Info,
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    for source in &mut sources {
        source.source.root = PathBuf::from(files::location(&source.source.root)?);
    }
    sources.sort_by_key(|s| s.scope.as_str());
    let captured = capture(&sources, provider)?;
    let built = store.transaction(|t| {
        let before = passports::current(t, id, expected, &identity)?;
        verify(t, &before)?;
        build(before, &captured, provider, at)
    })?;
    Ok(Plan {
        schema_version: 1,
        action: "component.adaptation.edit".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
        stable_id: id.into(),
        expected_revision: expected.into(),
        sources,
        provider: provider.document().clone(),
        source_digests: built.source_digests,
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
        || plan.action != "component.adaptation.edit"
        || plan.identity != *identity
        || plan.digest()? != expected_digest
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.sources.iter().any(|s| !s.source.root.is_absolute())
    {
        return Err(invalid());
    }
    if let Some(state) = journal::state(
        &store.connection,
        &plan.operation_id,
        &plan.action,
        expected_digest,
    )? {
        if state != "verified" {
            return Err(invalid());
        }
        return replay(&store.connection, plan);
    }
    if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        return Err(invalid());
    }
    let provider = Info::parse(&canonical::bytes(&plan.provider)?)?;
    let captured = capture(&plan.sources, &provider)?;
    store.transaction(|t| {
        if let Some(state) = journal::state(t,&plan.operation_id,&plan.action,expected_digest)? {
            if state != "verified" { return Err(invalid()); }
            return replay(t,plan);
        }
        let before = passports::current(t,&plan.stable_id,&plan.expected_revision,identity)?;
        verify(t,&before)?;
        let built = build(before,&captured,&provider,&plan.created_at)?;
        if built.document != plan.passport || built.source_digests != plan.source_digests { return Err(invalid()); }
        for bytes in built.artifacts.values() { revisions::content(t,bytes,at)?; }
        verify(t,&built.document)?;
        let after = revisions::commit(t,&built.document,&identity.device_id,Some(&plan.operation_id),Write::Advance {expected_heads:std::slice::from_ref(&plan.expected_revision)})?;
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        Ok(after)
    })
}
