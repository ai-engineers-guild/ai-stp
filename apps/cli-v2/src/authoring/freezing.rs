//! Deterministic draft compilation. Only the caller's transaction may store bytes.

use std::collections::{BTreeMap, BTreeSet};

use rusqlite::{Connection, Transaction};
use serde_json::{Value, json};

use super::contribution::{self, Format};
use super::{native_identity, source_project};
use crate::{
    artifacts::{self, Member},
    digest,
    error::{Failure, Result},
    harnesses::Shape,
    passport,
    projection::{self, Scope, artifact},
    provider::Info,
    store::revisions,
};

fn invalid() -> Failure {
    Failure::precondition("the component draft has incomplete or inconsistent native release facts")
}

fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str> {
    value[field]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(invalid)
}

fn fact_values(document: &Value) -> Result<Value> {
    Ok(Value::Object(
        document["facts"]
            .as_object()
            .ok_or_else(invalid)?
            .iter()
            .map(|(key, fact)| (key.clone(), fact["value"].clone()))
            .collect(),
    ))
}

fn default(value: &Value, field: &str, fallback: Value) -> Value {
    value
        .get(field)
        .filter(|value| !value.is_null())
        .cloned()
        .unwrap_or(fallback)
}

fn permissions(value: &Value) -> Result<Value> {
    let mut value = if value.is_null() {
        json!({})
    } else {
        value.clone()
    };
    let object = value.as_object_mut().ok_or_else(invalid)?;
    for key in ["filesystem", "network", "process"] {
        object.entry(key).or_insert(json!([]));
    }
    Ok(value)
}

pub(crate) fn verify(connection: &Connection, document: &Value) -> Result<()> {
    passport::versions::validate_document(document)?;
    let payload = revisions::read_content(connection, text(&document["artifact"], "digest")?)?;
    if document["artifact"]["size_bytes"] != payload.len() {
        return Err(invalid());
    }
    drop(payload);
    for adaptation in document["adaptations"].as_array().ok_or_else(invalid)? {
        if !adaptation["source_artifact"].is_null() {
            let source = &adaptation["source_artifact"];
            let bytes = revisions::read_content(connection, text(source, "digest")?)?;
            if source["size_bytes"] != bytes.len() {
                return Err(invalid());
            }
        }
        for scope in adaptation["scope_adaptations"]
            .as_array()
            .ok_or_else(invalid)?
        {
            let payload = revisions::read_content(
                connection,
                text(&scope["projection_artifact"], "digest")?,
            )?;
            let files = artifact::verify(scope, &payload)?;
            native_identity::verify_files(
                text(document, "component_type")?,
                text(adaptation, "harness_id")?,
                scope["members"].as_array().ok_or_else(invalid)?,
                &files,
            )?;
        }
    }
    Ok(())
}

pub(super) fn compile(
    transaction: &Transaction<'_>,
    mut document: Value,
    version: &str,
    providers: &[Info],
    store_at: Option<&str>,
) -> Result<Value> {
    document["version"] = version.into();
    document["parent_revision_ids"] = json!([]);
    // Presence commits the draft to its complete graph. Invalid complete data must
    // never fall through to a reconstruction from one harness's flat facts.
    if document.get("adaptations").is_some() {
        if source_project::unfinished("description.md", text(&document, "description")?.as_bytes())
        {
            return Err(invalid());
        }
        let references = document
            .as_object_mut()
            .ok_or_else(invalid)?
            .entry("requires_components")
            .or_insert(json!([]));
        passport::versions::normalize_component_refs(references)?;
        let document = revisions::seal(&document)?;
        verify(transaction, &document)?;
        return Ok(document);
    }
    let values = fact_values(&document)?;
    for field in [
        "name",
        "description",
        "tags",
        "harness_id",
        "component_type",
        "projection_kind",
        "license",
    ] {
        if values[field].is_null() {
            return Err(invalid());
        }
    }
    if source_project::unfinished("description.md", text(&values, "description")?.as_bytes()) {
        return Err(invalid());
    }
    let sources = match values.get("adaptation_contents") {
        None | Some(Value::Null) => std::slice::from_ref(&values),
        Some(Value::Array(sources)) if !sources.is_empty() && sources.len() <= 21 => sources,
        _ => return Err(invalid()),
    };
    let mut harnesses: BTreeMap<&str, Value> = BTreeMap::new();
    for source in sources {
        let adaptation = freeze(transaction, &values, source, providers, store_at)?;
        if let Some(existing) = harnesses.get_mut(text(source, "harness_id")?) {
            let selected = &adaptation["scope_adaptations"][0];
            let scopes = existing["scope_adaptations"]
                .as_array_mut()
                .ok_or_else(invalid)?;
            if scopes
                .iter()
                .any(|scope| scope["scope"] == selected["scope"])
            {
                return Err(Failure::precondition(
                    "a release cannot declare the same resolved harness scope twice",
                ));
            }
            scopes.push(selected.clone());
            scopes.sort_by(|a, b| a["scope"].as_str().cmp(&b["scope"].as_str()));
        } else {
            harnesses.insert(text(source, "harness_id")?, adaptation);
        }
    }
    let adaptations = harnesses
        .into_values()
        .map(|value| passport::versions::seal_adaptation(&value))
        .collect::<Result<Vec<_>>>()?;
    complete(document, &values, adaptations)
}

