//! Corporate runtime usage from an owned native installation.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    account::usage,
    error::{Failure, Result},
    installation::planning::UsageSignal,
};
use clap::ArgMatches;
use serde_json::Value;
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    ConsentPlan,
    ConsentApply,
    Status,
    Disable,
    Record,
    Flush,
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::ConsentPlan => "plan",
            Self::Status => "read",
            _ => "apply",
        }
    }
}

const CONTEXT: Parameter = Parameter {
    name: "context",
    summary: "Exact original corporate context ID.",
    kind: ParameterType::String,
    required: true,
};
const OPERATION: Parameter = Parameter {
    name: "operation",
    summary: "Current completed native installation operation ID.",
    kind: ParameterType::String,
    required: true,
};
const COMPONENT: Parameter = Parameter {
    name: "component",
    summary: "Owned component stable ID to resolve against the installation receipt.",
    kind: ParameterType::String,
    required: true,
};
const SIGNAL: Parameter = Parameter {
    name: "signal-id",
    summary: "Opaque stable harness invocation ID for retry deduplication.",
    kind: ParameterType::String,
    required: true,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["corporate", "usage", "consent", "plan"],
        summary: "Review runtime usage collection under the original corporate policy.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Usage(Handler::ConsentPlan),
    },
    Declaration {
        path: &["corporate", "usage", "consent", "apply"],
        summary: "Enable the reviewed corporate runtime usage collection.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact consent plan JSON.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the reviewed plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Usage(Handler::ConsentApply),
    },
    Declaration {
        path: &["corporate", "usage", "status"],
        summary: "Show local runtime consent and pending delivery without network disclosure.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Usage(Handler::Status),
    },
    Declaration {
        path: &["corporate", "usage", "disable"],
        summary: "Stop local runtime usage collection and retire undelivered observations.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Usage(Handler::Disable),
    },
    Declaration {
        path: &["corporate", "usage", "record"],
        summary: "Queue a content-free agent-reported signal for an unchanged owned component.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            OPERATION,
            COMPONENT,
            SIGNAL,
            Parameter {
                name: "activity-kind",
                summary: "Observed activity.",
                kind: ParameterType::Choice(&["invocation", "load"]),
                required: true,
            },
            Parameter {
                name: "outcome",
                summary: "Observed outcome.",
                kind: ParameterType::Choice(&["succeeded", "failed", "cancelled"]),
                required: true,
            },
        ],
        handler: super::Handler::Usage(Handler::Record),
    },
    Declaration {
        path: &["corporate", "usage", "flush"],
        summary: "Send retained original usage events with exact receipt reconciliation.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Usage(Handler::Flush),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("usage path is required"))
    };
    let value = |name: &str| {
        args.get_one::<String>(name)
            .map(String::as_str)
            .ok_or_else(|| Failure::input("usage argument is required"))
    };
    let at = format!("{:.3}", jiff::Timestamp::now());
    match handler {
        Handler::ConsentPlan => usage::consent_plan(path("state-dir")?, value("context")?, &at),
        Handler::ConsentApply => usage::consent_apply(path("plan")?, value("plan-digest")?, &at),
        Handler::Status => usage::status(path("state-dir")?, value("context")?),
        Handler::Disable => usage::disable(path("state-dir")?, value("context")?),
        Handler::Record => usage::record(
            path("state-dir")?,
            value("context")?,
            &UsageSignal {
                operation: value("operation")?,
                component: value("component")?,
                signal_id: value("signal-id")?,
                activity_kind: value("activity-kind")?,
                outcome: value("outcome")?,
                at: &at,
            },
        ),
        Handler::Flush => usage::flush(path("state-dir")?, value("context")?),
    }
}
