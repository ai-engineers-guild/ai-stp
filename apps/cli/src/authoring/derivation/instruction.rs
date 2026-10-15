//! Relocate one standalone instruction file without inventing loader controls.

use serde_json::{Value, json};

use super::{invalid, text};
use crate::{
    artifacts::{self, Member},
    authoring::freezing,
    error::Result,
    harnesses::Shape,
    projection::{self, Scope},
    provider::Info,
};

fn supported(harness: &str) -> Result<()> {
    match harness {
        "claude-code" | "codex" | "opencode" | "pi" => Ok(()),
        _ => Err(invalid()),
    }
}

pub(super) fn project(
    before: &Value,
    scope: &Value,
    source_harness: &str,
    provider: &Info,
    files: &[Member],
) -> Result<(Value, Vec<u8>)> {
    let target = text(provider.document(), "harness_id")?;
    supported(source_harness)?;
    supported(target)?;
    let requested: Scope = serde_json::from_value(scope["scope"].clone()).map_err(|_| invalid())?;
    let route = |harness| -> Result<&projection::Route> {
        projection::route("instruction", harness, requested)?
            .filter(|route| {
                route.target_scope == requested
                    && route.shape == Shape::File
                    && route.declared_key.is_empty()
            })
            .ok_or_else(invalid)
    };
    let from = route(source_harness)?;
    let to = route(target)?;
    let [file] = files else {
        return Err(invalid());
    };
    let declarations = scope["members"].as_array().ok_or_else(invalid)?;
    let [member] = declarations.as_slice() else {
        return Err(invalid());
    };
    if file.path != from.relative
        || member["path"] != from.relative
        || member["ownership"] != "whole"
        || member["object_type"] != "file"
        || scope["projection_kind"] != from.projection_kind
        || scope["provider_component_kind"] != "instruction"
    {
        return Err(invalid());
    }
    let body = std::str::from_utf8(&file.bytes).map_err(|_| invalid())?;
    // Imports and native preprocessing can acquire or lose meaning in another
    // loader. Keep this transform to standalone text, with no syntax guessing.
    if body.trim().is_empty()
        || body.starts_with('\u{feff}')
        || body.lines().next().is_some_and(|line| line.trim() == "---")
        || body
            .chars()
            .any(|c| c.is_control() && !matches!(c, '\n' | '\r' | '\t'))
        || ["@", "${", "{env:", "{file:", "!`", "```!", "$ARGUMENTS"]
            .iter()
            .any(|token| body.contains(token))
        || body
            .as_bytes()
            .windows(2)
            .any(|pair| pair[0] == b'$' && pair[1].is_ascii_digit())
    {
        return Err(invalid());
    }
    let values = json!({"harness_id":target,"scope":requested,
        "projection_kind":to.projection_kind,"managed_paths":[to.relative],
        "declared_key":"","content_format":artifacts::FILE_FORMAT,
        "source_mode":file.mode,"native_ids":[],"permissions":scope["permissions"],
        "supported_os":scope["supported_os"],"supported_arch":scope["supported_arch"],
        "supported_harness_versions":[]});
    freezing::project(
        before,
        &values,
        file.bytes.clone(),
        std::slice::from_ref(provider),
    )
}
