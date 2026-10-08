//! Immutable version invariants not expressible by the generated wire schema.

use serde_json::{Value, json};
use std::collections::BTreeSet;

use super::markdown;
use crate::wire::Schema;
use crate::{
    digest,
    error::{Failure, Result},
};

static COMPONENT: Schema = Schema::reader(include_str!(
    "../../../../schemas/v1/component-version-passport.schema.json"
));
static SETUP: Schema = Schema::reader(include_str!(
    "../../../../schemas/v1/setup-version-passport.schema.json"
));
static SCOPE: Schema = Schema::definition(
    include_str!("../../../../schemas/v1/component-adaptation.schema.json"),
    "ScopeAdaptation",
);

pub fn validate_document(document: &Value) -> Result<()> {
    match document["kind"].as_str() {
        Some("component") => &COMPONENT,
        Some("setup") => &SETUP,
        _ => return Err(invalid()),
    }
    .validate(document)?;
    super::validate_identity(document)?;
    validate(document)
}

fn invalid() -> Failure {
    Failure::precondition("immutable passport has inconsistent adaptations, paths or ownership")
}
fn array(value: &Value) -> Result<&[Value]> {
    value.as_array().map(Vec::as_slice).ok_or_else(invalid)
}
fn unique(values: &[Value], field: &str) -> Result<()> {
    let mut seen = BTreeSet::new();
    for value in values {
        let value = if field.is_empty() {
            value
        } else {
            &value[field]
        };
        if !seen.insert(value.as_str().ok_or_else(invalid)?) {
            return Err(invalid());
        }
    }
    Ok(())
}

/// Call after the component/setup wire schema. Unknown passport extensions stay intact.
pub fn validate(document: &Value) -> Result<()> {
    markdown::validate(document["description"].as_str().ok_or_else(invalid)?)?;
    if !array(&document["parent_revision_ids"])?.is_empty() {
        return Err(invalid());
    }
    unique(array(&document["tags"])?, "")?;
    if !document["source"].is_null() {
        let path = document["source"]["path"].as_str().ok_or_else(invalid)?;
        if path.is_empty() || path.starts_with('/') || path.split('/').any(|part| part == "..") {
            return Err(invalid());
        }
    }
    if document.get("variant_id").is_some() {
        return Err(invalid());
    }
    if document["kind"] == "component" {
        for forbidden in [
            "harness_id",
            "harness_ids",
            "managed_paths",
            "native_ids",
            "projection_kind",
            "supported_os",
            "portability_claims",
        ] {
            if document.get(forbidden).is_some() {
                return Err(invalid());
            }
        }
        let adaptations = array(&document["adaptations"])?;
        unique(adaptations, "harness_id")?;
        for adaptation in adaptations {
            if adaptation["logical_component_type"] != document["component_type"] {
                return Err(invalid());
            }
            validate_adaptation(adaptation)?;
        }
    }
    Ok(())
}

fn validate_adaptation(adaptation: &Value) -> Result<()> {
    let scopes = array(&adaptation["scope_adaptations"])?;
    unique(scopes, "scope")?;
    for scope in scopes {
        scope_invariants(scope)?;
    }
    // Adaptation IDs are over the complete model, unlike published passport
    // digests. Fill only the defaults owned by this closed adaptation contract.
    let mut payload = adaptation.clone();
    let object = payload.as_object_mut().ok_or_else(invalid)?;
    let held = object.remove("adaptation_id").ok_or_else(invalid)?;
    object.entry("source_artifact").or_insert(Value::Null);
    object.entry("transform").or_insert(Value::Null);
    for scope in object
        .get_mut("scope_adaptations")
        .and_then(Value::as_array_mut)
        .ok_or_else(invalid)?
    {
        let scope = scope.as_object_mut().ok_or_else(invalid)?;
        for field in [
            "supported_harness_versions",
            "supported_os",
            "supported_arch",
            "semantic_losses",
        ] {
            scope.entry(field).or_insert(json!([]));
        }
        scope
            .entry("technical_support_reason")
            .or_insert(Value::Null);
        let permissions = scope
            .entry("permissions")
            .or_insert(json!({}))
            .as_object_mut()
            .ok_or_else(invalid)?;
        for field in ["filesystem", "network", "process"] {
            permissions.entry(field).or_insert(json!([]));
        }
        for member in scope
            .get_mut("members")
            .and_then(Value::as_array_mut)
            .ok_or_else(invalid)?
        {
            let member = member.as_object_mut().ok_or_else(invalid)?;
            for field in ["content_artifact", "parser_id", "ownership_key"] {
                member.entry(field).or_insert(Value::Null);
            }
            member.entry("native_ids").or_insert(json!([]));
        }
    }
    let expected = digest::canonical("ai-stp:component-adaptation:v1", &payload)?.replacen(
        "sha256:",
        "adaptation_",
        1,
    );
    if held != expected {
        return Err(invalid());
    }
    Ok(())
}

pub(crate) fn validate_scope(scope: &Value) -> Result<()> {
    SCOPE.validate(scope)?;
    scope_invariants(scope)
}

fn scope_invariants(scope: &Value) -> Result<()> {
    let members = array(&scope["members"])?;
    let mut paths = BTreeSet::new();
    for member in members {
        let path = member["path"].as_str().ok_or_else(invalid)?;
        if !paths.insert(unicase::UniCase::new(path).to_folded_case()) {
            return Err(invalid());
        }
        if member["ownership"] == "contribution" {
            if member["object_type"] != "file"
                || member["parser_id"].is_null()
                || member["ownership_key"].is_null()
                || member["write_semantics"] != "merge"
                || member["withdrawal_semantics"] != "preserve_unowned"
            {
                return Err(invalid());
            }
        } else if !member["ownership_key"].is_null()
            || member["write_semantics"] != "replace"
            || member["withdrawal_semantics"] != "remove_path"
        {
            return Err(invalid());
        }
    }
    Ok(())
}
