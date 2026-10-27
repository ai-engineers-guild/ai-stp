//! Corporate reads bind a saved view once and return observations, not authority.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    account::{
        corporate::{self, ObjectKind, Request},
        project_links,
    },
    error::{Failure, Result},
};
use clap::ArgMatches;
use serde_json::{Value, json};
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Teams,
    Projects,
    Project,
    LinkTarget,
    LinkPreview,
    LinkCurrent,
    LinkOutcome,
    LinkSettlement,
    LinkRequestOutcome,
    UnlinkOutcome,
    UnlinkSettlement,
    UnlinkRequestOutcome,
    LinkRequestPlan,
    LinkConfirmPlan,
    LinkAdoptPlan,
    LinkRetirePlan,
    LinkRetireApply,
    LinkApply,
    LinkStatus,
    LinkList,
    LinkObservedOutcome,
    Technologies,
    Mappings,
    Mapping,
    Catalog,
    Preview,
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::Preview
            | Self::LinkPreview
            | Self::LinkRequestPlan
            | Self::LinkConfirmPlan
            | Self::LinkAdoptPlan => "plan",
            Self::LinkRetirePlan => "plan",
            Self::LinkApply | Self::LinkRetireApply => "apply",
            _ => "read",
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

const GIT: Parameter = Parameter {
    name: "git-executable",
    summary: "Existing trusted Git executable at an absolute path; no installation or update.",
    kind: ParameterType::Path,
    required: false,
};
const LINK_OPERATION: Parameter = Parameter {
    name: "operation",
    summary: "Exact retained native project-link operation ID.",
    kind: ParameterType::String,
    required: true,
};
const LINK_REQUEST: Parameter = Parameter {
    name: "request-operation",
    summary: "Original retained native link-request operation ID; its request key and actor are preserved.",
    kind: ParameterType::String,
    required: true,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["corporate", "project", "link-retire", "plan"],
        summary: "Review local retirement of an unknown request, or an unknown confirmation with exact expired settlement and no active binding.",
        parameters: &[
            STATE_DIR,
            LINK_OPERATION,
            Parameter {
                summary: "Exact same-account current reader for expired confirmation settlement; omit for offline local request retirement.",
                ..CONTEXT
            },
        ],
        handler: super::Handler::Corporate(Handler::LinkRetirePlan),
    },
    Declaration {
        path: &["corporate", "project", "link-retire", "apply"],
        summary: "Apply an exact reviewed retirement; retain unknown request outcome, release only settled unbound confirmation reservations, and never resend a remote write.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact reviewed native checkout retirement plan JSON, at most 256 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the exact reviewed native retirement plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::LinkRetireApply),
    },
    Declaration {
        path: &["corporate", "project", "link-request", "plan"],
        summary: "Review a durable original request for a server-authored link plan; create no link or installation authority.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            super::ROOT,
            Parameter {
                required: true,
                ..PROJECT
            },
            Parameter {
                name: "provider-project",
                summary: "Optional exact authorized provider_project ID; never inferred from Git URLs.",
                kind: ParameterType::String,
                required: false,
            },
            GIT,
        ],
        handler: super::Handler::Corporate(Handler::LinkRequestPlan),
    },
    Declaration {
        path: &["corporate", "project", "link-confirm", "plan"],
        summary: "Review confirmation of the original ready server plan through its original device and a freshly checked checkout.",
        parameters: &[STATE_DIR, LINK_REQUEST, GIT],
        handler: super::Handler::Corporate(Handler::LinkConfirmPlan),
    },
    Declaration {
        path: &["corporate", "project", "link-adopt", "plan"],
        summary: "Review local binding adoption from an exact active applied link and a fresh current context/checkout; grant no installation authority.",
        parameters: &[STATE_DIR, LINK_REQUEST, CONTEXT, super::ROOT, GIT],
        handler: super::Handler::Corporate(Handler::LinkAdoptPlan),
    },
    Declaration {
        path: &["corporate", "project", "link", "apply"],
        summary: "Apply one exact reviewed request/confirmation/binding intent or reconcile its original unknown outcome without repeating a write.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact reviewed native project-link plan JSON, at most 256 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the exact reviewed native plan.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                summary: "Explicit same-account replacement context only for reading an already admitted original outcome; never retarget a new write.",
                ..CONTEXT
            },
            GIT,
        ],
        handler: super::Handler::Corporate(Handler::LinkApply),
    },
    Declaration {
        path: &["corporate", "project", "link", "show"],
        summary: "Read an original native project-link intent and its retained progress without network access or checkout recreation.",
        parameters: &[STATE_DIR, LINK_OPERATION],
        handler: super::Handler::Corporate(Handler::LinkStatus),
    },
    Declaration {
        path: &["corporate", "project", "link", "list"],
        summary: "Page native project-link intents and receipts without querying accounts or changing contexts.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "cursor",
                summary: "Exact previous page cursor; an operation ID, not an account or organization selector.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "limit",
                summary: "Page size from 1 to 100; default 50.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Corporate(Handler::LinkList),
    },
    Declaration {
        path: &["corporate", "project", "link", "outcome"],
        summary: "Read the original account-owned request outcome through an explicit matching context; 404 remains unknown and no binding is adopted.",
        parameters: &[STATE_DIR, LINK_OPERATION, CONTEXT],
        handler: super::Handler::Corporate(Handler::LinkObservedOutcome),
    },
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
        path: &["corporate", "project", "link-preview"],
        summary: "Preview registered checkout and current corporate link coordinates without admitting a request, linking a project or granting installation authority.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            super::ROOT,
            Parameter {
                required: true,
                ..PROJECT
            },
            Parameter {
                name: "provider-project",
                summary: "Optional exact authorized provider_project ID; never inferred from Git URLs.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "git-executable",
                summary: "Existing trusted Git executable at an absolute path; no installation or update.",
                kind: ParameterType::Path,
                required: false,
            },
        ],
        handler: super::Handler::Corporate(Handler::LinkPreview),
    },
    Declaration {
        path: &["corporate", "project", "link-current"],
        summary: "Observe an exact current company link with project.unlink capability; no unlink or local binding retirement.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "link-id",
                summary: "Exact current server project_link identifier.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::LinkCurrent),
    },
    Declaration {
        path: &["corporate", "project", "link-outcome"],
        summary: "Read the original account-owned link plan outcome without retrying confirmation or binding a checkout.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "plan-id",
                summary: "Exact retained server link_plan identifier.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::LinkOutcome),
    },
    Declaration {
        path: &["corporate", "project", "link-settlement"],
        summary: "Read the original plan after its confirmation barrier; an observation alone never releases a local checkout reservation.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "plan-id",
                summary: "Exact retained server link_plan identifier.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::LinkSettlement),
    },
    Declaration {
        path: &["corporate", "project", "link-request-outcome"],
        summary: "Read an original account-owned link request outcome by its retained idempotency key; an absent result leaves in-flight effects unknown.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "request-key",
                summary: "Original link-plan request idempotency key, 16 to 128 ASCII letters, digits or ._~-.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::LinkRequestOutcome),
    },
    Declaration {
        path: &["corporate", "project", "unlink-outcome"],
        summary: "Read original account-owned unlink evidence without confirming or releasing a local binding.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "plan-id",
                summary: "Exact retained server unlink_plan identifier.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::UnlinkOutcome),
    },
    Declaration {
        path: &["corporate", "project", "unlink-settlement"],
        summary: "Observe the original unlink after its confirmation barrier; never release local ownership from this read.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "plan-id",
                summary: "Exact retained server unlink_plan identifier.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::UnlinkSettlement),
    },
    Declaration {
        path: &["corporate", "project", "unlink-request-outcome"],
        summary: "Read the original unlink request by its retained key; an absent result leaves the original effect unknown.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "request-key",
                summary: "Original unlink-plan request key, 16 to 128 ASCII letters, digits or ._~-.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::UnlinkRequestOutcome),
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
    let state = || {
        args.get_one::<PathBuf>("state-dir")
            .map(|p| p.as_path())
            .ok_or_else(|| Failure::input("state-dir is required"))
    };
    let checkout = || {
        args.get_one::<PathBuf>("root")
            .map(|p| p.as_path())
            .ok_or_else(|| Failure::input("root is required"))
    };
    let git = || {
        args.get_one::<PathBuf>("git-executable")
            .map(|p| p.as_path())
    };
    let output = |plan: project_links::Plan| -> Result<Value> {
        Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
    };
    let at = format!("{:.3}", jiff::Timestamp::now());
    match handler {
        Handler::LinkRetirePlan => {
            let plan = project_links::retirement::plan(
                state()?,
                &text("operation")?,
                optional("context").as_deref(),
                &at,
            )?;
            return Ok(json!({"plan_digest":plan.digest()?,"plan":plan}));
        }
        Handler::LinkRetireApply => {
            let plan = project_links::retirement::read_plan(
                args.get_one::<PathBuf>("plan")
                    .ok_or_else(|| Failure::input("plan is required"))?,
            )?;
            return project_links::retirement::apply(
                plan.state_parent(),
                &plan,
                &text("plan-digest")?,
                &at,
            );
        }
        Handler::LinkRequestPlan => {
            return output(project_links::request_plan(
                state()?,
                optional("context").as_deref(),
                checkout()?,
                &text("project")?,
                optional("provider-project").as_deref(),
                git(),
                &at,
            )?);
        }
        Handler::LinkConfirmPlan => {
            return output(project_links::confirmation_plan(
                state()?,
                &text("request-operation")?,
                git(),
                &at,
            )?);
        }
        Handler::LinkAdoptPlan => {
            return output(project_links::adoption_plan(
                state()?,
                &text("request-operation")?,
                optional("context").as_deref(),
                checkout()?,
                git(),
                &at,
            )?);
        }
        Handler::LinkApply => {
            let plan = project_links::read_plan(
                args.get_one::<PathBuf>("plan")
                    .ok_or_else(|| Failure::input("plan is required"))?,
            )?;
            return project_links::apply(
                plan.state_parent(),
                &plan,
                &text("plan-digest")?,
                optional("context").as_deref(),
                git(),
                &at,
            );
        }
        Handler::LinkStatus => return project_links::status(state()?, &text("operation")?),
        Handler::LinkList => {
            return project_links::list(
                state()?,
                optional("cursor").as_deref(),
                optional("limit")
                    .map_or(Ok(50), |value| value.parse::<u16>())
                    .map_err(|_| Failure::input("limit must be from 1 to 100"))?,
            );
        }
        Handler::LinkObservedOutcome => {
            return project_links::outcome(
                state()?,
                &text("operation")?,
                optional("context").as_deref(),
            );
        }
        _ => (),
    }
    if matches!(handler, Handler::LinkPreview) {
        return project_links::preview(
            args.get_one::<PathBuf>("state-dir")
                .ok_or_else(|| Failure::input("state-dir is required"))?,
            optional("context").as_deref(),
            args.get_one::<PathBuf>("root")
                .ok_or_else(|| Failure::input("root is required"))?,
            &text("project")?,
            optional("provider-project").as_deref(),
            args.get_one::<PathBuf>("git-executable")
                .map(|path| path.as_path()),
        );
    }
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
        Handler::LinkCurrent => Request::LinkCurrent {
            link_id: text("link-id")?,
        },
        Handler::LinkOutcome => Request::LinkOutcome {
            plan_id: text("plan-id")?,
        },
        Handler::LinkSettlement => Request::LinkSettlement {
            plan_id: text("plan-id")?,
        },
        Handler::LinkRequestOutcome => Request::LinkRequestOutcome {
            request_key: text("request-key")?,
        },
        Handler::UnlinkOutcome => Request::UnlinkOutcome {
            plan_id: text("plan-id")?,
        },
        Handler::UnlinkSettlement => Request::UnlinkSettlement {
            plan_id: text("plan-id")?,
        },
        Handler::UnlinkRequestOutcome => Request::UnlinkRequestOutcome {
            request_key: text("request-key")?,
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
        Handler::LinkPreview
        | Handler::LinkRequestPlan
        | Handler::LinkConfirmPlan
        | Handler::LinkAdoptPlan
        | Handler::LinkRetirePlan
        | Handler::LinkRetireApply
        | Handler::LinkApply
        | Handler::LinkStatus
        | Handler::LinkList
        | Handler::LinkObservedOutcome => {
            return Err(Failure::input("link coordinates are absent"));
        }
    };
    corporate::observe(
        args.get_one::<PathBuf>("state-dir")
            .ok_or_else(|| Failure::input("the native registry location is absent"))?,
        optional("context").as_deref(),
        request,
    )
}
