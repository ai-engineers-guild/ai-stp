//! Authenticated provider observation commands, separate from installation.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    error::{Failure, Result},
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
}

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
        parameters: &[
            STATE_DIR,
            Parameter {
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
            },
            Parameter {
                name: "version",
                summary: "Exact canonical provider X.Y.Z version; no floating selector.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::Inspect),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let runtime = Runtime::observe()?;
    match handler {
        Handler::Network => Ok(runtime.report()),
        Handler::Inspect => {
            let parent = args
                .get_one::<PathBuf>("state-dir")
                .ok_or_else(|| Failure::input("the explicit state parent is required"))?;
            let harness = args
                .get_one::<String>("harness")
                .ok_or_else(|| Failure::input("the harness is required"))?;
            let version = args
                .get_one::<String>("version")
                .ok_or_else(|| Failure::input("the exact version is required"))?;
            let trust = trust::refresh(parent)?;
            let artifact = artifact::fetch(harness, version, runtime::platform()?, &trust)?;
            runtime.inspect(&artifact)
        }
    }
}
