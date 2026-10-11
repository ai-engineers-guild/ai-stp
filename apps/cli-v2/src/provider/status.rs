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
    let mut paths = Vec::new();
    for row in rows.as_array().ok_or_else(invalid)? {
        let path = row["path"].as_str().ok_or_else(invalid)?;
        if !path_valid(path) {
            return Err(invalid());
        }
        let keys = row["ownership_keys"].as_array().ok_or_else(invalid)?;
        let keys = keys
            .iter()
            .map(|v| v.as_str().ok_or_else(invalid))
            .collect::<Result<Vec<_>>>()?;
        if keys.iter().any(|key| key.len() > 255) || keys.windows(2).any(|pair| pair[0] >= pair[1])
        {
            return Err(invalid());
        }
        if row["ownership"] == "contribution"
            && !match row["parser_id"].as_str() {
                Some("json/1") => path.ends_with(".json") || path.ends_with(".jsonc"),
                Some("toml/1") => path.ends_with(".toml"),
                _ => false,
            }
        {
            return Err(invalid());
        }
        paths.push(path);
    }
    let state = &document["provider_state"];
    if paths.windows(2).any(|pair| pair[0] >= pair[1])
        || state["present"] != true && !paths.is_empty()
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

fn path_valid(path: &str) -> bool {
    path.len() <= 4096
        && !path
            .chars()
            .any(|ch| ch.is_control() || matches!(ch, '\\' | ':'))
        && path
            .split('/')
            .all(|part| !matches!(part, "" | "." | "..") && part.len() <= 255)
}
