//! Local skill entries in provider-pinned Cursor 2026.10.01-e373342.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;

use super::invalid;
use crate::{authoring::frontmatter, error::Result};

fn local_path(path: &str) -> &str {
    path.strip_prefix(".cursor/")
        .or_else(|| path.strip_prefix(".agents/"))
        .unwrap_or(path)
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
        if parts.last() != Some(&"SKILL.md")
            || parts.len() > 11
            || parts[..parts.len() - 1].iter().any(|part| {
                part.starts_with('.')
                    || matches!(*part, "node_modules" | "__pycache__" | "dist" | "build")
            })
        {
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
