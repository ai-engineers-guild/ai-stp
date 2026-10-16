//! Existing reporter wire schemas and the bounded disclosure boundary.

use serde_json::{Value, json};

use super::invalid;
use crate::{error::Result, passport, wire};

const SOURCE: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/report-case-create-request.schema.json"
));
static REQUEST: wire::Schema = wire::Schema::new(SOURCE);
static CASE: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/report-case-response.schema.json"
)));
static LIST: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/report-case-list-response.schema.json"
)));

pub(super) fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key].as_str().ok_or_else(invalid)
}

pub(super) fn bytes(value: &Value) -> Result<Vec<u8>> {
    // Canonical JSON normalizes Unicode. Transport and retained previews must
    // instead preserve the submitted text; their raw digest binds those bytes.
    serde_json::to_vec(value).map_err(|_| invalid())
}

pub(super) fn prepare(mut body: Value) -> Result<Value> {
    let object = body.as_object_mut().ok_or_else(invalid)?;
    if object.contains_key("schema_version") || object.contains_key("diagnostics_previewed") {
        return Err(invalid());
    }
    let schema: Value = serde_json::from_str(SOURCE).map_err(|_| invalid())?;
    for (key, field) in schema["properties"].as_object().ok_or_else(invalid)? {
        if let Some(default) = field.get("default") {
            object.entry(key.clone()).or_insert_with(|| default.clone());
        }
    }
    object.entry("validation_snapshot_ids").or_insert(json!([]));
    object.insert("diagnostics_previewed".into(), true.into());
    validate(&body)?;
    Ok(body)
}

pub(super) fn validate(body: &Value) -> Result<()> {
    REQUEST.validate(body).map_err(|_| invalid())?;
    if body["schema_version"] != 1 || body["diagnostics_previewed"] != true {
        return Err(invalid());
    }
    let topic = text(body, "topic")?;
    let object = ["object_kind", "stable_id", "version", "content_digest"];
    let any_object = object.iter().any(|key| !body[*key].is_null());
    let extra = !body["author_account_id"].is_null() || !body["recipient_account_id"].is_null();
    let catalog = !body["country"].is_null() || !body["service"].is_null();
    let subject = !text(body, "subject")?.is_empty();
    let component = body["object_kind"].is_null() || body["object_kind"] == "component";
    let valid = match topic {
        "object_report" => {
            object.iter().all(|key| !body[*key].is_null()) && !catalog && !extra && !subject
        }
        "service_request" => {
            !body["service"].is_null()
                && body["country"].is_null()
                && !any_object
                && !extra
                && !subject
        }
        "country_request" => {
            !body["country"].is_null()
                && body["service"].is_null()
                && !any_object
                && !extra
                && !subject
        }
        "component_complaint" => !body["stable_id"].is_null() && component && !catalog && !subject,
        "author_complaint" | "verification_request" => {
            !body["author_account_id"].is_null()
                && !catalog
                && !subject
                && body["recipient_account_id"].is_null()
        }
        "ownership_transfer" => {
            !body["stable_id"].is_null()
                && component
                && !body["recipient_account_id"].is_null()
                && !text(body, "message")?.trim().is_empty()
                && !catalog
                && !subject
        }
        "other" => !text(body, "subject")?.trim().is_empty() && !catalog,
        _ => false,
    };
    if !valid || (topic != "object_report" && body["vulnerability"] == true) {
        return Err(invalid());
    }
    let diagnostics = text(body, "diagnostics")?;
    let path =
        regex::Regex::new(r"(?:^|\s)(?:/[^\s]+|[A-Za-z]:[\\/][^\s]+)").map_err(|_| invalid())?;
    let assignment = regex::Regex::new(
        r"(?i)(?:token|secret|password|passwd|api[_-]?key|authorization)\s*[:=]\s*\S+",
    )
    .map_err(|_| invalid())?;
    if diagnostics.len() > 4000
        || diagnostics.contains('\0')
        || path.is_match(diagnostics)
        || assignment.is_match(diagnostics)
    {
        return Err(invalid());
    }
    for key in [
        "diagnostics",
        "error_code",
        "message",
        "evidence",
        "subject",
    ] {
        safe(text(body, key)?)?;
    }
    for key in ["service", "country"] {
        if let Some(fields) = body[key].as_object() {
            for value in fields.values().filter_map(Value::as_str) {
                safe(value)?;
            }
        }
    }
    Ok(())
}

fn safe(value: &str) -> Result<()> {
    let lower = value.to_lowercase();
    if [
        "password",
        "secret",
        "token",
        "private_key",
        ".env",
        "home/",
        "c:\\users\\",
    ]
    .iter()
    .any(|marker| lower.contains(marker))
        || value.contains('\0')
    {
        return Err(invalid());
    }
    Ok(())
}

