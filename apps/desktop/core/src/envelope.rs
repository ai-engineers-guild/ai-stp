//! ai-stp CLI machine envelope (`docs/contracts/cli-json.md`).
//!
//! Invariants enforced here:
//! - stdout must be exactly one JSON object (plus optional trailing newline);
//! - `schema_version` must equal a supported major (1) — additive minor fields
//!   are tolerated, unknown majors are refused;
//! - errors are keyed on `error.code`, never on message text.

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const SUPPORTED_SCHEMA_MAJOR: u64 = 1;
pub const MAX_STDOUT_BYTES: usize = 4 * 1024 * 1024;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CliError {
    pub code: String,
    pub message: String,
    #[serde(default)]
    pub retryable: bool,
    #[serde(default)]
    pub details: Value,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Continuation {
    pub kind: String,
    #[serde(default)]
    pub path: Vec<String>,
    #[serde(default)]
    pub arguments: Value,
    #[serde(default)]
    pub missing: Vec<String>,
    /// Ready-to-spawn argument list; the executable form, never eval'd.
    #[serde(default)]
    pub argv: Vec<String>,
    #[serde(default)]
    pub actor: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ContinuationActor {
    /// The app may run `argv` itself.
    Cli,
    /// A live executor owns progress — poll status, never re-run.
    External,
    /// An agent executor drives this continuation — the app prompts rather
    /// than auto-running, like `Human`, but the distinction is the
    /// contract's to make, not ours to flatten.
    Agent,
    /// A human decision/input is required (e.g. `task answer`).
    Human,
}

impl Continuation {
    /// The actor the contract expects to drive this continuation.
    /// An unknown/absent actor is treated conservatively as `Human` —
    /// we show it as a prompt rather than auto-running an argv we were
    /// not explicitly handed.
    pub fn actor_kind(&self) -> ContinuationActor {
        match self.actor.as_deref() {
            Some("cli") => ContinuationActor::Cli,
            Some("external") => ContinuationActor::External,
            Some("agent") => ContinuationActor::Agent,
            _ => ContinuationActor::Human,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Envelope {
    pub schema_version: u64,
    pub ok: bool,
    #[serde(default)]
    pub request_id: Option<String>,
    #[serde(default)]
    pub operation_id: Option<String>,
    #[serde(default)]
    pub data: Option<Value>,
    #[serde(default)]
    pub warnings: Vec<String>,
    #[serde(default)]
    pub error: Option<CliError>,
    #[serde(default)]
    pub next_actions: Vec<Value>,
    #[serde(default)]
    pub continuations: Vec<Continuation>,
}

#[derive(Debug)]
pub enum ParseFailure {
    /// stdout was not a single JSON object (interpreter crash, stray output).
    NotJson(String),
    /// Schema major outside the supported set — fail closed, prompt update.
    UnsupportedSchema(u64),
    /// Envelope fields malformed.
    Malformed(String),
}

impl std::fmt::Display for ParseFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotJson(s) => write!(f, "cli output was not a machine envelope: {s}"),
            Self::UnsupportedSchema(v) => {
                write!(f, "cli emitted unsupported schema_version {v}")
            }
            Self::Malformed(e) => write!(f, "cli envelope malformed: {e}"),
        }
    }
}

impl std::error::Error for ParseFailure {}

/// Parse one CLI envelope. Exit code and stderr are provided by the caller
/// so the caller decides whether stderr matters (it only does when stdout
/// carries no envelope).
pub fn parse(stdout: &[u8]) -> Result<Envelope, ParseFailure> {
    if stdout.len() > MAX_STDOUT_BYTES {
        return Err(ParseFailure::NotJson(format!(
            "stdout exceeds {} bytes",
            MAX_STDOUT_BYTES
        )));
    }
    let text = String::from_utf8_lossy(stdout);
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Err(ParseFailure::NotJson("empty stdout".into()));
    }
    let value: Value =
        serde_json::from_str(trimmed).map_err(|e| ParseFailure::NotJson(e.to_string()))?;
    if !value.is_object() {
        return Err(ParseFailure::NotJson("top level is not an object".into()));
    }
    let version = value
        .get("schema_version")
        .and_then(Value::as_u64)
        .ok_or_else(|| ParseFailure::Malformed("missing schema_version".into()))?;
    if version != SUPPORTED_SCHEMA_MAJOR {
        return Err(ParseFailure::UnsupportedSchema(version));
    }
    serde_json::from_value(value).map_err(|e| ParseFailure::Malformed(e.to_string()))
}
