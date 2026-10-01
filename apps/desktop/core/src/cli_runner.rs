//! Spawn `ai-stp` with `--json`, capture exactly one envelope.
//!
//! Rules (ADR-0222):
//! - the executable is resolved by bundled path → explicit config → PATH,
//!   in that order — never a bare-name lookup in untrusted dirs;
//! - `--json` is always appended (it is a global option);
//! - timeouts are explicit; a timeout on a mutating call means "effect
//!   unconfirmed" — the caller must inspect before retrying;
//! - stderr is captured for diagnostics but never parsed for semantics.

use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::Duration;

use crate::envelope::{parse, Envelope, ParseFailure};

const DEFAULT_TIMEOUT: Duration = Duration::from_secs(120);

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
    for dir in std::env::split_paths(&path_var) {
        let candidate = dir.join(name);
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
        // Minimal base env; the caller's managed profile adds XDG_*.
        for key in [
            "PATH",
            "HOME",
            "USER",
            "LANG",
            "SystemRoot",
            "WINDIR",
            "COMSPEC",
        ] {
            if let Ok(v) = std::env::var(key) {
                cmd.env(key, v);
            }
        }
        for (k, v) in &self.env {
            cmd.env(k, v);
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
