//! One explicit plan/apply boundary for isolated account session actions.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    account,
    error::{Failure, Result},
};
use clap::ArgMatches;
use serde_json::{Value, json};
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Plan,
    Apply,
    Status,
    Providers,
}

pub(super) fn warnings(result: &Result<Value>) -> Vec<String> {
    result
        .as_ref()
        .ok()
        .and_then(|data| data["warnings"].as_array())
        .map_or_else(Vec::new, |items| {
            items
                .iter()
                .filter_map(|v| v.as_str())
                .filter(|v| *v == "remote_logout_unconfirmed")
                .map(str::to_owned)
                .collect()
        })
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::Plan => "plan",
            Self::Apply => "apply",
            Self::Status | Self::Providers => "read",
        }
    }
}

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["account", "providers"],
        summary: "Read the sign-in providers enabled by the chosen server; no credentials, browser flow or local writes.",
        parameters: &[Parameter {
            name: "api-url",
            summary: "HTTPS account API origin, or explicit loopback HTTP; defaults to the public service.",
            kind: ParameterType::String,
            required: false,
        }],
        handler: super::Handler::Account(Handler::Providers),
    },
    Declaration {
        path: &["account", "plan"],
        summary: "Plan a session action, owner attachment or revoked-key recovery against the exact isolated account revision and device key.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "action",
                summary: "One bounded account operation; poll honors its durable minimum interval.",
                kind: ParameterType::Choice(&[
                    "start", "poll", "refresh", "logout", "attach", "recover",
                ]),
                required: true,
            },
            Parameter {
                name: "api-url",
                summary: "HTTPS account API origin, or explicit loopback HTTP; defaults to the retained session origin or the public service.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "provider",
                summary: "Sign-in provider; use account providers to discover this server's enabled choices. Defaults to the retained provider or GitHub.",
                kind: ParameterType::Choice(account::providers::IDS),
                required: false,
            },
        ],
        handler: super::Handler::Account(Handler::Plan),
    },
    Declaration {
        path: &["account", "apply"],
        summary: "Apply or recover one exact account intent; secrets stay in the selected credential store. Read account status for a pending browser code.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact JSON plan returned by account plan or pending_operation in account status.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact public account plan digest.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Account(Handler::Apply),
    },
    Declaration {
        path: &["account", "status"],
        summary: "Read cached isolated authorization and any unfinished intent without network access, owner transfer or a claim of live authentication.",
        parameters: &[STATE_DIR],
        handler: super::Handler::Account(Handler::Status),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let at = format!("{:.3}", jiff::Timestamp::now());
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("required account path is absent"))
    };
    match handler {
        Handler::Plan => {
            let action = match args.get_one::<String>("action").map(String::as_str) {
                Some("start") => account::Action::Start,
                Some("poll") => account::Action::Poll,
                Some("refresh") => account::Action::Refresh,
                Some("logout") => account::Action::Logout,
                Some("attach") => account::Action::Attach,
                Some("recover") => account::Action::Recover,
                _ => return Err(Failure::input("account action is absent")),
            };
            let plan = account::plan(
                path("state-dir")?,
                action,
                args.get_one::<String>("api-url").map(String::as_str),
                args.get_one::<String>("provider").map(String::as_str),
                &at,
            )?;
            Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::Apply => account::apply(
            &account::read_plan(path("plan")?)?,
            args.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("account plan digest is absent"))?,
            &at,
        ),
        Handler::Status => account::status(path("state-dir")?, &at),
        Handler::Providers => {
            account::providers::read(args.get_one::<String>("api-url").map(String::as_str))
        }
    }
}
