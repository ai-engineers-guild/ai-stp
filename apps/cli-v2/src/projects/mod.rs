//! Bounded project evidence through held directory handles, without writes.

mod discovery;
mod index;

pub use discovery::discover;
pub use index::index;

use std::{
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

use cap_std::fs::{Dir, DirEntry};

use crate::{
    error::{ErrorKind, Failure, Result},
    files,
};

const MANIFESTS: &[&str] = &[
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pubspec.yaml",
];
const SKIPPED: &[&str] = &[
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "vendor",
    "target",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".hypothesis",
    ".cache",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".turbo",
    "htmlcov",
    ".pnpm-store",
    ".playwright-mcp",
    ".site",
    ".site-user-docs",
    "storybook-static",
    ".idea",
    ".vscode",
    ".ai-stp",
];
const DOCUMENTS: &[&str] = &["md", "markdown", "rst", "txt", "adoc"];
const MAX_FILE_BYTES: u64 = 1024 * 1024;
const MAX_ENTRIES: usize = 20_000;
const MAX_DIRECTORY: usize = 2000;
const MAX_DEPTH: usize = 12;

pub fn secret_name(name: &str) -> bool {
    let name = name.to_lowercase();
    [
        ".env",
        ".envrc",
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".htpasswd",
        "credentials",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "secrets.yaml",
        "secrets.yml",
        "secrets.json",
        "token.json",
        "tokens.json",
        ".mcp.json",
        "claude_desktop_config.json",
    ]
    .contains(&name.as_str())
        || name.starts_with(".env.")
        || (name.ends_with(".json")
            && (name.starts_with("credentials") || name.starts_with("service-account")))
        || [
            ".pem",
            ".key",
            ".p12",
            ".pfx",
            ".jks",
            ".keystore",
            ".ppk",
            ".ovpn",
        ]
        .iter()
        .any(|suffix| name.ends_with(suffix))
}

fn open_root(path: &Path) -> Result<(PathBuf, Dir)> {
    let path = if path.starts_with("~") {
        files::home()
            .ok_or_else(|| Failure::input("home directory is not configured"))?
            .join(
                path.strip_prefix("~")
                    .map_err(|_| Failure::input("invalid root"))?,
            )
    } else {
        path.to_owned()
    };
    let root = path
        .canonicalize()
        .map_err(|_| Failure::new(ErrorKind::NotFound, "project root is not accessible"))?;
    if root.parent().is_none()
        || files::home()
            .and_then(|p| p.canonicalize().ok())
            .is_some_and(|home| home == root)
    {
        return Err(Failure::input(
            "name a project directory rather than a home or filesystem root",
        ));
    }
    let directory = Dir::open_ambient_dir(&root, cap_std::ambient_authority()).map_err(|_| {
        Failure::new(
            ErrorKind::NotFound,
            "project root is not a readable directory",
        )
    })?;
    Ok((root, directory))
}

fn listed(directory: &Dir) -> std::result::Result<Vec<DirEntry>, &'static str> {
    let mut entries = Vec::new();
    for entry in directory
        .entries()
        .map_err(|_| "cannot be read")?
        .take(MAX_DIRECTORY + 1)
    {
        entries.push(entry.map_err(|_| "cannot be read")?);
    }
    if entries.len() > MAX_DIRECTORY {
        return Err("directory entry budget");
    }
    entries.sort_by_key(DirEntry::file_name);
    Ok(entries)
}

fn relative(path: &Path) -> String {
    let result = path
        .components()
        .filter(|c| !matches!(c, std::path::Component::CurDir))
        .map(|c| c.as_os_str().to_string_lossy())
        .collect::<Vec<_>>()
        .join("/");
    if result.is_empty() {
        ".".into()
    } else {
        result
    }
}

struct Budget {
    started: Instant,
    entries: usize,
}
impl Budget {
    fn new() -> Self {
        Self {
            started: Instant::now(),
            entries: 0,
        }
    }
    fn stop(&self) -> Option<&'static str> {
        if self.entries >= MAX_ENTRIES {
            Some("entry budget")
        } else if self.started.elapsed() >= Duration::from_secs(20) {
            Some("time budget")
        } else {
            None
        }
    }
}
