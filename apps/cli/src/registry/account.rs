//! One explicit plan/apply boundary for isolated account session actions.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    account,
    error::{Failure, Result},
};
use clap::ArgMatches;
use serde_json::{Value, json};
use std::path::PathBuf;

pub(super) const CONNECTION: Parameter = Parameter {
    name: "connection",
    summary: "Exact retained connection ID; absence explicitly uses the legacy local-owner session.",
    kind: ParameterType::String,
    required: false,
};

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Plan,
    Apply,
    Status,
    Providers,
    ConnectionPlan,
    ConnectionApply,
    Connections,
    EnrollmentRecoveryPlan,
    EnrollmentRecoveryApply,
    EnrollmentRecoveries,
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
            Self::Plan | Self::ConnectionPlan | Self::EnrollmentRecoveryPlan => "plan",
            Self::Apply | Self::ConnectionApply | Self::EnrollmentRecoveryApply => "apply",
            Self::Status | Self::Providers | Self::Connections | Self::EnrollmentRecoveries => {
                "read"
            }
        }
    }
}

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["account", "connections", "recovery", "plan"],
        summary: "Plan a same-account replacement for one positively revoked enrollment; retain its local identity, original contexts and historical evidence.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "connection",
                summary: "Exact revoked retained connection ID.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "label",
                summary: "Label for the new independently owned replacement enrollment.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Account(Handler::EnrollmentRecoveryPlan),
    },
    Declaration {
        path: &["account", "connections", "recovery", "apply"],
        summary: "Admit or resume the reviewed registry-56 enrollment recovery and exact child key; sign in to its replacement connection to confirm the same account.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact reviewed enrollment recovery plan JSON, at most 128 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact reviewed enrollment recovery plan digest.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Account(Handler::EnrollmentRecoveryApply),
    },
    Declaration {
        path: &["account", "connections", "recovery", "list"],
        summary: "Read retained recovery plans, child-key progress and same-account authorization receipts without network access or credentials.",
        parameters: &[STATE_DIR],
        handler: super::Handler::Account(Handler::EnrollmentRecoveries),
    },
    Declaration {
        path: &["account", "connections", "plan"],
        summary: "Plan a retained server connection with its own enrollment key; review the registry format upgrade before applying.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "label",
                summary: "Local connection label, 1 to 120 UTF-8 bytes.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "api-url",
                summary: "Exact HTTPS server origin, or explicit loopback HTTP.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "provider",
                summary: "Sign-in provider; account providers reports the server's configured availability.",
                kind: ParameterType::Choice(account::providers::IDS),
                required: true,
            },
        ],
        handler: super::Handler::Account(Handler::ConnectionPlan),
    },
    Declaration {
        path: &["account", "connections", "apply"],
        summary: "Create or recover an exact retained connection and its native enrollment key, preserving the local identity and existing operations.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact connection plan JSON, at most 64 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact reviewed connection plan digest.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Account(Handler::ConnectionApply),
    },
    Declaration {
        path: &["account", "connections", "list"],
        summary: "List retained connection metadata without network access, tokens or an authentication claim.",
        parameters: &[STATE_DIR],
        handler: super::Handler::Account(Handler::Connections),
    },
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
            CONNECTION,
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
        parameters: &[STATE_DIR, CONNECTION],
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
        Handler::EnrollmentRecoveryPlan => {
            let plan = account::enrollment_recovery::plan(
                path("state-dir")?,
                args.get_one::<String>("connection")
                    .ok_or_else(|| Failure::input("revoked connection is absent"))?,
                args.get_one::<String>("label")
                    .ok_or_else(|| Failure::input("replacement connection label is absent"))?,
                &at,
            )?;
            Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::EnrollmentRecoveryApply => account::enrollment_recovery::apply(
            &account::enrollment_recovery::read_plan(path("plan")?)?,
            args.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("enrollment recovery digest is absent"))?,
            &at,
        ),
        Handler::EnrollmentRecoveries => account::enrollment_recovery::list(path("state-dir")?),
        Handler::ConnectionPlan => {
            let text = |name: &str| {
                args.get_one::<String>(name)
                    .map(String::as_str)
                    .ok_or_else(|| Failure::input("required connection argument is absent"))
            };
            let plan = account::connections::plan(
                path("state-dir")?,
                text("label")?,
                text("api-url")?,
                text("provider")?,
                &at,
            )?;
            Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::ConnectionApply => account::connections::apply(
            &account::connections::read_plan(path("plan")?)?,
            args.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("connection plan digest is absent"))?,
            &at,
        ),
        Handler::Connections => account::connections::list(path("state-dir")?),
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
            let plan = account::plan_for_connection(
                path("state-dir")?,
                action,
                args.get_one::<String>("api-url").map(String::as_str),
                args.get_one::<String>("provider").map(String::as_str),
                args.get_one::<String>("connection").map(String::as_str),
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
        Handler::Status => account::status_for_connection(
            path("state-dir")?,
            args.get_one::<String>("connection").map(String::as_str),
            &at,
        ),
        Handler::Providers => {
            account::providers::read(args.get_one::<String>("api-url").map(String::as_str))
        }
    }
}
