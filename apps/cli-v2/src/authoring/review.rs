//! Read-only structural readiness and optional hints over the exact current head.

use std::collections::BTreeSet;

use rusqlite::Transaction;
use serde_json::{Value, json};

use super::{freezing, passports::Patch};
use crate::{
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    provider::Info,
    store::Store,
    wire::Schema,
};

static VALIDATION: Schema = Schema::new(include_str!(
    "../../../../schemas/v1/cli-component-passport-validation.schema.json"
));
static QUALITY: Schema = Schema::new(include_str!(
    "../../../../schemas/v1/cli-component-quality-report.schema.json"
));

struct Review {
    document: Value,
    values: Value,
    validation: Value,
}

fn nonempty(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::String(text) => !text.trim().is_empty(),
        Value::Array(items) => !items.is_empty(),
        Value::Object(items) => !items.is_empty(),
        _ => true,
    }
}

fn values(document: &Value) -> Value {
    if document.get("adaptations").is_some() {
        return document.clone();
    }
    let mut values: Value = document["facts"]
        .as_object()
        .into_iter()
        .flatten()
        .map(|(key, value)| (key.clone(), value["value"].clone()))
        .collect::<serde_json::Map<_, _>>()
        .into();
    if values["source"].is_null()
        && ["source_repository", "source_revision", "source_subpath"]
            .iter()
            .all(|key| nonempty(&values[key]))
    {
        values["source"] = json!({"repository":values["source_repository"],"commit":values["source_revision"],"path":values["source_subpath"]});
    }
    values
}

fn inspect(t: &Transaction<'_>, id: &str, providers: &[Info]) -> Result<Review> {
    let harnesses: BTreeSet<_> = providers
        .iter()
        .map(|info| info.document()["harness_id"].as_str())
        .collect();
    if providers.len() > 7 || harnesses.len() != providers.len() {
        return Err(Failure::input(
            "review requires at most one provider declaration per harness",
        ));
    }
    let objects = Objects { connection: t };
    let document = objects.head("component", id)?;
    let values = values(&document);
    let mut missing = BTreeSet::new();
    let mut invalid = BTreeSet::new();
    for key in ["name", "description", "tags", "license", "source"] {
        if !nonempty(&values[key]) {
            missing.insert(key);
        }
    }
    if nonempty(&values["license"]) && !nonempty(&values["license"]["spdx_id"]) {
        missing.insert("license.spdx_id");
    }
    if nonempty(&values["source"]) && Patch::try_from(json!({"source":values["source"]})).is_err() {
        invalid.insert("source");
    }
    if document.get("adaptations").is_none() {
        for key in [
            "harness_id",
            "component_type",
            "projection_kind",
            "content_digest",
            "byte_length",
            "scope",
            "source_path",
        ] {
            if values[key].is_null() {
                missing.insert(key);
            }
        }
    }
    let mut checks = Vec::new();
    if let Err(error) = objects.require_active(id) {
        invalid.insert("lifecycle_state");
        checks.push(
            json!({"code":error.kind.code(),"summary":error.message,"details":error.details}),
        );
    }
    // This checks the same retained CAS, native identities and projection
    // constraints as release. None prevents storing any generated archive.
    // The temporary version is a shape check, not a reserved immutable number.
    if let Err(error) = freezing::compile(t, document.clone(), "1.0", providers, None) {
        if matches!(error.kind, ErrorKind::Internal | ErrorKind::Unavailable) {
            return Err(error);
        }
        invalid.insert("native_release");
        checks.push(
            json!({"code":error.kind.code(),"summary":error.message,"details":error.details}),
        );
    }
    let validation = json!({"schema_version":1,"stable_id":document["stable_id"],"revision_id":document["revision_id"],
        "for_publication":true,"ready":missing.is_empty() && invalid.is_empty(),
        "missing_fields":missing,"invalid_fields":invalid,"blocking_checks":checks});
    VALIDATION.validate(&validation)?;
    Ok(Review {
        document,
        values,
        validation,
    })
}

pub fn validate(store: &mut Store, id: &str, providers: &[Info]) -> Result<Value> {
    store.transaction(|t| Ok(inspect(t, id, providers)?.validation))
}

fn hint(code: &str, passed: bool, fields: &[&str], message: &str) -> Value {
    json!({"schema_version":1,"code":code,"status":if passed {"passed"} else {"hint"},
        "fields":fields,"message":if passed {"No hint."} else {message}})
}

