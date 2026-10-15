//! Local Markdown identities observed in provider-pinned Grok Build 1.0.49.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;

use super::invalid;
use crate::{authoring::frontmatter, error::Result};

fn local_path(path: &str) -> &str {
    path.strip_prefix(".grok/")
        .or_else(|| path.strip_prefix(".agents/"))
        .unwrap_or(path)
}

fn normalize(name: &str) -> Option<String> {
    let mut result = String::with_capacity(name.len().min(65));
    for character in name.trim().chars() {
        let character = character.to_ascii_lowercase();
        if character.is_ascii_lowercase() || character.is_ascii_digit() {
            result.push(character);
        } else if !result.is_empty() && !result.ends_with('-') {
            result.push('-');
        }
        if result.len() > 65 {
            return None;
        }
    }
    let result = result.trim_end_matches('-');
    (!result.is_empty() && result.len() <= 64).then(|| result.to_owned())
}

fn name(bytes: &[u8], fallback: &str) -> Result<String> {
    let text = std::str::from_utf8(bytes).map_err(|_| invalid())?;
    let content = text.trim_start();
    let header = if content.starts_with("---") {
        // The native 4 KiB reader counts opening/closing lines and leading blanks.
        let mut length = text.len() - content.len();
        let mut closed = false;
        for (index, line) in content.split_inclusive('\n').enumerate() {
            length += line.len();
            if length > 4096 {
                return Err(invalid());
            }
            if index > 0 && line.trim() == "---" {
                closed = true;
                break;
            }
        }
        if !closed {
            return Err(invalid());
        }
        let header: Option<Value> =
            frontmatter::decode(content.as_bytes(), frontmatter::Dialect::Core)?;
        if header.as_ref().is_some_and(|value| !value.is_object()) {
            return Err(invalid());
        }
        header.unwrap_or(Value::Null)
    } else {
        Value::Null
    };
    let declared = match &header["name"] {
        Value::String(value) => normalize(value),
        Value::Bool(value) => normalize(&value.to_string()),
        Value::Number(value) if value.is_i64() || value.is_u64() => normalize(&value.to_string()),
        // Float renderings differ across YAML implementations; require a quoted name.
        Value::Number(_) => return Err(invalid()),
        _ => None,
    };
    declared.or_else(|| normalize(fallback)).ok_or_else(invalid)
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
    let names = visible("skill", files)?;
    if names.is_empty() {
        return Err(invalid());
    }
    Ok(names)
}

pub(super) fn visible<'a>(
    kind: &str,
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let root = match kind {
        "skill" => "skills/",
        "command" => "commands/",
        _ => return Err(invalid()),
    };
    let mut captured = BTreeMap::new();
    for (path, bytes) in files {
        if let Some(path) = local_path(path).strip_prefix(root)
            && captured.insert(path, bytes).is_some()
        {
            return Err(invalid());
        }
    }
    let mut names = BTreeSet::new();
    for (path, bytes) in captured {
        let fallback = if kind == "skill" {
            let parts: Vec<_> = path.split('/').collect();
            // The local scanner checks children through six directories, including hidden ones.
            if parts.last() != Some(&"SKILL.md") || !(2..=7).contains(&parts.len()) {
                continue;
            }
            parts[parts.len() - 2]
        } else if !path.contains('/')
            && let Some(stem) = path.strip_suffix(".md")
        {
            stem
        } else {
            continue;
        };
        if !names.insert(name(bytes, fallback)?) {
            return Err(
                invalid().with_details([("constraint".into(), "native_id_collision".into())])
            );
        }
    }
    Ok(names.into_iter().collect())
}
