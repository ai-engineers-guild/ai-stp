//! Entries observed in provider-pinned Pi 1.0.0, over captured bytes only.

use std::collections::{BTreeMap, BTreeSet};

use ignore::gitignore::{Gitignore, GitignoreBuilder};

use super::invalid;
use crate::{authoring::frontmatter, error::Result};

fn local_path<'a>(kind: &str, path: &'a str) -> Option<&'a str> {
    let path = path
        .strip_prefix(".pi/")
        .or_else(|| path.strip_prefix(".agents/"))
        .unwrap_or(path);
    path.strip_prefix(match kind {
        "skill" => "skills/",
        "command" => "prompts/",
        _ => return None,
    })
}

struct Skills<'a> {
    files: BTreeMap<&'a str, &'a [u8]>,
    directories: BTreeMap<&'a str, BTreeSet<&'a str>>,
    rules: GitignoreBuilder,
    matcher: Gitignore,
    patterns: usize,
}

impl<'a> Skills<'a> {
    fn new(files: BTreeMap<&'a str, &'a [u8]>) -> Result<Self> {
        let mut directories: BTreeMap<_, BTreeSet<_>> = BTreeMap::new();
        for path in files.keys() {
            let mut child = *path;
            while let Some((parent, _)) = child.rsplit_once('/') {
                directories.entry(parent).or_default().insert(child);
                child = parent;
            }
            directories.entry("").or_default().insert(child);
        }
        let mut rules = GitignoreBuilder::new("");
        // The upstream node-ignore matcher is case-insensitive on every OS.
        rules.case_insensitive(true).map_err(|_| invalid())?;
        let matcher = rules.build().map_err(|_| invalid())?;
        Ok(Self {
            files,
            directories,
            rules,
            matcher,
            patterns: 0,
        })
    }

    fn add_rules(&mut self, directory: &str) -> Result<()> {
        let prefix = if directory.is_empty() {
            String::new()
        } else {
            format!("{directory}/")
        };
        let mut changed = false;
        for name in [".gitignore", ".ignore", ".fdignore"] {
            let Some(bytes) = self.files.get(format!("{prefix}{name}").as_str()) else {
                continue;
            };
            if bytes.len() > 64 * 1024 {
                return Err(invalid());
            }
            for line in std::str::from_utf8(bytes).map_err(|_| invalid())?.lines() {
                if line.trim().is_empty() || line.trim().starts_with('#') {
                    continue;
                }
                self.patterns += 1;
                if self.patterns > 10_000 || line.len() > 4096 {
                    return Err(invalid());
                }
                let (negative, pattern) = if let Some(pattern) = line.strip_prefix('!') {
                    ("!", pattern)
                } else {
                    ("", line.strip_prefix("\\!").unwrap_or(line))
                };
                let pattern = pattern.strip_prefix('/').unwrap_or(pattern);
                self.rules
                    .add_line(None, &format!("{negative}{prefix}{pattern}"))
                    .map_err(|_| invalid())?;
                changed = true;
            }
        }
        if changed {
            self.matcher = self.rules.build().map_err(|_| invalid())?;
        }
        Ok(())
    }

    fn skill(&self, path: &str, declared: bool) -> Result<Option<String>> {
        let bytes = self.files.get(path).ok_or_else(invalid)?;
        let header = frontmatter::optional(bytes, frontmatter::Dialect::Core)?;
        if header
            .get("description")
            .and_then(serde_json::Value::as_str)
            .is_none_or(|description| description.trim().is_empty())
        {
            return if declared { Err(invalid()) } else { Ok(None) };
        }
        let parent = path.rsplit_once('/').map_or("skills", |(parent, _)| {
            parent.rsplit('/').next().unwrap_or(parent)
        });
        // Pi warns about non-spec names but loads them; non-string/empty names
        // fall back to the containing directory, not the Markdown filename.
        let name = header
            .get("name")
            .and_then(serde_json::Value::as_str)
            .filter(|name| !name.is_empty())
            .unwrap_or(parent);
        Ok(Some(name.to_owned()))
    }

    fn scan(&mut self, directory: &str, names: &mut Vec<String>) -> Result<()> {
        if directory.matches('/').count() >= 32 {
            return Err(invalid());
        }
        self.add_rules(directory)?;
        let declared = if directory.is_empty() {
            "SKILL.md".into()
        } else {
            format!("{directory}/SKILL.md")
        };
        if self.files.contains_key(declared.as_str())
            && !self.matcher.matched(&declared, false).is_ignore()
        {
            if let Some(name) = self.skill(&declared, true)? {
                names.push(name);
            }
            return Ok(());
        }
        let children: Vec<_> = self
            .directories
            .get(directory)
            .into_iter()
            .flatten()
            .copied()
            .collect();
        for path in children {
            let name = path.rsplit('/').next().ok_or_else(invalid)?;
            if name.starts_with('.') || name == "node_modules" {
                continue;
            }
            let is_directory = !self.files.contains_key(path);
            if self.matcher.matched(path, is_directory).is_ignore() {
                continue;
            }
            if is_directory {
                self.scan(path, names)?;
            } else if directory.is_empty()
                && name.ends_with(".md")
                && let Some(name) = self.skill(path, false)?
            {
                names.push(name);
            }
        }
        Ok(())
    }
}

/// Bundle checks include every file under these roots, across component owners.
/// This catches a skill root or ignore file masking an otherwise valid component.
pub(super) fn visible<'a>(
    kind: &str,
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let mut captured = BTreeMap::new();
    for (path, bytes) in files {
        if let Some(path) = local_path(kind, path)
            && captured.insert(path, bytes).is_some()
        {
            return Err(invalid());
        }
    }
    let mut names = Vec::new();
    match kind {
        "skill" => Skills::new(captured)?.scan("", &mut names)?,
        "command" => {
            for (path, bytes) in captured {
                if path.contains('/') {
                    continue;
                }
                let Some(name) = path.strip_suffix(".md") else {
                    continue;
                };
                frontmatter::optional(bytes, frontmatter::Dialect::Core)?;
                names.push(name.to_owned());
            }
        }
        _ => return Err(invalid()),
    }
    let unique: BTreeSet<_> = names.iter().collect();
    if unique.len() != names.len() {
        return Err(invalid().with_details([("constraint".into(), "native_id_collision".into())]));
    }
    names.sort();
    Ok(names)
}

pub(super) fn entries<'a>(
    kind: &str,
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let files: Vec<_> = files.into_iter().collect();
    if files
        .iter()
        .any(|(path, _)| local_path(kind, path).is_none())
    {
        return Err(invalid());
    }
    let names = visible(kind, files)?;
    if names.is_empty() {
        return Err(invalid());
    }
    Ok(names)
}
