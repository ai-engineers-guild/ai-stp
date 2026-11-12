//! Skill scanning and path IDs observed in OpenCode 2.2.7.

use std::collections::{BTreeMap, BTreeSet};

use super::{invalid, valid};
use crate::{authoring::frontmatter, error::Result};

pub(super) fn visible<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    Ok(skills(
        files
            .into_iter()
            .filter(|(path, _)| super::opencode::local_path("skill", path).is_ok()),
    )?
    .into_values()
    .flatten()
    .collect())
}

pub(super) fn skills<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<BTreeMap<String, Vec<String>>> {
    let mut local = BTreeMap::new();
    let mut result = BTreeMap::new();
    for (path, bytes) in files {
        let relative = super::opencode::local_path("skill", path)?;
        if local.insert(relative, (path, bytes)).is_some() {
            return Err(invalid());
        }
        result.insert(path.to_owned(), Vec::new());
    }
    let mut observed = BTreeSet::new();
    for (relative, (path, bytes)) in &local {
        let parts: Vec<_> = relative.split('/').collect();
        let (leaf, parents) = parts.split_last().ok_or_else(invalid)?;
        if leaf.starts_with('.')
            || parents.len() > 6
            || parents.iter().any(|part| {
                part.starts_with('.')
                    || matches!(
                        *part,
                        "node_modules" | ".git" | ".venv" | "venv" | "__pycache__"
                    )
            })
            || (0..parents.len()).any(|depth| {
                let mut ancestor = parents[..depth].to_vec();
                ancestor.push("SKILL.md");
                local.contains_key(ancestor.join("/").as_str())
            })
            || *leaf != "SKILL.md" && (!parents.is_empty() || !leaf.ends_with(".md"))
        {
            continue;
        }
        let header = if bytes.starts_with(b"---\n") || bytes.starts_with(b"---\r\n") {
            frontmatter::decode(bytes, frontmatter::Dialect::JsYaml3)?
        } else {
            frontmatter::optional(bytes, frontmatter::Dialect::JsYaml3)?
        };
        if !(header.is_object() || header.is_null())
            || ["name", "description"]
                .iter()
                .any(|field| header.get(*field).is_some_and(|value| !value.is_string()))
        {
            return Err(invalid());
        }
        let name = match parents.last() {
            Some(parent) => (*parent).to_owned(),
            None if *leaf == "SKILL.md" => "skills".into(),
            None => leaf.strip_suffix(".md").ok_or_else(invalid)?.to_owned(),
        };
        valid(std::slice::from_ref(&name))?;
        if !observed.insert(name.clone()) {
            return Err(
                invalid().with_details([("constraint".into(), "native_id_collision".into())])
            );
        }
        result.insert((*path).to_owned(), vec![name]);
    }
    if observed.is_empty() {
        return Err(invalid());
    }
    Ok(result)
}
