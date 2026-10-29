//! Local Git evidence for a later reviewed checkout binding, never authority.

use std::{
    ffi::OsString,
    path::{Path, PathBuf},
    process::Output,
    time::{Duration, Instant},
};

use cap_fs_ext::MetadataExt;
use cap_std::fs::Dir;
use serde_json::{Value, json};

use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, process,
};

const LIMIT: usize = 256 * 1024;

fn invalid() -> Failure {
    Failure::precondition("the checkout is incomplete, unsupported or changed during observation")
}

fn path_value(path: &Path) -> Result<Value> {
    files::serialize_path(path, serde_json::value::Serializer).map_err(|_| invalid())
}

fn identity(directory: &Dir) -> Result<[String; 2]> {
    let metadata = directory.dir_metadata().map_err(|_| invalid())?;
    Ok([metadata.dev().to_string(), metadata.ino().to_string()])
}

struct Directory {
    path: PathBuf,
    held: Dir,
    identity: [String; 2],
}

impl Directory {
    fn open(path: &Path) -> Result<Self> {
        let path = path.canonicalize().map_err(|_| invalid())?;
        let held =
            Dir::open_ambient_dir(&path, cap_std::ambient_authority()).map_err(|_| invalid())?;
        let identity = identity(&held)?;
        Ok(Self {
            path,
            held,
            identity,
        })
    }

    fn check(&self) -> Result<()> {
        if identity(&self.held)? != self.identity
            || Self::open(&self.path)?.identity != self.identity
        {
            return Err(invalid());
        }
        Ok(())
    }

    fn value(&self) -> Result<Value> {
        Ok(json!({"path":path_value(&self.path)?,"identity":self.identity}))
    }
}

struct Git {
    executable: PathBuf,
    executable_digest: String,
    environment: Vec<(OsString, OsString)>,
    started: Instant,
}

impl Git {
    fn new(explicit: Option<&Path>) -> Result<Self> {
        if explicit.is_some_and(|path| !path.is_absolute()) {
            return Err(Failure::input("Git executable must be an absolute path"));
        }
        let name = if cfg!(windows) { "git.exe" } else { "git" };
        let executable = explicit
            .map(Path::to_owned)
            .or_else(|| {
                std::env::var_os("PATH").and_then(|paths| {
                    std::env::split_paths(&paths)
                        .filter(|path| path.is_absolute())
                        .map(|path| path.join(name))
                        .find(|path| path.is_file())
                })
            })
            .ok_or_else(|| {
                Failure::new(
                    ErrorKind::Unavailable,
                    "checkout observation requires an existing user-managed Git executable",
                )
            })?;
        let executable = executable.canonicalize().map_err(|_| invalid())?;
        let executable_digest = digest::sha256(&files::read(&executable, 32 * 1024 * 1024)?);
        // No HOME, credentials, Git overrides, proxy variables or development
        // PATH. These builtins do not need a helper executable. Git for Windows
        // still needs its ordinary OS process environment.
        let mut environment: Vec<_> = ["SYSTEMROOT", "WINDIR", "TEMP", "TMP"]
            .iter()
            .filter_map(|key| std::env::var_os(key).map(|value| ((*key).into(), value)))
            .collect();
        let null = if cfg!(windows) { "NUL" } else { "/dev/null" };
        environment.extend([
            ("GIT_CONFIG_NOSYSTEM".into(), "1".into()),
            ("GIT_CONFIG_SYSTEM".into(), null.into()),
            ("GIT_CONFIG_GLOBAL".into(), null.into()),
            ("GIT_OPTIONAL_LOCKS".into(), "0".into()),
            ("GIT_NO_LAZY_FETCH".into(), "1".into()),
            ("GIT_TERMINAL_PROMPT".into(), "0".into()),
            ("GIT_ALLOW_PROTOCOL".into(), "".into()),
            ("GIT_PROTOCOL_FROM_USER".into(), "0".into()),
            ("GIT_NO_REPLACE_OBJECTS".into(), "1".into()),
            ("LC_ALL".into(), "C".into()),
        ]);
        Ok(Self {
            executable,
            executable_digest,
            environment,
            started: Instant::now(),
        })
    }

