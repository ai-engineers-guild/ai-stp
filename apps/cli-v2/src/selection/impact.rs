//! Read-only context and capability differences over exact retained setup graphs.

mod history;
mod price;

use std::collections::{BTreeMap, BTreeSet};

use rusqlite::Connection;
use serde_json::{Value, json};

use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
    projection::artifact,
    store::{Store, revisions},
    wire::Schema,
};

static REPORT: Schema = Schema::new(include_str!(
    "../../../../schemas/v1/cli-selection-impact-report.schema.json"
));
const MAX_BYTES: usize = 128 * 1024 * 1024;
const CAPABILITIES: [&str; 8] = [
    "tools",
    "mcp_servers",
    "hooks",
    "network_requirements",
    "credential_requirements",
    "filesystem_permissions",
    "network_permissions",
    "process_permissions",
];

pub struct Request<'a> {
    pub setup_id: &'a str,
    pub setup_version: &'a str,
    pub baseline: Option<(&'a str, &'a str)>,
    pub project_id: Option<&'a str>,
    pub estimator_profile: &'a str,
    pub price_profile: Option<&'a Value>,
}

fn invalid() -> Failure {
    Failure::new(
        ErrorKind::Conflict,
        "the exact setup graph cannot support a complete local report",
    )
}

struct Graph {
    coordinate: Value,
    harness: String,
    budget: Value,
    capabilities: Value,
}

type Claims = BTreeMap<&'static str, BTreeSet<String>>;

fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str> {
    value[field].as_str().ok_or_else(invalid)
}

fn coordinate(document: &Value) -> Result<Value> {
    Ok(
        json!({"stable_id":document["stable_id"],"version":document["version"],
        "passport_digest":digest::canonical("ai-stp:passport:v1", document)?}),
    )
}

fn bytes(connection: &Connection, reference: &Value, remaining: &mut usize) -> Result<Vec<u8>> {
    let size = reference["size_bytes"].as_u64().ok_or_else(invalid)?;
    if size > *remaining as u64 {
        return Err(Failure::precondition(
            "the report exceeds its 128 MiB artifact budget",
        ));
    }
    let payload = revisions::read_content(connection, text(reference, "digest")?)?;
    if size != payload.len() as u64 {
        return Err(invalid());
    }
    *remaining -= payload.len();
    Ok(payload)
}

fn claim(claims: &mut Claims, name: &'static str, values: &Value) -> Result<()> {
    if values.is_null() {
        return Ok(());
    }
    for value in values.as_array().ok_or_else(invalid)? {
        claims
            .entry(name)
            .or_default()
            .insert(value.as_str().ok_or_else(invalid)?.into());
    }
    Ok(())
}

