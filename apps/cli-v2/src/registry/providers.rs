//! Authenticated provider observation commands, separate from installation.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    error::{Failure, Result},
    files,
    projection::Scope,
    provider::{
        artifact, managed, plan,
        runtime::{self, Runtime, TargetRequest},
        software, trust,
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
    Plan,
    SoftwarePlan,
    SoftwareAcquire,
    ProgramInstallPlan,
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
    summary: "Exact setup-component X.Y.Z override; omission uses this ai-stp build's managed release.",
    kind: ParameterType::String,
    required: false,
};
const TARGET: Parameter = Parameter {
    name: "target",
    summary: "Explicit existing absolute target directory; symbolic path components are refused.",
    kind: ParameterType::Path,
    required: true,
};
const SCOPE: Parameter = Parameter {
    name: "scope",
    summary: "Exact provider target scope; no scope is inferred.",
    kind: ParameterType::Choice(&["global", "user_root", "project"]),
    required: true,
};

const SOFTWARE_PARAMETERS: &[Parameter] = &[
    STATE_DIR,
    HARNESS,
    VERSION,
    TARGET,
    SCOPE,
    Parameter {
        name: "prefix",
        summary: "Explicit absolute software directory, existing or absent under an existing plain parent; disjoint from target and trust state.",
        kind: ParameterType::Path,
        required: true,
    },
    Parameter {
        name: "request",
        summary: "Closed JSON up to 8 KiB: software operation, operation_id, expires_at and optional exact software_version; omission uses the authenticated build pin.",
        kind: ParameterType::Path,
        required: true,
    },
];

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["program", "install", "plan"],
        summary: "Plan a new program directory with a bound absent destination and an authenticated empty-stage component plan; no installation.",
        parameters: &[
            STATE_DIR,
            HARNESS,
            VERSION,
            TARGET,
            SCOPE,
            Parameter {
                name: "prefix",
                summary: "Absent absolute software directory under an existing plain parent, disjoint from target and state.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "software-version",
                summary: "Exact harness program version; omission uses the authenticated component's compiled pin.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: super::Handler::Provider(Handler::ProgramInstallPlan),
    },
    Declaration {
        path: &["provider", "software", "plan"],
        summary: "Observe an exact software plan through an authenticated provider with read-only target and prefix mounts.",
        parameters: SOFTWARE_PARAMETERS,
        handler: super::Handler::Provider(Handler::SoftwarePlan),
    },
    Declaration {
        path: &["provider", "software", "acquire"],
        summary: "Acquire exact authenticated software plan artifacts into private state with streamed length and digest verification.",
        parameters: SOFTWARE_PARAMETERS,
        handler: super::Handler::Provider(Handler::SoftwareAcquire),
    },
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
        parameters: &[STATE_DIR, HARNESS, VERSION, TARGET, SCOPE],
        handler: super::Handler::Provider(Handler::Status),
    },
    Declaration {
        path: &["provider", "plan"],
        summary: "Validate exact bundle bytes and observe a digest-bound provider plan without authorizing or applying it.",
        parameters: &[
            STATE_DIR,
            HARNESS,
            VERSION,
            TARGET,
            SCOPE,
            Parameter {
                name: "bundle",
                summary: "Exact ai-stp-bundle/2 ZIP bytes, at most 64 MiB; no extraction or target writes.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "request",
                summary: "Closed plan request JSON up to 8 KiB: operation, operation_id, expires_at and exact bundle binding.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::Plan),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    let runtime = Runtime::observe()?;
    match handler {
        Handler::Network => Ok(runtime.report()),
        Handler::Inspect
        | Handler::Status
        | Handler::Plan
        | Handler::SoftwarePlan
        | Handler::ProgramInstallPlan
        | Handler::SoftwareAcquire => {
            let parent = args
                .get_one::<PathBuf>("state-dir")
                .ok_or_else(|| Failure::input("the explicit state parent is required"))?;
            let harness = args
                .get_one::<String>("harness")
                .ok_or_else(|| Failure::input("the harness is required"))?;
            let version = managed::version(args.get_one::<String>("version").map(String::as_str))?;
            match handler {
                Handler::Inspect => {
                    let trust = trust::refresh(parent)?;
                    let artifact = artifact::fetch(harness, version, runtime::platform()?, &trust)?;
                    runtime.inspect(&artifact)
                }
                Handler::Status
                | Handler::Plan
                | Handler::SoftwarePlan
                | Handler::ProgramInstallPlan
                | Handler::SoftwareAcquire => {
                    let target = args
                        .get_one::<PathBuf>("target")
                        .ok_or_else(|| Failure::input("the explicit target is required"))?;
                    let scope = match args.get_one::<String>("scope").map(String::as_str) {
                        Some("global") => Scope::Global,
                        Some("user_root") => Scope::UserRoot,
                        Some("project") => Scope::Project,
                        _ => return Err(Failure::input("the target scope is required")),
                    };
                    let context = TargetRequest {
                        state_parent: parent,
                        harness,
                        version,
                        path: target,
                        scope,
                    };
                    if matches!(handler, Handler::Status) {
                        runtime.status(&context)
                    } else if matches!(handler, Handler::ProgramInstallPlan) {
                        let prefix = args.get_one::<PathBuf>("prefix").ok_or_else(|| {
                            Failure::input("the explicit software prefix is required")
                        })?;
                        runtime.program_install_plan(
                            &context,
                            prefix,
                            args.get_one::<String>("software-version")
                                .map(String::as_str),
                        )
                    } else if matches!(handler, Handler::SoftwarePlan | Handler::SoftwareAcquire) {
                        let request = software::Request::parse(
                            &files::read(
                                args.get_one::<PathBuf>("request").ok_or_else(|| {
                                    Failure::input("the software plan request is required")
                                })?,
                                8192,
                            )?,
                            jiff::Timestamp::now(),
                        )?;
                        let prefix = args.get_one::<PathBuf>("prefix").ok_or_else(|| {
                            Failure::input("the explicit software prefix is required")
                        })?;
                        if matches!(handler, Handler::SoftwareAcquire) {
                            runtime.software_acquire(&context, prefix, &request)
                        } else {
                            runtime.software_plan(&context, prefix, &request)
                        }
                    } else {
                        let request = plan::Request::parse(
                            &files::read(
                                args.get_one::<PathBuf>("request").ok_or_else(|| {
                                    Failure::input("the exact plan request is required")
                                })?,
                                8192,
                            )?,
                            jiff::Timestamp::now(),
                        )?;
                        let bundle = files::read(
                            args.get_one::<PathBuf>("bundle").ok_or_else(|| {
                                Failure::input("the exact bundle path is required")
                            })?,
                            plan::MAX_BUNDLE_BYTES as u64,
                        )?;
                        runtime.plan(&context, &request, &bundle)
                    }
                }
                Handler::Network => Err(Failure::input("the provider command is invalid")),
            }
        }
    }
}
