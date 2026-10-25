//! Explicit author evidence; an exact plan is required before signing.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    attestation,
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
}
impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::Plan => "plan",
            Self::Apply => "apply",
            Self::Status => "read",
        }
    }
}

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["attestation", "plan"],
        summary: "Plan an author's declared check evidence for one exact local component or setup; no check or harness is executed.",
        parameters: &[
            STATE_DIR,
            super::account::CONNECTION,
            Parameter {
                name: "request",
                summary: "Closed JSON with stable_id, version and evidence; at most 256 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "output",
                summary: "New private JSON file in an existing physical directory; never overwrite.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "api-url",
                summary: "Exact retained account origin; HTTPS or loopback only.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Attestation(Handler::Plan),
    },
    Declaration {
        path: &["attestation", "apply"],
        summary: "Sign the exact approved plan with the active device and export its retained record; completed replay only reads its receipt.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact JSON plan from attestation plan.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the reviewed attestation plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Attestation(Handler::Apply),
    },
    Declaration {
        path: &["attestation", "status"],
        summary: "Read exact retained author evidence without a session, network or new signature.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "operation-id",
                summary: "Exact original attestation operation identifier.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Attestation(Handler::Status),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("the required attestation path is absent"))
    };
    let text = |name: &str| {
        args.get_one::<String>(name)
            .map(String::as_str)
            .ok_or_else(|| Failure::input("the required attestation identifier is absent"))
    };
    let at = format!("{:.3}", jiff::Timestamp::now());
    match handler {
        Handler::Plan => {
            let plan = attestation::plan_for_connection(
                path("state-dir")?,
                args.get_one::<String>("api-url").map(String::as_str),
                args.get_one::<String>("connection").map(String::as_str),
                attestation::read_request(path("request")?)?,
                path("output")?,
                &at,
            )?;
            Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::Apply => attestation::apply(
            &attestation::read_plan(path("plan")?)?,
            text("plan-digest")?,
            &at,
        ),
        Handler::Status => attestation::status(path("state-dir")?, text("operation-id")?),
    }
}
