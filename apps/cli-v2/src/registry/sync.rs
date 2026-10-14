//! Parser declarations for exact private sync intents; the engine owns state.

use super::{CONFIG, Declaration, ID, Parameter, ParameterType, STATE_DIR};
use crate::{
    error::{Failure, Result},
    sync::runtime::{self, Request},
};
use clap::ArgMatches;
use serde_json::{Value, json};
use std::{collections::BTreeSet, path::PathBuf};

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Push,
    Pull,
    Apply,
}
impl Handler {
    pub fn mutability(self) -> &'static str {
        if matches!(self, Self::Apply) {
            "apply"
        } else {
            "plan"
        }
    }
}

const API: Parameter = Parameter {
    name: "api-url",
    summary: "Exact retained account origin; HTTPS or loopback only.",
    kind: ParameterType::String,
    required: false,
};
pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["sync", "push", "plan"],
        summary: "Capture one private head and its ancestors, immutable versions, deletion mark, or permitted device/consent summary without writing the registry.",
        parameters: &[STATE_DIR, API, CONFIG, ID],
        handler: super::Handler::Sync(Handler::Push),
    },
    Declaration {
        path: &["sync", "pull", "plan"],
        summary: "Plan one bounded private page from the current account cursor, with explicit durable event abandonments.",
        parameters: &[
            STATE_DIR,
            API,
            CONFIG,
            Parameter {
                name: "page-size",
                summary: "Page size from 1 to 100; defaults to 100.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "skip-event",
                summary: "Exact event id to abandon for this account; repeat only for individually reviewed events.",
                kind: ParameterType::Strings,
                required: false,
            },
        ],
        handler: super::Handler::Sync(Handler::Pull),
    },
    Declaration {
        path: &["sync", "apply"],
        summary: "Apply an exact private sync plan, retaining requests and atomic page receipts; completed operations replay locally after logout.",
        parameters: &[
            CONFIG,
            Parameter {
                name: "plan",
                summary: "Exact JSON plan from sync push plan or sync pull plan.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the reviewed private sync plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Sync(Handler::Apply),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |key: &str| {
        args.get_one::<PathBuf>(key)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("the required sync path is absent"))
    };
    let configuration = args.get_one::<PathBuf>("config").map(PathBuf::as_path);
    let at = format!("{:.3}", jiff::Timestamp::now());
    if matches!(handler, Handler::Apply) {
        return runtime::apply(
            &runtime::read_plan(path("plan")?)?,
            args.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("the sync plan digest is absent"))?,
            configuration,
            &at,
        );
    }
    let request = match handler {
        Handler::Push => Request::Push {
            id: args
                .get_one::<String>("id")
                .ok_or_else(|| Failure::input("the sync object id is absent"))?
                .clone(),
        },
        Handler::Pull => Request::Pull {
            page_size: args
                .get_one::<String>("page-size")
                .map_or(Ok(100), |v| v.parse::<u16>())
                .map_err(|_| {
                    Failure::input("the sync page size must be an integer from 1 to 100")
                })?,
            skip_event_ids: args
                .get_many::<String>("skip-event")
                .map(|v| v.cloned().collect::<BTreeSet<_>>())
                .unwrap_or_default(),
        },
        Handler::Apply => return Err(Failure::input("invalid sync command")),
    };
    let plan = runtime::plan(
        path("state-dir")?,
        args.get_one::<String>("api-url").map(String::as_str),
        configuration,
        request,
        &at,
    )?;
    Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
}
