//! The native IPC reply, shared by Tauri and generated TypeScript.
use crate::{Continuation, Envelope};
use serde::Serialize;

/// Every IPC reply is a typed result — the frontend renders `ok` or the
/// structured error; it never receives raw stderr.
#[derive(Default, Serialize)]
#[cfg_attr(test, derive(ts_rs::TS))]
pub struct CmdResult {
    pub ok: bool,
    #[cfg_attr(test, ts(type = "unknown"))]
    pub data: Option<serde_json::Value>,
    pub warnings: Vec<String>,
    pub continuations: Vec<Continuation>,
    pub error: Option<String>,
    /// Stable machine code when the CLI produced one — the frontend keys
    /// on this, never on the message text.
    pub error_code: Option<String>,
    /// Contract fields the UI can route on: operation tracking
    /// and retry/disposition hints ride along unmodified.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub request_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub operation_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub error_retryable: Option<bool>,
    /// `error.details` verbatim — `details.options` is the contract's
    /// one-retry repair channel (cli-json.md) and losing it here would make
    /// the shell thinner than the contract allows.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    #[cfg_attr(test, ts(type = "unknown"))]
    pub error_details: Option<serde_json::Value>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    #[cfg_attr(test, ts(type = "unknown[]"))]
    pub next_actions: Vec<serde_json::Value>,
}

impl CmdResult {
    pub fn success(data: serde_json::Value) -> Self {
        Self {
            ok: true,
            data: Some(data),
            ..Self::default()
        }
    }

    pub fn from_envelope(env: Envelope) -> Self {
        Self {
            ok: env.ok,
            data: env.data,
            warnings: env.warnings,
            continuations: env.continuations,
            error: env
                .error
                .as_ref()
                .map(|e| format!("{}: {}", e.code, e.message)),
            error_code: env.error.as_ref().map(|e| e.code.clone()),
            request_id: env.request_id,
            operation_id: env.operation_id,
            error_retryable: env.error.as_ref().map(|e| e.retryable),
            error_details: env.error.and_then(|e| {
                let d = e.details;
                // `details` is a required wire field that defaults to `{}` —
                // an empty object is no detail at all, so render nothing.
                (!d.is_null() && !d.as_object().is_some_and(|o| o.is_empty())).then_some(d)
            }),
            next_actions: env.next_actions,
        }
    }
    pub fn failed(code: &str, msg: impl ToString) -> Self {
        Self {
            ok: false,
            data: None,
            warnings: Vec::new(),
            continuations: Vec::new(),
            error: Some(msg.to_string()),
            error_code: Some(code.into()),
            request_id: None,
            operation_id: None,
            error_retryable: None,
            error_details: None,
            next_actions: Vec::new(),
        }
    }
}
