//! Exact local selection inputs derived here, never accepted as authority JSON.

#[cfg(test)]
mod tests;

use std::{collections::BTreeMap, path::Path};

use rusqlite::Connection;
use serde::Deserialize;
use serde_json::{Value, json};

use super::{
    eligibility::{self, Evidence, Target},
    graph,
};
use crate::{
    authoring::{Identity, freezing, setups},
    canonical,
    error::{Failure, Result},
    files, harnesses, identity,
    objects::Objects,
    passport,
    projection::Scope,
    provider::{Info, artifact, runtime, trust},
    store::{Store, revisions},
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
}

fn invalid() -> Failure {
    Failure::input("selection requires a closed bounded request with exact object coordinates")
}

impl Request {
    fn parse(path: &Path) -> Result<Self> {
        let request: Self =
            serde_json::from_value(canonical::parse(&files::read(path, MAX_REQUEST)?)?)
                .map_err(|_| invalid())?;
        harnesses::definition(&request.harness_id)?;
        let version = &request.provider_version;
        if request.harness_id == "undefined"
            || version.len() > 64
            || version.split('.').count() != 3
            || version.split('.').any(|part| {
                part.parse::<u64>().is_err()
                    || !part.bytes().all(|b| b.is_ascii_digit())
                    || part.len() > 1 && part.starts_with('0')
            })
            || request.members.is_empty()
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

    fn target(&self, identity: &Identity) -> Result<Target> {
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
            for_redistribution: self.for_redistribution,
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
    json!({"target":target,"assessment":assessment,"verified_artifact_bytes":bytes,
        "provider":null,"provider_observed":false,
        "not_observed":["harness_version","project_capabilities","cloud_trust","cloud_grants"],
        "permission_policy":"none_granted","installation_authorized":false,"harness_written":false})
}

/// All exact bytes and assessments are read in the same SQLite transaction.
fn assess_snapshot(
    connection: &Connection,
    roots: &[Value],
    mut target: Target,
    provider: &Info,
) -> Result<Value> {
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
    let mut evidence = BTreeMap::new();
    for document in &documents {
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
                passport_digest: crate::digest::canonical("ai-stp:passport:v1", document)?,
                registrable: true,
                blocked: false,
                author_verified: false,
                component_verified: false,
                checks_current: false,
                consented: false,
            },
        );
    }
    let assessment =
        eligibility::assess_connection(connection, roots, &target, &evidence, Some(provider))?;
    Ok(report(target, assessment, total))
}

/// Network access authenticates the provider only; local owner authority comes
/// from the isolated identity. Public trust, grants and consent remain absent.
pub fn assess(parent: &Path, path: &Path) -> Result<Value> {
    let request = Request::parse(path)?;
    let identity = identity::current(parent)?
        .ok_or_else(|| {
            Failure::precondition(
                "initialize the isolated native identity before assessing owned objects",
            )
        })?
        .context();
    let target = request.target(&identity)?;
    let roots = serde_json::to_value(&request.members)
        .map_err(|_| invalid())?
        .as_array()
        .ok_or_else(invalid)?
        .clone();
    let mut store = Store::planning(parent)?;
    // Refuse missing or conflicting coordinates before network or trust writes.
    let graph = store.transaction(|t| graph::exact(t, &roots))?;
    drop(store);
    if graph["resolved"] != true {
        return Ok(report(
            target,
            json!({"schema_version":1,"graph":graph,
            "assessments":[],"admissible":false,"auto_selectable":false}),
            0,
        ));
    }
    let runtime = runtime::Runtime::observe()?;
    let trust = trust::refresh(parent)?;
    let artifact = artifact::fetch(
        &request.harness_id,
        &request.provider_version,
        runtime::platform()?,
        &trust,
    )?;
    let (provider, report) = runtime.declaration(&artifact)?;
    if identity::current(parent)?.map(|current| current.context()) != Some(identity) {
        return Err(Failure::precondition(
            "the isolated identity changed during provider observation",
        ));
    }
    // Release the registry lock during external I/O, then read the entire graph
    // again. A changed local object cannot inherit the preflight's verdict.
    let mut store = Store::planning(parent)?;
    let mut result = store.transaction(|t| assess_snapshot(t, &roots, target, &provider))?;
    artifact.executable()?;
    result["provider"] = report;
    result["provider_observed"] = true.into();
    Ok(result)
}
