//! Corporate reads bind a saved view once and return observations, not authority.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    account::{
        corporate::{self, ObjectKind, Request},
        heartbeats, project_links, project_unlinks,
    },
    error::{Failure, Result},
};
use clap::ArgMatches;
use serde_json::{Value, json};
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Teams,
    HeartbeatPolicy,
    HeartbeatStatus,
    HeartbeatConsentPlan,
    HeartbeatConsentApply,
    HeartbeatDelivery,
    HeartbeatFlush,
    HeartbeatDisable,
    HeartbeatMaintain,
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
    UnlinkRequestPlan,
    UnlinkConfirmPlan,
    UnlinkApply,
    UnlinkStatus,
    UnlinkList,
    UnlinkObservedOutcome,
    UnlinkRetirePlan,
    UnlinkRetireApply,
    BindingRetirePlan,
    BindingRetireApply,
    MissingBindingRetirePlan,
    MissingBindingRetireApply,
    MissingBindingRetireStatus,
    LocationAnchorPlan,
    LocationRelocatePlan,
    LocationApply,
    LocationStatus,
    LocationList,
    Technologies,
    Mappings,
    Mapping,
    Catalog,
    Preview,
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::HeartbeatConsentPlan
            | Self::Preview
            | Self::LinkPreview
            | Self::LinkRequestPlan
            | Self::LinkConfirmPlan
            | Self::LinkAdoptPlan
            | Self::UnlinkRequestPlan
            | Self::UnlinkConfirmPlan
            | Self::UnlinkRetirePlan => "plan",
            Self::LinkRetirePlan
            | Self::BindingRetirePlan
            | Self::MissingBindingRetirePlan
            | Self::LocationAnchorPlan
            | Self::LocationRelocatePlan => "plan",
            Self::HeartbeatConsentApply
            | Self::HeartbeatFlush
            | Self::HeartbeatDisable
            | Self::HeartbeatMaintain
            | Self::LinkApply
            | Self::LinkRetireApply
            | Self::UnlinkApply
            | Self::UnlinkRetireApply
            | Self::BindingRetireApply
            | Self::MissingBindingRetireApply
            | Self::LocationApply => "apply",
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
const HEARTBEAT_CONTEXT: Parameter = Parameter {
    name: "context",
    summary: "Exact original saved corporate context; never use an ambient selected view for delivery.",
    kind: ParameterType::String,
    required: true,
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
        path: &["corporate", "project", "location", "show"],
        summary: "Read one immutable completed location receipt offline, without opening a checkout or consulting a future binding.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "operation",
                summary: "Exact retained completed location operation ID.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::LocationStatus),
    },
    Declaration {
        path: &["corporate", "project", "location", "list"],
        summary: "Page one original adoption's completed location history offline; historical receipts do not grant current installation authority.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "binding-operation",
                summary: "Exact original native adoption operation ID, including a retired binding.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "cursor",
                summary: "Optional next_cursor from the preceding page of this same binding's history.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Corporate(Handler::LocationList),
    },
    Declaration {
        path: &["corporate", "project", "location-anchor", "plan"],
        summary: "Review full physical identity at the present registered checkout using current original-company authority; keep original receipts, files and tasks.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            GIT,
            Parameter {
                name: "binding-operation",
                summary: "Exact completed native adoption operation ID; the current registered directory must be present.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::LocationAnchorPlan),
    },
    Declaration {
        path: &["corporate", "project", "location-relocate", "plan"],
        summary: "Review a manually moved checkout against its trusted full-identity anchor, unchanged embedded Git topology and fresh original-company authority; require an absent previous path and no conflicting work.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            GIT,
            Parameter {
                name: "binding-operation",
                summary: "Exact original completed native adoption operation ID; a reviewed location anchor is required.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "root",
                summary: "Present destination of the same physical checkout; no directory is created or repaired.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::LocationRelocatePlan),
    },
    Declaration {
        path: &["corporate", "project", "location", "apply"],
        summary: "Revalidate an exact reviewed anchor or same-object move and commit only its terminal receipt/private location metadata; completed replay is offline history.",
        parameters: &[
            GIT,
            Parameter {
                name: "plan",
                summary: "Exact reviewed location JSON plan, at most 256 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of this exact reviewed location operation.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::LocationApply),
    },
    Declaration {
        path: &["corporate", "project", "binding-retire", "plan"],
        summary: "Review local retirement of one active checkout binding using fresh current authority and exact terminal unlinked evidence; retain original receipts, files and tasks.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "binding-operation",
                summary: "Exact retained completed native adoption operation ID; the original checkout must be physically present.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::BindingRetirePlan),
    },
    Declaration {
        path: &["corporate", "project", "binding-retire", "apply"],
        summary: "Revalidate exact fresh unlinked evidence and atomically retire only the reviewed local binding/reservation; keep immutable adoption evidence and future bindings.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact reviewed binding-retirement JSON plan, at most 256 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the exact reviewed local binding retirement.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::BindingRetireApply),
    },
    Declaration {
        path: &["corporate", "project", "binding-retire-missing", "plan"],
        summary: "Review an absent checkout under its exact physical parent and a positively unlinked original server result; retain history, files and tasks.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "binding-operation",
                summary: "Exact completed adoption operation ID; its current retained checkout name must be absent under an inspectable parent.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::MissingBindingRetirePlan),
    },
    Declaration {
        path: &["corporate", "project", "binding-retire-missing", "apply"],
        summary: "Revalidate the reviewed absence and current project.link authority; atomically release only that local binding without remote writes or file cleanup.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact reviewed missing-checkout retirement JSON plan, at most 256 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the exact reviewed missing-checkout retirement.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::MissingBindingRetireApply),
    },
    Declaration {
        path: &["corporate", "project", "binding-retire-missing", "show"],
        summary: "Read the original missing-checkout retirement receipt offline without reopening a checkout or changing a later binding.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "operation",
                summary: "Exact missing-checkout retirement operation ID.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::MissingBindingRetireStatus),
    },
    Declaration {
        path: &["corporate", "project", "unlink-retire", "plan"],
        summary: "Review local closure of an unknown unlink request, or a confirmation with fresh exact expired/unapplied settlement; keep the active checkout binding.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "operation",
                summary: "Exact retained pending native unlink operation ID.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                summary: "Current same-account reader for confirmation settlement; omit for offline unknown request closure.",
                ..CONTEXT
            },
        ],
        handler: super::Handler::Corporate(Handler::UnlinkRetirePlan),
    },
    Declaration {
        path: &["corporate", "project", "unlink-retire", "apply"],
        summary: "Close only the exact reviewed pending unlink intent, rechecking confirmation expiry on the server; retain binding and reservation, and never resend a remote write.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact reviewed local unlink-retirement plan JSON, at most 256 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the exact reviewed unlink-retirement plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::UnlinkRetireApply),
    },
    Declaration {
        path: &["corporate", "project", "unlink-request", "plan"],
        summary: "Review an original server unlink-plan request for one retained active checkout binding; release no local binding or installation authority.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "binding-operation",
                summary: "Exact completed native link-adoption operation ID for this active physical checkout.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::UnlinkRequestPlan),
    },
    Declaration {
        path: &["corporate", "project", "unlink-confirm", "plan"],
        summary: "Review the original ready unlink decision under its unchanged device, current context and active physical binding.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "request-operation",
                summary: "Original retained native unlink-request operation ID; its actor and original request key remain fixed.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::UnlinkConfirmPlan),
    },
    Declaration {
        path: &["corporate", "project", "unlink", "apply"],
        summary: "Apply one reviewed unlink intent, or read its admitted original result; never resend an uncertain write or retire its local binding.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Exact reviewed native unlink plan JSON, at most 256 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Digest of the exact reviewed unlink plan.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                summary: "Same-account current reader only for an already admitted original outcome; unused plans retain their reviewed context.",
                ..CONTEXT
            },
        ],
        handler: super::Handler::Corporate(Handler::UnlinkApply),
    },
    Declaration {
        path: &["corporate", "project", "unlink", "show"],
        summary: "Read the retained native unlink intent and receipt offline without reopening its checkout or reauthorizing a write.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "operation",
                summary: "Exact retained native unlink operation ID.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::UnlinkStatus),
    },
    Declaration {
        path: &["corporate", "project", "unlink", "list"],
        summary: "Page retained native unlink intents and receipts without network access or context switching.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "cursor",
                summary: "Exact previous page cursor: a native operation ID.",
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
        handler: super::Handler::Corporate(Handler::UnlinkList),
    },
    Declaration {
        path: &["corporate", "project", "unlink", "outcome"],
        summary: "Observe the original unlink plan through a matching current reader; missing outcomes remain unknown and local reservations remain held.",
        parameters: &[
            STATE_DIR,
            CONTEXT,
            Parameter {
                name: "operation",
                summary: "Exact retained native unlink operation ID.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::UnlinkObservedOutcome),
    },
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
        path: &["corporate", "heartbeat", "policy"],
        summary: "Read the current corporate heartbeat policy and its version; this does not opt in or send telemetry.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Corporate(Handler::HeartbeatPolicy),
    },
    Declaration {
        path: &["corporate", "heartbeat", "status"],
        summary: "Read only the original context's enrolled device heartbeat; no inventory, invocation or reporting consent is inferred.",
        parameters: &[STATE_DIR, CONTEXT],
        handler: super::Handler::Corporate(Handler::HeartbeatStatus),
    },
    Declaration {
        path: &["corporate", "heartbeat", "consent", "plan"],
        summary: "Review explicit local consent for content-free foreground device liveness under the current company policy; sends no report.",
        parameters: &[STATE_DIR, HEARTBEAT_CONTEXT],
        handler: super::Handler::Corporate(Handler::HeartbeatConsentPlan),
    },
    Declaration {
        path: &["corporate", "heartbeat", "consent", "apply"],
        summary: "Enable only the exact reviewed context/policy; no service or startup entry is installed.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Original reviewed consent plan JSON file.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact reviewed plan digest.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Corporate(Handler::HeartbeatConsentApply),
    },
    Declaration {
        path: &["corporate", "heartbeat", "delivery"],
        summary: "Read local consent, pacing and original outbox status without network access or payload disclosure.",
        parameters: &[STATE_DIR, HEARTBEAT_CONTEXT],
        handler: super::Handler::Corporate(Handler::HeartbeatDelivery),
    },
    Declaration {
        path: &["corporate", "heartbeat", "flush"],
        summary: "When explicitly enabled and due, observe or retry one original signed device heartbeat in this foreground process.",
        parameters: &[STATE_DIR, HEARTBEAT_CONTEXT],
        handler: super::Handler::Corporate(Handler::HeartbeatFlush),
    },
    Declaration {
        path: &["corporate", "heartbeat", "disable"],
        summary: "Disable local consent and retire only this context's queued payload, including after logout/offline.",
        parameters: &[STATE_DIR, HEARTBEAT_CONTEXT],
        handler: super::Handler::Corporate(Handler::HeartbeatDisable),
    },
    Declaration {
        path: &["corporate", "heartbeat", "maintain"],
        summary: "Locally retire expired owned heartbeat payloads at foreground startup; sends no network requests.",
        parameters: &[STATE_DIR],
        handler: super::Handler::Corporate(Handler::HeartbeatMaintain),
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
        Handler::HeartbeatConsentPlan => {
            return heartbeats::consent_plan(state()?, &text("context")?, &at);
        }
        Handler::HeartbeatConsentApply => {
            let plan = heartbeats::read_plan(
                args.get_one::<PathBuf>("plan")
                    .ok_or_else(|| Failure::input("plan is required"))?,
            )?;
            return heartbeats::consent_apply(&plan, &text("plan-digest")?, &at);
        }
        Handler::HeartbeatDelivery => return heartbeats::status(state()?, &text("context")?),
        Handler::HeartbeatFlush => return heartbeats::flush(state()?, &text("context")?),
        Handler::HeartbeatDisable => return heartbeats::disable(state()?, &text("context")?),
        Handler::HeartbeatMaintain => return heartbeats::maintain(state()?),
        Handler::LocationStatus => {
            return project_links::location::status(state()?, &text("operation")?);
        }
        Handler::LocationList => {
            return project_links::location::list(
                state()?,
                &text("binding-operation")?,
                optional("cursor").as_deref(),
            );
        }
        Handler::LocationAnchorPlan | Handler::LocationRelocatePlan => {
            let binding = text("binding-operation")?;
            let plan = if matches!(handler, Handler::LocationAnchorPlan) {
                project_links::location::anchor_plan(
                    state()?,
                    optional("context").as_deref(),
                    &binding,
                    git(),
                    &at,
                )?
            } else {
                project_links::location::relocation_plan(
                    state()?,
                    optional("context").as_deref(),
                    &binding,
                    checkout()?,
                    git(),
                    &at,
                )?
            };
            return Ok(json!({"plan_digest":plan.digest()?,"plan":plan}));
        }
        Handler::LocationApply => {
            let plan = project_links::location::read_plan(
                args.get_one::<PathBuf>("plan")
                    .ok_or_else(|| Failure::input("plan is required"))?,
            )?;
            return project_links::location::apply(
                plan.state_parent(),
                &plan,
                &text("plan-digest")?,
                git(),
                &at,
            );
        }
        Handler::BindingRetirePlan => {
            let plan = project_unlinks::binding_retirement::plan(
                state()?,
                optional("context").as_deref(),
                &text("binding-operation")?,
                &at,
            )?;
            return Ok(json!({"plan_digest":plan.digest()?,"plan":plan}));
        }
        Handler::BindingRetireApply => {
            let plan = project_unlinks::binding_retirement::read_plan(
                args.get_one::<PathBuf>("plan")
                    .ok_or_else(|| Failure::input("plan is required"))?,
            )?;
            return project_unlinks::binding_retirement::apply(
                plan.state_parent(),
                &plan,
                &text("plan-digest")?,
                &at,
            );
        }
        Handler::MissingBindingRetirePlan => {
            let plan = project_unlinks::missing_checkout::plan(
                state()?,
                optional("context").as_deref(),
                &text("binding-operation")?,
                &at,
            )?;
            return Ok(json!({"plan_digest":plan.digest()?,"plan":plan}));
        }
        Handler::MissingBindingRetireApply => {
            let plan = project_unlinks::missing_checkout::read_plan(
                args.get_one::<PathBuf>("plan")
                    .ok_or_else(|| Failure::input("plan is required"))?,
            )?;
            return project_unlinks::missing_checkout::apply(
                plan.state_parent(),
                &plan,
                &text("plan-digest")?,
                &at,
            );
        }
        Handler::MissingBindingRetireStatus => {
            return project_unlinks::missing_checkout::status(state()?, &text("operation")?);
        }
        Handler::UnlinkRetirePlan => {
            let plan = project_unlinks::retirement::plan(
                state()?,
                &text("operation")?,
                optional("context").as_deref(),
                &at,
            )?;
            return Ok(json!({"plan_digest":plan.digest()?,"plan":plan}));
        }
        Handler::UnlinkRetireApply => {
            let plan = project_unlinks::retirement::read_plan(
                args.get_one::<PathBuf>("plan")
                    .ok_or_else(|| Failure::input("plan is required"))?,
            )?;
            return project_unlinks::retirement::apply(
                plan.state_parent(),
                &plan,
                &text("plan-digest")?,
                &at,
            );
        }
        Handler::UnlinkRequestPlan => {
            let plan = project_unlinks::request_plan(
                state()?,
                optional("context").as_deref(),
                &text("binding-operation")?,
                &at,
            )?;
            return Ok(json!({"plan_digest":plan.digest()?,"plan":plan}));
        }
        Handler::UnlinkConfirmPlan => {
            let plan =
                project_unlinks::confirmation_plan(state()?, &text("request-operation")?, &at)?;
            return Ok(json!({"plan_digest":plan.digest()?,"plan":plan}));
        }
        Handler::UnlinkApply => {
            let plan = project_unlinks::read_plan(
                args.get_one::<PathBuf>("plan")
                    .ok_or_else(|| Failure::input("plan is required"))?,
            )?;
            return project_unlinks::apply(
                plan.state_parent(),
                &plan,
                &text("plan-digest")?,
                optional("context").as_deref(),
                &at,
            );
        }
        Handler::UnlinkStatus => return project_unlinks::status(state()?, &text("operation")?),
        Handler::UnlinkList => {
            return project_unlinks::list(
                state()?,
                optional("cursor").as_deref(),
                optional("limit")
                    .map_or(Ok(50), |value| value.parse::<u16>())
                    .map_err(|_| Failure::input("limit must be from 1 to 100"))?,
            );
        }
        Handler::UnlinkObservedOutcome => {
            return project_unlinks::outcome(
                state()?,
                &text("operation")?,
                optional("context").as_deref(),
            );
        }
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
        Handler::HeartbeatPolicy => Request::HeartbeatPolicy,
        Handler::HeartbeatStatus => Request::HeartbeatStatus,
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
        | Handler::LinkObservedOutcome
        | Handler::UnlinkRequestPlan
        | Handler::UnlinkConfirmPlan
        | Handler::UnlinkApply
        | Handler::UnlinkStatus
        | Handler::UnlinkList
        | Handler::UnlinkObservedOutcome
        | Handler::UnlinkRetirePlan
        | Handler::UnlinkRetireApply
        | Handler::BindingRetirePlan
        | Handler::BindingRetireApply
        | Handler::MissingBindingRetirePlan
        | Handler::MissingBindingRetireApply
        | Handler::MissingBindingRetireStatus
        | Handler::LocationAnchorPlan
        | Handler::LocationRelocatePlan
        | Handler::LocationApply
        | Handler::LocationStatus
        | Handler::LocationList
        | Handler::HeartbeatConsentPlan
        | Handler::HeartbeatConsentApply
        | Handler::HeartbeatDelivery
        | Handler::HeartbeatFlush
        | Handler::HeartbeatDisable
        | Handler::HeartbeatMaintain => {
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
