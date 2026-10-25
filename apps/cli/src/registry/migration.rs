//! Explicit production transfer; ordinary commands never infer consent to migrate.

use super::{Declaration, Parameter, ParameterType};
use crate::{
    config,
    error::{Failure, Result},
    files, identity, migration,
};
use clap::ArgMatches;
use serde_json::Value;
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Plan,
    Apply,
    Status,
}
impl Handler {
    pub(super) fn mutability(self) -> &'static str {
        match self {
            Self::Plan => "plan",
            Self::Apply => "apply",
            Self::Status => "read",
        }
    }
}
const STATE: Parameter = Parameter {
    name: "state-dir",
    summary: "Existing production data directory containing owner.json, device.json and the schema-53 registry.sqlite.",
    kind: ParameterType::Path,
    required: true,
};
pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["state", "migrate", "plan"],
        summary: "Plan an in-place production writer transfer, preserving exact rows, owner, device key and session; refuse unfinished legacy work.",
        parameters: &[
            STATE,
            Parameter {
                name: "provider",
                summary: "Existing account sign-in provider; the previous session format does not store it.",
                kind: ParameterType::Choice(crate::account::providers::IDS),
                required: true,
            },
            Parameter {
                name: "credential-store",
                summary: "Existing credential backend; no discovery or fallback.",
                kind: ParameterType::Choice(&["os_keyring", "file"]),
                required: true,
            },
            Parameter {
                name: "api-url",
                summary: "Existing account API origin; defaults to the public service. No authentication request is made.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Migration(Handler::Plan),
    },
    Declaration {
        path: &["state", "migrate", "apply"],
        summary: "Transfer the exact planned registry in place and resume interrupted credential retirement; old Python writers refuse schema 54.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact retained production transfer plan JSON, at most 128 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact reviewed production transfer digest.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Migration(Handler::Apply),
    },
    Declaration {
        path: &["state", "migrate", "status"],
        summary: "Read the retained transfer plan or terminal receipt without credentials or a network request.",
        parameters: &[STATE],
        handler: super::Handler::Migration(Handler::Status),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("required production transfer path is absent"))
    };
    match handler {
        Handler::Plan => migration::plan(
            path("state-dir")?,
            match args
                .get_one::<String>("credential-store")
                .map(String::as_str)
            {
                Some("os_keyring") => identity::Storage::OsKeyring,
                Some("file") => identity::Storage::File,
                _ => return Err(Failure::input("credential backend is absent")),
            },
            args.get_one::<String>("api-url")
                .map_or(config::CATALOG_URL, String::as_str),
            args.get_one::<String>("provider")
                .ok_or_else(|| Failure::input("existing identity provider is absent"))?,
        ),
        Handler::Apply => migration::apply(
            &files::read(path("plan")?, 128 * 1024)?,
            args.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("production transfer digest is absent"))?,
        ),
        Handler::Status => migration::status(path("state-dir")?),
    }
}
