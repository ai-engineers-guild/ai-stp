//! Local Claude names, including skill directory aliases and nested commands.

use std::collections::BTreeSet;

use super::invalid;
use crate::{authoring::frontmatter, error::Result};

pub(super) fn agent_names(bytes: &[u8]) -> Result<Vec<String>> {
    let header = frontmatter::required(bytes)?;
    let name = header["name"].as_str().ok_or_else(invalid)?;
    if name.starts_with('-')
        || name.contains(':')
        || name.chars().count() > 256
        || header["description"]
            .as_str()
            .is_none_or(|text| text.trim().is_empty())
    {
        return Err(invalid());
    }
    Ok(vec![name.to_owned()])
}

fn local_path<'a>(path: &'a str, root: &str) -> Result<&'a str> {
    path.strip_prefix(root)
        .or_else(|| {
            path.strip_prefix(".claude/")
                .or_else(|| path.strip_prefix(".agents/"))
                .and_then(|path| path.strip_prefix(root))
        })
        .ok_or_else(invalid)
}

fn reserved(name: &str) -> bool {
    let name = name.to_ascii_lowercase();
    name == "anthropic-skills" || name.starts_with("anthropic-skills:")
}

fn skill(path: &str, bytes: &[u8]) -> Result<Option<BTreeSet<String>>> {
    let path = local_path(path, "skills/")?;
    let Some((folder, "SKILL.md")) = path.split_once('/') else {
        return Ok(None);
    };
    if folder.eq_ignore_ascii_case("synced") || reserved(folder) {
        return Err(invalid());
    }
    let mut names = BTreeSet::from([folder.to_owned()]);
    let header = frontmatter::optional(bytes)?;
    if let Some(name) = header.get("name") {
        let name = name.as_str().ok_or_else(invalid)?;
        if name.is_empty()
            || name.chars().any(char::is_whitespace)
            || name.contains(['/', '\\'])
            || reserved(name)
        {
            return Err(invalid());
        }
        names.insert(name.to_owned());
    }
    Ok(Some(names))
}

/// Auxiliary skill files carry no extra invocation; legacy Markdown files do.
pub(super) fn invocations<'a>(
    kind: &str,
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let mut names = BTreeSet::new();
    for (path, bytes) in files {
        let next = if kind == "skill" {
            if path.ends_with("/.claude-plugin/plugin.json") {
                return Err(invalid());
            }
            skill(path, bytes)?
        } else {
            let path = local_path(path, "commands/")?;
            match path.strip_suffix(".md") {
                Some(name) if !name.is_empty() && !reserved(name) => {
                    Some(BTreeSet::from([name.replace('/', ":")]))
                }
                Some(_) => return Err(invalid()),
                None => None,
            }
        };
        if let Some(next) = next {
            for name in next {
                if name.chars().any(char::is_whitespace) {
                    return Err(invalid());
                }
                if !names.insert(name) {
                    return Err(invalid()
                        .with_details([("constraint".into(), "native_id_collision".into())]));
                }
            }
        }
    }
    if names.is_empty() {
        return Err(invalid());
    }
    Ok(names.into_iter().collect())
}
