//! Spawn `ai-stp` with `--json`, capture exactly one envelope.
//!
//! Rules (ADR-0222):
//! - the executable is resolved by bundled path → explicit config → PATH,
//!   in that order — never a bare-name lookup in untrusted dirs;
//! - `--json` is always appended (it is a global option);
//! - timeouts are explicit; a timeout on a mutating call means "effect
//!   unconfirmed" — the caller must inspect before retrying;
//! - stderr is captured for diagnostics but never parsed for semantics.

use std::ffi::OsString;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::Duration;

use crate::envelope::{parse, Envelope, ParseFailure};

const DEFAULT_TIMEOUT: Duration = Duration::from_secs(120);

/// Env vars inherited by the spawned CLI when present in the parent env.
///
/// The Windows entries are load-bearing for the PyInstaller onefile
/// sidecar: its bootloader resolves the `_MEI` extraction dir through
/// `GetTempPathW` (`TMP` → `TEMP` → `USERPROFILE` → the Windows
/// directory). Stripping all three drops extraction into `C:\Windows`,
/// which a non-elevated user cannot write — the binary then dies before
/// the CLI runs with `[PYI-*:ERROR] Could not create temporary
/// directory!`. The AppData/HOME entries keep Python's profile and
/// `expanduser`/`Path.home()` resolution working inside the frozen CLI,
/// and the proxy/CA entries keep registry/auth traffic working behind
/// corporate proxies.
#[doc(hidden)]
pub const PASSTHROUGH_ENV: &[&str] = &[
    "PATH",
    "HOME",
    "USER",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TMPDIR",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
    "SSH_AUTH_SOCK",
    "SSH_AGENT_PID",
    "GPG_AGENT_INFO",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "all_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
    "SystemRoot",
    "WINDIR",
    "SYSTEMDRIVE",
    "COMSPEC",
    "PATHEXT",
    "OS",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "USERNAME",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PUBLIC",
    "PSModulePath",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
];

/// Compute the environment the CLI child runs under, from an explicit
/// parent-env snapshot: the inherited passthrough set, every `AI_STP_*`
/// var (locale, credential-store pins, future config), synthesized temp
/// vars when the parent supplies none, then the caller's managed-profile
/// overrides last so they win. `temp_root` is the parent's own temp dir,
/// used only when the snapshot offers no usable temp anchor at all.
///
/// Pure over its inputs — tests drive it with fabricated snapshots rather
/// than mutating process env, so they cannot race parallel tests that
/// call `std::env::temp_dir()`.
fn child_env(
    vars: &[(OsString, OsString)],
    temp_root: &Path,
    overrides: &[(String, String)],
) -> Vec<(OsString, OsString)> {
    let get = |name: &str| {
        vars.iter()
            .find(|(k, _)| k.to_str() == Some(name))
            .map(|(_, v)| v)
    };
    let mut env: Vec<(OsString, OsString)> = PASSTHROUGH_ENV
        .iter()
        .filter_map(|k| get(k).map(|v| (OsString::from(*k), v.clone())))
        .collect();
    for (k, v) in vars {
        if k.to_str().is_some_and(|s| s.starts_with("AI_STP_"))
            && !env.iter().any(|(ek, _)| ek == k)
        {
            env.push((k.clone(), v.clone()));
        }
    }
    // The child's temp chain must never be empty: on Windows `GetTempPathW`
    // degrades to the unwritable Windows directory when TMP/TEMP/
    // USERPROFILE are all absent, and the frozen CLI dies in its
    // bootloader. Inherited-but-nonexistent temp paths are just as
    // broken, so only a value naming a real directory counts.
    let usable_temp = ["TMPDIR", "TMP", "TEMP"]
        .iter()
        .filter_map(|k| get(k))
        .any(|v| Path::new(&v).is_dir());
    if !usable_temp {
        let base = get("LOCALAPPDATA")
            .map(PathBuf::from)
            .filter(|p| p.is_dir())
            .unwrap_or_else(|| temp_root.to_path_buf())
            .join("ai-stp-desktop");
        let _ = std::fs::create_dir_all(&base);
        for k in ["TMPDIR", "TMP", "TEMP"] {
            env.push((OsString::from(k), base.as_os_str().to_os_string()));
        }
    }
    env.extend(overrides.iter().map(|(k, v)| (k.into(), v.into())));
    env
}

#[derive(Debug)]
pub enum RunError {
    NotFound(String),
    Spawn(std::io::Error),
    /// Process exceeded the deadline; effect on the target is unconfirmed.
    TimeoutUnconfirmed,
    /// Process died before emitting an envelope.
    NoEnvelope {
        exit: Option<i32>,
        stderr: String,
    },
    Parse(ParseFailure),
}

