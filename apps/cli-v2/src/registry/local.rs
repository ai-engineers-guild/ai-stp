//! Local authoring command declarations and argument conversion only.

use clap::ArgMatches;
use serde::de::DeserializeOwned;
use serde_json::Value;
use std::path::{Path, PathBuf};

use super::{Declaration, ID, KIND, Parameter, ParameterType, ROOT, STATE_DIR};
use crate::{
    authoring::{
        adoption, discovery, forks, native_edit, passports, project_binding, releases, runtime,
        setups,
    },
    canonical,
    error::{Failure, Result},
    files,
    provider::Info,
    store::versions::Increment,
};

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Bind,
    Adopt,
    Discover,
    Update,
    NativeEdit,
    Release,
    Fork,
    Compose,
    Apply,
    Show,
    Version,
    Versions,
}

impl Handler {
    pub(super) fn mutability(self) -> &'static str {
        match self {
            Self::Discover | Self::Show | Self::Version | Self::Versions => "read",
            Self::Apply => "apply",
            _ => "plan",
        }
    }
}

const HARNESS: Parameter = Parameter {
    name: "harness",
    summary: "Native layout harness, or undefined for shared user skill sources.",
    kind: ParameterType::Choice(&[
        "claude-code",
        "codex",
        "pi",
        "opencode",
        "grok-build",
        "cursor",
        "antigravity",
        "undefined",
    ]),
    required: true,
};
const SCOPE: Parameter = Parameter {
    name: "scope",
    summary: "Native discovery layout scope.",
    kind: ParameterType::Choice(&["global", "project"]),
    required: true,
};
const ROOT_KIND: Parameter = Parameter {
    name: "root-kind",
    summary: "Meaning of the explicit native root directory.",
    kind: ParameterType::Choice(&["config", "home", "cursor_config"]),
    required: true,
};
const NATIVE_ROOT: Parameter = Parameter {
    name: "root",
    summary: "Explicit directory for the selected native layout root.",
    kind: ParameterType::Path,
    required: true,
};
const REVISION: Parameter = Parameter {
    name: "expected-revision",
    summary: "Exact current draft revision identifier.",
    kind: ParameterType::String,
    required: true,
};
const VERSION: Parameter = Parameter {
    name: "version",
    summary: "Exact immutable X.Y coordinate.",
    kind: ParameterType::String,
    required: true,
};
const PROVIDERS: Parameter = Parameter {
    name: "provider-info",
    summary: "Explicit v3 provider declaration JSON, at most seven files of 1 MiB each. Describes packaging; does not establish executable trust.",
    kind: ParameterType::Paths,
    required: false,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["component", "adaptation", "edit", "plan"],
        summary: "Plan a complete native adaptation replacement in an owned draft, preserving every existing scope and other harness.",
        parameters: &[
            STATE_DIR,
            ID,
            REVISION,
            Parameter {
                name: "sources",
                summary: "JSON array of {scope, source: {root: {display, utf8_base64}, harness_id, scope, root_kind, candidate_id}}; at most three entries and 256 KiB. Root uses the exact absolute UTF-8 path and its NFC display.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "provider-info",
                summary: "Exact v3 provider declaration JSON for this harness, at most 1 MiB; not executable trust.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::NativeEdit),
    },
    Declaration {
        path: &["component", "source", "bind", "plan"],
        summary: "Plan an atomic binding and adaptation refresh from one exact portable source snapshot.",
        parameters: &[
            STATE_DIR,
            ROOT,
            Parameter {
                name: "target",
                summary: "Explicit harness:scope adaptation target; repeat for all required scopes.",
                kind: ParameterType::Strings,
                required: true,
            },
            Parameter {
                required: true,
                ..PROVIDERS
            },
        ],
        handler: super::Handler::Local(Handler::Bind),
    },
    Declaration {
        path: &["component", "discover"],
        summary: "Inspect declared native layouts without reading credentials or changing the harness.",
        parameters: &[NATIVE_ROOT, HARNESS, SCOPE, ROOT_KIND],
        handler: super::Handler::Local(Handler::Discover),
    },
    Declaration {
        path: &["component", "adopt", "plan"],
        summary: "Plan local adoption of an exact native discovery candidate.",
        parameters: &[
            STATE_DIR,
            NATIVE_ROOT,
            HARNESS,
            SCOPE,
            ROOT_KIND,
            Parameter {
                name: "candidate-id",
                summary: "Exact candidate identifier from component discover.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::Adopt),
    },
    Declaration {
        path: &["component", "passport", "update", "plan"],
        summary: "Plan a confirmed metadata edit against the exact owned draft revision.",
        parameters: &[
            STATE_DIR,
            ID,
            REVISION,
            Parameter {
                name: "patch",
                summary: "Closed passport patch JSON, at most 256 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::Update),
    },
    Declaration {
        path: &["component", "version", "release", "plan"],
        summary: "Plan a private immutable release from the exact owned draft and retained source graph.",
        parameters: &[
            STATE_DIR,
            ID,
            REVISION,
            PROVIDERS,
            Parameter {
                name: "increment",
                summary: "Requested version increment; a first release is always 1.0.",
                kind: ParameterType::Choice(&["minor", "major"]),
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::Release),
    },
    Declaration {
        path: &["component", "fork", "plan"],
        summary: "Plan a private owned draft from one exact retained component version.",
        parameters: &[
            STATE_DIR,
            ID,
            VERSION,
            Parameter {
                name: "passport-digest",
                summary: "Exact canonical passport digest of the source version.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::Fork),
    },
    Declaration {
        path: &["setup", "compose", "plan"],
        summary: "Plan a private immutable setup from a complete exact component graph.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "request",
                summary: "Closed composition request JSON (harness_id, name, description, purpose, members), at most 256 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::Compose),
    },
    Declaration {
        path: &["local", "apply"],
        summary: "Apply or replay an exact local authoring plan using its bound state directory and current identity.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Explicit local authoring plan JSON, at most 16 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by the authoring plan command.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::Apply),
    },
    Declaration {
        path: &["local", "passport", "show"],
        summary: "Read the verified current component or setup passport from explicit preview state without credentials.",
        parameters: &[STATE_DIR, KIND, ID],
        handler: super::Handler::Local(Handler::Show),
    },
    Declaration {
        path: &["local", "version", "show"],
        summary: "Read and verify an exact immutable component or setup version from preview state.",
        parameters: &[STATE_DIR, KIND, ID, VERSION],
        handler: super::Handler::Local(Handler::Version),
    },
    Declaration {
        path: &["local", "version", "list"],
        summary: "Read verified immutable coordinates from explicit preview state.",
        parameters: &[STATE_DIR, ID],
        handler: super::Handler::Local(Handler::Versions),
    },
];

fn text<'a>(args: &'a ArgMatches, name: &str) -> Result<&'a str> {
    args.get_one::<String>(name)
        .map(String::as_str)
        .ok_or_else(|| Failure::input("a required authoring parameter is absent"))
}
fn path<'a>(args: &'a ArgMatches, name: &str) -> Result<&'a Path> {
    args.get_one::<PathBuf>(name)
        .map(PathBuf::as_path)
        .ok_or_else(|| Failure::input("a required authoring path is absent"))
}
fn choice<T: DeserializeOwned>(args: &ArgMatches, name: &str) -> Result<T> {
    serde_json::from_value(text(args, name)?.into())
        .map_err(|_| Failure::input("invalid authoring choice"))
}
fn providers(args: &ArgMatches) -> Result<Vec<Info>> {
    let paths: Vec<_> = args
        .get_many::<PathBuf>("provider-info")
        .into_iter()
        .flatten()
        .collect();
    if paths.len() > 7 {
        return Err(Failure::input(
            "at most seven provider declarations are allowed",
        ));
    }
    paths
        .into_iter()
        .map(|path| Info::parse(&files::read(path, 1024 * 1024)?))
        .collect()
}

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    match handler {
        Handler::NativeEdit => {
            let sources: Vec<native_edit::Source> = serde_json::from_value(canonical::parse(
                &files::read(path(args, "sources")?, 256 * 1024)?,
            )?)
            .map_err(|_| Failure::input("invalid native adaptation source selections"))?;
            let provider = Info::parse(&files::read(path(args, "provider-info")?, 1024 * 1024)?)?;
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                native_edit::plan(
                    store,
                    text(args, "id")?,
                    text(args, "expected-revision")?,
                    sources,
                    &provider,
                    identity,
                    at,
                )
            })
        }
        Handler::Apply => runtime::apply(path(args, "plan")?, text(args, "plan-digest")?),
        Handler::Show | Handler::Version => runtime::inspect(
            path(args, "state-dir")?,
            text(args, "kind")?,
            text(args, "id")?,
            if matches!(handler, Handler::Version) {
                Some(text(args, "version")?)
            } else {
                None
            },
        ),
        Handler::Versions => runtime::versions(path(args, "state-dir")?, text(args, "id")?),
        Handler::Discover => serde_json::to_value(discovery::at(
            path(args, "root")?,
            text(args, "harness")?,
            choice(args, "scope")?,
            choice(args, "root-kind")?,
        )?)
        .map_err(|_| Failure::input("discovery could not be encoded")),
        Handler::Bind => {
            let targets: Vec<_> = args
                .get_many::<String>("target")
                .into_iter()
                .flatten()
                .collect();
            if targets.len() > 21 {
                return Err(Failure::input("at most 21 adaptation targets are allowed"));
            }
            let targets = targets
                .into_iter()
                .map(|target| {
                    let (harness, scope) = target.split_once(':').ok_or_else(|| {
                        Failure::input("an adaptation target must be harness:scope")
                    })?;
                    Ok(project_binding::Target {
                        harness_id: harness.into(),
                        scope: serde_json::from_value(scope.into())
                            .map_err(|_| Failure::input("invalid adaptation scope"))?,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            let request = project_binding::Request {
                root: path(args, "root")?.into(),
                targets,
            };
            let providers = providers(args)?;
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                project_binding::plan(store, request, &providers, identity, at)
            })
        }
        Handler::Adopt => {
            let source = adoption::Source {
                root: path(args, "root")?.into(),
                harness_id: text(args, "harness")?.into(),
                scope: choice(args, "scope")?,
                root_kind: choice(args, "root-kind")?,
                candidate_id: text(args, "candidate-id")?.into(),
            };
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                adoption::plan(store, source, identity, at)
            })
        }
        Handler::Update => {
            let patch = passports::Patch::read(path(args, "patch")?)?;
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                passports::plan(
                    store,
                    text(args, "id")?,
                    text(args, "expected-revision")?,
                    patch,
                    identity,
                    at,
                )
            })
        }
        Handler::Release => {
            let providers = providers(args)?;
            let increment: Increment = choice(args, "increment")?;
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                releases::plan(
                    store,
                    text(args, "id")?,
                    text(args, "expected-revision")?,
                    increment,
                    &providers,
                    identity,
                    at,
                )
            })
        }
        Handler::Fork => {
            let source = forks::Source {
                stable_id: text(args, "id")?.into(),
                version: text(args, "version")?.into(),
                passport_digest: text(args, "passport-digest")?.into(),
            };
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                forks::plan(store, source, identity, at)
            })
        }
        Handler::Compose => {
            let request: setups::Request = serde_json::from_value(canonical::parse(&files::read(
                path(args, "request")?,
                256 * 1024,
            )?)?)
            .map_err(|_| Failure::input("invalid setup composition request"))?;
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                setups::plan(store, request, identity, at)
            })
        }
    }
}
