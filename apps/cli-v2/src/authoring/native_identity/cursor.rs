//! Local skill and agent entries in provider-pinned Cursor 2026.10.01-e373342.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;

use super::invalid;
use crate::{authoring::frontmatter, error::Result};

fn local_path(path: &str) -> &str {
    path.strip_prefix(".cursor/")
        .or_else(|| path.strip_prefix(".agents/"))
        .unwrap_or(path)
}

fn scanned_directories(parts: &[&str]) -> bool {
    parts.len() <= 10
        && parts.iter().all(|part| {
            !part.starts_with('.')
                && !matches!(*part, "node_modules" | "__pycache__" | "dist" | "build")
        })
}

pub(super) fn skills<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let files: Vec<_> = files.into_iter().collect();
    if files
        .iter()
        .any(|(path, _)| !local_path(path).starts_with("skills/"))
    {
        return Err(invalid());
    }
    let names = visible(files)?;
    if names.is_empty() {
        return Err(invalid());
    }
    Ok(names)
}

fn cli_surface(metadata: &Value) -> Result<bool> {
    Ok(match &metadata["surfaces"] {
        Value::Array(surfaces) => {
            surfaces.is_empty() || surfaces.iter().any(|surface| surface == "cli")
        }
        Value::String(surfaces) => {
            let mut surfaces = surfaces.split(',').map(str::trim).filter(|s| !s.is_empty());
            surfaces.next().is_none_or(|first| first == "cli")
                || surfaces.any(|surface| surface == "cli")
        }
        Value::Null => true,
        _ => return Err(invalid()),
    })
}

pub(super) fn visible<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let mut captured = BTreeMap::new();
    for (path, bytes) in files {
        if captured.insert(local_path(path), bytes).is_some() {
            return Err(invalid());
        }
    }
    let mut names = BTreeSet::new();
    for (path, bytes) in captured {
        let Some(relative) = path.strip_prefix("skills/") else {
            continue;
        };
        let parts: Vec<_> = relative.split('/').collect();
        if parts.last() != Some(&"SKILL.md") || !scanned_directories(&parts[..parts.len() - 1]) {
            continue;
        }
        let header = frontmatter::required(bytes, frontmatter::Dialect::JsYaml3)?;
        if !cli_surface(&header["metadata"])? {
            continue;
        }
        // Cursor turns these into rules; that requires an explicit instruction adaptation.
        if header["alwaysApply"] == true || header["description"].as_str().is_none_or(str::is_empty)
        {
            return Err(invalid());
        }
        // Local discovery preserves the path; frontmatter name does not rename it.
        let name = parts.iter().rev().nth(1).copied().unwrap_or("skills");
        if !names.insert(name.to_owned()) {
            return Err(
                invalid().with_details([("constraint".into(), "native_id_collision".into())])
            );
        }
    }
    Ok(names.into_iter().collect())
}

fn js_space(character: char) -> bool {
    character == '\u{feff}' || character.is_whitespace() && character != '\u{85}'
}

fn agent_name(bytes: &[u8], fallback: &str) -> Result<String> {
    let text = std::str::from_utf8(bytes).map_err(|_| invalid())?;
    let rest = text
        .strip_prefix("---\n")
        .or_else(|| text.strip_prefix("---\r\n"))
        .ok_or_else(invalid)?;
    let mut offset = 0;
    let mut header = None;
    for line in rest.split_inclusive('\n') {
        if line.trim_end_matches(['\r', '\n']) == "---" {
            if offset == 0
                || rest[offset + line.len()..]
                    .trim_matches(js_space)
                    .is_empty()
            {
                return Err(invalid());
            }
            header = Some(&rest[..offset]);
            break;
        }
        offset += line.len();
        if offset > 64 * 1024 {
            return Err(invalid());
        }
    }
    // The pinned loader splits lines, not YAML: quotes, comments and scalar
    // spellings remain literal. Keys ignore case and the final name wins.
    let mut name = "";
    for line in header.ok_or_else(invalid)?.split('\n') {
        let line = line.trim_matches(js_space);
        if line.starts_with('#') {
            continue;
        }
        if let Some((key, value)) = line.split_once(':')
            && key.trim_matches(js_space).eq_ignore_ascii_case("name")
        {
            name = value.trim_matches(js_space);
        }
    }
    if !name.is_empty() {
        return Ok(name.into());
    }
    let mut name = String::new();
    let mut separator = false;
    for character in fallback.chars() {
        if character == '_' || js_space(character) {
            if !separator {
                name.push('-');
            }
            separator = true;
        } else {
            name.push(character);
            separator = false;
        }
    }
    Ok(name)
}

pub(super) fn agents<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let files: Vec<_> = files.into_iter().collect();
    if files.iter().any(|(path, _)| {
        !path
            .strip_prefix(".cursor/")
            .unwrap_or(path)
            .starts_with("agents/")
    }) {
        return Err(invalid());
    }
    let names = visible_agents(files)?;
    if names.is_empty() {
        return Err(invalid());
    }
    Ok(names)
}

pub(super) fn visible_agents<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let mut names = BTreeSet::new();
    for (path, bytes) in files {
        let Some(relative) = path
            .strip_prefix(".cursor/")
            .unwrap_or(path)
            .strip_prefix("agents/")
        else {
            continue;
        };
        let parts: Vec<_> = relative.split('/').collect();
        if !scanned_directories(&parts[..parts.len() - 1]) {
            continue;
        }
        let file = std::path::Path::new(relative);
        if !file
            .extension()
            .and_then(|s| s.to_str())
            .is_some_and(|ext| {
                ["md", "mdc", "markdown"]
                    .iter()
                    .any(|candidate| ext.eq_ignore_ascii_case(candidate))
            })
        {
            continue;
        }
        let fallback = file
            .file_stem()
            .and_then(|s| s.to_str())
            .ok_or_else(invalid)?;
        let name = agent_name(bytes, fallback)?;
        if name == "claude-code-tutor" {
            continue;
        }
        if !names.insert(name) {
            return Err(
                invalid().with_details([("constraint".into(), "native_id_collision".into())])
            );
        }
    }
    Ok(names.into_iter().collect())
}