/// Shared complete-passport assembly; source projects and native releases use one contract.
pub(super) fn complete(
    mut document: Value,
    values: &Value,
    adaptations: Vec<Value>,
) -> Result<Value> {
    if adaptations.is_empty() {
        return Err(invalid());
    }
    document["artifact"] = adaptations[0]["scope_adaptations"][0]["projection_artifact"].clone();
    document["artifact_format"] = artifact::FORMAT.into();
    document["adaptations"] = adaptations.into();
    document["origin_harness_id"] = values["harness_id"].clone();
    for field in ["name", "description", "tags", "license", "component_type"] {
        document[field] = values[field].clone();
    }
    document["source"] = values["source"].clone();
    if document["source"].is_null()
        && ["source_repository", "source_revision", "source_subpath"]
            .iter()
            .all(|field| {
                values[field]
                    .as_str()
                    .is_some_and(|value| !value.is_empty())
            })
    {
        document["source"] = json!({"repository":values["source_repository"],
            "commit":values["source_revision"],"path":values["source_subpath"]});
    }
    for field in [
        "required_env",
        "external_endpoints",
        "compatibility_evidence_refs",
        "provides_capabilities",
        "requires_components",
        "requires_capabilities",
        "runtime_requirements",
    ] {
        document[field] = default(values, field, json!([]));
    }
    document["requires_credentials"] = default(values, "requires_credentials", false.into());
    document["requires_authorization"] = default(values, "requires_authorization", "none".into());
    document["permissions"] = permissions(&values["permissions"])?;
    let mut conflicts = default(values, "conflicts", json!({}));
    let object = conflicts.as_object_mut().ok_or_else(invalid)?;
    for key in ["paths", "commands", "agents", "hooks", "mcp", "plugins"] {
        object.entry(key).or_insert(json!([]));
    }
    document["conflicts"] = conflicts;
    passport::versions::normalize_component_refs(&mut document["requires_components"])?;
    let document = revisions::seal(&document)?;
    let mut version = document.clone();
    version["parent_revision_ids"] = json!([]);
    passport::versions::validate_document(&revisions::seal(&version)?)?;
    Ok(document)
}

fn freeze(
    transaction: &Transaction<'_>,
    values: &Value,
    source: &Value,
    providers: &[Info],
    store_at: Option<&str>,
) -> Result<Value> {
    let payload = revisions::read_content(transaction, text(source, "content_digest")?)?;
    if source["byte_length"].as_u64() != Some(payload.len() as u64) {
        return Err(invalid().with_details([("constraint".into(), "source_size_mismatch".into())]));
    }
    let (adaptation, bytes) = project(values, source, payload, providers)?;
    if let Some(at) = store_at {
        revisions::content(transaction, &bytes, at)?;
    }
    Ok(adaptation)
}

