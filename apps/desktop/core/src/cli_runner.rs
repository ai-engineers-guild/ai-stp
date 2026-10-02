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

pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(120);
/// Mutating runs (plan/apply, task steps) can sit inside the CLI's own
/// 300 s provider-verification budget — the shell deadline must outlive
/// it or a healthy apply is killed mid-flight.
pub const MUTATING_TIMEOUT: Duration = Duration::from_secs(420);
/// Output caps: stdout must hold one envelope (envelope.rs rejects past
/// 4 MiB anyway); stderr is diagnostics only.
const MAX_STDOUT_BYTES: usize = 4 * 1024 * 1024 + 64;
const MAX_STDERR_BYTES: usize = 256 * 1024;
/// Grace for drain threads after the child exits — a grandchild that
/// inherited the pipes must not pin `run` forever.
const DRAIN_GRACE: Duration = Duration::from_secs(5);

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

/// Compute the environment the CLI child runs under: the inherited
/// passthrough set, every `AI_STP_*` var (locale, credential-store pins,
/// future config), synthesized temp vars when the parent supplies none,
/// then the caller's managed-profile overrides last so they win.
fn child_env(overrides: &[(String, String)]) -> Vec<(OsString, OsString)> {
    let mut env: Vec<(OsString, OsString)> = PASSTHROUGH_ENV
        .iter()
        .filter_map(|k| std::env::var_os(k).map(|v| (OsString::from(k), v)))
        .collect();
    for (k, v) in std::env::vars_os() {
        if k.to_str().is_some_and(|s| s.starts_with("AI_STP_"))
            && !env.iter().any(|(ek, _)| ek == &k)
        {
            env.push((k, v));
        }
    }
    // The child's temp chain must never be empty: on Windows `GetTempPathW`
    // degrades to the unwritable Windows directory when TMP/TEMP/
    // USERPROFILE are all absent, and the frozen CLI dies in its
    // bootloader. Inherited-but-nonexistent temp paths are just as
    // broken, so only a value naming a real directory counts.
    let usable_temp = ["TMPDIR", "TMP", "TEMP"]
        .iter()
        .any(|k| std::env::var_os(k).is_some_and(|v| Path::new(&v).is_dir()));
    if !usable_temp {
        let base = std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .filter(|p| p.is_dir())
            .unwrap_or_else(std::env::temp_dir)
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
    /// Internal state failure (poisoned lock, …) — not a child problem.
    Internal(String),
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
                let exit = match exit {
                    Some(c) => format!("exit {c}"),
                    None => "terminated by signal".to_string(),
                };
                write!(f, "cli {exit} without an envelope: {stderr}")
            }
            Self::Parse(e) => write!(f, "{e}"),
            Self::Internal(m) => write!(f, "{m}"),
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
        for (k, v) in child_env(&self.env) {
            cmd.env(k, v);
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            // Own process group so a timeout can kill the whole tree: the
            // PyInstaller onefile bootloader forks the real CLI, and
            // `Child::kill` alone would orphan the in-flight mutation.
            cmd.process_group(0);
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
        // deadlock the child on write until the deadline hits. Reads are
        // byte-bounded so a runaway child cannot exhaust memory, and the
        // results come back over a channel so a pipe inherited by a stray
        // grandchild cannot pin `run` past the drain grace.
        let (out_tx, out_rx) = std::sync::mpsc::channel();
        let (err_tx, err_rx) = std::sync::mpsc::channel();
        if let Some(s) = child.stdout.take() {
            thread::spawn(move || {
                let mut buf = Vec::new();
                let _ = s.take(MAX_STDOUT_BYTES as u64).read_to_end(&mut buf);
                let _ = out_tx.send(buf);
            });
        } else {
            let _ = out_tx.send(Vec::new());
        }
        if let Some(s) = child.stderr.take() {
            thread::spawn(move || {
                let mut buf = Vec::new();
                let _ = s.take(MAX_STDERR_BYTES as u64).read_to_end(&mut buf);
                let _ = err_tx.send(buf);
            });
        } else {
            let _ = err_tx.send(Vec::new());
        }
        let collect = |rx: &std::sync::mpsc::Receiver<Vec<u8>>| {
            rx.recv_timeout(DRAIN_GRACE).unwrap_or_default()
        };
        match wait_bounded(&mut child, self.timeout) {
            Ok(status) => {
                let out = collect(&out_rx);
                let err = String::from_utf8_lossy(&collect(&err_rx)).into_owned();
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
                kill_tree(&mut child);
                Err(RunError::TimeoutUnconfirmed)
            }
            Err(WaitError::Io(e)) => {
                // try_wait failed — reap so the child is not abandoned.
                kill_tree(&mut child);
                Err(RunError::Spawn(e))
            }
        }
    }
}

/// Kill the child's whole process tree. The onefile bootloader is a parent
/// process: reaping only the direct child would leave the real CLI
/// running a mutation we just declared unconfirmed.
fn kill_tree(child: &mut Child) {
    #[cfg(unix)]
    {
        // `kill` resolves through /bin — the child's filtered env does not
        // apply to this spawn (it inherits ours).
        let pgid = format!("-{}", child.id());
        let _ = Command::new("kill")
            .args(["-TERM", &pgid])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        for _ in 0..20 {
            if matches!(child.try_wait(), Ok(Some(_))) {
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
        let _ = Command::new("kill")
            .args(["-KILL", &pgid])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        let _ = child.kill();
    }
    #[cfg(windows)]
    {
        // /T kills the tree (bootloader + extracted CLI), /F forces.
        use std::os::windows::process::CommandExt;
        let _ = Command::new("taskkill")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .creation_flags(0x0800_0000)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        let _ = child.kill();
    }
    #[cfg(not(any(unix, windows)))]
    let _ = child.kill();
    let _ = child.wait();
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