fn dimension(name: &str, checks: Vec<Value>) -> Value {
    json!({"schema_version":1,"dimension":name,"status":if checks.iter().all(|c| c["status"] == "passed") {"passed"} else {"hint"},"checks":checks})
}

fn surfaces(kind: &str) -> Result<&'static [&'static str]> {
    match kind {
        "instruction" | "skill" => Ok(&["managed_paths", "entry_points"]),
        "mcp" => Ok(&["native_ids", "entry_points"]),
        "setting" => Ok(&["native_ids", "managed_paths"]),
        "hook" | "command" | "agent" | "plugin" | "cli" => {
            Ok(&["native_ids", "managed_paths", "entry_points"])
        }
        _ => Err(Failure::precondition(
            "quality guidance requires a declared component type",
        )),
    }
}

pub fn quality(store: &mut Store, id: &str, providers: &[Info]) -> Result<Value> {
    store.transaction(|t| {
        let Review {document,values,validation} = inspect(t,id,providers)?;
        let kind = values["component_type"].as_str().unwrap_or("");
        let surfaces = surfaces(kind)?;
        let (harness, surface) = if document.get("adaptations").is_some() {
            let adaptations = document["adaptations"].as_array().map(Vec::as_slice).unwrap_or_default();
            let harness = !adaptations.is_empty() && adaptations.iter().all(|a| a["harness_id"].as_str().is_some_and(|h| !h.is_empty() && h != "undefined"));
            let surface = harness && adaptations.iter().all(|a| {
                a["scope_adaptations"].as_array().is_some_and(|scopes| !scopes.is_empty() && scopes.iter().all(|scope| {
                    surfaces.iter().any(|field| nonempty(&scope[field])) || scope["members"].as_array().is_some_and(|members| !members.is_empty() && members.iter().all(|m| surfaces.iter().any(|field| nonempty(&m[field]))))
                }))
            });
            (harness,surface)
        } else {
            (values["harness_id"].as_str().is_some_and(|h| !h.is_empty() && h != "undefined"), surfaces.iter().any(|field| nonempty(&values[field])))
        };
        let fields: Vec<_> = validation["missing_fields"].as_array().into_iter().flatten()
            .chain(validation["invalid_fields"].as_array().into_iter().flatten()).filter_map(Value::as_str).collect();
        let source = nonempty(&values["source"]) && Patch::try_from(json!({"source":values["source"]})).is_ok();
        let dimensions = vec![
            dimension("safety",vec![
                hint("declared_permissions", values["permissions"].is_object(), &["permissions"], "Declare the bounded filesystem, network, and process permissions."),
                hint("declared_access_requirements", values["requires_credentials"].is_boolean() && values["requires_authorization"].as_str().is_some_and(|s| !s.trim().is_empty()), &["requires_credentials","requires_authorization"], "Declare credential and external authorization requirements explicitly."),
            ]),
            dimension("clarity",vec![
                hint("named_component",nonempty(&values["name"]),&["name"],"Add a name."),
                hint("described_component",nonempty(&values["description"]),&["description"],"Explain the component's purpose and operating boundary."),
            ]),
            dimension("reusability",vec![
                hint("exact_source",source,&["source"],"Bind reusable content to an exact repository commit and subpath."),
                hint("redistributable_license",values["license"]["redistribution_allowed"] == true,&["license"],"Declare a license that permits redistribution when reuse is intended."),
                hint("harness_scope",harness,&["adaptations"],"Name each harness whose native contract this component targets."),
            ]),
            dimension("completeness",vec![hint("publication_structure",validation["ready"] == true,&fields,"Resolve every structural publication-readiness field.")]),
            dimension("actionability",vec![hint("declared_action_surface",surface,surfaces,"Declare a type-appropriate entry point or native surface in every adaptation scope.")]),
        ];
        let result = json!({"schema_version":1,"stable_id":document["stable_id"],"revision_id":document["revision_id"],
            "component_type":kind,"profile_version":"mechanical/1","informational_only":true,
            "affects_component_verified":false,"affects_trust_lane":false,"affects_publication_readiness":false,"dimensions":dimensions});
        QUALITY.validate(&result)?;
        Ok(result)
    })
}
