//! Complete remote grant management through one exact request plan.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    account::grants,
    error::{Failure, Result},
};
use clap::ArgMatches;
use serde_json::{Value, json};
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    List,
    Plan,
    Apply,
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::List => "read",
            Self::Plan => "plan",
            Self::Apply => "apply",
        }
    }
}

const API: Parameter = Parameter {
    name: "api-url",
    summary: "Explicit HTTPS or loopback account origin; defaults to the retained isolated account session.",
    kind: ParameterType::String,
    required: false,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["grant", "list"],
        summary: "Observe current invitations and owned or received grants through fresh same-device authentication, without caching authority or changing local objects.",
        parameters: &[STATE_DIR, API],
        handler: super::Handler::Grant(Handler::List),
    },
    Declaration {
        path: &["grant", "plan"],
        summary: "Bind an exact direct, invite, accept, revoke or revoke_invitation request to the isolated account session; preserve the original key and revision on retry.",
        parameters: &[
            STATE_DIR,
            API,
            Parameter {
                name: "request",
                summary: "Closed JSON action/body request; target_id identifies a grant/invitation and token_env names the acceptance token variable. Never put a token in the JSON body.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Grant(Handler::Plan),
    },
    Declaration {
        path: &["grant", "apply"],
        summary: "Execute one reviewed grant plan with the original idempotency key and preconditions; the API owns durable retry and current access state.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact JSON plan from grant plan, valid for fifteen minutes and the original account session.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest of the reviewed public grant plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Grant(Handler::Apply),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("required grant path is absent"))
    };
    let at = format!("{:.3}", jiff::Timestamp::now());
    match handler {
        Handler::List => grants::list(
            path("state-dir")?,
            args.get_one::<String>("api-url").map(String::as_str),
        ),
        Handler::Plan => {
            let plan = grants::plan(
                path("state-dir")?,
                args.get_one::<String>("api-url").map(String::as_str),
                path("request")?,
                &at,
            )?;
            Ok(json!({"plan_digest":plan.digest()?, "plan":plan}))
        }
        Handler::Apply => grants::apply(
            &grants::read_plan(path("plan")?)?,
            args.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("grant plan digest is absent"))?,
            &at,
        ),
    }
}
