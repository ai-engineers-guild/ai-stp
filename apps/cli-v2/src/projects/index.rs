use std::io::Read;

use cap_fs_ext::{DirExt, MetadataExt};
use serde_json::{Value, json};

use super::*;
use crate::digest;

fn classification(path: &Path) -> (&'static str, Option<&'static str>) {
    let name = path.file_name().and_then(|s| s.to_str()).unwrap_or("");
    if [
        "AGENTS.md",
        "CLAUDE.md",
        "CLAUDE.local.md",
        "SKILL.md",
        ".mcp.json",
    ]
    .contains(&name)
    {
        return ("agent_surface", None);
    }
    if MANIFESTS.contains(&name) || ["setup.cfg", "requirements.txt"].contains(&name) {
        return ("manifest", None);
    }
    if [
        "uv.lock",
        "poetry.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "Cargo.lock",
        "go.sum",
        "pubspec.lock",
    ]
    .contains(&name)
    {
        return ("lock", None);
    }
    let suffix = path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_lowercase();
    let language = match suffix.as_str() {
        "py" | "pyi" => Some("python"),
        "ts" | "tsx" | "mts" | "cts" => Some("typescript"),
        "js" | "jsx" | "mjs" | "cjs" => Some("javascript"),
        "rs" => Some("rust"),
        "go" => Some("go"),
        "dart" => Some("dart"),
        _ => None,
    };
    if language.is_some() {
        ("source", language)
    } else if DOCUMENTS.contains(&suffix.as_str()) {
        ("document", None)
    } else if ["toml", "yaml", "yml", "json", "ini", "cfg", "properties"].contains(&suffix.as_str())
    {
        ("config", None)
    } else {
        ("text", None)
    }
}

type SourceObserver<'a> = dyn FnMut(&str, Option<&str>, Option<&[u8]>) + 'a;

struct Index<'a> {
    budget: Budget,
    files: Vec<Value>,
    excluded: Vec<Value>,
    stopped: Option<&'static str>,
    observe: &'a mut SourceObserver<'a>,
}

impl Index<'_> {
    fn exclude(&mut self, path: &Path, reason: &'static str) {
        self.excluded
            .push(json!({"schema_version": 1, "path": relative(path), "reason": reason}));
        if matches!(
            reason,
            "cannot be read"
                | "depth budget"
                | "directory entry budget"
                | "changed during observation"
        ) {
            self.stopped.get_or_insert(reason);
        }
    }

    fn walk(&mut self, directory: &Dir, path: &Path, depth: usize) {
        if let Some(reason) = self.budget.stop() {
            self.stopped.get_or_insert(reason);
            return;
        }
        if depth >= MAX_DEPTH {
            self.exclude(path, "depth budget");
            return;
        }
        let entries = match listed(directory) {
            Ok(entries) => entries,
            Err(reason) => {
                self.exclude(path, reason);
                return;
            }
        };
        for entry in entries {
            if let Some(reason) = self.budget.stop() {
                self.stopped.get_or_insert(reason);
                break;
            }
            self.budget.entries += 1;
            let name = entry.file_name();
            let child = path.join(&name);
            let Some(text) = name.to_str() else {
                self.exclude(&child, "cannot be read");
                continue;
            };
            if secret_name(text) {
                self.exclude(&child, "looks like a credential");
                continue;
            }
            let metadata = match entry.metadata() {
                Ok(metadata) => metadata,
                Err(_) => {
                    self.exclude(&child, "cannot be read");
                    continue;
                }
            };
            if metadata.file_type().is_symlink() {
                self.exclude(&child, "symlink is not followed");
                continue;
            }
            if metadata.is_dir() {
                if SKIPPED.contains(&text) {
                    self.exclude(&child, "excluded directory");
                    continue;
                }
                match directory.open_dir_nofollow(&name) {
                    Ok(dir) => self.walk(&dir, &child, depth + 1),
                    Err(_) => self.exclude(&child, "cannot be read"),
                }
                continue;
            }
            if !metadata.is_file() {
                self.exclude(&child, "not a regular file");
                continue;
            }
            let (kind, language) = classification(&child);
            let size = metadata.len();
            let mut hash = None;
            let mut lines = None;
            let mut content = Vec::new();
            if size <= MAX_FILE_BYTES {
                let result = (|| -> std::io::Result<()> {
                    let mut file = files::open_regular(directory, Path::new(&name))?;
                    let before = file.metadata()?;
                    file.by_ref()
                        .take(MAX_FILE_BYTES + 1)
                        .read_to_end(&mut content)?;
                    let after = file.metadata()?;
                    if content.len() as u64 != size
                        || before.nlink() != 1
                        || after.nlink() != 1
                        || before.len() != after.len()
                        || before.modified()? != after.modified()?
                    {
                        return Err(std::io::Error::other("changed during observation"));
                    }
                    Ok(())
                })();
                if result.is_err() {
                    self.exclude(&child, "cannot be read");
                    continue;
                }
                if content.iter().take(8000).any(|b| *b == 0) {
                    self.exclude(&child, "binary content");
                    continue;
                }
                hash = Some(digest::sha256(&content));
                lines = Some(
                    content.iter().filter(|b| **b == b'\n').count()
                        + usize::from(!content.is_empty() && !content.ends_with(b"\n")),
                );
            }
            (self.observe)(
                &relative(&child),
                language,
                hash.as_ref().map(|_| content.as_slice()),
            );
            self.files.push(
                json!({"schema_version": 1, "path": relative(&child), "kind": kind,
                "language": language, "size_bytes": size, "digest": hash, "lines": lines}),
            );
        }
    }
}

pub fn index(path: &Path) -> Result<Value> {
    visit(path, &mut |_, _, _| {})
}

/// Source observers receive the exact bytes already read and hashed by the index.
pub(super) fn visit(path: &Path, observe: &mut SourceObserver<'_>) -> Result<Value> {
    let (root, directory) = open_root(path)?;
    visit_at(&root, &directory, observe)
}

pub(super) fn visit_at(
    root: &Path,
    directory: &Dir,
    observe: &mut SourceObserver<'_>,
) -> Result<Value> {
    let mut index = Index {
        budget: Budget::new(),
        files: Vec::new(),
        excluded: Vec::new(),
        stopped: None,
        observe,
    };
    index.walk(directory, Path::new("."), 0);
    for entries in [&mut index.files, &mut index.excluded] {
        entries.sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
    }
    Ok(
        json!({"schema_version": 1, "root": files::display(root), "state": if index.stopped.is_some() {"partial"} else {"complete"},
        "stopped_by": index.stopped, "files": index.files, "excluded": index.excluded}),
    )
}
