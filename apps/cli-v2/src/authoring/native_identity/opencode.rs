//! Markdown entry identities observed in provider-pinned OpenCode 1.18.34.

use std::collections::BTreeSet;

use super::invalid;
use crate::{authoring::frontmatter, error::Result};

fn local_path<'a>(kind: &str, path: &'a str) -> Result<&'a str> {
    let path = path
        .strip_prefix(".opencode/")
        .or_else(|| path.strip_prefix(".agents/"))
        .unwrap_or(path);
    let roots = match kind {
        "skill" => ["skills/", "skill/"],
        "command" => ["commands/", "command/"],
        "agent" => ["agents/", "agent/"],
        _ => return Err(invalid()),
    };
    roots
        .into_iter()
        .find_map(|root| path.strip_prefix(root))
        .ok_or_else(invalid)
}

/// Skills use declared names; commands/agents may override their relative stem.
/// Upstream config/entry-name.ts preserves nested slashes, and skill/index.ts
/// accepts an optional description rather than requiring name = directory.
pub(super) fn entries<'a>(
    kind: &str,
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let mut names = BTreeSet::new();
    for (path, bytes) in files {
        let path = local_path(kind, path)?;
        let (header, fallback) = if kind == "skill" {
            if path.rsplit('/').next() != Some("SKILL.md") {
                continue;
            }
            (
                frontmatter::required(bytes, frontmatter::Dialect::JsYaml3)?,
                None,
            )
        } else {
            let Some(stem) = path.strip_suffix(".md") else {
                continue;
            };
            (
                frontmatter::optional(bytes, frontmatter::Dialect::JsYaml3)?,
                Some(stem),
            )
        };
        if header
            .get("description")
            .is_some_and(|value| !value.is_string())
        {
            return Err(invalid());
        }
        let name = match header.get("name") {
            Some(value) => value.as_str().ok_or_else(invalid)?,
            None => fallback.ok_or_else(invalid)?,
        };
        if !names.insert(name.to_owned()) {
            return Err(
                invalid().with_details([("constraint".into(), "native_id_collision".into())])
            );
        }
    }
    if names.is_empty() {
        return Err(invalid());
    }
    Ok(names.into_iter().collect())
}
