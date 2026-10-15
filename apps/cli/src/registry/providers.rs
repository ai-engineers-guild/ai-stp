//! Component observation and exact configuration command adapters.

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    error::{Failure, Result},
    files,
    projection::Scope,
    provider::{
        artifact, managed, plan,
        runtime::{self, Runtime, TargetRequest},
        trust,
    },
};
use clap::ArgMatches;
use serde_json::Value;
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub(super) enum Handler {
    SetPlan,
    SetApply,
    SetPrepare,
    SetConfirm,
    SetCancel,
    SetStatus,
    ProgramStatus,
    Network,
    Inspect,
    Status,
    Plan,
    ConfigurationPlan,
    ConfigurationApply,
    ConfigurationCancel,
}

impl Handler {
    pub(super) fn mutability(self) -> &'static str {
        match self {
            Self::SetApply
            | Self::SetPrepare
            | Self::SetConfirm
            | Self::SetCancel
            | Self::ConfigurationApply
            | Self::ConfigurationCancel => "apply",
            Self::SetPlan | Self::Plan | Self::ConfigurationPlan => "plan",
            Self::SetStatus
            | Self::Network
            | Self::Inspect
            | Self::Status
            | Self::ProgramStatus => "read",
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

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["configuration", "set", "plan"],
        summary: "Plan complete setup installation across one to three explicit, disjoint configuration roots.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "request",
                summary: "Closed JSON: harness_id, optional provider_version/project_root, operation, targets [{scope,path,bundle?}]; at most 32 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::SetPlan),
    },
    Declaration {
        path: &["configuration", "set", "prepare"],
        summary: "Stage all configuration roots and bind active consumers; publish no configuration until those sessions exit.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "plan",
                summary: "Original complete configuration set plan JSON, at most 32 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by configuration set plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::SetPrepare),
    },
    Declaration {
        path: &["configuration", "set", "confirm"],
        summary: "Confirm verified configuration from the restarted harness session using its observed process identity.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "plan",
                summary: "Original complete configuration set plan JSON, at most 32 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by configuration set plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::SetConfirm),
    },
    Declaration {
        path: &["configuration", "set", "apply"],
        summary: "Prepare every root before ordered publication; resume from durable complete-set checkpoints.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "plan",
                summary: "Original complete configuration set plan JSON, at most 32 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by configuration set plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::SetApply),
    },
    Declaration {
        path: &["configuration", "set", "cancel"],
        summary: "Cancel all roots before publication has begun; partial publication requires forward recovery.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "plan",
                summary: "Original complete configuration set plan JSON, at most 32 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by configuration set plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::SetCancel),
    },
    Declaration {
        path: &["configuration", "set", "status"],
        summary: "Read the exact complete-set journal without opening targets, providers or the network.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "plan",
                summary: "Original complete configuration set plan JSON, at most 32 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by configuration set plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Provider(Handler::SetStatus),
    },
    Declaration {
        path: &["program", "status"],
        summary: "Observe the user-installed harness version; never install, update or remove the executable.",
        parameters: &[
            HARNESS,
            Parameter {
                name: "executable",
                summary: "Absolute harness executable; omission resolves its declared name on PATH.",
                kind: ParameterType::Path,
                required: false,
            },
        ],
        handler: super::Handler::Provider(Handler::ProgramStatus),
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
                name: "project-id",
                summary: "Bind this project-scope operation to its registered project and exact selected setup.",
                kind: ParameterType::String,
                required: false,
            },
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
        Handler::SetPlan
            | Handler::SetApply
            | Handler::SetPrepare
            | Handler::SetConfirm
            | Handler::SetCancel
            | Handler::SetStatus
    ) {
        let parent = args
            .get_one::<PathBuf>("state-dir")
            .ok_or_else(|| Failure::input("the explicit state parent is required"))?;
        if matches!(handler, Handler::SetPlan) {
            let path = args
                .get_one::<PathBuf>("request")
                .ok_or_else(|| Failure::input("the configuration set request is required"))?;
            return runtime::configuration_set_plan(parent, &files::read(path, 32 * 1024)?);
        }
        let path = args
            .get_one::<PathBuf>("plan")
            .ok_or_else(|| Failure::input("the original configuration set plan is required"))?;
        let digest = args
            .get_one::<String>("plan-digest")
            .ok_or_else(|| Failure::input("the exact configuration set plan digest is required"))?;
        let action = match handler {
            Handler::SetApply => "apply",
            Handler::SetPrepare => "prepare",
            Handler::SetConfirm => "confirm",
            Handler::SetCancel => "cancel",
            _ => "status",
        };
        return runtime::configuration_set(
            parent,
            &files::read(path, runtime::CONFIGURATION_PLAN_BYTES as u64)?,
            digest,
            action,
        );
    }
    if matches!(handler, Handler::ProgramStatus) {
        return crate::program::observe(
            args.get_one::<String>("harness")
                .ok_or_else(|| Failure::input("the harness is required"))?,
            args.get_one::<PathBuf>("executable").map(PathBuf::as_path),
        );
    }
    if matches!(
        handler,
        Handler::ConfigurationApply | Handler::ConfigurationCancel
    ) {
        let parent = args
            .get_one::<PathBuf>("state-dir")
            .ok_or_else(|| Failure::input("the explicit state parent is required"))?;
        let path = args
            .get_one::<PathBuf>("plan")
            .ok_or_else(|| Failure::input("the original configuration plan is required"))?;
        let digest = args
            .get_one::<String>("plan-digest")
            .ok_or_else(|| Failure::input("the exact configuration plan digest is required"))?;
        let bytes = files::read(path, runtime::CONFIGURATION_PLAN_BYTES as u64)?;
        return if matches!(handler, Handler::ConfigurationCancel) {
            runtime::configuration_cancel(parent, &bytes, digest)
        } else {
            runtime::configuration_apply(
                parent,
                &bytes,
                digest,
                args.get_one::<PathBuf>("bundle").map(PathBuf::as_path),
            )
        };
    }
    let runtime = Runtime::observe()?;
    match handler {
        Handler::Network => Ok(runtime.report()),
        Handler::SetPlan
        | Handler::SetApply
        | Handler::SetPrepare
        | Handler::SetConfirm
        | Handler::SetCancel
        | Handler::SetStatus
        | Handler::ProgramStatus
        | Handler::ConfigurationApply
        | Handler::ConfigurationCancel => {
            Err(Failure::input("the installation command is invalid"))
        }
        Handler::Inspect | Handler::ConfigurationPlan | Handler::Status | Handler::Plan => {
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
                Handler::Status | Handler::ConfigurationPlan | Handler::Plan => {
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
                        runtime.configuration_plan(
                            &context,
                            operation,
                            bundle.as_deref(),
                            args.get_one::<String>("project-id").map(String::as_str),
                        )
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
                Handler::SetPlan
                | Handler::SetApply
                | Handler::SetPrepare
                | Handler::SetConfirm
                | Handler::SetCancel
                | Handler::SetStatus
                | Handler::Network
                | Handler::ProgramStatus
                | Handler::ConfigurationApply
                | Handler::ConfigurationCancel => {
                    Err(Failure::input("the provider command is invalid"))
                }
            }
        }
    }
}