/// The same deterministic projection compiler serves release and source preparation.
pub(super) fn project(
    values: &Value,
    source: &Value,
    payload: Vec<u8>,
    providers: &[Info],
) -> Result<(Value, Vec<u8>)> {
    let harness = text(source, "harness_id")?;
    let kind = text(values, "component_type")?;
    let requested: Scope =
        serde_json::from_value(source["scope"].clone()).map_err(|_| invalid())?;
    let route = projection::route(kind, harness, requested)?.ok_or_else(|| {
        Failure::precondition(
            "this harness and component kind have no declared native provider route",
        )
    })?;
    let provider = providers
        .iter()
        .find(|info| info.document()["harness_id"] == harness)
        .ok_or_else(|| {
            Failure::precondition(
                "native release requires an explicit provider declaration for every source harness",
            )
        })?;
    let profile = provider
        .profile(route.target_scope)
        .ok_or_else(|| Failure::precondition("the provider has no profile for the source scope"))?;
    if source["projection_kind"] != route.projection_kind {
        return Err(invalid());
    }
    let paths: Vec<&str> = source["managed_paths"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(|value| {
            value
                .as_str()
                .filter(|path| artifacts::safe_path(path))
                .ok_or_else(invalid)
        })
        .collect::<Result<_>>()?;
    match route.shape {
        Shape::File => {
            let expected = projection::claimed_paths(&route.relative, kind == "hook")?;
            if paths.len() != expected.len()
                || paths.iter().copied().collect::<BTreeSet<_>>()
                    != expected.iter().map(String::as_str).collect()
            {
                return Err(invalid());
            }
        }
        Shape::Directory => {
            if paths.len() != 1 || !paths[0].starts_with(&format!("{}/", route.relative)) {
                return Err(invalid());
            }
        }
    }
    let key = match source.get("declared_key") {
        None | Some(Value::Null) => "",
        Some(Value::String(key)) => key,
        _ => return Err(invalid()),
    };
    if key != route.declared_key {
        return Err(invalid());
    }
    if !key.is_empty() && source["source_locator"] != format!("{}#{key}", route.relative) {
        return Err(invalid());
    }
    let mut files = match text(source, "content_format")? {
        artifacts::FILE_FORMAT => {
            if payload.len() > artifacts::MAX_FILE_BYTES {
                return Err(invalid());
            }
            let mode = match source.get("source_mode") {
                None | Some(Value::Null) => 0o644,
                Some(mode) => mode.as_u64().ok_or_else(invalid)?,
            };
            if !matches!(mode, 0o644 | 0o755) {
                return Err(invalid());
            }
            vec![Member {
                path: String::new(),
                bytes: payload,
                mode: mode as u32,
            }]
        }
        artifacts::TREE_FORMAT => artifacts::decode_tree(&payload)?,
        _ => {
            return Err(Failure::precondition(
                "this source artifact format is not supported by native release",
            ));
        }
    };
    if files.is_empty() || (!key.is_empty() && (files.len() != 1 || !files[0].path.is_empty())) {
        return Err(invalid());
    }
    let parser = if key.is_empty() {
        None
    } else {
        let format = Format::for_path(&route.relative)?;
        contribution::assemble(format, None, key, &files[0].bytes)?;
        Some(if format == Format::Toml {
            "toml/1"
        } else {
            "json/1"
        })
    };
    for file in &mut files {
        file.path = if file.path.is_empty() {
            if route.shape == Shape::File {
                route.relative.clone()
            } else {
                paths[0].into()
            }
        } else if route.shape == Shape::File {
            if kind != "hook"
                || !route.relative.ends_with("hooks.json")
                || (file.path != "hooks.json" && !file.path.starts_with("hooks/"))
            {
                return Err(invalid());
            }
            match route.relative.rsplit_once('/') {
                Some((parent, _)) => format!("{parent}/{}", file.path),
                None => file.path.clone(),
            }
        } else {
            format!("{}/{}", paths[0], file.path)
        };
        if source_project::unfinished(&file.path, &file.bytes) {
            return Err(Failure::precondition(
                "the source still contains an unfinished scaffold marker",
            )
            .with_details([
                ("constraint".into(), "scaffold_marker".into()),
                ("path".into(), file.path.clone().into()),
            ]));
        }
    }
    if route.shape == Shape::File && !files.iter().any(|file| file.path == route.relative) {
        return Err(invalid());
    }
    files.sort_by(|a, b| a.path.cmp(&b.path));
    let native_ids = default(source, "native_ids", json!([]));
    let members = files.iter().map(|file| Ok(json!({
        "path":file.path,"object_type":"file","mode":file.mode,
        "content_artifact":{"digest":digest::bytes("ai-stp:artifact:v1",&file.bytes)?,"size_bytes":file.bytes.len()},
        "native_ids":native_ids,"content_format":"application/octet-stream","parser_id":parser,
        "ownership":if key.is_empty(){"whole"}else{"contribution"},
        "ownership_key":if key.is_empty(){None}else{Some(key)},
        "write_semantics":if key.is_empty(){"replace"}else{"merge"},
        "withdrawal_semantics":if key.is_empty(){"remove_path"}else{"preserve_unowned"}
    }))).collect::<Result<Vec<_>>>()?;
    native_identity::verify_files(kind, harness, &members, &files)?;
    let bytes = artifact::build_members(&members, &files)?;
    let address = digest::bytes("ai-stp:artifact:v1", &bytes)?;
    let mut scope = json!({"scope":route.target_scope,"projection_format":artifact::FORMAT,
        "projection_artifact":{"digest":address,"size_bytes":bytes.len()},
        "provider_component_kind":if route.provider_kind.is_empty(){kind}else{&route.provider_kind},
        "projection_kind":route.projection_kind,"required_surface":{"profile_id":profile["profile_id"],
        "profile_digest":profile["digest"],"bundle_format":"ai-stp-bundle/2"},
        "permissions":permissions(source.get("permissions").unwrap_or(&values["permissions"]))?,"members":members,
        "technical_support":"experimental","technical_support_reason":"locally authored component pending assessment",
        "semantic_losses":[]});
    for field in [
        "supported_harness_versions",
        "supported_os",
        "supported_arch",
    ] {
        scope[field] = default(source, field, default(values, field, json!([])));
    }
    if !provider.supports_scope(route.target_scope, &scope) {
        return Err(Failure::precondition(
            "the exact provider declaration does not cover this native projection",
        ));
    }
    let adaptation = passport::versions::seal_adaptation(
        &json!({"harness_id":harness,"implementation_mode":"native",
        "source_artifact":null,"transform":null,"logical_component_type":kind,"scope_adaptations":[scope]}),
    )?;
    Ok((adaptation, bytes))
}
