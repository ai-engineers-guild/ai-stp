//! Verified setup definitions and their bounded, independently sealed embedded members.

use std::collections::BTreeMap;

use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use serde::Deserialize;
use serde_json::{Map, Value, json};

use crate::{
    authoring::native_identity,
    canonical, digest,
    error::{Failure, Result},
    passport,
    projection::artifact,
};

pub(super) const FORMAT: &str = "ai-stp-setup-definition/1";
const EMBEDDED_FORMAT: &str = "ai-stp-setup-definition/2";
const MAX_BYTES: usize = 20 * 1024 * 1024;
const MAX_RECORDS: usize = 500;

pub(crate) struct Embedded {
    pub passport: Value,
    pub passport_digest: String,
    pub artifact: Vec<u8>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    #[serde(rename = "ref")]
    reference: Value,
    passport: Value,
    snapshot: Map<String, Value>,
    artifact_b64: String,
    artifact_digest: String,
    artifact_size_bytes: usize,
    passport_digest: String,
    passport_size_bytes: usize,
}

fn invalid() -> Failure {
    Failure::precondition(
        "the setup definition or embedded index disagrees with its exact passports",
    )
}

pub(super) fn document(passport: &Value) -> Value {
    json!({"schema_version":1,"format":FORMAT,"stable_id":passport["stable_id"],
        "version":passport["version"],"harness_id":passport["harness_id"],
        "input_digest":passport["facts"]["snapshot"]["value"],"components":passport["components"]})
}

pub(crate) fn verify(passport: &Value, payload: &[u8]) -> Result<BTreeMap<String, Embedded>> {
    if payload.len() > MAX_BYTES || passport["artifact"]["size_bytes"] != payload.len() {
        return Err(invalid());
    }
    let mut retained = canonical::parse(payload)?;
    if payload != canonical::bytes(&retained)? {
        return Err(invalid());
    }
    let mut expected = document(passport);
    let records = match passport["artifact_format"].as_str() {
        Some(FORMAT) => Vec::new(),
        Some(EMBEDDED_FORMAT) => {
            expected["schema_version"] = 2.into();
            expected["format"] = EMBEDDED_FORMAT.into();
            let Value::Array(records) = retained
                .as_object_mut()
                .ok_or_else(invalid)?
                .remove("embedded")
                .ok_or_else(invalid)?
            else {
                return Err(invalid());
            };
            if records.is_empty() || records.len() > MAX_RECORDS {
                return Err(invalid());
            }
            records
        }
        _ => return Err(invalid()),
    };
    let address = retained["input_digest"].as_str().ok_or_else(invalid)?;
    if address.len() != 71
        || !address.starts_with("sha256:")
        || !address[7..]
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    {
        return Err(invalid());
    }
    // Published definitions can own provenance without repeating it in facts.
    if expected["input_digest"].is_null() {
        expected["input_digest"] = retained["input_digest"].clone();
    }
    // Compare reference meaning without rewriting historical addressed bytes.
    passport::versions::normalize_component_refs(&mut retained["components"])?;
    passport::versions::normalize_component_refs(&mut expected["components"])?;
    if retained != expected {
        return Err(invalid());
    }
    let references = expected["components"].as_array().ok_or_else(invalid)?;
    let mut embedded = BTreeMap::new();
    for value in records {
        let record: Record = serde_json::from_value(value).map_err(|_| invalid())?;
        let mut normalized = json!([record.reference]);
        passport::versions::normalize_component_refs(&mut normalized)?;
        if !references.contains(&normalized[0])
            || ["author_verified", "component_verified", "target_write"]
                .iter()
                .any(|field| record.snapshot.get(*field).is_some_and(|v| v != false))
        {
            return Err(invalid());
        }
        passport::versions::validate_document(&record.passport)?;
        passport::validate(&record.passport)?;
        let bytes = canonical::bytes(&record.passport)?;
        let reference = &normalized[0];
        if record.passport["kind"] != "component"
            || record.passport["stable_id"] != reference["stable_id"]
            || record.passport["version"] != reference["version"]
            || record.passport_digest != reference["passport_digest"]
            || bytes.len() != record.passport_size_bytes
            || digest::bytes("ai-stp:passport:v1", &bytes)? != record.passport_digest
            || ["reactions", "publisher_page", "catalog"]
                .iter()
                .any(|key| record.passport.get(*key).is_some())
        {
            return Err(invalid());
        }
        let bytes = URL_SAFE_NO_PAD
            .decode(&record.artifact_b64)
            .map_err(|_| invalid())?;
        if bytes.len() != record.artifact_size_bytes
            || digest::bytes("ai-stp:artifact:v1", &bytes)? != record.artifact_digest
            || record.passport["artifact"]
                != json!({"digest":record.artifact_digest,"size_bytes":record.artifact_size_bytes})
        {
            return Err(invalid());
        }
        let adaptations = record.passport["adaptations"]
            .as_array()
            .ok_or_else(invalid)?;
        if adaptations.len() != 1 || adaptations[0]["harness_id"] != passport["harness_id"] {
            return Err(invalid());
        }
        let scopes = adaptations[0]["scope_adaptations"]
            .as_array()
            .ok_or_else(invalid)?;
        if scopes.len() != 1 || scopes[0]["projection_artifact"] != record.passport["artifact"] {
            return Err(invalid());
        }
        let files = artifact::verify(&scopes[0], &bytes)?;
        native_identity::verify_files(
            record.passport["component_type"]
                .as_str()
                .ok_or_else(invalid)?,
            passport["harness_id"].as_str().ok_or_else(invalid)?,
            scopes[0]["members"].as_array().ok_or_else(invalid)?,
            &files,
        )?;
        let id = reference["stable_id"]
            .as_str()
            .ok_or_else(invalid)?
            .to_owned();
        if embedded
            .insert(
                id,
                Embedded {
                    passport: record.passport,
                    passport_digest: record.passport_digest,
                    artifact: bytes,
                },
            )
            .is_some()
        {
            return Err(invalid());
        }
    }
    Ok(embedded)
}
