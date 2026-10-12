//! Component observation and exact program/configuration command adapters.

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
    ProgramInstallApply,
    ProgramInstallCancel,
    ProgramUpdatePlan,
    ProgramRemovePlan,
    ProgramUpdateApply,
    ProgramRemoveApply,
    ProgramUpdateCancel,
    ProgramRemoveCancel,
    ConfigurationPlan,
    ConfigurationApply,
    ConfigurationCancel,
}

impl Handler {
    pub(super) fn mutability(self) -> &'static str {
        match self {
            Self::ProgramInstallApply
            | Self::ConfigurationApply
            | Self::ConfigurationCancel
            | Self::ProgramInstallCancel
            | Self::ProgramUpdateApply
            | Self::ProgramUpdateCancel
            | Self::ProgramRemoveCancel
            | Self::ProgramRemoveApply => "apply",
            Self::Plan
            | Self::ConfigurationPlan
            | Self::SoftwarePlan
            | Self::ProgramInstallPlan
            | Self::ProgramUpdatePlan
            | Self::ProgramRemovePlan => "plan",
            Self::Network | Self::Inspect | Self::Status | Self::SoftwareAcquire => "read",
        }
    }
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

const INSTALL_PARAMETERS: &[Parameter] = &[
    STATE_DIR,
    Parameter {
        name: "plan",
        summary: "Original program operation plan JSON, at most 64 KiB.",
        kind: ParameterType::Path,
        required: true,
    },
    Parameter {
        name: "plan-digest",
        summary: "Exact digest returned by the corresponding program plan command.",
        kind: ParameterType::String,
        required: true,
    },
];

