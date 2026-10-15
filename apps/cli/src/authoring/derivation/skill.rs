//! Byte-preserving common skills; native execution extensions are not portable.

use serde_json::{Value, json};

use super::{invalid, text};
use crate::{
    artifacts::{self, Member},
    authoring::{
        freezing,
        frontmatter::{self, Dialect},
    },
    error::Result,
    harnesses::Shape,
    projection::{self, Scope},
    provider::Info,
};

fn supported(harness: &str) -> Result<()> {
    match harness {
        "claude-code" | "codex" | "opencode" => Ok(()),
        _ => Err(invalid()),
    }
}

fn header(bytes: &[u8]) -> Result<String> {
    let header = frontmatter::required(bytes, Dialect::Core)?;
    for dialect in [Dialect::CoreMerged, Dialect::JsYaml3] {
        if frontmatter::required(bytes, dialect)? != header {
            return Err(invalid());
        }
    }
    let object = header.as_object().ok_or_else(invalid)?;
    if object.keys().any(|key| {
        ![
            "name",
            "description",
            "license",
            "compatibility",
            "metadata",
        ]
        .contains(&key.as_str())
    }) {
        return Err(invalid());
    }
    let name = text(&header, "name")?;
    if name.len() > 64
        || name.starts_with('-')
        || name.ends_with('-')
        || name.contains("--")
        || !name
            .bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-')
    {
        return Err(invalid());
    }
    let description = text(&header, "description")?;
    if description.trim().is_empty() || description.chars().count() > 1024 {
        return Err(invalid());
    }
    for key in ["license", "compatibility"] {
        if let Some(value) = object.get(key) {
            let value = value.as_str().ok_or_else(invalid)?;
            if value.trim().is_empty() || key == "compatibility" && value.chars().count() > 500 {
                return Err(invalid());
            }
        }
    }
    if let Some(metadata) = object.get("metadata")
        && metadata
            .as_object()
            .is_none_or(|fields| fields.values().any(|value| !value.is_string()))
    {
        return Err(invalid());
    }
    let contents = std::str::from_utf8(bytes).map_err(|_| invalid())?;
    // A literal token can acquire or lose preprocessing when moved in either
    // direction. Escaping rules differ too, so refuse rather than rewrite it.
    if ["!`", "```!", "$ARGUMENTS", "${"]
        .iter()
        .any(|token| contents.contains(token))
        || contents
            .as_bytes()
            .windows(2)
            .any(|pair| pair[0] == b'$' && pair[1].is_ascii_digit())
    {
        return Err(invalid());
    }
    Ok(name.into())
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
        projection::route("skill", harness, requested)?
            .filter(|r| {
                r.target_scope == requested
                    && r.shape == Shape::Directory
                    && r.declared_key.is_empty()
            })
            .ok_or_else(invalid)
    };
    let from = route(source_harness)?;
    let to = route(target)?;
    let primary = files
        .iter()
        .find(|file| file.path.ends_with("/SKILL.md"))
        .ok_or_else(invalid)?;
    let name = header(&primary.bytes)?;
    let prefix = format!("{}/{name}/", from.relative);
    if primary.path != format!("{prefix}SKILL.md")
        || scope["projection_kind"] != from.projection_kind
        || scope["provider_component_kind"] != "skill"
    {
        return Err(invalid());
    }
    let declarations = scope["members"].as_array().ok_or_else(invalid)?;
    if declarations.len() != files.len()
        || declarations.iter().any(|member| {
            member["object_type"] != "file"
                || member["ownership"] != "whole"
                || member["native_ids"] != json!([name])
        })
    {
        return Err(invalid());
    }
    let mut relocated = Vec::with_capacity(files.len());
    for file in files {
        let path = file.path.strip_prefix(&prefix).ok_or_else(invalid)?;
        // Hidden manifests/ignore files and native sidecars can change loaders,
        // invocation policy or permissions. Nested skills add other invocations.
        if path.split('/').any(|part| {
            part.starts_with('.') || part.eq_ignore_ascii_case("SKILL.md") && path != "SKILL.md"
        }) || path.eq_ignore_ascii_case("agents/openai.yaml")
        {
            return Err(invalid());
        }
        relocated.push(Member {
            path: path.into(),
            bytes: file.bytes.clone(),
            mode: file.mode,
        });
    }
    let values = json!({"harness_id":target,"scope":requested,"projection_kind":to.projection_kind,
        "managed_paths":[format!("{}/{name}",to.relative)],"declared_key":"",
        "content_format":artifacts::TREE_FORMAT,"native_ids":[name],
        "permissions":scope["permissions"],"supported_os":scope["supported_os"],"supported_arch":scope["supported_arch"],"supported_harness_versions":[]});
    freezing::project(
        before,
        &values,
        artifacts::encode_tree(&relocated)?,
        std::slice::from_ref(provider),
    )
}
