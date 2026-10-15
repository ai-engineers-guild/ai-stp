//! Public recorded ownership; omission never proves an empty managed target.

use std::collections::BTreeSet;

use serde_json::Value;

use crate::{
    error::{Failure, Result},
    wire::Schema,
};

static STATUS: Schema = Schema::new(include_str!(
    "../../../../provider-kit/v3/status-response.schema.json"
));

fn invalid() -> Failure {
    Failure::precondition(
        "the provider status carries inconsistent recorded configuration ownership",
    )
}

/// Validate the shared wire shape and the ownership bindings it cannot express.
pub fn validate(document: &Value) -> Result<()> {
    STATUS.validate(document)?;
    let Some(rows) = document
        .get("configuration_ownership")
        .filter(|v| !v.is_null())
    else {
        return Ok(());
    };
    let paths = ownership_paths(rows)?;
    let state = &document["provider_state"];
    if state["present"] != true && !paths.is_empty()
        || state["present"] == true && state["readable"] != true
    {
        return Err(invalid());
    }
    if let Some(written) = document.get("written_paths") {
        let written = written
            .as_array()
            .ok_or_else(invalid)?
            .iter()
            .map(|value| value.as_str().ok_or_else(invalid))
            .collect::<Result<BTreeSet<_>>>()?;
        if written != paths.into_iter().collect() {
            return Err(invalid());
        }
    }
    Ok(())
}

/// A planned ownership list can be validated without inventing provider state.
pub(crate) fn ownership_paths(rows: &Value) -> Result<Vec<&str>> {
    let rows = rows.as_array().ok_or_else(invalid)?;
    if rows.len() > 8192 {
        return Err(invalid());
    }
    let mut paths = Vec::new();
    for row in rows {
        let fields = row.as_object().ok_or_else(invalid)?;
        if fields.len() != 4
            || ["path", "ownership", "parser_id", "ownership_keys"]
                .iter()
                .any(|key| !fields.contains_key(*key))
        {
            return Err(invalid());
        }
        let path = row["path"].as_str().ok_or_else(invalid)?;
        if !path_valid(path) {
            return Err(invalid());
        }
        let keys = row["ownership_keys"].as_array().ok_or_else(invalid)?;
        let keys = keys
            .iter()
            .map(|v| v.as_str().ok_or_else(invalid))
            .collect::<Result<Vec<_>>>()?;
        if keys.len() > 2000
            || keys
                .iter()
                .any(|key| key.is_empty() || key.len() > 255 || key.chars().any(char::is_control))
            || keys.windows(2).any(|pair| pair[0] >= pair[1])
        {
            return Err(invalid());
        }
        if !match row["ownership"].as_str() {
            Some("whole") => row["parser_id"].is_null() && keys.is_empty(),
            Some("contribution") => {
                !keys.is_empty()
                    && match row["parser_id"].as_str() {
                        Some("json/1") => path.ends_with(".json") || path.ends_with(".jsonc"),
                        Some("toml/1") => path.ends_with(".toml"),
                        _ => false,
                    }
            }
            _ => false,
        } {
            return Err(invalid());
        }
        paths.push(path);
    }
    if paths.windows(2).any(|pair| pair[0] >= pair[1]) {
        return Err(invalid());
    }
    Ok(paths)
}

fn path_valid(path: &str) -> bool {
    path.len() <= 4096
        && !path
            .chars()
            .any(|ch| ch.is_control() || matches!(ch, '\\' | ':'))
        && path
            .split('/')
            .all(|part| !matches!(part, "" | "." | "..") && part.len() <= 255)
}
