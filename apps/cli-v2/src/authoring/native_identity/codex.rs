//! Local skill identities observed in provider-pinned Codex 0.160.0.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;

use super::invalid;
use crate::{
    authoring::frontmatter,
    error::{Failure, Result},
};

#[derive(Deserialize)]
struct Header {
    name: Option<String>,
    description: Option<String>,
    #[serde(default, rename = "metadata")]
    _metadata: Metadata,
}

#[derive(Default, Deserialize)]
struct Metadata {
    #[serde(rename = "short-description")]
    _short_description: Option<String>,
}

fn single_line(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

pub(super) const PLUGIN_DIRECTORIES: [&str; 3] =
    [".codex-plugin", ".claude-plugin", ".cursor-plugin"];

fn local_path(path: &str) -> &str {
    path.strip_prefix(".codex/")
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
    for (path, bytes) in &captured {
        let Some(relative) = path.strip_prefix("skills/") else {
            continue;
        };
        let parts: Vec<_> = relative.split('/').collect();
        // The upstream recursive scanner reaches six directories below its root.
        if parts.last() != Some(&"SKILL.md")
            || parts.len() > 7
            || parts.iter().any(|part| part.starts_with('.'))
        {
            continue;
        }
        let mut ancestor = path.rsplit_once('/').map_or("", |(parent, _)| parent);
        loop {
            let prefix = if ancestor.is_empty() {
                String::new()
            } else {
                format!("{ancestor}/")
            };
            for directory in PLUGIN_DIRECTORIES {
                if captured.contains_key(format!("{prefix}{directory}/plugin.json").as_str()) {
                    return Err(Failure::precondition(
                        "namespaced skills require a plugin adaptation",
                    ));
                }
            }
            if ancestor.is_empty() {
                break;
            }
            ancestor = ancestor.rsplit_once('/').map_or("", |(parent, _)| parent);
        }
        let header: Header = frontmatter::decode(bytes, frontmatter::Dialect::Core)?;
        if header
            .description
            .as_deref()
            .is_none_or(|value| single_line(value).is_empty())
        {
            return Err(invalid());
        }
        let folder = parts.iter().rev().nth(1).copied().unwrap_or("skills");
        let name = header
            .name
            .as_deref()
            .map(single_line)
            .filter(|name| !name.is_empty())
            .unwrap_or_else(|| single_line(folder));
        if name.is_empty() || name.chars().count() > 64 {
            return Err(invalid());
        }
        if !names.insert(name) {
            return Err(
                invalid().with_details([("constraint".into(), "native_id_collision".into())])
            );
        }
    }
    Ok(names.into_iter().collect())
}
