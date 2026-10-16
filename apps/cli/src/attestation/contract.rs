//! Shared author-evidence wire shape, digest and exact publication binding.

use base64::{Engine, engine::general_purpose::STANDARD};
use ed25519_dalek::{Signature, VerifyingKey};
use serde_json::{Value, json};

use crate::{
    account::access::Binding,
    canonical, digest,
    error::{Failure, Result},
    passport,
    wire::Schema,
};

pub(super) const LIMIT: u64 = 256 * 1024;
pub(super) const TARGETS: [&str; 6] = [
    "adaptation_id",
    "projection_digest",
    "scope",
    "provider_profile_digest",
    "os",
    "arch",
];
static SCHEMA: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/publication-author-attestation.schema.json"
)));

pub(super) fn invalid() -> Failure {
    Failure::precondition("author evidence differs from its exact subject, account or signature")
}

/// Pydantic model defaults are part of the existing signed payload. Ed25519
/// signs this domain digest's UTF-8 string, not an Ed25519ph prehash.
pub fn payload(record: &Value) -> Result<Value> {
    if canonical::bytes(record)?.len() as u64 > LIMIT {
        return Err(invalid());
    }
    SCHEMA.validate(record)?;
    let mut payload = record.clone();
    let fields = payload.as_object_mut().ok_or_else(invalid)?;
    fields.remove("signature");
    fields.entry("schema_version").or_insert(1.into());
    fields.entry("tool_versions").or_insert(json!({}));
    for key in TARGETS {
        if fields.get(key).is_none_or(Value::is_null) {
            fields.remove(key);
        }
    }
    if payload["subject"]["stable_id"]
        .as_str()
        .is_some_and(|id| passport::stable_id(id, "component"))
    {
        payload["subject"]
            .as_object_mut()
            .ok_or_else(invalid)?
            .entry("variant_id")
            .or_insert(Value::Null);
    }
    Ok(payload)
}

pub fn hash(record: &Value) -> Result<String> {
    digest::canonical("ai-stp:attestation:v1", &payload(record)?)
}

pub fn verify(record: &Value, public_key: &str) -> Result<String> {
    let hash = hash(record)?;
    let public: [u8; 32] = STANDARD
        .decode(public_key)
        .map_err(|_| invalid())?
        .try_into()
        .map_err(|_| invalid())?;
    let signature = STANDARD
        .decode(record["signature"].as_str().ok_or_else(invalid)?)
        .map_err(|_| invalid())?;
    let signature = Signature::from_slice(&signature).map_err(|_| invalid())?;
    VerifyingKey::from_bytes(&public)
        .map_err(|_| invalid())?
        .verify_strict(hash.as_bytes(), &signature)
        .map_err(|_| invalid())?;
    Ok(hash)
}

pub(crate) fn bind(record: &Value, document: &Value, account: &Binding) -> Result<()> {
    let subject = &record["subject"];
    if record["object_digest"] != document["artifact"]["digest"]
        || subject["stable_id"] != document["stable_id"]
        || subject["version"] != document["version"]
        || subject["passport_digest"] != digest::canonical("ai-stp:passport:v1", document)?
        || !subject["variant_id"].is_null()
        || record["account_id"] != account.account_id
        || record["device_id"] != account.device_id
    {
        return Err(invalid());
    }
    Ok(())
}

/// Generation accepts only coordinates supported by this immutable passport.
/// Version strings describe the author's execution; no harness is invoked.
pub(super) fn coordinates(record: &Value, document: &Value) -> Result<()> {
    let matches = |value: &Value, field: &str, expected: &Value| {
        value[field].is_null() || value[field] == *expected
    };
    let platform = |scope: &Value| {
        [
            ("os", "supported_os", &["linux", "macos", "windows"][..]),
            ("arch", "supported_arch", &["x86_64", "aarch64"][..]),
        ]
        .into_iter()
        .all(|(key, supported, known)| {
            record[key].is_null()
                || record[key].as_str().is_some_and(|v| {
                    known.contains(&v)
                        && scope[supported]
                            .as_array()
                            .is_some_and(|items| items.is_empty() || items.contains(&record[key]))
                })
        })
    };
    let valid = if document["kind"] == "setup" {
        record["harness_id"] == document["harness_id"]
            && platform(document)
            && TARGETS[..4].iter().all(|key| record[*key].is_null())
    } else {
        document["adaptations"].as_array().is_some_and(|items| {
            items.iter().any(|a| {
                record["harness_id"] == a["harness_id"]
                    && matches(record, "adaptation_id", &a["adaptation_id"])
                    && a["scope_adaptations"].as_array().is_some_and(|scopes| {
                        scopes.iter().any(|scope| {
                            matches(record, "scope", &scope["scope"])
                                && matches(
                                    record,
                                    "projection_digest",
                                    &scope["projection_artifact"]["digest"],
                                )
                                && matches(
                                    record,
                                    "provider_profile_digest",
                                    &scope["required_surface"]["profile_digest"],
                                )
                                && platform(scope)
                        })
                    })
            })
        })
    };
    if !valid {
        return Err(invalid());
    }
    Ok(())
}
