//! Read-only report command declarations and argument conversion.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    canonical,
    error::{Failure, Result},
    files,
    selection::impact,
    store::Store,
};
use clap::ArgMatches;
use serde_json::Value;
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Impact,
    Radius,
    Program,
    Eligibility,
    Matrix,
}

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["select", "eligibility-matrix"],
        summary: "Discover a bounded page of local candidates and assess each independently across explicit authenticated harness targets.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "request",
                summary: "Closed JSON up to 16 KiB: targets (one to seven distinct harness_id/scope/provider_version selectors), optional after, limit (1–50, default 10) and for_redistribution. No claimed authority fields.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Report(Handler::Matrix),
    },
    Declaration {
        path: &["select", "eligibility"],
        summary: "Assess an exact local graph using the current identity, platform, stored bytes and authenticated provider; no claimed rights are accepted.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "request",
                summary: "Closed JSON up to 256 KiB: harness_id, scope, exact provider_version, exact members and optional for_redistribution.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Report(Handler::Eligibility),
    },
    Declaration {
        path: &["program", "inspect"],
        summary: "Observe an explicit software prefix and unfinished stages without executing or trusting local records.",
        parameters: &[
            Parameter {
                name: "prefix",
                summary: "Absolute software prefix; its parent must exist. No state is created.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "entry-point",
                summary: "Exact relative bin/command name, including any platform suffix.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Report(Handler::Program),
    },
    Declaration {
        path: &["select", "impact"],
        summary: "Compare verified local setup context and capabilities in one read-only snapshot, without selecting or installing.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "setup-id",
                summary: "Exact candidate setup identifier.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "setup-version",
                summary: "Exact candidate X.Y version.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "against-setup-id",
                summary: "Optional explicit baseline setup identifier; requires its version.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "against-setup-version",
                summary: "Exact baseline X.Y version; requires its identifier.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "project-id",
                summary: "Optional local project for unambiguous installed or selected baseline attribution.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "tokenizer-profile",
                summary: "Local measurement profile; defaults to Unicode codepoints divided by four, not a model tokenizer.",
                kind: ParameterType::Choice(&[
                    "ai-stp:utf8-bytes/1",
                    "ai-stp:unicode-chars-div4/1",
                ]),
                required: false,
            },
            Parameter {
                name: "price-profile",
                summary: "Optional explicit price snapshot JSON, at most 64 KiB; no rates are fetched.",
                kind: ParameterType::Path,
                required: false,
            },
        ],
        handler: super::Handler::Report(Handler::Impact),
    },
    Declaration {
        path: &["select", "blast-radius"],
        summary: "Find exact local setup, project and current installation references without changing them.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "component-id",
                summary: "Exact component identifier.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "component-version",
                summary: "Exact immutable X.Y version.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "scenario",
                summary: "Report scenario; defaults to update. All scenarios are read-only.",
                kind: ParameterType::Choice(&[
                    "update",
                    "deprecation",
                    "blocked",
                    "expired_evidence",
                    "advisory",
                ]),
                required: false,
            },
        ],
        handler: super::Handler::Report(Handler::Radius),
    },
];

fn text<'a>(args: &'a ArgMatches, name: &str) -> Result<&'a str> {
    args.get_one::<String>(name)
        .map(String::as_str)
        .ok_or_else(|| Failure::input("a required report parameter is absent"))
}

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    match handler {
        Handler::Matrix => crate::selection::runtime::matrix::assess(
            args.get_one::<PathBuf>("state-dir")
                .ok_or_else(|| Failure::input("the explicit state parent is required"))?,
            args.get_one::<PathBuf>("request")
                .ok_or_else(|| Failure::input("the explicit matrix request is required"))?,
        ),
        Handler::Eligibility => crate::selection::runtime::assess(
            args.get_one::<PathBuf>("state-dir")
                .ok_or_else(|| Failure::input("the explicit state parent is required"))?,
            args.get_one::<PathBuf>("request")
                .ok_or_else(|| Failure::input("the explicit selection request is required"))?,
        ),
        Handler::Program => crate::program::inspect(
            args.get_one::<PathBuf>("prefix")
                .ok_or_else(|| Failure::input("the explicit program prefix is required"))?,
            text(args, "entry-point")?,
        ),
        Handler::Impact => {
            let baseline = match (
                args.get_one::<String>("against-setup-id"),
                args.get_one::<String>("against-setup-version"),
            ) {
                (Some(id), Some(version)) => Some((id.as_str(), version.as_str())),
                (None, None) => None,
                _ => {
                    return Err(Failure::input(
                        "baseline id and version must be supplied together",
                    ));
                }
            };
            let price = args
                .get_one::<PathBuf>("price-profile")
                .map(|path| canonical::parse(&files::read(path, 64 * 1024)?))
                .transpose()?;
            let request = impact::Request {
                setup_id: text(args, "setup-id")?,
                setup_version: text(args, "setup-version")?,
                baseline,
                project_id: args.get_one::<String>("project-id").map(String::as_str),
                estimator_profile: args
                    .get_one::<String>("tokenizer-profile")
                    .map_or("ai-stp:unicode-chars-div4/1", String::as_str),
                price_profile: price.as_ref(),
            };
            impact::report(
                &mut Store::planning(
                    args.get_one::<PathBuf>("state-dir").ok_or_else(|| {
                        Failure::input("the explicit state directory is required")
                    })?,
                )?,
                &request,
                &format!("{:.3}", jiff::Timestamp::now()),
            )
        }
        Handler::Radius => impact::radius::report(
            &mut Store::planning(
                args.get_one::<PathBuf>("state-dir")
                    .ok_or_else(|| Failure::input("the explicit state directory is required"))?,
            )?,
            text(args, "component-id")?,
            text(args, "component-version")?,
            args.get_one::<String>("scenario")
                .map_or("update", String::as_str),
            &format!("{:.3}", jiff::Timestamp::now()),
        ),
    }
}
