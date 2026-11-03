//! Explicit corporate inventory; no background or personal collection.
use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    account::inventory,
    error::{Failure, Result},
};
use clap::ArgMatches;
use serde_json::Value;
use std::path::PathBuf;
#[derive(Clone, Copy)]
pub(super) enum Handler {
    ConsentPlan,
    ConsentApply,
    Status,
    Disable,
    Scan,
    Flush,
}
impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::ConsentPlan => "plan",
            Self::Status => "read",
            _ => "apply",
        }
    }
}
const CONTEXT: Parameter = Parameter {
    name: "context",
    summary: "Exact original corporate context ID; never the selected personal view.",
    kind: ParameterType::String,
    required: true,
};
pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["corporate", "inventory", "consent", "plan"],
        summary: "Review explicit owned-inventory disclosure under the original company's fresh policy.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Inventory(Handler::ConsentPlan),
    },
    Declaration {
        path: &["corporate", "inventory", "consent", "apply"],
        summary: "Enable exactly reviewed foreground inventory consent; install no service or scheduler.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact consent plan JSON.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of reviewed disclosure, context and policy.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Inventory(Handler::ConsentApply),
    },
    Declaration {
        path: &["corporate", "inventory", "status"],
        summary: "Read local consent and pending original-batch status without network disclosure.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Inventory(Handler::Status),
    },
    Declaration {
        path: &["corporate", "inventory", "disable"],
        summary: "Disable original-context inventory and retire its unsent payload locally.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Inventory(Handler::Disable),
    },
    Declaration {
        path: &["corporate", "inventory", "scan"],
        summary: "Stage content-free observations of actual owned corporate refs under current consent and original link policy.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Inventory(Handler::Scan),
    },
    Declaration {
        path: &["corporate", "inventory", "flush"],
        summary: "Send or retry the exact original inventory batch; changed policy, link, account or receipt refuses.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Inventory(Handler::Flush),
    },
];
pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let path = |name: &str| {
        args.get_one::<PathBuf>(name)
            .map(PathBuf::as_path)
            .ok_or_else(|| Failure::input("inventory path is required"))
    };
    let text = |name: &str| {
        args.get_one::<String>(name)
            .map(String::as_str)
            .ok_or_else(|| Failure::input("inventory argument is required"))
    };
    let at = format!("{:.3}", jiff::Timestamp::now());
    match handler {
        Handler::ConsentPlan => inventory::consent_plan(path("state-dir")?, text("context")?, &at),
        Handler::ConsentApply => inventory::consent_apply(path("plan")?, text("plan-digest")?, &at),
        Handler::Status => inventory::status(path("state-dir")?, text("context")?),
        Handler::Disable => inventory::disable(path("state-dir")?, text("context")?),
        Handler::Scan => inventory::scan(path("state-dir")?, text("context")?, &at),
        Handler::Flush => inventory::flush(path("state-dir")?, text("context")?, &at),
    }
}