fn graph(
    connection: &Connection,
    id: &str,
    version: &str,
    exact_units: bool,
    remaining: &mut usize,
) -> Result<Graph> {
    if !passport::stable_id(id, "setup") {
        return Err(Failure::input("the candidate must name an exact setup"));
    }
    let objects = Objects { connection };
    let setup = objects.exact_version(id, version, None)?;
    let harness = text(&setup, "harness_id")?;
    let payload = bytes(connection, &setup["artifact"], remaining)?;
    if setup["artifact_format"] == "ai-stp-setup-definition/1" {
        crate::authoring::setups::verify_definition(&setup, &payload)?;
    }
    let references = setup["components"].as_array().ok_or_else(invalid)?;
    if references.len() > 512 {
        return Err(Failure::precondition(
            "the report exceeds 512 exact members",
        ));
    }
    let mut held = BTreeMap::new();
    let mut dependencies = Vec::new();
    let mut claims: Claims = CAPABILITIES
        .into_iter()
        .map(|name| (name, BTreeSet::new()))
        .collect();
    let mut measured = Vec::new();
    let (mut always, mut conditional, mut unavailable) = (0_u64, 0_u64, 0_u64);
    for reference in references {
        if !reference["variant_id"].is_null() {
            return Err(invalid());
        }
        let id = text(reference, "stable_id")?;
        let document = objects.exact_version(
            id,
            text(reference, "version")?,
            Some(text(reference, "passport_digest")?),
        )?;
        if document["kind"] != "component"
            || held.insert(id.to_owned(), coordinate(&document)?).is_some()
        {
            return Err(invalid());
        }
        if let Some(required) = document["requires_components"].as_array() {
            dependencies.extend(required.iter().cloned());
            if dependencies.len() > 8192 {
                return Err(Failure::precondition(
                    "the report exceeds 8192 dependency edges",
                ));
            }
        }
        let adaptation = document["adaptations"]
            .as_array()
            .ok_or_else(invalid)?
            .iter()
            .find(|item| item["harness_id"] == harness)
            .ok_or_else(invalid)?;
        let scopes = adaptation["scope_adaptations"]
            .as_array()
            .ok_or_else(invalid)?;
        let kind = text(&document, "component_type")?;
        let tokenized = matches!(kind, "instruction" | "skill" | "agent" | "command");
        let label = format!("{}@{}", id, text(&document, "version")?);
        let mut native = BTreeSet::new();
        let (mut byte_count, mut codepoints) = (0_u64, 0_u64);
        let mut valid_utf8 = true;
        for scope in scopes {
            let payload = bytes(connection, &scope["projection_artifact"], remaining)?;
            let files = artifact::verify(scope, &payload)?;
            for member in scope["members"].as_array().ok_or_else(invalid)? {
                for id in member["native_ids"].as_array().ok_or_else(invalid)? {
                    native.insert(id.as_str().ok_or_else(invalid)?.to_owned());
                }
            }
            if tokenized && scopes.len() == 1 {
                for file in files {
                    byte_count += file.bytes.len() as u64;
                    match std::str::from_utf8(&file.bytes) {
                        Ok(text) => codepoints += text.chars().count() as u64,
                        Err(_) => valid_utf8 = false,
                    }
                }
            }
        }
        let capability = match kind {
            "command" => Some("tools"),
            "mcp" => Some("mcp_servers"),
            "hook" => Some("hooks"),
            _ => None,
        };
        if let Some(capability) = capability {
            if native.is_empty() {
                native.insert(label.clone());
            }
            claims.entry(capability).or_default().extend(native);
        }
        claim(
            &mut claims,
            "network_requirements",
            &document["external_endpoints"],
        )?;
        if document["requires_credentials"] == true
            || document["required_env"]
                .as_array()
                .is_some_and(|items| !items.is_empty())
        {
            claims
                .entry("credential_requirements")
                .or_default()
                .insert(label);
        }
        for (category, name) in [
            ("filesystem", "filesystem_permissions"),
            ("network", "network_permissions"),
            ("process", "process_permissions"),
        ] {
            claim(&mut claims, name, &document["permissions"][category])?;
        }
        if tokenized {
            let reason = if scopes.len() != 1 {
                Some("adaptation_selection_required")
            } else if !valid_utf8 {
                Some("content_is_not_utf8")
            } else {
                None
            };
            let loading = if kind == "instruction" {
                "always"
            } else {
                "conditional"
            };
            let tokens = reason.is_none().then(|| {
                if exact_units {
                    byte_count
                } else {
                    codepoints.div_ceil(4)
                }
            });
            if let Some(tokens) = tokens {
                if loading == "always" {
                    always += tokens;
                } else {
                    conditional += tokens;
                }
            } else {
                unavailable += 1;
            }
            measured.push(json!({"component":coordinate(&document)?,"component_type":kind,
                "loading":loading,"status":if reason.is_some() {"unavailable"} else if exact_units {"exact"} else {"estimated"},
                "tokens":tokens,"utf8_bytes":byte_count,"reason":reason}));
        }
    }
    for dependency in dependencies {
        if !dependency["variant_id"].is_null() {
            return Err(invalid());
        }
        let candidate = held
            .get(text(&dependency, "stable_id")?)
            .ok_or_else(invalid)?;
        if candidate["version"] != dependency["version"]
            || candidate["passport_digest"] != dependency["passport_digest"]
        {
            return Err(invalid());
        }
    }
    Ok(Graph {
        coordinate: coordinate(&setup)?,
        harness: harness.into(),
        budget: json!({"always_tokens":always,"conditional_tokens":conditional,"unavailable_components":unavailable,"components":measured}),
        capabilities: serde_json::to_value(claims).map_err(|_| invalid())?,
    })
}