pub(super) fn case(value: &Value) -> Result<Value> {
    CASE.validate(value).map_err(|_| invalid())?;
    if value["schema_version"] != 1
        || !passport::stable_id(text(value, "case_id")?, "report")
        || !passport::timestamp(text(value, "created_at")?)
    {
        return Err(invalid());
    }
    // Forward-compatible response fields may contain staff-only data. Never
    // pass them through to machine output or persist them in reporter history.
    Ok(Value::Object(
        [
            "schema_version",
            "case_id",
            "topic",
            "object_kind",
            "stable_id",
            "version",
            "state",
            "vulnerability",
            "locale",
            "created_at",
        ]
        .into_iter()
        .map(|key| (key.into(), value[key].clone()))
        .collect(),
    ))
}

pub(super) fn bound(value: &Value, body: &Value) -> Result<Value> {
    let value = case(value)?;
    for key in ["topic", "vulnerability", "locale"] {
        if value[key] != body[key] {
            return Err(invalid());
        }
    }
    for key in ["object_kind", "stable_id", "version"] {
        if value[key]
            != body
                .get(key)
                .filter(|v| !v.is_null())
                .cloned()
                .unwrap_or(json!(""))
        {
            return Err(invalid());
        }
    }
    Ok(value)
}

pub(in crate::account) fn cursor(value: &str) -> bool {
    (1..=512).contains(&value.len())
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'))
}

pub(super) fn page(value: &Value, previous: Option<&str>) -> Result<Value> {
    LIST.validate(value).map_err(|_| invalid())?;
    let items = value["items"].as_array().ok_or_else(invalid)?;
    let next = &value["page"]["next_cursor"];
    if value["schema_version"] != 1
        || items.len() > 100
        || value["page"]["page_size"]
            .as_u64()
            .is_none_or(|size| items.len() as u64 > size)
        || (!next.is_null()
            && next
                .as_str()
                .is_none_or(|v| !cursor(v) || Some(v) == previous))
    {
        return Err(invalid());
    }
    let items = items.iter().map(case).collect::<Result<Vec<_>>>()?;
    let mut ids = std::collections::BTreeSet::new();
    if items
        .iter()
        .any(|v| !ids.insert(v["case_id"].clone().to_string()))
    {
        return Err(invalid());
    }
    Ok(json!({"schema_version":1,"items":items,"page":{
        "schema_version":1,"next_cursor":next,"page_size":value["page"]["page_size"]}}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn existing_topics_and_disclosure_bounds_remain_closed()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let component = format!("component_{}", ulid::Ulid::generate());
        let account = format!("account_{}", ulid::Ulid::generate());
        let mut examples = vec![
            json!({"topic":"object_report","object_kind":"component","stable_id":component,"version":"1.0","content_digest":format!("sha256:{}","a".repeat(64))}),
            json!({"topic":"service_request","service":{"name":"Example","primary_url":"https://example.com","source_url":"https://example.com","description_ru":"Example","description_en":"Example","country_codes":[]}}),
            json!({"topic":"country_request","country":{"code":"KZ","name_ru":"Example","name_en":"Example"}}),
            json!({"topic":"component_complaint","stable_id":component}),
            json!({"topic":"author_complaint","author_account_id":account}),
            json!({"topic":"ownership_transfer","stable_id":component,"recipient_account_id":account,"message":"Please review the owner."}),
            json!({"topic":"verification_request","author_account_id":account}),
            json!({"topic":"other","subject":"A question"}),
        ];
        for input in &mut examples {
            input["idempotency_key"] = "report-contract-01".into();
            let prepared = prepare(input.clone())?;
            assert_eq!(prepared["topic"], input["topic"]);
            let mut bad = input.clone();
            bad["unexpected"] = true.into();
            assert!(prepare(bad).is_err());
        }
        let input = examples.pop().ok_or("absent fixture")?;
        for diagnostics in [
            "/etc/example",
            r"C:\example",
            "API_KEY=example",
            "passWd: example",
            "a\0b",
        ] {
            let mut bad = input.clone();
            bad["diagnostics"] = diagnostics.into();
            assert!(prepare(bad).is_err());
        }
        let mut bad = input.clone();
        bad["diagnostics"] = "é".repeat(2001).into();
        assert!(prepare(bad).is_err());
        let mut bad = input.clone();
        bad["vulnerability"] = true.into();
        assert!(prepare(bad).is_err());
        let mut bad = input.clone();
        bad["diagnostics_previewed"] = true.into();
        assert!(prepare(bad).is_err());
        let mut bad = input.clone();
        bad["subject"] = "  ".into();
        assert!(prepare(bad).is_err());
        let mut unicode = input;
        unicode["message"] = "Cafe\u{301}".into();
        assert_eq!(prepare(unicode)?["message"], "Cafe\u{301}");
        Ok(())
    }
}
