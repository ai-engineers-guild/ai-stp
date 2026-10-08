//! Explicit preview configuration; no discovery, writes or credential access.

use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

use serde_json::{Value, json};

use crate::{
    error::{Failure, Result},
    files,
};

pub const HARNESSES: [&str; 7] = [
    "antigravity",
    "claude-code",
    "codex",
    "cursor",
    "grok-build",
    "opencode",
    "pi",
];
pub const CATALOG_URL: &str = "https://ai-stp.aiguild.space";
const MAX_BYTES: u64 = 1024 * 1024;

struct Field {
    name: String,
    default: Value,
    is_path: bool,
}

fn fields() -> Vec<Field> {
    let data = std::env::var_os("XDG_DATA_HOME")
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .or_else(|| files::home().map(|p| p.join(".local/share")))
        .unwrap_or_else(|| PathBuf::from(".local/share"));
    let mut fields: Vec<_> = [
        ("catalog.enabled", json!(true), false),
        ("catalog.url", json!(CATALOG_URL), false),
        ("sync.enabled", json!(false), false),
        (
            "registry.path",
            json!(data.join("ai-stp-v2/registry.sqlite")),
            true,
        ),
        ("search.result_limit", json!(20), false),
        ("projects.discovery_roots", json!([]), true),
        ("telemetry.enabled", json!(false), false),
        (
            "telemetry.url",
            json!("https://telemetry.ai-stp.example"),
            false,
        ),
        ("update.enabled", json!(true), false),
        ("update.channel", json!("stable"), false),
        ("update.check_ttl_hours", json!(24), false),
        ("update.notifications", json!(true), false),
    ]
    .into_iter()
    .map(|(name, default, is_path)| Field {
        name: name.into(),
        default,
        is_path,
    })
    .collect();
    fields.extend(HARNESSES.map(|name| Field {
        name: format!("provider.paths.{name}"),
        default: json!(""),
        is_path: true,
    }));
    fields
}

fn invalid() -> Failure {
    Failure::input("configuration must use declared fields, valid types and schema version 1")
}

fn validate(value: Value, field: &Field) -> Result<Value> {
    let valid_type = match &field.default {
        Value::Bool(_) => value.is_boolean(),
        Value::Number(_) => value.as_i64().is_some(),
        Value::String(_) => value.is_string(),
        Value::Array(_) => value
            .as_array()
            .is_some_and(|items| items.iter().all(Value::is_string)),
        _ => false,
    };
    if !valid_type
        || (field.name == "update.channel" && value != "stable" && value != "prerelease")
        || (field.name == "update.check_ttl_hours" && value.as_i64().is_none_or(|v| v < 1))
    {
        return Err(invalid());
    }
    Ok(value)
}

fn argument(text: &str, field: &Field) -> Result<Value> {
    let value = match &field.default {
        Value::Bool(_) => match text.trim().to_ascii_lowercase().as_str() {
            "true" | "yes" | "1" | "on" => json!(true),
            "false" | "no" | "0" | "off" => json!(false),
            _ => return Err(invalid()),
        },
        Value::Number(_) => json!(text.trim().parse::<i64>().map_err(|_| invalid())?),
        Value::Array(_) => json!(
            text.split(',')
                .map(str::trim)
                .filter(|v| !v.is_empty())
                .collect::<Vec<_>>()
        ),
        _ => json!(text),
    };
    validate(value, field)
}

fn document(path: &Path) -> Result<Value> {
    let bytes = files::read(path, MAX_BYTES)?;
    let text = std::str::from_utf8(&bytes).map_err(|_| invalid())?;
    let options = serde_saphyr::options! {
        budget: serde_saphyr::budget! {
            max_depth: 8,
            max_events: 10_000,
            max_aliases: 100,
            max_documents: 1,
        },
    };
    // Include/property features are absent. Never forward parser snippets:
    // a rejected value may itself contain a credential.
    let value: Value = serde_saphyr::from_str_with_options(text, options).map_err(|_| invalid())?;
    Ok(if value.is_null() { json!({}) } else { value })
}

fn redacted(value: Value) -> Value {
    match value {
        Value::String(text) => json!(files::display(Path::new(&text))),
        Value::Array(items) => Value::Array(items.into_iter().map(redacted).collect()),
        other => other,
    }
}

pub fn show(path: Option<&Path>, overrides: &[String]) -> Result<Value> {
    let fields = fields();
    let value = path.map(document).transpose()?.unwrap_or_else(|| json!({}));
    let object = value.as_object().ok_or_else(invalid)?;
    let mut stored = BTreeMap::new();
    for (section, value) in object {
        if section == "schema_version" {
            if value.as_u64() != Some(1) {
                return Err(invalid());
            }
            continue;
        }
        let mapping = value.as_object().ok_or_else(invalid)?;
        if !fields
            .iter()
            .any(|field| field.name.starts_with(&format!("{section}.")))
        {
            return Err(invalid());
        }
        for (key, value) in mapping {
            let name = format!("{section}.{key}");
            let field = fields.iter().find(|f| f.name == name).ok_or_else(invalid)?;
            stored.insert(name, validate(value.clone(), field)?);
        }
    }
    let mut supplied = BTreeMap::new();
    for assignment in overrides {
        let (name, text) = assignment.split_once('=').ok_or_else(invalid)?;
        let field = fields
            .iter()
            .find(|f| f.name == name.trim())
            .ok_or_else(invalid)?;
        supplied.insert(field.name.clone(), argument(text, field)?);
    }
    let values: Vec<_> = fields.into_iter().map(|field| {
        let (value, source) = if let Some(value) = supplied.remove(&field.name) { (value, "command_argument") }
            else if let Some(value) = stored.remove(&field.name) { (value, "config_file") }
            else { (field.default, "default") };
        json!({"path": field.name, "value": if field.is_path {redacted(value)} else {value}, "source": source})
    }).collect();
    Ok(json!({"schema_version": 1, "config_path": path.map(files::display), "values": values}))
}