    fn run(&self, root: &Path, arguments: &[&str]) -> Result<Output> {
        let remaining = Duration::from_secs(20)
            .checked_sub(self.started.elapsed())
            .filter(|value| !value.is_zero())
            .ok_or_else(invalid)?;
        let arguments: Vec<OsString> = [
            "--no-pager",
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "maintenance.auto=false",
            "-c",
            "gc.auto=0",
        ]
        .into_iter()
        .chain(arguments.iter().copied())
        .map(Into::into)
        .collect();
        process::run(process::Request {
            executable: &self.executable,
            arguments: &arguments,
            directory: root,
            environment: &self.environment,
            timeout: remaining.min(Duration::from_secs(5)),
            output_limit: LIMIT,
        })
    }

    fn text(&self, root: &Path, arguments: &[&str]) -> Result<String> {
        let output = self.run(root, arguments)?;
        if !output.status.success() {
            return Err(invalid());
        }
        line(&output.stdout)
    }
}

fn line(bytes: &[u8]) -> Result<String> {
    let value = std::str::from_utf8(bytes).map_err(|_| invalid())?;
    let value = value.strip_suffix('\n').ok_or_else(invalid)?;
    let value = value.strip_suffix('\r').unwrap_or(value);
    if value.is_empty() || value.len() > 8192 || value.chars().any(char::is_control) {
        return Err(invalid());
    }
    Ok(value.into())
}

fn configurations(git: &Git, root: &Path) -> Result<(String, String, usize)> {
    let mut configurations = Vec::new();
    let mut routing = Vec::new();
    let mut endpoints = 0;
    let worktree = git.run(
        root,
        &[
            "config",
            "get",
            "--local",
            "--no-includes",
            "--type=bool",
            "extensions.worktreeConfig",
        ],
    )?;
    let scopes = if worktree.status.success() {
        match line(&worktree.stdout)?.as_str() {
            "true" => vec!["--local", "--worktree"],
            "false" => vec!["--local"],
            _ => return Err(invalid()),
        }
    } else if worktree.status.code() == Some(1) && worktree.stdout.is_empty() {
        vec!["--local"]
    } else {
        return Err(invalid());
    };
    for scope in scopes {
        let output = git.run(root, &["config", "list", scope, "--no-includes", "--null"])?;
        if !output.status.success() || (!output.stdout.is_empty() && !output.stdout.ends_with(&[0]))
        {
            return Err(invalid());
        }
        let mut records = Vec::new();
        for record in output
            .stdout
            .split(|byte| *byte == 0)
            .filter(|record| !record.is_empty())
        {
            let split = record
                .iter()
                .position(|byte| *byte == b'\n')
                .unwrap_or(record.len());
            let key = std::str::from_utf8(&record[..split]).map_err(|_| invalid())?;
            if key.starts_with("include.") || key.starts_with("includeif.") {
                // An unobserved include must not become silent routing authority.
                return Err(Failure::precondition(
                    "checkout observation requires explicit repository configuration without includes",
                ));
            }
            let hash = digest::sha256(record);
            records.push(hash.clone());
            if key.starts_with("remote.")
                || key.starts_with("url.")
                || key.starts_with("branch.")
                || key.starts_with("extensions.")
                || matches!(
                    key,
                    "core.worktree" | "core.bare" | "core.repositoryformatversion"
                )
            {
                routing.push(json!([scope, hash]));
            }
            if key.starts_with("remote.") && (key.ends_with(".url") || key.ends_with(".pushurl")) {
                endpoints += 1;
            }
            if records.len() > 2048 || endpoints > 256 {
                return Err(invalid());
            }
        }
        configurations.push(json!([scope, records]));
    }
    Ok((
        fingerprint("configuration", &json!(configurations))?,
        fingerprint("routing", &json!(routing))?,
        endpoints,
    ))
}

fn fingerprint(kind: &str, value: &Value) -> Result<String> {
    Ok(digest::sha256(&canonical::bytes(&json!([
        "ai-stp-native-checkout/1",
        kind,
        value
    ]))?))
}

