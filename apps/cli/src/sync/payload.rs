//! The shared private-sync payload policy, embedded from its Python package owner.

use std::sync::OnceLock;

use serde::Deserialize;
use serde_json::Value;

use crate::error::{ErrorKind, Failure, Result};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Policy {
    forbidden_payload_kinds: Vec<String>,
    forbidden_key_fragments: Vec<String>,
    required_env_key: String,
    required_env_fields: Vec<String>,
    max_required_env_entries: usize,
    requires_authorization_key: String,
    requires_authorization_values: Vec<String>,
    absolute_path_pattern: String,
}

fn policy() -> Result<&'static (Policy, regex::Regex)> {
    static POLICY: OnceLock<std::result::Result<(Policy, regex::Regex), String>> = OnceLock::new();
    POLICY
        .get_or_init(|| {
            let policy: Policy = serde_json::from_str(include_str!(concat!(
                env!("CARGO_MANIFEST_DIR"),
                "/resources/packages/contracts/src/ai_stp_contracts/sync_payload_policy.json"
            )))
            .map_err(|_| "embedded sync payload policy is invalid".to_owned())?;
            let pattern = regex::Regex::new(&policy.absolute_path_pattern)
                .map_err(|_| "embedded sync path policy is invalid".to_owned())?;
            Ok((policy, pattern))
        })
        .as_ref()
        .map_err(|message| Failure::new(ErrorKind::Internal, message.clone()))
}

fn refused(path: &str) -> Failure {
    Failure::input(
        "the private sync payload contains a forbidden field, path or malformed declaration",
    )
    .with_details([(
        "field".into(),
        if path.is_empty() { "/" } else { path }.into(),
    )])
}

fn visit(
    value: &Value,
    path: &str,
    depth: usize,
    policy: &Policy,
    absolute: &regex::Regex,
) -> Result<()> {
    if depth > 64 {
        return Err(refused(path));
    }
    match value {
        Value::Object(fields) => {
            for (key, value) in fields {
                let at = if path.is_empty() {
                    key.clone()
                } else {
                    format!("{path}.{key}")
                };
                let key = key.to_lowercase();
                if key == "kind"
                    && value.as_str().is_some_and(|v| {
                        policy.forbidden_payload_kinds.iter().any(|kind| kind == v)
                    })
                {
                    return Err(refused(&at));
                }
                if key == policy.required_env_key {
                    let entries = value
                        .as_array()
                        .filter(|v| v.len() <= policy.max_required_env_entries)
                        .ok_or_else(|| refused(&at))?;
                    for (index, entry) in entries.iter().enumerate() {
                        let fields = entry
                            .as_object()
                            .ok_or_else(|| refused(&format!("{at}[{index}]")))?;
                        if fields.len() != policy.required_env_fields.len()
                            || !policy
                                .required_env_fields
                                .iter()
                                .all(|name| fields.get(name).is_some_and(Value::is_string))
                        {
                            return Err(refused(&format!("{at}[{index}]")));
                        }
                    }
                } else if key == policy.requires_authorization_key {
                    if !value.as_str().is_some_and(|v| {
                        policy
                            .requires_authorization_values
                            .iter()
                            .any(|allowed| allowed == v)
                    }) {
                        return Err(refused(&at));
                    }
                } else {
                    if policy
                        .forbidden_key_fragments
                        .iter()
                        .any(|part| key.contains(part))
                    {
                        return Err(refused(&at));
                    }
                    visit(value, &at, depth + 1, policy, absolute)?;
                }
            }
        }
        Value::Array(items) => {
            for (index, item) in items.iter().enumerate() {
                visit(
                    item,
                    &format!("{path}[{index}]"),
                    depth + 1,
                    policy,
                    absolute,
                )?;
            }
        }
        Value::String(value) if absolute.is_match(value) => return Err(refused(path)),
        _ => {}
    }
    Ok(())
}

/// Refusals include field paths, never the values excluded from transport.
pub fn check(value: &Value) -> Result<()> {
    let (policy, absolute) = policy()?;
    visit(value, "", 0, policy, absolute)
}
