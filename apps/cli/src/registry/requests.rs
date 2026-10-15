//! Thin adapters for the account reporter workflow.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    account::reports,
    error::{Failure, Result},
};
use clap::ArgMatches;
use serde_json::Value;
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Preview,
    Confirm,
    List,
    Status,
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::Preview => "plan",
            Self::Confirm => "apply",
            Self::List | Self::Status => "read",
        }
    }
}

const API: Parameter = Parameter {
    name: "api-url",
    summary: "Explicit HTTPS or loopback origin; defaults to the retained account session.",
    kind: ParameterType::String,
    required: false,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["report", "preview"],
        summary: "Retain an exact account-bound report preview without sending its contents; a reused caller key must have identical content.",
        parameters: &[
            STATE_DIR,
            API,
            Parameter {
                name: "request",
                summary: "Bounded closed report JSON with topic-specific fields and a 16–128 character idempotency_key. Diagnostics are explicit text only; schema_version and diagnostics_previewed are CLI-owned.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Request(Handler::Preview),
    },
    Declaration {
        path: &["report", "confirm"],
        summary: "Deliver the exact retained preview after explicit confirmation and account verification; repeat the original digest after a lost response.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "plan-id",
                summary: "Exact retained report preview ID.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by the reviewed preview.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "confirm",
                summary: "Approve sending only the exact previewed request to its account API.",
                kind: ParameterType::Boolean,
                required: false,
            },
        ],
        handler: super::Handler::Request(Handler::Confirm),
    },
    Declaration {
        path: &["report", "list"],
        summary: "Read one bounded page of the account's report cases and expose the next cursor explicitly.",
        parameters: &[
            STATE_DIR,
            API,
            Parameter {
                name: "cursor",
                summary: "Opaque next cursor returned by the preceding page, at most 512 characters.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Request(Handler::List),
    },
    Declaration {
        path: &["report", "status"],
        summary: "Read the current reporter-visible state of one exact account report case.",
        parameters: &[
            STATE_DIR,
            API,
            Parameter {
                name: "case-id",
                summary: "Exact report case ID.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Request(Handler::Status),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let root = args
        .get_one::<PathBuf>("state-dir")
        .ok_or_else(|| Failure::input("the explicit state parent is required"))?;
    let required = |name: &str| {
        args.get_one::<String>(name)
            .map(String::as_str)
            .ok_or_else(|| Failure::input("a required report argument is absent"))
    };
    match handler {
        Handler::Preview => reports::preview(
            root,
            args.get_one::<String>("api-url").map(String::as_str),
            args.get_one::<PathBuf>("request")
                .ok_or_else(|| Failure::input("the report request is absent"))?,
            &format!("{:.3}", jiff::Timestamp::now()),
        ),
        Handler::Confirm => reports::confirm(
            root,
            required("plan-id")?,
            required("plan-digest")?,
            args.get_flag("confirm"),
        ),
        Handler::List => reports::list(
            root,
            args.get_one::<String>("api-url").map(String::as_str),
            args.get_one::<String>("cursor").map(String::as_str),
        ),
        Handler::Status => reports::status(
            root,
            args.get_one::<String>("api-url").map(String::as_str),
            required("case-id")?,
        ),
    }
}