impl std::fmt::Display for RunError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotFound(m) => write!(f, "ai-stp executable not found: {m}"),
            Self::Spawn(e) => write!(f, "failed to spawn ai-stp: {e}"),
            Self::TimeoutUnconfirmed => {
                write!(
                    f,
                    "cli exceeded deadline; effect unconfirmed — inspect before retrying"
                )
            }
            Self::NoEnvelope { exit, stderr } => {
                write!(f, "cli exited {exit:?} without an envelope: {stderr}")
            }
            Self::Parse(e) => write!(f, "{e}"),
        }
    }
}

impl std::error::Error for RunError {}

#[derive(Debug, Clone)]
pub struct CliLocator {
    /// App-managed/bundled executable (highest priority, must exist).
    pub bundled: Option<PathBuf>,
    /// User-configured override path.
    pub configured: Option<PathBuf>,
}

impl CliLocator {
    /// Resolution order: bundled → configured → PATH (`ai-stp`).
    /// A bundled/configured path that does not exist is an error, not a
    /// silent fallthrough — a missing pinned binary is a tamper signal.
    pub fn resolve(&self) -> Result<PathBuf, RunError> {
        if let Some(candidate) = [&self.bundled, &self.configured]
            .into_iter()
            .flatten()
            .next()
        {
            if candidate.is_file() {
                return Ok(candidate.clone());
            }
            return Err(RunError::NotFound(format!(
                "pinned path does not exist: {}",
                candidate.display()
            )));
        }
        which("ai-stp")
            .ok_or_else(|| RunError::NotFound("not on PATH and no bundled binary".into()))
    }
}

fn which(name: &str) -> Option<PathBuf> {
    let path_var = std::env::var_os("PATH")?;
    let name = if cfg!(windows) {
        format!("{name}.exe")
    } else {
        name.to_string()
    };
    for dir in std::env::split_paths(&path_var) {
        let candidate = dir.join(&name);
        if candidate.is_file() && is_executable(&candidate) {
            return Some(candidate);
        }
    }
    None
}

#[cfg(unix)]
fn is_executable(p: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    p.metadata()
        .map(|m| m.permissions().mode() & 0o111 != 0)
        .unwrap_or(false)
}

#[cfg(not(unix))]
fn is_executable(p: &Path) -> bool {
    p.is_file()
}

/// The executable + the environment a managed profile runs under.
#[derive(Debug, Clone)]
pub struct CliRunner {
    pub executable: PathBuf,
    /// Extra env for a managed profile (XDG homes, credential-store pin).
    pub env: Vec<(String, String)>,
    pub timeout: Duration,
}

impl CliRunner {
    pub fn system(locator: &CliLocator) -> Result<Self, RunError> {
        Ok(Self {
            executable: locator.resolve()?,
            env: Vec::new(),
            timeout: DEFAULT_TIMEOUT,
        })
    }

    /// Run one command path with args; returns the parsed envelope.
    /// `args` must already be the full argument list for the command
    /// (built by the caller from `help --agent` descriptors); `--json`
    /// is appended unconditionally.
    pub fn run(&self, args: &[String]) -> Result<Envelope, RunError> {
        let mut cmd = Command::new(&self.executable);
        cmd.args(args).arg("--json");
        cmd.env_clear();
        // Snapshot the parent env once so the child_env computation sees a
        // single consistent view.
        let parent_env: Vec<(OsString, OsString)> = std::env::vars_os().collect();
        for (k, v) in child_env(&parent_env, &std::env::temp_dir(), &self.env) {
            cmd.env(k, v);
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            // The sidecar is a console-subsystem binary; without this flag
            // every spawn flashes a console window over the GUI.
            cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        }
        cmd.stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        let mut child = cmd.spawn().map_err(RunError::Spawn)?;
        // stdout/stderr must be drained while the child runs: a large
        // envelope (e.g. `help --agent`) would fill the pipe buffer and
        // deadlock the child on write until the deadline hits.
        let out_handle = child.stdout.take().map(|mut s| {
            thread::spawn(move || {
                let mut buf = Vec::new();
                let _ = s.read_to_end(&mut buf);
                buf
            })
        });
        let err_handle = child.stderr.take().map(|mut s| {
            thread::spawn(move || {
                let mut buf = String::new();
                let _ = s.read_to_string(&mut buf);
                buf
            })
        });
        match wait_bounded(&mut child, self.timeout) {
            Ok(status) => {
                let out = out_handle.and_then(|h| h.join().ok()).unwrap_or_default();
                let err = err_handle.and_then(|h| h.join().ok()).unwrap_or_default();
                match parse(&out) {
                    Ok(env) => Ok(env),
                    Err(e) => Err(RunError::NoEnvelope {
                        exit: status.code(),
                        stderr: if err.trim().is_empty() {
                            format!("unparsable stdout: {e}")
                        } else {
                            err.trim().chars().take(2000).collect()
                        },
                    }),
                }
            }
            Err(WaitError::Timeout) => {
                let _ = child.kill();
                let _ = child.wait();
                Err(RunError::TimeoutUnconfirmed)
            }
            Err(WaitError::Io(e)) => Err(RunError::Spawn(e)),
        }
    }
}

