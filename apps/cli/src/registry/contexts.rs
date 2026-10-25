//! Retained context records and revision-checked selection, without installation.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    account::contexts,
    error::{Failure, Result},
};
use clap::ArgMatches;
use serde_json::{Value, json};
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    CreatePlan,
    SelectPlan,
    Apply,
    List,
    Show,
    Organizations,
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::CreatePlan | Self::SelectPlan => "plan",
            Self::Apply => "apply",
            _ => "read",
        }
    }
}

const CONTEXT: Parameter = Parameter {
    name: "context",
    summary: "Exact retained context ID.",
    kind: ParameterType::String,
    required: true,
};
const LEGACY: Parameter = Parameter {
    name: "legacy-account",
    summary: "Explicitly use the existing local-owner account journal and key; do not copy credentials or create an enrollment.",
    kind: ParameterType::Boolean,
    required: false,
};
pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["context", "create", "plan"],
        summary: "Plan a local context or resolve an authenticated personal/corporate organization through an explicit connection; cached capabilities grant no authority.",
        parameters: &[
            STATE_DIR,
            LEGACY,
            Parameter {
                name: "label",
                summary: "Local label, 1 to 120 UTF-8 bytes.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "connection",
                summary: "Retained connection ID; without this or legacy-account, create a native offline context.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "organization",
                summary: "Authorized organization ID; a remote connection without this option resolves its personal organization.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Context(Handler::CreatePlan),
    },
    Declaration {
        path: &["context", "select", "plan"],
        summary: "Plan a revision-checked UI default change; no session, key, operation or harness file is moved.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Context(Handler::SelectPlan),
    },
    Declaration {
        path: &["context", "apply"],
        summary: "Apply or replay one exact context creation/selection plan in the shared authority registry.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact JSON context plan, at most 128 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the reviewed context plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Context(Handler::Apply),
    },
    Declaration {
        path: &["context", "list"],
        summary: "List local context observations and the selected preference without network access or installation authority.",
        parameters: &[STATE_DIR],
        handler: super::Handler::Context(Handler::List),
    },
    Declaration {
        path: &["context", "show"],
        summary: "Inspect one retained context; explicitly refresh organization membership/capabilities through its original connection.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "refresh",
                summary: "Read current organization membership and capability observations online; do not change the retained context.",
                kind: ParameterType::Boolean,
                required: false,
            },
        ],
        handler: super::Handler::Context(Handler::Show),
    },
    Declaration {
        path: &["account", "organizations"],
        summary: "Read organizations available to one authenticated retained connection; no implicit membership or installation changes.",
        parameters: &[
            STATE_DIR,
            LEGACY,
            Parameter {
                name: "connection",
                summary: "Exact retained connection ID.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Context(Handler::Organizations),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("required context path is absent"))
    };
    let text = |name: &str| {
        args.get_one::<String>(name)
            .map(String::as_str)
            .ok_or_else(|| Failure::input("required context argument is absent"))
    };
    let optional = |name: &str| args.get_one::<String>(name).map(String::as_str);
    let at = format!("{:.3}", jiff::Timestamp::now());
    match handler {
        Handler::CreatePlan => {
            let legacy = args.get_flag("legacy-account");
            if legacy && optional("connection").is_some() {
                return Err(Failure::input(
                    "choose a retained connection or the existing local-owner session",
                ));
            }
            let plan = if legacy {
                contexts::create_legacy_plan(
                    path("state-dir")?,
                    text("label")?,
                    optional("organization"),
                    &at,
                )?
            } else {
                contexts::create_plan(
                    path("state-dir")?,
                    text("label")?,
                    optional("connection"),
                    optional("organization"),
                    &at,
                )?
            };
            Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::SelectPlan => {
            let plan = contexts::select_plan(path("state-dir")?, text("context")?, &at)?;
            Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::Apply => contexts::apply(
            &contexts::read_plan(path("plan")?)?,
            text("plan-digest")?,
            &at,
        ),
        Handler::List => contexts::list(path("state-dir")?),
        Handler::Show => contexts::show(
            path("state-dir")?,
            text("context")?,
            args.get_flag("refresh"),
        ),
        Handler::Organizations => match (args.get_flag("legacy-account"), optional("connection")) {
            (true, None) => contexts::legacy_organizations(path("state-dir")?),
            (false, Some(connection)) => contexts::organizations(path("state-dir")?, connection),
            _ => Err(Failure::input(
                "choose exactly one of connection or legacy-account",
            )),
        },
    }
}
