use cap_fs_ext::DirExt;
use serde_json::{Value, json};

use super::*;

fn candidate(root: &Path, entries: &[DirEntry], kind: &str, reason: Option<&str>) -> Value {
    let mut markers = Vec::new();
    let mut documents = 0;
    let mut other = 0;
    for entry in entries {
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        if MANIFESTS.contains(&name) {
            markers.push(name.to_owned());
        }
        if name == ".git" {
            markers.push("git".to_owned());
        }
        if !name.starts_with('.') && entry.file_type().is_ok_and(|ft| ft.is_file()) {
            if Path::new(name)
                .extension()
                .and_then(|s| s.to_str())
                .is_some_and(|suffix| DOCUMENTS.contains(&suffix.to_lowercase().as_str()))
            {
                documents += 1;
            } else {
                other += 1;
            }
        }
    }
    markers.sort();
    let manifest = markers.iter().any(|name| name != "git");
    let established = manifest || other > 0;
    let reason = reason.unwrap_or(if manifest {
        "carries a project manifest"
    } else if other > 0 {
        "carries files but no manifest"
    } else if documents > 0 {
        "only documentation so far"
    } else {
        "nothing here yet"
    });
    json!({"schema_version": 1, "root": files::display(root), "kind": kind, "state": if established {"established"} else {"new"}, "markers": markers, "reason": reason})
}

struct Discovery {
    budget: Budget,
    candidates: Vec<Value>,
    diagnostics: Vec<Value>,
    complete: bool,
}

impl Discovery {
    fn diagnostic(&mut self, path: &Path, code: &str, reason: &str) {
        self.complete &= !matches!(code, "entry_limit" | "unreadable");
        self.diagnostics.push(json!({"schema_version": 1, "path": files::display(path), "code": code, "reason": reason}));
    }

    fn walk(
        &mut self,
        directory: &Dir,
        root: &Path,
        entries: Vec<DirEntry>,
        inside: bool,
        direct: bool,
        depth: usize,
    ) {
        for entry in entries {
            if let Some(reason) = self.budget.stop() {
                self.diagnostic(root, "entry_limit", reason);
                break;
            }
            self.budget.entries += 1;
            let name = entry.file_name();
            let child = root.join(&name);
            let Some(text) = name.to_str() else {
                self.diagnostic(&child, "unreadable", "path is not UTF-8");
                continue;
            };
            if text == ".git" {
                continue;
            }
            if SKIPPED.contains(&text) || secret_name(text) {
                self.diagnostic(&child, "excluded", "directory is excluded by policy");
                continue;
            }
            let file_type = match entry.file_type() {
                Ok(kind) => kind,
                Err(_) => {
                    self.diagnostic(&child, "unreadable", "path cannot be inspected");
                    continue;
                }
            };
            if file_type.is_symlink() {
                self.diagnostic(&child, "symlink", "symlink is not followed");
                continue;
            }
            if !file_type.is_dir() {
                continue;
            }
            if depth >= MAX_DEPTH {
                self.diagnostic(&child, "entry_limit", "depth budget");
                continue;
            }
            let dir = match directory.open_dir_nofollow(&name) {
                Ok(dir) => dir,
                Err(_) => {
                    self.diagnostic(&child, "unreadable", "directory cannot be opened");
                    continue;
                }
            };
            let children = match listed(&dir) {
                Ok(entries) => entries,
                Err(reason) => {
                    self.diagnostic(
                        &child,
                        if reason == "directory entry budget" {
                            "entry_limit"
                        } else {
                            "unreadable"
                        },
                        reason,
                    );
                    continue;
                }
            };
            let is_repository = children.iter().any(|e| e.file_name() == ".git");
            let mut child_inside = inside;
            if direct || is_repository {
                let kind = if !direct && inside {
                    "nested_repository"
                } else {
                    "project"
                };
                let reason = if direct {
                    None
                } else if inside {
                    Some("a separate repository inside the root; register it only on purpose")
                } else {
                    Some("a Git repository inside the named discovery scope")
                };
                let found = candidate(&child, &children, kind, reason);
                child_inside |= is_repository || found["state"] == "established";
                self.candidates.push(found);
            }
            self.walk(&dir, &child, children, child_inside, false, depth + 1);
        }
    }
}

pub fn discover(path: &Path) -> Result<Value> {
    let (root, directory) = open_root(path)?;
    let mut discovery = Discovery {
        budget: Budget::new(),
        candidates: Vec::new(),
        diagnostics: Vec::new(),
        complete: true,
    };
    match listed(&directory) {
        Ok(entries) => {
            let own = candidate(&root, &entries, "project", None);
            let established = own["state"] == "established";
            if established {
                discovery.candidates.push(own.clone());
            }
            discovery.walk(&directory, &root, entries, established, !established, 0);
            if discovery.candidates.is_empty() && discovery.complete {
                discovery.candidates.push(own);
            }
        }
        Err(reason) => discovery.diagnostic(
            &root,
            if reason == "directory entry budget" {
                "entry_limit"
            } else {
                "unreadable"
            },
            reason,
        ),
    }
    discovery
        .candidates
        .sort_by(|a, b| a["root"].as_str().cmp(&b["root"].as_str()));
    discovery
        .diagnostics
        .sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
    Ok(
        json!({"schema_version": 1, "discovery_root": files::display(&root), "complete": discovery.complete,
        "candidates": discovery.candidates, "diagnostics": discovery.diagnostics}),
    )
}
