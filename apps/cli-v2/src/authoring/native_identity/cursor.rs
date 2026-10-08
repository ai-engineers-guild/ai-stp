//! Local skill entries in provider-pinned Cursor 2026.10.01-e373342.

use std::{
    collections::{BTreeMap, BTreeSet},
    sync::LazyLock,
};

use serde::Deserialize;
use serde_json::Value;
use serde_saphyr::{
    Spanned,
    granit_parser::{Event, Parser, ScalarStyle},
};

use super::invalid;
use crate::{authoring::frontmatter, error::Result};

#[derive(Deserialize)]
struct Header {
    description: Option<Spanned<Value>>,
    #[serde(default, rename = "alwaysApply")]
    always_apply: Value,
    #[serde(default)]
    metadata: Value,
}

// js-yaml 3 additionally infers timestamps and base-60 numbers from plain scalars.
// The ordinary numeric/boolean cases are already handled by the bounded YAML reader.
static LEGACY_SCALAR: LazyLock<std::result::Result<regex::Regex, regex::Error>> =
    LazyLock::new(|| {
        regex::Regex::new(concat!(
            r"\A(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|",
            r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt]|[ \t]+)[0-9]{1,2}:[0-9]{2}:[0-9]{2}",
            r"(?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?|",
            r"[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+|",
            r"[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.(?:[0-9_]*[0-9])?",
            r")\z"
        ))
    });

fn header(bytes: &[u8]) -> Result<Header> {
    let yaml = frontmatter::header(bytes)?;
    let mut options = frontmatter::options();
    options.strict_booleans = true;
    options.legacy_octal_numbers = true;
    options.reject_unsupported_tags = true;
    let header: Header =
        serde_saphyr::from_str_with_options(&yaml, options).map_err(|_| invalid())?;
    if let Some(description) = &header.description {
        let offset = description
            .defined
            .span()
            .byte_offset()
            .ok_or_else(invalid)?;
        let mut found = false;
        for event in Parser::new_from_str(&yaml) {
            let (event, span) = event.map_err(|_| invalid())?;
            if let Event::Scalar(value, ScalarStyle::Plain, _, tag) = &event {
                // The Rust parser also accepts mixed-case Boolean/null spellings.
                // Require quotes instead of silently changing Cursor's string type.
                if tag.as_ref().is_none_or(|tag| {
                    tag.is_yaml_core_schema_tag("bool") || tag.is_yaml_core_schema_tag("null")
                }) && matches!(
                    value.to_ascii_lowercase().as_str(),
                    "true" | "false" | "null"
                ) && !matches!(
                    value.as_ref(),
                    "true"
                        | "True"
                        | "TRUE"
                        | "false"
                        | "False"
                        | "FALSE"
                        | "null"
                        | "Null"
                        | "NULL"
                ) {
                    return Err(invalid());
                }
            }
            if span
                .byte_range()
                .is_none_or(|range| range.start as u64 != offset)
            {
                continue;
            }
            if let Event::Scalar(value, style, _, tag) = event {
                found = true;
                if tag
                    .as_ref()
                    .is_some_and(|tag| !tag.is_yaml_core_schema_tag("str"))
                    || tag.is_none()
                        && style == ScalarStyle::Plain
                        && LEGACY_SCALAR
                            .as_ref()
                            .map_err(|_| invalid())?
                            .is_match(&value)
                {
                    return Err(invalid());
                }
            }
        }
        if description.value.is_string() && !found {
            return Err(invalid());
        }
    }
    Ok(header)
}

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
        let header = header(bytes)?;
        if !cli_surface(&header.metadata)? {
            continue;
        }
        // Cursor turns these into rules; that requires an explicit instruction adaptation.
        if header.always_apply == true
            || header
                .description
                .as_ref()
                .and_then(|description| description.value.as_str())
                .is_none_or(str::is_empty)
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
