//! Local authoring command declarations and argument conversion only.

use clap::ArgMatches;
use serde::de::DeserializeOwned;
use serde_json::Value;
use std::path::{Path, PathBuf};

use super::{Declaration, ID, KIND, Parameter, ParameterType, ROOT, STATE_DIR};
use crate::{
    authoring::{
        adoption, derivation, discovery, forks, importing, lifecycle, materialization, native_edit,
        passports, project_binding, releases, review, runtime, scaffold, setups,
    },
    canonical,
    error::{Failure, Result},
    files,
    passport::{developer, device},
    projects,
    provider::Info,
    store::{Store, versions::Increment},
};

#[derive(Clone, Copy)]
pub(super) enum Handler {
    DeveloperInitialize,
    DeveloperUpdate,
    DeviceRefresh,
    Validate,
    Quality,
    Suggest,
    ProjectPassport,
    TechnologyPlan,
    TechnologyFindings,
    Bind,
    Adopt,
    Import,
    Discover,
    Update,
    NativeEdit,
    Derive,
    Materialize,
    Release,
    Fork,
    Forget,
    Compose,
    SetupUpdate,
    SetupRelease,
    SetupFork,
    SetupRecast,
    ExportPlan,
    ExportApply,
    SetupScaffoldPlan,
    SetupScaffoldApply,
    Apply,
    Show,
    Version,
    Versions,
}

impl Handler {
    pub(super) fn mutability(self) -> &'static str {
        match self {
            Self::Discover
            | Self::TechnologyFindings
            | Self::Show
            | Self::Version
            | Self::Versions
            | Self::Validate
            | Self::Quality
            | Self::Suggest => "read",
            Self::Apply | Self::ExportApply | Self::SetupScaffoldApply => "apply",
            _ => "plan",
        }
    }
}

