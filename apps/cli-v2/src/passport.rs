//! Passport shape, identity and content addressing at the native boundary.

pub mod developer;
pub(crate) mod markdown;
pub mod versions;

use serde_json::{Value, json};

use crate::{
    digest,
    error::{Failure, Result},
    wire::Schema,
};

static ENVELOPE: Schema = Schema::new(include_str!(
    "../../../schemas/v1/passport-envelope.schema.json"
));

pub fn stable_id(value: &str, kind: &str) -> bool {
    value
        .strip_prefix(kind)
        .and_then(|s| s.strip_prefix('_'))
        .is_some_and(|suffix| {
            suffix.len() == 26
                && suffix
                    .bytes()
                    .all(|c| b"0123456789ABCDEFGHJKMNPQRSTVWXYZ".contains(&c))
                && suffix.parse::<ulid::Ulid>().is_ok()
        })
}

pub fn version_number(text: &str) -> bool {
    text.split_once('.').is_some_and(|(major, minor)| {
        [major, minor].iter().all(|part| {
            !part.is_empty()
                && part.bytes().all(|b| b.is_ascii_digit())
                && (part.len() == 1 || !part.starts_with('0'))
        })
    })
}

pub fn timestamp(value: &str) -> bool {
    value.len() == 24
        && value.as_bytes()[19] == b'.'
        && value.ends_with('Z')
        && value.parse::<jiff::Timestamp>().is_ok()
}

pub fn revision_id(document: &Value) -> Result<String> {
    let mut payload = document.clone();
    payload
        .as_object_mut()
        .ok_or_else(invalid)?
        .remove("revision_id");
    Ok(digest::canonical("ai-stp:revision:v1", &payload)?.replacen("sha256:", "revision_", 1))
}

fn invalid() -> Failure {
    Failure::precondition("passport shape, identity or content digest is invalid")
}

pub fn validate(document: &Value) -> Result<()> {
    ENVELOPE.validate(document)?;
    validate_identity(document)?;
    if document["revision_id"] != revision_id(document)? {
        return Err(invalid());
    }
    Ok(())
}

/// Identity and facts after the caller validated the appropriate wire schema.
/// Historical public snapshots are addressed by their published passport digest.
pub fn validate_identity(document: &Value) -> Result<()> {
    let kind = document["kind"].as_str().ok_or_else(invalid)?;
    if !stable_id(document["stable_id"].as_str().ok_or_else(invalid)?, kind)
        || !timestamp(document["created_at"].as_str().ok_or_else(invalid)?)
    {
        return Err(invalid());
    }
    // Cross-field rules are domain behavior, beyond generated JSON Schema.
    for fact in document["facts"].as_object().ok_or_else(invalid)?.values() {
        if (fact["confirmation"] == "none" && !fact["confirmed_at"].is_null())
            || (!fact["confidence"].is_null() && fact["origin"] != "observed")
        {
            return Err(invalid());
        }
        for field in ["observed_at", "confirmed_at"] {
            if !fact[field].is_null() && !fact[field].as_str().is_some_and(timestamp) {
                return Err(invalid());
            }
        }
    }
    Ok(())
}

pub fn view(document: &Value) -> Value {
    json!({"schema_version": 1, "kind": document["kind"], "stable_id": document["stable_id"],
        "revision_id": document["revision_id"], "parent_revision_ids": document["parent_revision_ids"],
        "created_at": document["created_at"], "owner_id": document["owner_id"], "facts": document["facts"]})
}
