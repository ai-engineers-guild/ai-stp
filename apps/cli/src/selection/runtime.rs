//! Exact local selection inputs derived here, never accepted as authority JSON.

#[cfg(test)]
mod tests;

pub(crate) mod access;
pub mod bundles;
pub mod matrix;
mod program;
pub mod reports;
pub mod sessions;

use std::{collections::BTreeMap, path::Path};

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    eligibility::{self, Evidence, Target},
    graph,
};
use crate::{
    authoring::{
        Identity, freezing,
        runtime::{Owner, owner},
        setups,
    },
    error::{Failure, Result},
    files, harnesses,
    objects::Objects,
    passport,
    projection::Scope,
    provider::{Info, artifact, runtime, trust},
    store::revisions,
};

const MAX_REQUEST: u64 = 256 * 1024;
const MAX_CONTENT: u64 = 64 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    harness_id: String,
    scope: Scope,
    provider_version: String,
    members: Vec<setups::Member>,
    #[serde(default)]
    for_redistribution: bool,
    #[serde(default)]
    harness_executable: Option<program::Executable>,
    #[serde(default)]
    access: access::Request,
}

fn invalid() -> Failure {
    Failure::input("selection requires a closed bounded request with exact object coordinates")
}

impl Request {
    fn parse(path: &Path, empty: bool) -> Result<Self> {
        Self::from_value(crate::wire::parse(&files::read(path, MAX_REQUEST)?)?, empty)
    }

    fn from_value(mut value: Value, empty: bool) -> Result<Self> {
        crate::provider::managed::resolve_request(&mut value);
        let request: Self = serde_json::from_value(value).map_err(|_| invalid())?;
        request.selector().validate()?;
        request.access.validate()?;
        if request.members.is_empty() != empty
            || request.members.len() > 512
            || request.members.iter().any(|member| {
                (!passport::stable_id(&member.stable_id, "component")
                    && !passport::stable_id(&member.stable_id, "setup"))
                    || !passport::version_number(&member.version)
                    || !member
                        .passport_digest
                        .strip_prefix("sha256:")
                        .is_some_and(|s| {
                            s.len() == 64
                                && s.bytes()
                                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                        })
            })
        {
            return Err(invalid());
        }
        Ok(request)
    }

    fn selector(&self) -> Selector {
        Selector {
            harness_id: self.harness_id.clone(),
            scope: self.scope,
            provider_version: self.provider_version.clone(),
            harness_executable: self.harness_executable.clone(),
        }
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Selector {
    harness_id: String,
    scope: Scope,
    provider_version: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    harness_executable: Option<program::Executable>,
}

impl Selector {
    fn validate(&self) -> Result<()> {
        harnesses::definition(&self.harness_id)?;
        if self.harness_id == "undefined" {
            return Err(invalid());
        }
        crate::provider::managed::sequence(&self.provider_version)?;
        if let Some(prefix) = &self.harness_executable
            && (!prefix.0.is_absolute()
                || !prefix
                    .0
                    .to_str()
                    .is_some_and(|path| path.len() <= 4096 && !path.contains('\0')))
        {
            return Err(invalid());
        }
        Ok(())
    }

    fn target(&self, identity: &Identity) -> Result<Target> {
        self.validate()?;
        let (os, arch) = runtime::platform()?.split_once('/').ok_or_else(invalid)?;
        let target = Target {
            harness_id: self.harness_id.clone(),
            scope: self.scope,
            os: os.into(),
            arch: arch.into(),
            harness_version: String::new(),
            owner_id: identity.account_id.clone(),
            capabilities: Default::default(),
            permissions: Default::default(),
            entitlements: Default::default(),
            env_present: Default::default(),
            grants: Default::default(),
            pinned_passport_digests: Default::default(),
            owned_passport_digests: Default::default(),
            accessible_passport_digests: Default::default(),
            access_context_digest: None,
            for_redistribution: false,
        };
        target.validate()?;
        Ok(target)
    }
}

fn text<'a>(value: &'a Value, name: &str) -> Result<&'a str> {
    value[name].as_str().ok_or_else(invalid)
}

fn retain(total: &mut u64, reference: &Value) -> Result<()> {
    let size = reference["size_bytes"].as_u64().ok_or_else(invalid)?;
    *total = total.checked_add(size).ok_or_else(invalid)?;
    if *total > MAX_CONTENT {
        return Err(Failure::precondition(
            "the exact selection graph exceeds 64 MiB of artifact verification work",
        ));
    }
    Ok(())
}

fn report(target: Target, assessment: Value, bytes: u64) -> Value {
    let not_observed = program::unobserved(target.harness_version.is_empty());
    json!({"target":target,"assessment":assessment,"verified_artifact_bytes":bytes,
        "provider":null,"provider_observed":false,
        "not_observed":not_observed,
        "permission_policy":"none_granted","installation_authorized":false,"harness_written":false})
}

struct Inputs {
    target: Target,
    evidence: BTreeMap<String, Evidence>,
    bytes: u64,
}

/// Derive in the caller's transaction, including the transaction that records
/// a new proposal or confirmation. These observations are never deserialized.
fn inputs(connection: &Connection, roots: &[Value], target: Target) -> Result<Inputs> {
    inputs_with_budget(connection, roots, target, MAX_CONTENT)
}

