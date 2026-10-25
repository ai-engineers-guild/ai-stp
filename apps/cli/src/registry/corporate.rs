//! Corporate reads bind a saved view once and return observations, not authority.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    account::corporate::{self, ObjectKind, Request},
    error::{Failure, Result},
};
use clap::ArgMatches;
use serde_json::Value;
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Teams,
    Projects,
    Project,
    LinkTarget,
    Technologies,
    Mappings,
    Mapping,
    Catalog,
    Preview,
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        if matches!(self, Self::Preview) {
            "plan"
        } else {
            "read"
        }
    }
}

const CONTEXT: Parameter = Parameter {
    name: "context",
    summary: "Exact saved corporate context; absence resolves the selected view once for this new read.",
    kind: ParameterType::String,
    required: false,
};
const QUERY: Parameter = Parameter {
    name: "query",
    summary: "Bounded server search text, at most 200 UTF-8 bytes.",
    kind: ParameterType::String,
    required: false,
};
const PROJECT: Parameter = Parameter {
    name: "project",
    summary: "Authorized corporate Project ID; visibility alone does not imply assignment membership.",
    kind: ParameterType::String,
    required: false,
};
const HARNESS: Parameter = Parameter {
    name: "harness",
    summary: "User-managed harness; the read never launches or installs it.",
    kind: ParameterType::Choice(&[
        "codex",
        "claude-code",
        "antigravity",
        "grok-build",
        "cursor",
        "opencode",
        "pi",
    ]),
    required: false,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["corporate", "teams"],
        summary: "Read authorized teams through the saved corporate context.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Corporate(Handler::Teams),
    },
    Declaration {
        path: &["corporate", "projects"],
        summary: "Read visible corporate projects, or only the authenticated person's explicit memberships.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "membership-only",
                summary: "Use the current account's project-membership route; do not infer membership from visibility.",
                kind: ParameterType::Boolean,
                required: false,
            },
        ],
        handler: super::Handler::Corporate(Handler::Projects),
    },
    Declaration {
        path: &["corporate", "project", "show"],
        summary: "Read one corporate project and its current source coordinates without linking a checkout.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                required: true,
                ..PROJECT
            },
        ],
        handler: super::Handler::Corporate(Handler::Project),
    },
    Declaration {
        path: &["corporate", "project", "link-target"],
        summary: "Read exact current project and provider revisions before a separate link plan; create no link or installation authority.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                required: true,
                ..PROJECT
            },
        ],
        handler: super::Handler::Corporate(Handler::LinkTarget),
    },
    Declaration {
        path: &["corporate", "technologies"],
        summary: "Read organization-owned technologies; bundled local seeds grant no corporate authority.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            QUERY,
            Parameter {
                name: "offset",
                summary: "Server page offset; defaults to zero, at most 1000000. Each page is bounded to 128.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Corporate(Handler::Technologies),
    },
    Declaration {
        path: &["corporate", "mappings", "list"],
        summary: "Read versioned organization technology-mapping summaries.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Corporate(Handler::Mappings),
    },
    Declaration {
        path: &["corporate", "mappings", "show"],
        summary: "Read one exact organization-owned technology mapping, without modifying project findings.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "version",
                summary: "Exact mapping version, never a local seed alias.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::Mapping),
    },
    Declaration {
        path: &["corporate", "catalog", "search"],
        summary: "Read a fresh authenticated organization-scoped catalog page; no cache or installed state is changed.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            QUERY,
            HARNESS,
            Parameter {
                name: "kind",
                summary: "Catalog object kind.",
                kind: ParameterType::Choice(&["component", "setup"]),
                required: true,
            },
            Parameter {
                name: "cursor",
                summary: "Opaque server cursor, at most 512 UTF-8 bytes.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Corporate(Handler::Catalog),
    },
    Declaration {
        path: &["corporate", "assignments", "preview"],
        summary: "Observe the current server assignment diff for an empty managed inventory; this is not an executable installation grant.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                required: true,
                ..HARNESS
            },
            PROJECT,
            Parameter {
                name: "technology",
                summary: "Optional organization technology ID.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Corporate(Handler::Preview),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let optional = |name: &str| args.get_one::<String>(name).cloned();
    let text = |name: &str| {
        optional(name)
            .ok_or_else(|| Failure::input("a required corporate read coordinate is absent"))
    };
    let request = match handler {
        Handler::Teams => Request::Teams,
        Handler::Projects => Request::Projects {
            membership_only: args.get_flag("membership-only"),
        },
        Handler::Project => Request::Project {
            project_id: text("project")?,
        },
        Handler::LinkTarget => Request::LinkTarget {
            project_id: text("project")?,
        },
        Handler::Technologies => Request::Technologies {
            query: optional("query"),
            offset: optional("offset")
                .map_or(Ok(0), |value| value.parse::<u32>())
                .map_err(|_| {
                    Failure::input("the technology page offset must be an unsigned integer")
                })?,
        },
        Handler::Mappings => Request::Mappings,
        Handler::Mapping => Request::Mapping {
            version: text("version")?,
        },
        Handler::Catalog => Request::Catalog {
            object_kind: match text("kind")?.as_str() {
                "component" => ObjectKind::Component,
                "setup" => ObjectKind::Setup,
                _ => return Err(Failure::input("invalid corporate catalog kind")),
            },
            query: optional("query"),
            harness: optional("harness"),
            cursor: optional("cursor"),
        },
        Handler::Preview => Request::AssignmentPreview {
            harness: text("harness")?,
            project_id: optional("project"),
            technology_id: optional("technology"),
        },
    };
    corporate::observe(
        args.get_one::<PathBuf>("state-dir")
            .ok_or_else(|| Failure::input("the native registry location is absent"))?,
        optional("context").as_deref(),
        request,
    )
}
