//! Exact multi-target preparation; the writer commits all outputs or none.

mod output;
pub use output::Effect;

use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Identity, derivation, expiry, forks::Source, freezing};
use crate::{
    canonical, digest,
    error::{Failure, Result},
    files, harnesses,
    objects::Objects,
    passport,
    projection::Scope,
    provider::Info,
    store::{Store, database, journal, revisions},
};

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    Owned,
    Private,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub source: Source,
    pub source_harness: String,
    #[serde(default)]
    pub targets: Vec<String>,
    #[serde(default)]
    pub all_missing: bool,
    pub output: Mode,
    #[serde(default)]
    pub overlay_id: Option<String>,
}

impl Request {
    pub fn read(path: &Path) -> Result<Self> {
        serde_json::from_value(canonical::parse(&files::read(path, 16 * 1024)?)?)
            .map_err(|_| invalid())
    }

    fn validate(&self) -> Result<()> {
        if !passport::stable_id(&self.source.stable_id, "component")
            || !passport::version_number(&self.source.version)
            || self.targets.len() > 7
            || self.all_missing != self.targets.is_empty()
            || self.overlay_id.as_ref().is_some_and(|id| {
                self.output != Mode::Private
                    || !passport::stable_id(id, "component")
                    || *id == self.source.stable_id
            })
        {
            return Err(invalid());
        }
        let mut unique = BTreeSet::new();
        for target in self
            .targets
            .iter()
            .chain(std::iter::once(&self.source_harness))
        {
            if target == "undefined" {
                return Err(invalid());
            }
            harnesses::definition(target)?;
        }
        for target in &self.targets {
            if !unique.insert(target) {
                return Err(invalid());
            }
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Target {
    pub harness_id: String,
    pub disposition: String,
    pub reason: Option<String>,
    pub adaptation: Option<Value>,
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
    pub providers: Vec<Value>,
    pub targets: Vec<Target>,
    pub effect: Effect,
    pub passport: Option<Value>,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        if canonical::bytes(&value)?.len() > 8 * 1024 * 1024 {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }
}

fn invalid() -> Failure {
    Failure::precondition(
        "materialization requires exact source, distinct targets and a complete identity-bound result",
    )
}

fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str> {
    value[field]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(invalid)
}

/// Bound metadata before loading it; artifact verification reads at most 64 MiB
/// per pass, including repeated references, and never trusts declared sizes alone.
fn exact(
    connection: &Connection,
    id: &str,
    version: &str,
    expected: Option<&str>,
) -> Result<Value> {
    let size: i64 = connection.query_row(
        "SELECT length(CAST(r.content AS BLOB)) FROM object_version v JOIN revision r ON r.revision_id=v.revision_id WHERE v.stable_id=? AND v.version=?",
        params![id,version], |r| r.get(0)).map_err(database)?;
    if size > 1024 * 1024 {
        return Err(invalid());
    }
    Objects { connection }.exact_version(id, version, expected)
}

fn references(document: &Value) -> Result<Vec<&Value>> {
    let mut references = vec![&document["artifact"]];
    for adaptation in document["adaptations"].as_array().ok_or_else(invalid)? {
        if !adaptation["source_artifact"].is_null() {
            references.push(&adaptation["source_artifact"]);
        }
        for scope in adaptation["scope_adaptations"]
            .as_array()
            .ok_or_else(invalid)?
        {
            references.push(&scope["projection_artifact"]);
        }
    }
    let mut total = 0u64;
    for reference in &references {
        total = total
            .checked_add(reference["size_bytes"].as_u64().ok_or_else(invalid)?)
            .filter(|sum| *sum <= 64 * 1024 * 1024)
            .ok_or_else(invalid)?;
    }
    Ok(references)
}

fn verify(connection: &Connection, document: &Value) -> Result<()> {
    for reference in references(document)? {
        let size: i64 = connection
            .query_row(
                "SELECT length(bytes) FROM content WHERE digest=?",
                [text(reference, "digest")?],
                |r| r.get(0),
            )
            .map_err(database)?;
        if size < 0 || reference["size_bytes"].as_u64() != Some(size as u64) {
            return Err(invalid());
        }
    }
    freezing::verify(connection, document)
}

struct Built {
    targets: Vec<Target>,
    effect: output::Effect,
    passport: Option<Value>,
    artifacts: BTreeMap<String, Vec<u8>>,
}

fn build(
    connection: &Connection,
    request: &Request,
    providers: &[Info],
    identity: &Identity,
    at: &str,
) -> Result<Built> {
    request.validate()?;
    let objects = Objects { connection };
    objects.require_active(&request.source.stable_id)?;
    let before = exact(
        connection,
        &request.source.stable_id,
        &request.source.version,
        Some(&request.source.passport_digest),
    )?;
    verify(connection, &before)?;
    if request.output == Mode::Owned {
        let head = objects.head("component", &request.source.stable_id)?;
        if before["owner_id"] != identity.account_id || head["owner_id"] != identity.account_id {
            return Err(invalid());
        }
    }
    let adaptations = before["adaptations"].as_array().ok_or_else(invalid)?;
    if !adaptations
        .iter()
        .any(|a| a["harness_id"] == request.source_harness)
    {
        return Err(invalid());
    }
    let mut targets = if request.all_missing {
        harnesses::definitions()?
            .iter()
            .filter(|h| {
                h.harness_id != "undefined"
                    && !adaptations.iter().any(|a| a["harness_id"] == h.harness_id)
            })
            .map(|h| h.harness_id.clone())
            .collect()
    } else {
        request.targets.clone()
    };
    targets.sort();
    let mut declared = BTreeMap::new();
    if providers.len() > 7 {
        return Err(invalid());
    }
    for provider in providers {
        if declared
            .insert(text(provider.document(), "harness_id")?, provider)
            .is_some()
        {
            return Err(invalid());
        }
    }
    let mut built = Built {
        targets: Vec::new(),
        effect: output::Effect::Blocked,
        passport: None,
        artifacts: BTreeMap::new(),
    };
    let mut all = adaptations.clone();
    let mut size = 0usize;
    for harness in targets {
        let mut report = Target {
            harness_id: harness.clone(),
            disposition: "blocked".into(),
            reason: Some("an explicit target provider declaration is required".into()),
            adaptation: None,
        };
        if let Some(provider) = declared.get(harness.as_str()) {
            if let Some(existing) = adaptations.iter().find(|a| a["harness_id"] == harness) {
                let supported = existing["scope_adaptations"]
                    .as_array()
                    .ok_or_else(invalid)?
                    .iter()
                    .all(|scope| {
                        serde_json::from_value::<Scope>(scope["scope"].clone()).is_ok_and(|s| {
                            scope["technical_support"] != "unsupported"
                                && provider.supports_scope(s, scope)
                        })
                    });
                if supported {
                    report.disposition = "reuse".into();
                    report.reason = None;
                    report.adaptation = Some(existing.clone());
                } else {
                    report.reason = Some("the exact adaptation does not fit the declared provider scopes and profiles".into());
                }
            } else {
                match derivation::build(
                    connection,
                    before.clone(),
                    &request.source_harness,
                    provider,
                    at,
                ) {
                    Ok(derived) => {
                        let adaptation = derived.document["adaptations"]
                            .as_array()
                            .ok_or_else(invalid)?
                            .iter()
                            .find(|a| a["harness_id"] == harness)
                            .ok_or_else(invalid)?
                            .clone();
                        for (address, bytes) in derived.artifacts {
                            if let Some(held) = built.artifacts.get(&address) {
                                if held != &bytes {
                                    return Err(invalid());
                                }
                            } else {
                                size = size
                                    .checked_add(bytes.len())
                                    .filter(|s| *s <= 128 * 1024 * 1024)
                                    .ok_or_else(invalid)?;
                                built.artifacts.insert(address, bytes);
                            }
                        }
                        all.push(adaptation.clone());
                        report.disposition = "derive".into();
                        report.reason = None;
                        report.adaptation = Some(adaptation);
                    }
                    Err(error)
                        if error.details.get("constraint")
                            == Some(&json!("native_derivation_unsupported")) =>
                    {
                        report.reason = Some(error.message);
                    }
                    Err(error) => return Err(error),
                }
            }
        }
        built.targets.push(report);
    }
    if built
        .targets
        .iter()
        .any(|target| target.disposition == "blocked")
    {
        return Ok(built);
    }
    let changed = built
        .targets
        .iter()
        .any(|target| target.disposition == "derive");
    let mut document = before;
    if changed {
        all.sort_by(|a, b| a["harness_id"].as_str().cmp(&b["harness_id"].as_str()));
        document["artifact"] = all[0]["scope_adaptations"][0]["projection_artifact"].clone();
        document["adaptations"] = all.into();
    }
    let (effect, document) = output::prepare(connection, request, document, changed, identity, at)?;
    if canonical::bytes(&document)?.len() > 1024 * 1024 {
        return Err(invalid());
    }
    references(&document)?;
    built.effect = effect;
    built.passport = Some(document);
    Ok(built)
}

pub fn plan(
    store: &mut Store,
    mut request: Request,
    providers: &[Info],
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    request.validate()?;
    let expires_at = expiry(at)?;
    if request.output == Mode::Private && request.overlay_id.is_none() {
        request.overlay_id = Some(format!("component_{}", ulid::Ulid::generate()));
    }
    let built = store.transaction(|t| build(t, &request, providers, &identity, at))?;
    let plan = Plan {
        schema_version: 1,
        action: "component.materialize".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
        request,
        providers: providers.iter().map(|p| p.document().clone()).collect(),
        targets: built.targets,
        effect: built.effect,
        passport: built.passport,
    };
    plan.digest()?;
    Ok(plan)
}

pub fn apply(
    store: &mut Store,
    plan: &Plan,
    expected_digest: &str,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    identity.validate()?;
    plan.request.validate()?;
    if plan.schema_version != 1
        || plan.action != "component.materialize"
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected_digest
        || plan.effect == output::Effect::Blocked
    {
        return Err(invalid());
    }
    store.transaction(|t| {
        if let Some(state) = journal::state(t,&plan.operation_id,&plan.action,expected_digest)? {
            if state != "verified" { return Err(invalid()); }
            return output::replay(t,plan);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() || plan.providers.len() > 7 { return Err(invalid()); }
        let providers = plan.providers.iter().map(|p|Info::parse(&canonical::bytes(p)?)).collect::<Result<Vec<_>>>()?;
        let built = build(t,&plan.request,&providers,identity,&plan.created_at)?;
        if built.targets != plan.targets || built.effect != plan.effect || built.passport != plan.passport { return Err(invalid()); }
        for bytes in built.artifacts.values() { revisions::content(t,bytes,at)?; }
        let document = built.passport.ok_or_else(invalid)?;
        verify(t,&document)?;
        output::record(t,plan,&document,at)?;
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        Ok(document)
    })
}