fn inputs_with_budget(
    connection: &Connection,
    roots: &[Value],
    mut target: Target,
    budget: u64,
) -> Result<Inputs> {
    let closure = graph::exact(connection, roots)?;
    let mut documents = Vec::new();
    let mut total = 0;
    if closure["resolved"] == true {
        for node in closure["nodes"].as_array().ok_or_else(invalid)? {
            let document = Objects { connection }.exact_version(
                text(node, "stable_id")?,
                text(node, "version")?,
                Some(text(node, "passport_digest")?),
            )?;
            retain(&mut total, &document["artifact"])?;
            for adaptation in document["adaptations"].as_array().into_iter().flatten() {
                if !adaptation["source_artifact"].is_null() {
                    retain(&mut total, &adaptation["source_artifact"])?;
                }
                for scope in adaptation["scope_adaptations"]
                    .as_array()
                    .into_iter()
                    .flatten()
                {
                    retain(&mut total, &scope["projection_artifact"])?;
                }
            }
            documents.push(document);
        }
    }
    if total > budget {
        return Err(Failure::precondition(
            "selection artifact verification exceeds its aggregate byte budget; reduce the page limit",
        ));
    }
    let mut evidence = BTreeMap::new();
    let inherited = crate::account::attachment::inherited(connection, &target.owner_id)?;
    for document in &documents {
        let passport_digest = crate::digest::canonical("ai-stp:passport:v1", document)?;
        if document["owner_id"] != target.owner_id && inherited.contains(&passport_digest) {
            target
                .owned_passport_digests
                .insert(passport_digest.clone());
        }
        if document["kind"] == "component" {
            freezing::verify(connection, document)?;
        } else {
            let bytes =
                revisions::read_content(connection, text(&document["artifact"], "digest")?)?;
            setups::verify_definition(document, &bytes)?;
        }
        for variable in document["required_env"].as_array().into_iter().flatten() {
            let name = text(variable, "name")?;
            // Observe only declared names. Values never enter reports or digests.
            if std::env::var_os(name).is_some_and(|value| !value.is_empty()) {
                target.env_present.insert(name.into());
            }
        }
        evidence.insert(
            text(document, "stable_id")?.into(),
            Evidence {
                passport_digest,
                registrable: true,
                blocked: false,
                author_verified: false,
                component_verified: false,
                checks_current: false,
                consented: false,
            },
        );
    }
    Ok(Inputs {
        target,
        evidence,
        bytes: total,
    })
}

fn assess_snapshot(
    connection: &Connection,
    roots: &[Value],
    target: Target,
    provider: &Info,
    access: Option<&access::Observed>,
) -> Result<Value> {
    let mut observed = inputs(connection, roots, target)?;
    if let Some(access) = access {
        access.apply(&mut observed)?;
    }
    let assessment = eligibility::assess_connection(
        connection,
        roots,
        &observed.target,
        &observed.evidence,
        Some(provider),
    )?;
    Ok(report(observed.target, assessment, observed.bytes))
}

fn with_provider<T>(
    parent: &Path,
    selector: &Selector,
    identity: &Owner,
    effect: impl FnOnce(&Info, &artifact::Artifact<'_>, Value) -> Result<T>,
) -> Result<T> {
    selector.validate()?;
    let runtime = runtime::Runtime::observe()?;
    let trust = trust::refresh(parent)?;
    let artifact = artifact::fetch(
        &selector.harness_id,
        &selector.provider_version,
        runtime::platform()?,
        &trust,
    )?;
    let (provider, report) = runtime.declaration(&artifact)?;
    if *owner(parent)? != **identity {
        return Err(Failure::precondition(
            "the isolated identity changed during provider observation",
        ));
    }
    effect(&provider, &artifact, report)
}

/// Local owner authority comes from the isolated identity. Optional account
/// access and exact local trust decisions remain independent observations.
pub fn assess(parent: &Path, path: &Path) -> Result<Value> {
    let request = Request::parse(path, false)?;
    let identity = owner(parent)?;
    let roots = serde_json::to_value(&request.members)
        .map_err(|_| invalid())?
        .as_array()
        .ok_or_else(invalid)?
        .clone();
    let mut store = identity.planning()?;
    // Refuse missing or conflicting coordinates before network or trust writes.
    let graph = store.transaction(|t| graph::exact(t, &roots))?;
    drop(store);
    if graph["resolved"] != true {
        let mut store = identity.planning()?;
        let (mut target, program) =
            store.transaction(|t| request.selector().observe(t, parent, &identity))?;
        target.for_redistribution = request.for_redistribution;
        let mut result = report(
            target,
            json!({"schema_version":1,"graph":graph,
            "assessments":[],"admissible":false,"auto_selectable":false}),
            0,
        );
        result["program_observation_digest"] = json!(program);
        return Ok(result);
    }
    with_provider(
        parent,
        &request.selector(),
        &identity,
        |provider, artifact, report| {
            let access = access::Observed::capture(
                parent,
                &identity,
                std::slice::from_ref(&roots),
                access::Intent::Review(&request.access),
            )?;
            // Re-read the graph after external I/O; preflight is never a permit.
            let mut store = identity.planning()?;
            let mut result = store.transaction(|t| {
                let (mut target, program) = request.selector().observe(t, parent, &identity)?;
                target.for_redistribution = request.for_redistribution;
                let mut result = assess_snapshot(t, &roots, target, provider, Some(&access))?;
                result["program_observation_digest"] = json!(program);
                Ok(result)
            })?;
            artifact.executable()?;
            result["provider"] = report;
            result["provider_observed"] = true.into();
            if let Some(observation) = access.report()? {
                result["access_observation"] = observation;
            }
            Ok(result)
        },
    )
}
