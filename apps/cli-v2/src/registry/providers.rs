//! Authenticated provider observation commands, separate from installation.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    error::{Failure, Result},
    projection::Scope,
    provider::{
        artifact,
        runtime::{self, Runtime},
        trust,
    },
};
use clap::ArgMatches;
use serde_json::Value;
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Network,
    Inspect,
    Status,
}

const HARNESS: Parameter = Parameter {
    name: "harness",
    summary: "Canonical harness identifier.",
    kind: ParameterType::Choice(&[
        "claude-code",
        "codex",
        "pi",
        "opencode",
        "grok-build",
        "cursor",
        "antigravity",
    ]),
    required: true,
};
const VERSION: Parameter = Parameter {
    name: "version",
    summary: "Exact canonical provider X.Y.Z version; no floating selector.",
    kind: ParameterType::String,
    required: true,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["provider", "network"],
        summary: "Prove Linux IPv4, IPv6 and UDP network separation with a positive control.",
        parameters: &[],
        handler: super::Handler::Provider(Handler::Network),
    },
    Declaration {
        path: &["provider", "inspect"],
        summary: "Authenticate an exact provider artifact and observe provider-info under verified Linux isolation.",
        parameters: &[STATE_DIR, HARNESS, VERSION],
        handler: super::Handler::Provider(Handler::Inspect),
    },
    Declaration {
        path: &["provider", "status"],
        summary: "Observe an explicit target with an authenticated provider and a read-only isolated mount.",
        parameters: &[
            STATE_DIR,
            HARNESS,
            VERSION,
            Parameter {
                name: "target",
                summary: "Explicit existing absolute target directory; symbolic path components are refused.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "scope",
                summary: "Exact provider target scope; no scope is inferred.",
                kind: ParameterType::Choice(&["global", "user_root", "project"]),
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::Status),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let runtime = Runtime::observe()?;
    match handler {
        Handler::Network => Ok(runtime.report()),
        Handler::Inspect | Handler::Status => {
            let parent = args
                .get_one::<PathBuf>("state-dir")
                .ok_or_else(|| Failure::input("the explicit state parent is required"))?;
            let harness = args
                .get_one::<String>("harness")
                .ok_or_else(|| Failure::input("the harness is required"))?;
            let version = args
                .get_one::<String>("version")
                .ok_or_else(|| Failure::input("the exact version is required"))?;
            match handler {
                Handler::Inspect => {
                    let trust = trust::refresh(parent)?;
                    let artifact = artifact::fetch(harness, version, runtime::platform()?, &trust)?;
                    runtime.inspect(&artifact)
                }
                Handler::Status => {
                    let target = args
                        .get_one::<PathBuf>("target")
                        .ok_or_else(|| Failure::input("the explicit target is required"))?;
                    let scope = match args.get_one::<String>("scope").map(String::as_str) {
                        Some("global") => Scope::Global,
                        Some("user_root") => Scope::UserRoot,
                        Some("project") => Scope::Project,
                        _ => return Err(Failure::input("the target scope is required")),
                    };
                    runtime.status(parent, harness, version, target, scope)
                }
                Handler::Network => Err(Failure::input("the provider command is invalid")),
            }
        }
    }
}
