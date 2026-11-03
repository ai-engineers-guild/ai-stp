//! First-party configuration commands; serialized plans are never authority.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    error::{Failure, Result},
    installation::runtime,
};
use clap::ArgMatches;
use serde_json::Value;
use std::path::PathBuf;
#[derive(Clone, Copy)]
pub(super) enum Handler {
    Plan,
    Prepare,
    Apply,
    Status,
    Cancel,
    Confirm,
    RemovePlan,
    Effective,
    Pending,
}
impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::Plan | Self::RemovePlan => "plan",
            Self::Status | Self::Effective | Self::Pending => "read",
            _ => "apply",
        }
    }
}
const OPERATION: Parameter = Parameter {
    name: "operation",
    summary: "Exact original native configuration operation ID.",
    kind: ParameterType::String,
    required: true,
};
const DIGEST: Parameter = Parameter {
    name: "plan-digest",
    summary: "Digest of the complete reviewed native custody, publications and handoff plan.",
    kind: ParameterType::String,
    required: true,
};
pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["configuration", "effective"],
        summary: "Read current owned setup references and drift for one saved context without manufacturing runtime health.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "context",
                summary: "Saved context ID; omission uses the current selected preference for this read only.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Configuration(Handler::Effective),
    },
    Declaration {
        path: &["configuration", "pending"],
        summary: "Recover the original active native operation and digest after losing caller files or replies.",
        parameters: &[STATE_DIR],
        handler: super::Handler::Configuration(Handler::Pending),
    },
    Declaration {
        path: &["configuration", "plan"],
        summary: "Review an exact setup through the native engine and original saved context without changing harness files.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "context",
                summary: "Original saved context; omission resolves the selected preference for this new plan only.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "input",
                summary: "Closed native request JSON: schema_version, exact setup, harness_id, operation, explicit roots and optional placements, corporate_binding, trust, trust_pins and permissions.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Configuration(Handler::Plan),
    },
    Declaration {
        path: &["configuration", "prepare"],
        summary: "Prepare exact native desired bytes and original custody; publish no harness configuration.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "plan",
                summary: "The exact returned data.plan JSON, at most 8 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            DIGEST,
        ],
        handler: super::Handler::Configuration(Handler::Prepare),
    },
    Declaration {
        path: &["configuration", "apply"],
        summary: "Apply or replay the retained original native operation with fresh authority and consumer checks before every file effect.",
        parameters: &[STATE_DIR, OPERATION, DIGEST],
        handler: super::Handler::Configuration(Handler::Apply),
    },
    Declaration {
        path: &["configuration", "status"],
        summary: "Read original native state and custody receipts; changing the selected context cannot redirect this operation.",
        parameters: &[STATE_DIR, OPERATION, DIGEST],
        handler: super::Handler::Configuration(Handler::Status),
    },
    Declaration {
        path: &["configuration", "cancel"],
        summary: "Cancel or replay an exact unpublished native preparation, including after plan expiry and lost caller files.",
        parameters: &[STATE_DIR, OPERATION, DIGEST],
        handler: super::Handler::Configuration(Handler::Cancel),
    },
    Declaration {
        path: &["configuration", "confirm"],
        summary: "Confirm the exact installed setup from a genuine later selected-harness process using every original root.",
        parameters: &[STATE_DIR, OPERATION, DIGEST],
        handler: super::Handler::Configuration(Handler::Confirm),
    },
    Declaration {
        path: &["configuration", "remove", "plan"],
        summary: "Review removal of the effective setup owned by one original operation; preserve shared refs and unowned data.",
        parameters: &[STATE_DIR, OPERATION, DIGEST],
        handler: super::Handler::Configuration(Handler::RemovePlan),
    },
];
pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("required native path is absent"))
    };
    let text = |name: &str| {
        args.get_one::<String>(name)
            .map(String::as_str)
            .ok_or_else(|| Failure::input("required native argument is absent"))
    };
    let root = path("state-dir")?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    match handler {
        Handler::Effective => {
            runtime::effective(root, args.get_one::<String>("context").map(String::as_str))
        }
        Handler::Pending => runtime::pending(root),
        Handler::Plan => runtime::plan(
            root,
            args.get_one::<String>("context").map(String::as_str),
            path("input")?,
            &at,
        ),
        Handler::Prepare => runtime::prepare(root, path("plan")?, text("plan-digest")?, &at),
        Handler::Apply => runtime::apply(root, text("operation")?, text("plan-digest")?, &at),
        Handler::Status => runtime::status(root, text("operation")?, text("plan-digest")?),
        Handler::Cancel => runtime::cancel(root, text("operation")?, text("plan-digest")?, &at),
        Handler::Confirm => runtime::confirm(root, text("operation")?, text("plan-digest")?, &at),
        Handler::RemovePlan => {
            runtime::remove_plan(root, text("operation")?, text("plan-digest")?, &at)
        }
    }
}
