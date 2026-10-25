//! Existing visibility outcomes over the isolated account API.

use super::{Declaration, Parameter, ParameterType, STATE_DIR, account::CONNECTION};
use crate::{
    account::visibility,
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
        path: &["publication", "visibility", "status"],
        summary: "Read one historical visibility plan through the authenticated account API.",
        parameters: &[
            STATE_DIR,
            API,
            CONNECTION,
            Parameter {
                name: "plan-id",
                summary: "Exact server visibility plan ID; a historical result is not current distribution state.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Visibility(Handler::Status),
    },
    Declaration {
        path: &["publication", "visibility", "plan"],
        summary: "Create or recover one server visibility plan with the original caller idempotency key; bind its exact effect to the current isolated account session.",
        parameters: &[
            STATE_DIR,
            API,
            CONNECTION,
            Parameter {
                name: "request",
                summary: "Closed JSON object_kind, stable_id, version, visibility and idempotency_key. Preserve the exact request on retry.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Visibility(Handler::Plan),
    },
    Declaration {
        path: &["publication", "visibility", "apply"],
        summary: "Confirm the exact reviewed visibility effect after current authority and server-plan revalidation. Terminal results remain historical.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact JSON visibility plan, valid for fifteen minutes and the original session.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest of the reviewed visibility plan.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "confirm",
                summary: "Explicitly approve the exact distribution access change.",
                kind: ParameterType::Boolean,
                required: false,
            },
        ],
        handler: super::Handler::Visibility(Handler::Apply),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("required visibility path is absent"))
    };
    let at = format!("{:.3}", jiff::Timestamp::now());
    match handler {
        Handler::Status => visibility::status_for_connection(
            path("state-dir")?,
            args.get_one::<String>("api-url").map(String::as_str),
            args.get_one::<String>("connection").map(String::as_str),
            args.get_one::<String>("plan-id")
                .ok_or_else(|| Failure::input("visibility plan ID is absent"))?,
        ),
        Handler::Plan => {
            let plan = visibility::plan_for_connection(
                path("state-dir")?,
                args.get_one::<String>("api-url").map(String::as_str),
                args.get_one::<String>("connection").map(String::as_str),
                path("request")?,
                &at,
            )?;
            Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::Apply => visibility::apply(
            &visibility::read_plan(path("plan")?)?,
            args.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("visibility plan digest is absent"))?,
            args.get_flag("confirm"),
            &at,
        ),
    }
}