const CHANGE_PREFIX: Parameter = Parameter {
    name: "prefix",
    summary: "Existing absolute program directory; physically bound and disjoint from target and state.",
    kind: ParameterType::Path,
    required: true,
};
const CHANGE_VERSION: Parameter = Parameter {
    name: "software-version",
    summary: "Exact program version; update omission uses the authenticated component pin.",
    kind: ParameterType::String,
    required: false,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["program", "update", "plan"],
        summary: "Plan an exact update inside an existing program directory; bind preserved content and authenticated component identity.",
        parameters: &[
            STATE_DIR,
            HARNESS,
            VERSION,
            TARGET,
            SCOPE,
            CHANGE_PREFIX,
            CHANGE_VERSION,
        ],
        handler: super::Handler::Provider(Handler::ProgramUpdatePlan),
    },
    Declaration {
        path: &["program", "remove", "plan"],
        summary: "Plan removal of one exact component-owned program version while retaining other versions and unrelated content.",
        parameters: &[
            STATE_DIR,
            HARNESS,
            VERSION,
            TARGET,
            SCOPE,
            CHANGE_PREFIX,
            Parameter {
                required: true,
                ..CHANGE_VERSION
            },
        ],
        handler: super::Handler::Provider(Handler::ProgramRemovePlan),
    },
    Declaration {
        path: &["program", "update", "cancel"],
        summary: "Cancel an exact update before component effects; return its original terminal receipt on retry.",
        parameters: INSTALL_PARAMETERS,
        handler: super::Handler::Provider(Handler::ProgramUpdateCancel),
    },
    Declaration {
        path: &["program", "remove", "cancel"],
        summary: "Cancel an exact removal before component effects; preserve the program and original terminal history.",
        parameters: INSTALL_PARAMETERS,
        handler: super::Handler::Provider(Handler::ProgramRemoveCancel),
    },
    Declaration {
        path: &["program", "update", "apply"],
        summary: "Apply or resume the original existing-program update through its authenticated component; verify payload and preserved content.",
        parameters: INSTALL_PARAMETERS,
        handler: super::Handler::Provider(Handler::ProgramUpdateApply),
    },
    Declaration {
        path: &["program", "remove", "apply"],
        summary: "Apply or resume the original exact-version removal; verify absence, retained launch entries and preserved content.",
        parameters: INSTALL_PARAMETERS,
        handler: super::Handler::Provider(Handler::ProgramRemoveApply),
    },
    Declaration {
        path: &["program", "install", "apply"],
        summary: "Apply or resume an exact fresh-program installation plan; verify its payload and publish the complete directory without replacing an existing destination.",
        parameters: INSTALL_PARAMETERS,
        handler: super::Handler::Provider(Handler::ProgramInstallApply),
    },
    Declaration {
        path: &["program", "install", "cancel"],
        summary: "Cancel an exact unpublished installation and durably discard only its recorded generated stage; no final program directory is removed.",
        parameters: INSTALL_PARAMETERS,
        handler: super::Handler::Provider(Handler::ProgramInstallCancel),
    },
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
        path: &["configuration", "cancel"],
        summary: "Cancel an exact configuration operation before component publication; existing terminal results remain unchanged.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "plan",
                summary: "Original configuration plan JSON, at most 32 MiB; its original component must support exact cancellation.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by configuration plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::ConfigurationCancel),
    },
    Declaration {
        path: &["configuration", "apply"],
        summary: "Apply or resume one exact forward configuration plan through its authenticated component and verify target bytes independently.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "plan",
                summary: "Original configuration plan JSON, at most 32 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by configuration plan.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "bundle",
                summary: "Original bundle for first install/replace admission; recovery uses retained bytes and removal takes no bundle.",
                kind: ParameterType::Path,
                required: false,
            },
        ],
        handler: super::Handler::Provider(Handler::ConfigurationApply),
    },
    Declaration {
        path: &["configuration", "plan"],
        summary: "Plan exact configuration installation, replacement or removal with independent file expectations and forward recovery.",
        parameters: &[
            STATE_DIR,
            HARNESS,
            VERSION,
            TARGET,
            SCOPE,
            Parameter {
                name: "operation",
                summary: "Configuration operation; removal withdraws recorded ownership without a bundle.",
                kind: ParameterType::Choice(&["install", "replace", "remove"]),
                required: true,
            },
            Parameter {
                name: "bundle",
                summary: "Exact ai-stp-bundle/2 archive, required for install/replace and forbidden for remove.",
                kind: ParameterType::Path,
                required: false,
            },
        ],
        handler: super::Handler::Provider(Handler::ConfigurationPlan),
    },
    Declaration {
        path: &["provider", "plan"],
        summary: "Observe an exact configuration plan without authorizing or applying it; removal requires forward recovery and no bundle.",
        parameters: &[
            STATE_DIR,
            HARNESS,
            VERSION,
            TARGET,
            SCOPE,
            Parameter {
                name: "bundle",
                summary: "Exact ai-stp-bundle/2 ZIP bytes, required for install/replace and forbidden for remove; at most 64 MiB.",
                kind: ParameterType::Path,
                required: false,
            },
            Parameter {
                name: "request",
                summary: "Closed plan request JSON up to 8 KiB: operation, operation_id, expires_at, exact bundle binding and optional recovery_mode=forward; requires declared component support.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::Plan),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    if matches!(
        handler,
        Handler::ProgramInstallApply
            | Handler::ConfigurationApply
            | Handler::ConfigurationCancel
            | Handler::ProgramInstallCancel
            | Handler::ProgramUpdateApply
            | Handler::ProgramUpdateCancel
            | Handler::ProgramRemoveCancel
            | Handler::ProgramRemoveApply
    ) {
        let parent = args
            .get_one::<PathBuf>("state-dir")
            .ok_or_else(|| Failure::input("the explicit state parent is required"))?;
        let path = args
            .get_one::<PathBuf>("plan")
            .ok_or_else(|| Failure::input("the original installation plan is required"))?;
        let digest = args
            .get_one::<String>("plan-digest")
            .ok_or_else(|| Failure::input("the exact installation plan digest is required"))?;
        if matches!(handler, Handler::ConfigurationCancel) {
            return runtime::configuration_cancel(
                parent,
                &files::read(path, runtime::CONFIGURATION_PLAN_BYTES as u64)?,
                digest,
            );
        }
        if matches!(handler, Handler::ConfigurationApply) {
            return runtime::configuration_apply(
                parent,
                &files::read(path, runtime::CONFIGURATION_PLAN_BYTES as u64)?,
                digest,
                args.get_one::<PathBuf>("bundle").map(PathBuf::as_path),
            );
        }
        let bytes = files::read(path, 64 * 1024)?;
        if matches!(
            handler,
            Handler::ProgramUpdateCancel | Handler::ProgramRemoveCancel
        ) {
            return runtime::program_change_cancel(
                parent,
                &bytes,
                digest,
                if matches!(handler, Handler::ProgramUpdateCancel) {
                    "program.update"
                } else {
                    "program.remove"
                },
            );
        }
        return if matches!(
            handler,
            Handler::ProgramUpdateApply | Handler::ProgramRemoveApply
        ) {
            runtime::program_change_apply(
                parent,
                &bytes,
                digest,
                if matches!(handler, Handler::ProgramUpdateApply) {
                    "program.update"
                } else {
                    "program.remove"
                },
            )
        } else if matches!(handler, Handler::ProgramInstallCancel) {
            runtime::program_install_cancel(parent, &bytes, digest)
        } else {
            runtime::program_install_apply(parent, &bytes, digest)
        };
    }
    let runtime = Runtime::observe()?;
    match handler {
        Handler::Network => Ok(runtime.report()),
        Handler::ProgramInstallApply
        | Handler::ConfigurationApply
        | Handler::ConfigurationCancel
        | Handler::ProgramInstallCancel
        | Handler::ProgramUpdateApply
        | Handler::ProgramUpdateCancel
        | Handler::ProgramRemoveCancel
        | Handler::ProgramRemoveApply => Err(Failure::input("the installation command is invalid")),
        Handler::Inspect
        | Handler::ConfigurationPlan
        | Handler::Status
        | Handler::Plan
        | Handler::SoftwarePlan
        | Handler::ProgramInstallPlan
        | Handler::ProgramUpdatePlan
        | Handler::ProgramRemovePlan
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
                | Handler::ConfigurationPlan
                | Handler::Plan
                | Handler::SoftwarePlan
                | Handler::ProgramInstallPlan
                | Handler::ProgramUpdatePlan
                | Handler::ProgramRemovePlan
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
                    } else if matches!(handler, Handler::ConfigurationPlan) {
                        let operation = args.get_one::<String>("operation").ok_or_else(|| {
                            Failure::input("the configuration operation is required")
                        })?;
                        let bundle = args
                            .get_one::<PathBuf>("bundle")
                            .map(|path| files::read(path, plan::MAX_BUNDLE_BYTES as u64))
                            .transpose()?;
                        runtime.configuration_plan(&context, operation, bundle.as_deref())
                    } else if matches!(
                        handler,
                        Handler::ProgramInstallPlan
                            | Handler::ProgramUpdatePlan
                            | Handler::ProgramRemovePlan
                    ) {
                        let prefix = args.get_one::<PathBuf>("prefix").ok_or_else(|| {
                            Failure::input("the explicit software prefix is required")
                        })?;
                        if matches!(
                            handler,
                            Handler::ProgramUpdatePlan | Handler::ProgramRemovePlan
                        ) {
                            runtime.program_change_plan(
                                &context,
                                prefix,
                                args.get_one::<String>("software-version")
                                    .map(String::as_str),
                                if matches!(handler, Handler::ProgramUpdatePlan) {
                                    "program.update"
                                } else {
                                    "program.remove"
                                },
                            )
                        } else {
                            runtime.program_install_plan(
                                &context,
                                prefix,
                                args.get_one::<String>("software-version")
                                    .map(String::as_str),
                            )
                        }
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
                        let bundle = match (args.get_one::<PathBuf>("bundle"), &request.bundle) {
                            (Some(path), Some(_)) => {
                                files::read(path, plan::MAX_BUNDLE_BYTES as u64)?
                            }
                            (None, None) => Vec::new(),
                            _ => {
                                return Err(Failure::input(
                                    "install/replace requires an exact bundle path; removal forbids one",
                                ));
                            }
                        };
                        runtime.plan(&context, &request, &bundle)
                    }
                }
                Handler::Network
                | Handler::ConfigurationApply
                | Handler::ConfigurationCancel
                | Handler::ProgramInstallApply
                | Handler::ProgramInstallCancel
                | Handler::ProgramUpdateApply
                | Handler::ProgramUpdateCancel
                | Handler::ProgramRemoveCancel
                | Handler::ProgramRemoveApply => {
                    Err(Failure::input("the provider command is invalid"))
                }
            }
        }
    }
}