fn snapshot(git: &Git, root: &Directory) -> Result<Value> {
    let top = git.text(
        &root.path,
        &["rev-parse", "--path-format=absolute", "--show-toplevel"],
    )?;
    if Directory::open(Path::new(&top))?.path != root.path {
        return Err(invalid());
    }
    let git_dir = Directory::open(Path::new(
        &git.text(&root.path, &["rev-parse", "--absolute-git-dir"])?,
    ))?;
    let common = Directory::open(Path::new(&git.text(
        &root.path,
        &["rev-parse", "--path-format=absolute", "--git-common-dir"],
    )?))?;
    let format = git.text(&root.path, &["rev-parse", "--show-object-format"])?;
    let length = match format.as_str() {
        "sha1" => 40,
        "sha256" => 64,
        _ => return Err(invalid()),
    };
    let symbolic = git.run(
        &root.path,
        &["symbolic-ref", "--quiet", "--no-recurse", "HEAD"],
    )?;
    let branch = if symbolic.status.success() {
        let name = line(&symbolic.stdout)?;
        if !name.starts_with("refs/heads/") || name.len() > 1024 {
            return Err(invalid());
        }
        Some(name)
    } else if symbolic.status.code() == Some(1) && symbolic.stdout.is_empty() {
        None
    } else {
        return Err(invalid());
    };
    let head = git.run(&root.path, &["rev-parse", "--verify", "HEAD"])?;
    let commit = if head.status.success() {
        let oid = line(&head.stdout)?;
        if oid.len() != length
            || !oid
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            || git.text(&root.path, &["cat-file", "-t", "HEAD"])? != "commit"
        {
            return Err(invalid());
        }
        Some(oid)
    } else if let Some(branch) = &branch {
        let absent = git.run(&root.path, &["show-ref", "--verify", "--quiet", branch])?;
        if absent.status.code() != Some(1) || !absent.stdout.is_empty() {
            return Err(invalid());
        }
        None
    } else {
        return Err(invalid());
    };
    let (configuration, routing, endpoints) = configurations(git, &root.path)?;
    let topology = json!({"root":root.value()?,"git_directory":git_dir.value()?,
        "common_directory":common.value()?,"object_format":format,"branch":branch,
        "routing_digest":routing});
    root.check()?;
    git_dir.check()?;
    common.check()?;
    Ok(
        json!({"topology_digest":fingerprint("topology", &topology)?,"topology":topology,
        "commit":commit,"head_state":if branch.is_none(){"detached"}else if commit.is_none(){"unborn"}else{"attached"},
        "configuration_digest":configuration,"remote_endpoint_count":endpoints}),
    )
}

/// Git is user-managed. This invokes only bounded local builtins; it neither
/// infers an immutable provider ID nor creates a marker, account or binding.
pub fn observe(path: &Path, executable: Option<&Path>) -> Result<Value> {
    let (path, held) = super::open_root(path)?;
    let root = Directory {
        identity: identity(&held)?,
        held,
        path,
    };
    // A project subdirectory must not silently inherit an ancestor repository.
    let marker = root.held.symlink_metadata(".git").map_err(|_| invalid())?;
    if marker.file_type().is_symlink() || !(marker.is_dir() || marker.is_file()) {
        return Err(invalid());
    }
    let git = Git::new(executable)?;
    let before = snapshot(&git, &root)?;
    let after = snapshot(&git, &root)?;
    if before != after
        || digest::sha256(&files::read(&git.executable, 32 * 1024 * 1024)?) != git.executable_digest
    {
        return Err(invalid());
    }
    let mut result = json!({"schema_version":1,"checkout":before,
        "git_executable":path_value(&git.executable)?,"git_executable_digest":git.executable_digest,
        "configuration_scope":"repository_only","observation_only":true,"installation_authority":false,
        "provider_identity_verified":false,"binding_created":false});
    result["observation_digest"] = fingerprint("observation", &result)?.into();
    Ok(result)
}

/// The first reviewed move supports an embedded, non-remapped Git directory.
/// All branch/commit/routing/configuration and object identities stay exact;
/// only the three known absolute path spellings and their digests may change.
pub(crate) fn relocated_observation(
    before: &Value,
    after: &Value,
    destination: &Path,
) -> Result<()> {
    let mut expected = before.clone();
    for (field, path) in [
        ("root", destination.to_owned()),
        ("git_directory", destination.join(".git")),
        ("common_directory", destination.join(".git")),
    ] {
        expected["checkout"]["topology"][field]["path"] = path_value(&path)?;
    }
    expected["checkout"]["topology_digest"] =
        fingerprint("topology", &expected["checkout"]["topology"])?.into();
    expected
        .as_object_mut()
        .ok_or_else(invalid)?
        .remove("observation_digest");
    expected["observation_digest"] = fingerprint("observation", &expected)?.into();
    if expected != *after {
        return Err(invalid());
    }
    Ok(())
}