const CONCRETE_HARNESSES: &[&str] = &[
    "claude-code",
    "codex",
    "pi",
    "opencode",
    "grok-build",
    "cursor",
    "antigravity",
];
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
const PASSPORT_DIGEST: Parameter = Parameter {
    name: "passport-digest",
    summary: "Exact canonical passport digest of the source version.",
    kind: ParameterType::String,
    required: true,
};
const PROVIDERS: Parameter = Parameter {
    name: "provider-info",
    summary: "Explicit v3 provider declaration JSON, at most seven files of 1 MiB each. Describes packaging; does not establish executable trust.",
    kind: ParameterType::Paths,
    required: false,
};
const SETUP_REQUEST: Parameter = Parameter {
    name: "request",
    summary: "Closed composition request JSON (harness_id, name, description, purpose, members, optional requirements), at most 256 KiB.",
    kind: ParameterType::Path,
    required: true,
};
const INCREMENT: Parameter = Parameter {
    name: "increment",
    summary: "Requested version increment; a first release is always 1.0.",
    kind: ParameterType::Choice(&["minor", "major"]),
    required: true,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["component", "materialize", "plan"],
        summary: "Plan all exact target adaptations together as an owned immutable version or a private component with retained origin.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "request",
                summary: "Closed JSON up to 16 KiB: exact source, source_harness, targets or all_missing, output owned/private, optional private overlay_id.",
                kind: ParameterType::Path,
                required: true,
            },
            PROVIDERS,
        ],
        handler: super::Handler::Local(Handler::Materialize),
    },
    Declaration {
        path: &["passport", "device", "refresh", "plan"],
        summary: "Plan private runtime platform and CLI-version observations; unobserved harness inventory stays absent.",
        parameters: &[STATE_DIR],
        handler: super::Handler::Local(Handler::DeviceRefresh),
    },
    Declaration {
        path: &["passport", "developer", "initialize", "plan"],
        summary: "Plan a private developer context or retain its exact current revision without inferring preferences.",
        parameters: &[STATE_DIR],
        handler: super::Handler::Local(Handler::DeveloperInitialize),
    },
    Declaration {
        path: &["passport", "developer", "update", "plan"],
        summary: "Plan explicit developer preferences against the exact current revision; environment and authority fields refuse.",
        parameters: &[
            STATE_DIR,
            REVISION,
            Parameter {
                name: "patch",
                summary: "Closed JSON declarations up to 16 KiB: role/autonomy strings and typical_tasks/priorities/preferred_languages/preferred_harnesses arrays.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::DeveloperUpdate),
    },
    Declaration {
        path: &["component", "passport", "validate"],
        summary: "Check local publication structure and retained native bytes without releasing or publishing.",
        parameters: &[STATE_DIR, ID, PROVIDERS],
        handler: super::Handler::Local(Handler::Validate),
    },
    Declaration {
        path: &["component", "passport", "quality"],
        summary: "Read deterministic authoring hints across every adaptation without changing trust or publication decisions.",
        parameters: &[STATE_DIR, ID, PROVIDERS],
        handler: super::Handler::Local(Handler::Quality),
    },
    Declaration {
        path: &["component", "passport", "suggest"],
        summary: "Read exact retained enrichment declarations without updating or confirming draft facts.",
        parameters: &[STATE_DIR, ID],
        handler: super::Handler::Local(Handler::Suggest),
    },
    Declaration {
        path: &["project", "technology", "plan"],
        summary: "Plan a repository technology observation for an owned registered local project, preserving review decisions.",
        parameters: &[STATE_DIR, ROOT],
        handler: super::Handler::Local(Handler::TechnologyPlan),
    },
    Declaration {
        path: &["project", "technology", "findings"],
        summary: "Read retained repository technology evidence for an owned local project without reopening its source.",
        parameters: &[STATE_DIR, ID],
        handler: super::Handler::Local(Handler::TechnologyFindings),
    },
    Declaration {
        path: &["project", "passport", "plan"],
        summary: "Plan or recover one private project observation and preview marker without importing production identity.",
        parameters: &[STATE_DIR, ROOT],
        handler: super::Handler::Local(Handler::ProjectPassport),
    },
    Declaration {
        path: &["component", "forget", "plan"],
        summary: "Plan an owned local component tombstone, retaining its source, immutable versions and history.",
        parameters: &[STATE_DIR, ID, REVISION],
        handler: super::Handler::Local(Handler::Forget),
    },
    Declaration {
        path: &["setup", "scaffold", "plan"],
        summary: "Plan one editable setup-request.json for exact composition, without nested components or generated documentation.",
        parameters: &[
            Parameter {
                name: "harness",
                summary: "The concrete harness this setup belongs to.",
                kind: ParameterType::Choice(CONCRETE_HARNESSES),
                required: true,
            },
            Parameter {
                name: "name",
                summary: "Lowercase setup name, at most 64 ASCII letters, digits or hyphens.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "output",
                summary: "Unused authoring directory beneath an existing parent.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::SetupScaffoldPlan),
    },
    Declaration {
        path: &["setup", "scaffold", "apply"],
        summary: "Create or replay the exact minimal setup authoring directory without overwriting existing content.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Closed setup scaffold plan JSON, at most 64 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by setup scaffold plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::SetupScaffoldApply),
    },
    Declaration {
        path: &["setup", "export", "plan"],
        summary: "Plan three exact setup review files from retained state; requires no credentials and creates no harness tree.",
        parameters: &[
            STATE_DIR,
            ID,
            VERSION,
            PASSPORT_DIGEST,
            Parameter {
                name: "output",
                summary: "Unused output directory beneath an existing parent.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::ExportPlan),
    },
    Declaration {
        path: &["setup", "export", "apply"],
        summary: "Verify the exact retained setup and safely publish or replay its review directory.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Closed setup export plan JSON, at most 8 MiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact digest returned by setup export plan.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::ExportApply),
    },
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
        path: &["component", "adaptation", "derive", "plan"],
        summary: "Plan a missing literal MCP or common skill adaptation from an exact owned draft without dropping controls, scopes or constraints.",
        parameters: &[
            STATE_DIR,
            ID,
            REVISION,
            Parameter {
                name: "source-harness",
                summary: "Existing native adaptation to convert.",
                kind: ParameterType::Choice(&["claude-code", "codex", "cursor", "opencode"]),
                required: true,
            },
            Parameter {
                name: "provider-info",
                summary: "Exact target provider declaration JSON, at most 1 MiB; not executable trust.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::Derive),
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
        summary: "Inspect native layouts and bounded local package metadata without changing the harness.",
        parameters: &[NATIVE_ROOT, HARNESS, SCOPE, ROOT_KIND],
        handler: super::Handler::Local(Handler::Discover),
    },
    Declaration {
        path: &["component", "adopt", "plan"],
        summary: "Plan local adoption of an exact native discovery candidate for a concrete harness.",
        parameters: &[
            STATE_DIR,
            NATIVE_ROOT,
            Parameter {
                summary: "Concrete destination harness; shared skills and external metadata retain neutral source ownership.",
                kind: ParameterType::Choice(CONCRETE_HARNESSES),
                ..HARNESS
            },
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
        path: &["setup", "import", "plan"],
        summary: "Plan one private draft from explicitly selected native components without changing the harness.",
        parameters: &[
            STATE_DIR,
            NATIVE_ROOT,
            Parameter {
                kind: ParameterType::Choice(CONCRETE_HARNESSES),
                summary: "Concrete destination harness for the selected configuration.",
                ..HARNESS
            },
            SCOPE,
            ROOT_KIND,
            Parameter {
                name: "candidate-id",
                summary: "Exact discovery candidate; repeat to select 1–128 components.",
                kind: ParameterType::Strings,
                required: true,
            },
        ],
        handler: super::Handler::Local(Handler::Import),
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
        parameters: &[STATE_DIR, ID, REVISION, PROVIDERS, INCREMENT],
        handler: super::Handler::Local(Handler::Release),
    },
    Declaration {
        path: &["component", "fork", "plan"],
        summary: "Plan a private owned draft from one exact retained component version.",
        parameters: &[STATE_DIR, ID, VERSION, PASSPORT_DIGEST],
        handler: super::Handler::Local(Handler::Fork),
    },
    Declaration {
        path: &["setup", "fork", "plan"],
        summary: "Plan a private owned setup copy from one exact complete version, preserving component coordinates and lineage.",
        parameters: &[STATE_DIR, ID, VERSION, PASSPORT_DIGEST],
        handler: super::Handler::Local(Handler::SetupFork),
    },
    Declaration {
        path: &["setup", "recast", "plan"],
        summary: "Plan an exact setup recast; an explicit provider declaration enables supported derivations with owned dependency replacements.",
        parameters: &[
            STATE_DIR,
            ID,
            VERSION,
            PASSPORT_DIGEST,
            Parameter {
                name: "target-harness",
                summary: "Concrete destination harness, distinct from the source setup.",
                kind: ParameterType::Choice(CONCRETE_HARNESSES),
                required: true,
            },
            Parameter {
                name: "provider-info",
                summary: "Optional target v3 provider declaration JSON, at most 1 MiB. Enables supported graph derivation; does not authorize provider execution.",
                kind: ParameterType::Path,
                required: false,
            },
        ],
        handler: super::Handler::Local(Handler::SetupRecast),
    },
    Declaration {
        path: &["setup", "passport", "update", "plan"],
        summary: "Plan an owned private setup draft from exact members while retaining its identity, harness and capture history.",
        parameters: &[STATE_DIR, ID, REVISION, SETUP_REQUEST],
        handler: super::Handler::Local(Handler::SetupUpdate),
    },
    Declaration {
        path: &["setup", "version", "release", "plan"],
        summary: "Plan an immutable version of the exact complete setup draft without moving its head.",
        parameters: &[STATE_DIR, ID, REVISION, INCREMENT],
        handler: super::Handler::Local(Handler::SetupRelease),
    },
    Declaration {
        path: &["setup", "compose", "plan"],
        summary: "Plan a private immutable setup from a complete exact component graph.",
        parameters: &[STATE_DIR, SETUP_REQUEST],
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
        summary: "Read one verified current passport by exact kind and ID from preview state without credentials.",
        parameters: &[
            STATE_DIR,
            Parameter {
                kind: ParameterType::Choice(&[
                    "component",
                    "setup",
                    "project",
                    "developer",
                    "device",
                ]),
                summary: "Local object kind.",
                ..KIND
            },
            ID,
        ],
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
        Handler::Materialize => {
            let request = materialization::Request::read(path(args, "request")?)?;
            let providers = providers(args)?;
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                materialization::plan(store, request, &providers, identity, at)
            })
        }
        Handler::DeviceRefresh => runtime::plan(path(args, "state-dir")?, device::plan),
        Handler::DeveloperInitialize | Handler::DeveloperUpdate => {
            let update = matches!(handler, Handler::DeveloperUpdate);
            let patch = update
                .then(|| developer::Patch::read(path(args, "patch")?))
                .transpose()?;
            let expected = update
                .then(|| text(args, "expected-revision"))
                .transpose()?;
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                developer::plan(store, expected, patch, identity, at)
            })
        }
        Handler::Suggest => {
            let mut store = Store::planning(path(args, "state-dir")?)?;
            review::suggest(&mut store, text(args, "id")?)
        }
        Handler::Validate | Handler::Quality => {
            let providers = providers(args)?;
            let mut store = Store::planning(path(args, "state-dir")?)?;
            if matches!(handler, Handler::Validate) {
                review::validate(&mut store, text(args, "id")?, &providers)
            } else {
                review::quality(&mut store, text(args, "id")?, &providers)
            }
        }
        Handler::ProjectPassport => {
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                projects::passports::plan(store, path(args, "root")?, identity, at)
            })
        }
        Handler::TechnologyPlan => {
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                projects::technology::retained::plan(store, path(args, "root")?, identity, at)
            })
        }
        Handler::TechnologyFindings => {
            projects::technology::retained::findings(path(args, "state-dir")?, text(args, "id")?)
        }
        Handler::Forget => runtime::plan(path(args, "state-dir")?, |store, identity, at| {
            lifecycle::plan(
                store,
                text(args, "id")?,
                text(args, "expected-revision")?,
                identity,
                at,
            )
        }),
        Handler::SetupScaffoldPlan => {
            let plan = scaffold::setup::plan(
                path(args, "output")?,
                scaffold::setup::Request {
                    name: text(args, "name")?.into(),
                    harness_id: text(args, "harness")?.into(),
                },
            )?;
            Ok(serde_json::json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::SetupScaffoldApply => scaffold::setup::apply(
            &scaffold::setup::read(path(args, "plan")?)?,
            text(args, "plan-digest")?,
        ),
        Handler::ExportPlan => {
            let plan = setups::export::plan(
                path(args, "state-dir")?,
                setups::Source {
                    stable_id: text(args, "id")?.into(),
                    version: text(args, "version")?.into(),
                    passport_digest: text(args, "passport-digest")?.into(),
                },
                path(args, "output")?,
            )?;
            Ok(serde_json::json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::ExportApply => setups::export::apply(
            &setups::export::read(path(args, "plan")?)?,
            text(args, "plan-digest")?,
        ),
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
        Handler::Derive => {
            let provider = Info::parse(&files::read(path(args, "provider-info")?, 1024 * 1024)?)?;
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                derivation::plan(
                    store,
                    text(args, "id")?,
                    text(args, "expected-revision")?,
                    text(args, "source-harness")?,
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
        Handler::Import => {
            let request = importing::Request {
                root: path(args, "root")?.into(),
                harness_id: text(args, "harness")?.into(),
                scope: choice(args, "scope")?,
                root_kind: choice(args, "root-kind")?,
                candidates: args
                    .get_many::<String>("candidate-id")
                    .into_iter()
                    .flatten()
                    .cloned()
                    .collect(),
            };
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                importing::plan(store, request, identity, at)
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
        Handler::SetupFork | Handler::SetupRecast => {
            let source = setups::Source {
                stable_id: text(args, "id")?.into(),
                version: text(args, "version")?.into(),
                passport_digest: text(args, "passport-digest")?.into(),
            };
            let target = if matches!(handler, Handler::SetupRecast) {
                Some(text(args, "target-harness")?)
            } else {
                None
            };
            let provider = if target.is_some() {
                args.get_one::<PathBuf>("provider-info")
                    .map(|path| Info::parse(&files::read(path, 1024 * 1024)?))
                    .transpose()?
            } else {
                None
            };
            if let Some(provider) = &provider
                && provider.document()["harness_id"].as_str() != target
            {
                return Err(Failure::input(
                    "the provider declaration must name the recast target harness",
                ));
            }
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                if let Some(provider) = &provider {
                    setups::copies::plan_with_provider(store, source, provider, identity, at)
                } else {
                    setups::copies::plan(store, source, target, identity, at)
                }
            })
        }
        Handler::SetupRelease => {
            let increment: Increment = choice(args, "increment")?;
            runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                setups::releases::plan(
                    store,
                    text(args, "id")?,
                    text(args, "expected-revision")?,
                    increment,
                    identity,
                    at,
                )
            })
        }
        Handler::Compose | Handler::SetupUpdate => {
            let request: setups::Request = serde_json::from_value(canonical::parse(&files::read(
                path(args, "request")?,
                256 * 1024,
            )?)?)
            .map_err(|_| Failure::input("invalid setup composition request"))?;
            if matches!(handler, Handler::SetupUpdate) {
                runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                    setups::drafts::plan(
                        store,
                        text(args, "id")?,
                        text(args, "expected-revision")?,
                        request,
                        identity,
                        at,
                    )
                })
            } else {
                runtime::plan(path(args, "state-dir")?, |store, identity, at| {
                    setups::plan(store, request, identity, at)
                })
            }
        }
    }
}
