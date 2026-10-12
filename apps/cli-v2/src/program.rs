//! Observe a user-owned harness through its declared version query.

use crate::{
    canonical, digest,
    error::{Failure, Result},
    files, harnesses, process,
};
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
    time::Duration,
};

fn path_value(path: &Path) -> Result<Value> {
    files::serialize_path(path, serde_json::value::Serializer)
        .map_err(|_| Failure::input("the harness path is not representable"))
}

fn executable(path: &Path) -> bool {
    let Ok(metadata) = path.metadata() else {
        return false;
    };
    if !metadata.is_file() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        metadata.permissions().mode() & 0o111 != 0
    }
    #[cfg(windows)]
    {
        path.extension()
            .and_then(|value| value.to_str())
            .is_some_and(|value| value.eq_ignore_ascii_case("exe"))
    }
}

fn resolve(name: &str) -> Option<PathBuf> {
    let search = std::env::var_os("PATH")?;
    std::env::split_paths(&search)
        .filter(|path| path.is_absolute())
        .find_map(|directory| {
            let path = directory.join(name);
            #[cfg(windows)]
            {
                ["exe", "cmd", "bat"]
                    .iter()
                    .map(|extension| path.with_extension(extension))
                    .find(|path| path.is_file())
            }
            #[cfg(unix)]
            {
                executable(&path).then_some(path)
            }
        })
}

fn identity(path: &Path) -> Result<Value> {
    let resolved = path
        .canonicalize()
        .map_err(|_| Failure::precondition("the harness executable changed during observation"))?;
    let metadata = fs::metadata(&resolved)
        .map_err(|_| Failure::precondition("the harness executable is inaccessible"))?;
    let modified = metadata
        .modified()
        .ok()
        .and_then(|time| time.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|time| time.as_nanos().to_string());
    let value =
        json!({"resolved_path":path_value(&resolved)?,"size":metadata.len(),"modified":modified});
    #[cfg(unix)]
    let value = {
        use std::os::unix::fs::MetadataExt;
        let mut value = value;
        value["device"] = metadata.dev().to_string().into();
        value["inode"] = metadata.ino().to_string().into();
        value["mode"] = metadata.mode().into();
        value
    };
    Ok(value)
}

/// No installation receipt, provider, state directory or desired version is required.
/// The local program's version answer is an observation, not publisher verification.
pub fn observe(harness: &str, explicit: Option<&Path>) -> Result<Value> {
    let definition = harnesses::definition(harness)?;
    let name = definition
        .executable
        .as_deref()
        .ok_or_else(|| Failure::input("this harness has no declared executable"))?;
    if explicit.is_some_and(|path| !path.is_absolute()) {
        return Err(Failure::input(
            "the harness executable must be an absolute path",
        ));
    }
    let path = explicit.map(Path::to_path_buf).or_else(|| resolve(name));
    let mut report = json!({"harness_id":harness,"state":"missing","version":null,"executable":null,
        "management":"user","installation_performed":false,"program_observed":false});
    if let Some(path) = path {
        report["executable"] = path_value(&path)?;
        if path.is_file() {
            report["state"] = "unknown_version".into();
        }
        if executable(&path) {
            let before = identity(&path)?;
            // Credentials and harness configuration overrides are not inherited.
            // Update suppression is scoped to this short query, never persisted.
            let mut environment: Vec<(OsString, OsString)> =
                ["PATH", "SYSTEMROOT", "SystemRoot", "TEMP", "TMP"]
                    .iter()
                    .filter_map(|key| std::env::var_os(key).map(|value| ((*key).into(), value)))
                    .collect();
            environment.extend([
                ("DISABLE_AUTOUPDATER".into(), "1".into()),
                (
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC".into(),
                    "1".into(),
                ),
                ("OPENCODE_DISABLE_AUTOUPDATE".into(), "true".into()),
                ("LANG".into(), "C.UTF-8".into()),
            ]);
            let arguments: Vec<OsString> = definition
                .version_arguments
                .iter()
                .map(Into::into)
                .collect();
            let directory = std::env::temp_dir();
            if let Ok(output) = process::run(process::Request {
                executable: &path,
                arguments: &arguments,
                directory: &directory,
                environment: &environment,
                timeout: Duration::from_secs(5),
                output_limit: 4096,
            }) && output.status.success()
            {
                let bytes = if output.stdout.is_empty() {
                    &output.stderr
                } else {
                    &output.stdout
                };
                if let Ok(answer) = std::str::from_utf8(bytes) {
                    let first = answer.lines().next().unwrap_or("").trim();
                    let pattern = regex::Regex::new(r"(?:^|[^0-9A-Za-z])([0-9]+(?:\.[0-9]+)+(?:[.+-][0-9A-Za-z][0-9A-Za-z.-]*)?)(?:$|[^0-9A-Za-z.+_-])")
                        .map_err(|_| Failure::input("the version expression is invalid"))?;
                    if first.len() <= 256
                        && !first.chars().any(char::is_control)
                        && let Some(version) =
                            pattern.captures(first).and_then(|capture| capture.get(1))
                        && version.as_str().len() <= 64
                    {
                        report["version"] = version.as_str().into();
                        report["state"] = "observed".into();
                        report["program_observed"] = true.into();
                    }
                }
            }
            if before != identity(&path)? {
                return Err(Failure::precondition(
                    "the harness executable changed during observation; retry",
                ));
            }
            report["identity"] = before;
        }
    }
    report["observation_digest"] = digest::sha256(&canonical::bytes(&report)?).into();
    Ok(report)
}
