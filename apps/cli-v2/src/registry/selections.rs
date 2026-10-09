//! Selection session declarations; domain services own all state transitions.

use std::path::{Path, PathBuf};

use clap::ArgMatches;
use serde_json::Value;

use super::{Declaration, ID, Parameter, ParameterType, STATE_DIR};
use crate::{
    error::{Failure, Result},
    projection::Scope,
    selection::runtime::{bundles, sessions},
};

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Propose,
    Confirm,
    Cancel,
    Apply,
    Show,
    Session,
    BundlePlan,
    BundleApply,
}

impl Handler {
    pub(super) fn mutability(self) -> &'static str {
        match self {
            Self::Apply | Self::BundleApply => "apply",
            Self::Show | Self::Session => "read",
            _ => "plan",
        }
    }
}

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["select", "session"],
        summary: "Read a bounded page of open proposals and the recorded current selection for one project and harness, without network or credentials.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "project-id",
                summary: "Exact local project passport identifier.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "harness",
                summary: "Concrete harness whose session is read.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "after",
                summary: "Opaque next_after proposal identity from the preceding page; each page is a fresh observation.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "limit",
                summary: "Maximum open proposals, from 1 to 100; defaults to 20. Reduce when the page exceeds 4 MiB.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Selection(Handler::Session),
    },
    Declaration {
        path: &["select", "bundle", "plan"],
        summary: "Compile and plan one exact provider bundle with authenticated capabilities and observed contribution hosts; publish nothing.",
        parameters: &[
            STATE_DIR,
            ID,
            Parameter {
                name: "version",
                summary: "Exact immutable setup X.Y version.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "passport-digest",
                summary: "Exact canonical digest of the setup version passport.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "scope",
                summary: "Exact provider target scope for all component adaptations.",
                kind: ParameterType::Choice(&["global", "user_root", "project"]),
                required: true,
            },
            Parameter {
                name: "provider-version",
                summary: "Exact authenticated provider X.Y.Z.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "target",
                summary: "Existing absolute, unaliased provider target; required for configuration contributions. Read-only.",
                kind: ParameterType::Path,
                required: false,
            },
            Parameter {
                name: "output",
                summary: "Unused directory beneath an existing parent, outside the target; apply publishes bundle.zip here.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Selection(Handler::BundlePlan),
    },
    Declaration {
        path: &["select", "bundle", "apply"],
        summary: "Recompile the exact planned bundle and publish one new directory without overwriting an existing destination or writing the harness.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Closed JSON from select bundle plan, at most 16 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest binding source, provider, host identity, artifact and output.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Selection(Handler::BundleApply),
    },
    Declaration {
        path: &["select", "propose", "plan"],
        summary: "Plan an exact local component selection from observed provider and owned context; no proposal is written.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "project-id",
                summary: "Owned project passport whose current sole head is bound to the proposal.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "request",
                summary: "Eligibility request JSON with exact component roots, scope and provider_version; redistribution must be false.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "empty",
                summary: "Explicitly propose an empty setup; members must be empty and the provider must support this target.",
                kind: ParameterType::Boolean,
                required: false,
            },
        ],
        handler: super::Handler::Selection(Handler::Propose),
    },
    Declaration {
        path: &["select", "confirm", "plan"],
        summary: "Plan confirmation intent; apply rechecks the proposal snapshot before freezing one setup and selecting it as pending_install.",
        parameters: &[
            STATE_DIR,
            ID,
            Parameter {
                name: "scope",
                summary: "The same provider target scope used for the proposal.",
                kind: ParameterType::Choice(&["global", "user_root", "project"]),
                required: true,
            },
            Parameter {
                name: "provider-version",
                summary: "The exact provider X.Y.Z used for the proposal; a new effect authenticates it again.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Selection(Handler::Confirm),
    },
    Declaration {
        path: &["select", "cancel", "plan"],
        summary: "Plan cancellation of a retained proposal; a confirmed proposal cannot be cancelled.",
        parameters: &[STATE_DIR, ID],
        handler: super::Handler::Selection(Handler::Cancel),
    },
    Declaration {
        path: &["select", "apply"],
        summary: "Apply one exact selection plan, rechecking new effects and replaying retained outcomes offline without changing later selections.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Closed JSON plan from select propose/confirm/cancel plan, at most 2 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest of the selection plan, state parent and provider selector.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Selection(Handler::Apply),
    },
    Declaration {
        path: &["select", "show"],
        summary: "Read one retained proposal and its current open, expired, cancelled or confirmed state.",
        parameters: &[STATE_DIR, ID],
        handler: super::Handler::Selection(Handler::Show),
    },
];

fn path<'a>(args: &'a ArgMatches, name: &str) -> Result<&'a Path> {
    args.get_one::<PathBuf>(name)
        .map(PathBuf::as_path)
        .ok_or_else(|| Failure::input("the explicit selection path is required"))
}

fn text<'a>(args: &'a ArgMatches, name: &str) -> Result<&'a str> {
    args.get_one::<String>(name)
        .map(String::as_str)
        .ok_or_else(|| Failure::input("the selection parameter is required"))
}

fn scope(args: &ArgMatches) -> Result<Scope> {
    match text(args, "scope")? {
        "global" => Ok(Scope::Global),
        "user_root" => Ok(Scope::UserRoot),
        "project" => Ok(Scope::Project),
        _ => Err(Failure::input("the selection scope is invalid")),
    }
}

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    match handler {
        Handler::Session => {
            let limit = args
                .get_one::<String>("limit")
                .map(|s| s.parse::<usize>())
                .transpose()
                .map_err(|_| Failure::input("session limit must be an integer from 1 to 100"))?
                .unwrap_or(20);
            sessions::view(
                path(args, "state-dir")?,
                text(args, "project-id")?,
                text(args, "harness")?,
                args.get_one::<String>("after").map(String::as_str),
                limit,
            )
        }
        Handler::BundlePlan => bundles::plan(
            path(args, "state-dir")?,
            crate::authoring::setups::Source {
                stable_id: text(args, "id")?.into(),
                version: text(args, "version")?.into(),
                passport_digest: text(args, "passport-digest")?.into(),
            },
            scope(args)?,
            text(args, "provider-version")?,
            args.get_one::<PathBuf>("target").map(PathBuf::as_path),
            path(args, "output")?,
        ),
        Handler::BundleApply => bundles::apply(path(args, "plan")?, text(args, "plan-digest")?),
        Handler::Propose => sessions::propose(
            path(args, "state-dir")?,
            text(args, "project-id")?,
            path(args, "request")?,
            args.get_flag("empty"),
        ),
        Handler::Confirm => sessions::decision(
            path(args, "state-dir")?,
            text(args, "id")?,
            Some((scope(args)?, text(args, "provider-version")?)),
        ),
        Handler::Cancel => sessions::decision(path(args, "state-dir")?, text(args, "id")?, None),
        Handler::Apply => sessions::apply(path(args, "plan")?, text(args, "plan-digest")?),
        Handler::Show => sessions::read(path(args, "state-dir")?, text(args, "id")?),
    }
}