enum WaitError {
    Timeout,
    Io(std::io::Error),
}

/// Bounded non-blocking wait; `Child` stays in the caller so a timeout can
/// kill the process.
fn wait_bounded(
    child: &mut Child,
    timeout: Duration,
) -> Result<std::process::ExitStatus, WaitError> {
    let started = std::time::Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) => return Ok(status),
            Ok(None) => {
                if started.elapsed() >= timeout {
                    return Err(WaitError::Timeout);
                }
                thread::sleep(Duration::from_millis(25));
            }
            Err(e) => return Err(WaitError::Io(e)),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vars(pairs: &[(&str, &str)]) -> Vec<(OsString, OsString)> {
        pairs
            .iter()
            .map(|(k, v)| (OsString::from(k), OsString::from(v)))
            .collect()
    }

    fn last(env: &[(OsString, OsString)], name: &str) -> Option<String> {
        env.iter()
            .filter(|(k, _)| k.to_str() == Some(name))
            .map(|(_, v)| v.to_string_lossy().into_owned())
            .last()
    }

    /// The Windows-bundle regression: TMP/TEMP/USERPROFILE/TMPDIR must be
    /// carried through `env_clear` or the PyInstaller bootloader falls
    /// back to an unwritable `C:\Windows` `_MEI` dir.
    #[test]
    fn child_env_carries_temp_and_profile_keys() {
        let snapshot = vars(&[
            ("TMP", "C:\\tmp"),
            ("TEMP", "C:\\tmp"),
            ("USERPROFILE", "C:\\Users\\u"),
            ("TMPDIR", "/tmp"),
            ("HOME", "/home/u"),
            ("SHOULD_NOT_LEAK", "x"),
        ]);
        let env = child_env(&snapshot, Path::new("/tmp"), &[]);
        for k in ["TMP", "TEMP", "USERPROFILE", "TMPDIR", "HOME"] {
            assert!(last(&env, k).is_some(), "missing {k}");
        }
        assert!(last(&env, "SHOULD_NOT_LEAK").is_none());
    }

    /// Every `AI_STP_*` var passes through even though it is not in the
    /// fixed passthrough list (locale, credential-store pins, future
    /// config keys).
    #[test]
    fn child_env_passes_ai_stp_prefix() {
        let snapshot = vars(&[("TMPDIR", "/tmp"), ("AI_STP_LOCALE", "ru"), ("OTHER", "x")]);
        let env = child_env(&snapshot, Path::new("/tmp"), &[]);
        assert_eq!(last(&env, "AI_STP_LOCALE").as_deref(), Some("ru"));
        assert!(last(&env, "OTHER").is_none());
    }

    /// A snapshot with no usable temp dir must yield a synthesized
    /// per-app temp — the same chain GetTempPathW needs on Windows.
    #[test]
    fn child_env_synthesizes_temp_when_parent_has_none() {
        let anchor = std::env::temp_dir().join("ai-stp-test-localappdata");
        std::fs::create_dir_all(&anchor).unwrap();
        let snapshot = vars(&[("LOCALAPPDATA", anchor.to_str().unwrap())]);
        let env = child_env(&snapshot, Path::new("/tmp"), &[]);
        let expected = anchor.join("ai-stp-desktop");
        for k in ["TMPDIR", "TMP", "TEMP"] {
            assert_eq!(
                last(&env, k).as_deref(),
                Some(expected.to_string_lossy().as_ref()),
                "{k} not synthesized"
            );
        }
        // With no LOCALAPPDATA either, the supplied temp root anchors it.
        let env = child_env(&[], Path::new("/tmp"), &[]);
        assert_eq!(last(&env, "TMPDIR").as_deref(), Some("/tmp/ai-stp-desktop"));
        let _ = std::fs::remove_dir_all(&anchor);
    }

    /// Managed-profile overrides land last, so they beat any inherited
    /// value for the same key.
    #[test]
    fn child_env_overrides_win_over_inherited() {
        let snapshot = vars(&[("TMPDIR", "/inherited")]);
        let env = child_env(
            &snapshot,
            Path::new("/tmp"),
            &[("TMPDIR".into(), "/override".into())],
        );
        assert_eq!(last(&env, "TMPDIR").as_deref(), Some("/override"));
    }
}