fn difference(left: &Value, right: &Value) -> Result<Value> {
    let mut result = serde_json::Map::new();
    for name in CAPABILITIES {
        let left = left[name].as_array().ok_or_else(invalid)?;
        let right = right[name].as_array().ok_or_else(invalid)?;
        result.insert(
            name.into(),
            left.iter()
                .filter(|item| !right.contains(item))
                .cloned()
                .collect(),
        );
    }
    Ok(result.into())
}

pub fn report(store: &mut Store, request: &Request<'_>, at: &str) -> Result<Value> {
    let exact = match request.estimator_profile {
        "ai-stp:utf8-bytes/1" => true,
        "ai-stp:unicode-chars-div4/1" => false,
        _ => {
            return Err(Failure::input(
                "the context estimator profile is unsupported",
            ));
        }
    };
    if !passport::timestamp(at)
        || request
            .project_id
            .is_some_and(|id| !passport::stable_id(id, "project"))
    {
        return Err(Failure::input(
            "the report timestamp or project identifier is invalid",
        ));
    }
    store.transaction(|connection| {
        let mut remaining = MAX_BYTES;
        let candidate = graph(
            connection,
            request.setup_id,
            request.setup_version,
            exact,
            &mut remaining,
        )?;
        let baseline = if let Some((id, version)) = request.baseline {
            Some((id.to_owned(), version.to_owned(), "explicit"))
        } else if let Some(project) = request.project_id {
            history::baseline(connection, project, &candidate.harness)?
        } else {
            None
        };
        let source = baseline.as_ref().map_or("none", |(_, _, source)| *source);
        let baseline = baseline
            .map(|(id, version, _)| graph(connection, &id, &version, exact, &mut remaining))
            .transpose()?;
        if baseline.as_ref().is_some_and(|other| other.harness != candidate.harness) {
            return Err(Failure::input("candidate and baseline belong to different harnesses"));
        }
        let mut delta = Value::Null;
        let mut capability_delta = Value::Null;
        if let Some(baseline) = &baseline {
            if candidate.budget["unavailable_components"] == 0 && baseline.budget["unavailable_components"] == 0 {
                delta = json!({"always_tokens":candidate.budget["always_tokens"].as_i64().ok_or_else(invalid)? - baseline.budget["always_tokens"].as_i64().ok_or_else(invalid)?,
                    "conditional_tokens":candidate.budget["conditional_tokens"].as_i64().ok_or_else(invalid)? - baseline.budget["conditional_tokens"].as_i64().ok_or_else(invalid)?});
            }
            capability_delta = json!({"added":difference(&candidate.capabilities,&baseline.capabilities)?,"removed":difference(&baseline.capabilities,&candidate.capabilities)?});
        }
        let result = json!({"schema_version":1,"generated_at":at,"freshness":"local_snapshot",
            "candidate_setup":candidate.coordinate,"baseline_setup":baseline.as_ref().map(|item| &item.coordinate),"baseline_source":source,
            "estimator":{"schema_version":1,"profile":request.estimator_profile,"accuracy":if exact {"exact"} else {"estimated"},
                "method":if exact {"utf8_byte_count"} else {"unicode_codepoints_div_4"},"model":null,"local_only":true},
            "candidate_context":candidate.budget,"baseline_context":baseline.as_ref().map(|item| &item.budget),"context_delta":delta,
            "candidate_capabilities":candidate.capabilities,"baseline_capabilities":baseline.as_ref().map(|item| &item.capabilities),
            "capability_delta":capability_delta,"token_cost":price::cost(&candidate.budget,request.estimator_profile,request.price_profile,at)?});
        REPORT.validate(&result)?;
        Ok(result)
    })
}
