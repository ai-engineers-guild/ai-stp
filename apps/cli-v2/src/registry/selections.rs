//! Selection session declarations; domain services own all state transitions.

use std::path::{Path, PathBuf};

use clap::ArgMatches;
use serde_json::Value;

use super::{Declaration, ID, Parameter, ParameterType, STATE_DIR};
use crate::{
    error::{Failure, Result},
    projection::Scope,
    selection::runtime::sessions,
};

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Propose,
    Confirm,
    Cancel,
    Apply,
    Show,
}

impl Handler {
    pub(super) fn mutability(self) -> &'static str {
        match self {
            Self::Apply => "apply",
            Self::Show => "read",
            _ => "plan",
        }
    }
}

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["select", "propose", "plan"],
        summary: "Plan an exact local component selection from observed provider and owned context; no proposal is written.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "project-id",
                summary: "Owned project passport whose current sole head is bound to the proposal.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "request",
                summary: "Eligibility request JSON with exact component roots, scope and provider_version; redistribution must be false.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "empty",
                summary: "Explicitly propose an empty setup; members must be empty and the provider must support this target.",
                kind: ParameterType::Boolean,
                required: false,
            },
        ],
        handler: super::Handler::Selection(Handler::Propose),
    },
    Declaration {
        path: &["select", "confirm", "plan"],
        summary: "Plan confirmation intent; apply rechecks the proposal snapshot before freezing one setup and selecting it as pending_install.",
        parameters: &[
            STATE_DIR,
            ID,
            Parameter {
                name: "scope",
                summary: "The same provider target scope used for the proposal.",
                kind: ParameterType::Choice(&["global", "user_root", "project"]),
                required: true,
            },
            Parameter {
                name: "provider-version",
                summary: "The exact provider X.Y.Z used for the proposal; a new effect authenticates it again.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Selection(Handler::Confirm),
    },
    Declaration {
        path: &["select", "cancel", "plan"],
        summary: "Plan cancellation of a retained proposal; a confirmed proposal cannot be cancelled.",
        parameters: &[STATE_DIR, ID],
        handler: super::Handler::Selection(Handler::Cancel),
    },
    Declaration {
        path: &["select", "apply"],
        summary: "Apply one exact selection plan, rechecking new effects and replaying retained outcomes offline without changing later selections.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Closed JSON plan from select propose/confirm/cancel plan, at most 2 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest of the selection plan, state parent and provider selector.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Selection(Handler::Apply),
    },
    Declaration {
        path: &["select", "show"],
        summary: "Read one retained proposal and its current open, expired, cancelled or confirmed state.",
        parameters: &[STATE_DIR, ID],
        handler: super::Handler::Selection(Handler::Show),
    },
];

fn path<'a>(args: &'a ArgMatches, name: &str) -> Result<&'a Path> {
    args.get_one::<PathBuf>(name)
        .map(PathBuf::as_path)
        .ok_or_else(|| Failure::input("the explicit selection path is required"))
}

fn text<'a>(args: &'a ArgMatches, name: &str) -> Result<&'a str> {
    args.get_one::<String>(name)
        .map(String::as_str)
        .ok_or_else(|| Failure::input("the selection parameter is required"))
}

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    match handler {
        Handler::Propose => sessions::propose(
            path(args, "state-dir")?,
            text(args, "project-id")?,
            path(args, "request")?,
            args.get_flag("empty"),
        ),
        Handler::Confirm => {
            let scope = match text(args, "scope")? {
                "global" => Scope::Global,
                "user_root" => Scope::UserRoot,
                "project" => Scope::Project,
                _ => return Err(Failure::input("the selection scope is invalid")),
            };
            sessions::decision(
                path(args, "state-dir")?,
                text(args, "id")?,
                Some((scope, text(args, "provider-version")?)),
            )
        }
        Handler::Cancel => sessions::decision(path(args, "state-dir")?, text(args, "id")?, None),
        Handler::Apply => sessions::apply(path(args, "plan")?, text(args, "plan-digest")?),
        Handler::Show => sessions::read(path(args, "state-dir")?, text(args, "id")?),
    }
}
