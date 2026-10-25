//! Existing selected-source outcomes over the isolated account API.

use super::{Declaration, Parameter, ParameterType, STATE_DIR, account::CONNECTION};
use crate::{
    account::github,
    error::{Failure, Result},
};
use clap::ArgMatches;
use serde_json::{Value, json};
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Status,
    Plan,
    Apply,
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::Status => "read",
            Self::Plan => "plan",
            Self::Apply => "apply",
        }
    }
}

const API: Parameter = Parameter {
    name: "api-url",
    summary: "Explicit HTTPS or loopback account origin; defaults to the retained isolated session.",
    kind: ParameterType::String,
    required: false,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["github", "status"],
        summary: "Read current selected GitHub repositories through the authenticated account API; no GitHub credential is accepted or stored by this command.",
        parameters: &[STATE_DIR, API, CONNECTION],
        handler: super::Handler::Github(Handler::Status),
    },
    Declaration {
        path: &["github", "source", "plan"],
        summary: "Bind one exact selected-repository snapshot request and its original idempotency key to the current isolated account session.",
        parameters: &[
            STATE_DIR,
            API,
            CONNECTION,
            Parameter {
                name: "request",
                summary: "Closed JSON installation_id, repository_id, full commit, canonical subpath and explicit idempotency_key. Preserve this exact request on retry.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Github(Handler::Plan),
    },
    Declaration {
        path: &["github", "source", "apply"],
        summary: "Prepare the exact reviewed source through the API; return its opaque publication binding. The server rechecks selected access and owns idempotent replay.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact JSON source plan, valid for fifteen minutes and the original session.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest of the reviewed source plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Github(Handler::Apply),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("required selected-source path is absent"))
    };
    let at = format!("{:.3}", jiff::Timestamp::now());
    match handler {
        Handler::Status => github::status_for_connection(
            path("state-dir")?,
            args.get_one::<String>("api-url").map(String::as_str),
            args.get_one::<String>("connection").map(String::as_str),
        ),
        Handler::Plan => {
            let plan = github::plan_for_connection(
                path("state-dir")?,
                args.get_one::<String>("api-url").map(String::as_str),
                args.get_one::<String>("connection").map(String::as_str),
                path("request")?,
                &at,
            )?;
            Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::Apply => github::apply(
            &github::read_plan(path("plan")?)?,
            args.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("source plan digest is absent"))?,
            &at,
        ),
    }
}
