//! Governed publication commands share the durable group engine.

use std::path::PathBuf;

use clap::ArgMatches;
use serde_json::{Value, json};

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    error::{Failure, Result},
    publication::runtime,
};

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Plan,
    Resume,
    Apply,
    Status,
    Reconcile,
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::Plan | Self::Resume => "plan",
            Self::Apply => "apply",
            Self::Status | Self::Reconcile => "read",
        }
    }
}

const API: Parameter = Parameter {
    name: "api-url",
    summary: "Exact retained account origin; HTTPS or loopback only.",
    kind: ParameterType::String,
    required: false,
};
const OPERATION: Parameter = Parameter {
    name: "operation-id",
    summary: "Original publication group identifier returned by planning, apply or status.",
    kind: ParameterType::String,
    required: true,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["publication", "plan"],
        summary: "Plan publication of one exact component or complete setup graph; private distribution by default.",
        parameters: &[
            STATE_DIR,
            API,
            Parameter {
                name: "request",
                summary: "Closed JSON request with stable_id, version, optional visibility, component_root and per-member evidence; at most 16 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Publication(Handler::Plan),
    },
    Declaration {
        path: &["publication", "resume", "plan"],
        summary: "Confirm the original unfinished publication intent with the current session and journal position; preserve all original request keys.",
        parameters: &[STATE_DIR, API, OPERATION],
        handler: super::Handler::Publication(Handler::Resume),
    },
    Declaration {
        path: &["publication", "apply"],
        summary: "Apply an exact publication plan, retaining partial progress; queued worker validation is not published completion.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact JSON plan from publication plan or publication resume plan.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the reviewed publication plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Publication(Handler::Apply),
    },
    Declaration {
        path: &["publication", "status"],
        summary: "Read local publication journal evidence without an account or network; omit operation-id to list unfinished groups.",
        parameters: &[
            STATE_DIR,
            Parameter {
                required: false,
                ..OPERATION
            },
        ],
        handler: super::Handler::Publication(Handler::Status),
    },
    Declaration {
        path: &["publication", "reconcile"],
        summary: "Read fresh remote evidence for a group interrupted by device replacement, without old-device writes or changing historical receipts.",
        parameters: &[STATE_DIR, API, OPERATION],
        handler: super::Handler::Publication(Handler::Reconcile),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("the required publication path is absent"))
    };
    let text = |name: &str| {
        args.get_one::<String>(name)
            .map(String::as_str)
            .ok_or_else(|| Failure::input("the required publication identifier is absent"))
    };
    let at = format!("{:.3}", jiff::Timestamp::now());
    if matches!(handler, Handler::Apply) {
        return runtime::apply(
            &runtime::read_plan(path("plan")?)?,
            text("plan-digest")?,
            &at,
        );
    }
    let root = path("state-dir")?;
    if matches!(handler, Handler::Status) {
        return runtime::status(
            root,
            args.get_one::<String>("operation-id").map(String::as_str),
        );
    }
    let origin = args.get_one::<String>("api-url").map(String::as_str);
    let plan = match handler {
        Handler::Plan => {
            runtime::plan(root, origin, runtime::read_request(path("request")?)?, &at)?
        }
        Handler::Resume => runtime::resume(root, origin, text("operation-id")?, &at)?,
        Handler::Reconcile => return runtime::reconcile(root, origin, text("operation-id")?),
        _ => return Err(Failure::input("invalid publication command")),
    };
    Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
}
