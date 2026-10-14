use super::{Declaration, Parameter, ParameterType};
use crate::{
    distribution,
    error::{Failure, Result},
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
const PREFIX: Parameter = Parameter {
    name: "prefix",
    summary: "Dedicated native installation directory under an existing parent; package-manager, shared bin and desktop directories are refused.",
    kind: ParameterType::Path,
    required: true,
};
pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["cli", "install", "plan"],
        summary: "Plan installation or update of this verified archive executable into its own prefix; never download or change user state/PATH.",
        parameters: &[PREFIX],
        handler: super::Handler::Distribution(Handler::Plan),
    },
    Declaration {
        path: &["cli", "install", "status"],
        summary: "Read archive ownership, installed binary digest and any pending installation plan.",
        parameters: &[PREFIX],
        handler: super::Handler::Distribution(Handler::Status),
    },
    Declaration {
        path: &["cli", "install", "apply"],
        summary: "Apply or resume the exact installation plan using this archive binary; atomic replacement and readback, without database rollback or package-manager overwrite.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Public installation plan JSON, at most 64 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact reviewed installation plan digest.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Distribution(Handler::Apply),
    },
];
pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("installation path is required"))
    };
    match handler {
        Handler::Plan => distribution::plan(path("prefix")?),
        Handler::Status => distribution::status(path("prefix")?),
        Handler::Apply => distribution::apply(
            path("plan")?,
            args.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("installation digest is required"))?,
        ),
    }
}
