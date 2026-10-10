//! One command definition drives both the parser and its machine description.

mod local;
mod providers;
mod reports;
mod selections;

use clap::{Arg, ArgAction, ArgMatches, Command, builder::ValueParser};
use serde_json::{Value, json};

use crate::{
    authoring::{scaffold, source_project, templates},
    catalog, config, digest, environment,
    error::{ErrorKind, Failure, Result},
    identity, projects, selection, snapshot,
};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Clone, Copy)]
enum Handler {
    Local(local::Handler),
    Report(reports::Handler),
    Provider(providers::Handler),
    Selection(selections::Handler),
    Version,
    Help,
    Capabilities,
    Snapshot,
    Config,
    Passport(&'static str),
    Versions,
    ProjectIndex,
    ProjectSymbols,
    ProjectTechnology,
    ProjectDiscover,
    CatalogSearch,
    CatalogShow,
    CatalogVersion,
    CatalogAcquirePlan,
    EnvironmentRequirements,
    DependencyGraph,
    TemplateRender,
    ScaffoldPlan,
    ScaffoldApply,
    SourceInspect,
    SourceCapture,
    SourceFetch,
    PackageSourceFetch,
    SourceAddress(bool),
    IdentityPlan,
    IdentityApply,
    IdentityShow,
}

#[derive(Clone, Copy)]
enum ParameterType {
    String,
    Boolean,
    Path,
    Paths,
    Strings,
    Choice(&'static [&'static str]),
}

struct Parameter {
    name: &'static str,
    summary: &'static str,
    kind: ParameterType,
    required: bool,
}

impl Parameter {
    fn argument(&self) -> Arg {
        let argument = Arg::new(self.name)
            .long(self.name)
            .help(self.summary)
            .required(self.required);
        match self.kind {
            ParameterType::Boolean => argument.action(ArgAction::SetTrue),
            ParameterType::String => argument.action(ArgAction::Set),
            ParameterType::Strings => argument.action(ArgAction::Append),
            ParameterType::Choice(values) => argument.value_parser(
                clap::builder::PossibleValuesParser::new(values.iter().copied()),
            ),
            ParameterType::Path => argument.value_parser(ValueParser::path_buf()),
            ParameterType::Paths => argument
                .value_parser(ValueParser::path_buf())
                .action(ArgAction::Append),
        }
    }

    fn descriptor(&self) -> Value {
        json!({"name": self.name, "kind": "option",
            "value_type": if matches!(self.kind, ParameterType::Boolean) { "boolean" } else { "string" },
            "required": self.required, "repeatable": matches!(self.kind, ParameterType::Strings | ParameterType::Paths), "summary": self.summary,
            "choices": match self.kind {ParameterType::Choice(values) => values, _ => &[]}})
    }
}

struct Declaration {
    path: &'static [&'static str],
    summary: &'static str,
    parameters: &'static [Parameter],
    handler: Handler,
}

const JSON: Parameter = Parameter {
    name: "json",
    summary: "Return one envelope v1 JSON object.",
    kind: ParameterType::Boolean,
    required: false,
};

const CONFIG: Parameter = Parameter {
    name: "config",
    summary: "Explicit YAML configuration file; omission uses preview defaults.",
    kind: ParameterType::Path,
    required: false,
};

const SNAPSHOT: Parameter = Parameter {
    name: "snapshot",
    summary: "Standalone schema-53 SQLite backup in DELETE journal mode (at most 128 MiB).",
    kind: ParameterType::Path,
    required: true,
};
const SHA256: Parameter = Parameter {
    name: "sha256",
    summary: "Expected sha256:<hex> digest of the exact backup bytes.",
    kind: ParameterType::String,
    required: true,
};
const ID: Parameter = Parameter {
    name: "id",
    summary: "Exact stable object identifier.",
    kind: ParameterType::String,
    required: true,
};

const ROOT: Parameter = Parameter {
    name: "root",
    summary: "Explicit project directory; home and filesystem roots are refused.",
    kind: ParameterType::Path,
    required: true,
};

const SOURCE: Parameter = Parameter {
    name: "source",
    summary: "Published name, GitHub address, explicit local path or collection address; at most 2 KiB.",
    kind: ParameterType::String,
    required: true,
};

const SOURCE_ROOT: Parameter = Parameter {
    name: "root",
    summary: "Explicit absolute base for a relative local address; parsing does not access its files.",
    kind: ParameterType::Path,
    required: false,
};

const SOURCE_PATH: Parameter = Parameter {
    name: "path",
    summary: "Portable relative file or directory under the explicit root; at most 512 bytes.",
    kind: ParameterType::String,
    required: true,
};

const STATE_DIR: Parameter = Parameter {
    name: "state-dir",
    summary: "Existing parent directory for isolated native preview state.",
    kind: ParameterType::Path,
    required: true,
};

const KIND: Parameter = Parameter {
    name: "kind",
    summary: "Public catalog object kind.",
    kind: ParameterType::Choice(&["component", "setup"]),
    required: true,
};
const CACHE: Parameter = Parameter {
    name: "cache-dir",
    summary: "Existing parent directory for an isolated, bounded public catalog cache.",
    kind: ParameterType::Path,
    required: false,
};
const OFFLINE: Parameter = Parameter {
    name: "offline",
    summary: "Read only the explicit cache without opening a network connection.",
    kind: ParameterType::Boolean,
    required: false,
};

const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["capabilities"],
        summary: "List the capabilities implemented by this native preview.",
        parameters: &[],
        handler: Handler::Capabilities,
    },
    Declaration {
        path: &["device", "initialize", "apply"],
        summary: "Initialize or recover exactly the planned offline identity without replacing an existing key.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Explicit JSON plan from device initialize plan.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact initialization plan digest returned by planning.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: Handler::IdentityApply,
    },
    Declaration {
        path: &["device", "initialize", "plan"],
        summary: "Plan a new offline owner and Ed25519 device without opening credentials or writing state.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "credential-store",
                summary: "Explicit credential store; file requires Unix private permissions and is not encrypted at rest. No automatic fallback.",
                kind: ParameterType::Choice(&["os_keyring", "file"]),
                required: true,
            },
        ],
        handler: Handler::IdentityPlan,
    },
    Declaration {
        path: &["device", "show"],
        summary: "Verify the isolated local key and return its public device identity without initializing it.",
        parameters: &[STATE_DIR],
        handler: Handler::IdentityShow,
    },
    Declaration {
        path: &["component", "passport", "show"],
        summary: "Read and verify the current component passport from an explicit snapshot.",
        parameters: &[SNAPSHOT, SHA256, ID],
        handler: Handler::Passport("component"),
    },
    Declaration {
        path: &["component", "scaffold", "apply"],
        summary: "Create exactly the planned portable source tree without replacing any path.",
        parameters: &[
            Parameter {
                name: "plan",
                summary: "Explicit JSON plan from component scaffold plan.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "plan-digest",
                summary: "Exact scaffold plan digest returned by planning.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: Handler::ScaffoldApply,
    },
    Declaration {
        path: &["component", "scaffold", "plan"],
        summary: "Preview every byte of a minimal portable component source tree.",
        parameters: &[
            Parameter {
                name: "type",
                summary: "Implemented portable source kind.",
                kind: ParameterType::Choice(scaffold::KINDS),
                required: true,
            },
            Parameter {
                name: "language",
                summary: "Use none for declarative components and an executable language for cli.",
                kind: ParameterType::Choice(scaffold::LANGUAGES),
                required: true,
            },
            Parameter {
                name: "name",
                summary: "Lowercase component slug, at most 64 ASCII characters.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "output",
                summary: "New authoring directory below an existing parent.",
                kind: ParameterType::Path,
                required: true,
            },
        ],
        handler: Handler::ScaffoldPlan,
    },
    Declaration {
        path: &["component", "source", "inspect"],
        summary: "Inspect exact portable source bytes and unresolved scaffold fields without executing code.",
        parameters: &[ROOT],
        handler: Handler::SourceInspect,
    },
    Declaration {
        path: &["component", "source", "package", "fetch"],
        summary: "Observe exact official package metadata and checksum evidence without execution or trust grants.",
        parameters: &[
            Parameter {
                name: "ecosystem",
                summary: "Implemented official package registry.",
                kind: ParameterType::Choice(&["go", "pypi", "npm", "crates.io", "pub.dev"]),
                required: true,
            },
            Parameter {
                name: "name",
                summary: "Exact registry package name or Go module path.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "version",
                summary: "Exact registry version; Go requires the v prefix.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "filename",
                summary: "Exact distribution filename, required only for PyPI.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "platform",
                summary: "Exact wheel platform tag or source for an sdist, required only for PyPI.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: Handler::PackageSourceFetch,
    },
    Declaration {
        path: &["component", "source", "fetch"],
        summary: "Observe a public GitHub source pinned to a full commit; bounded download without credentials or target writes.",
        parameters: &[SOURCE],
        handler: Handler::SourceFetch,
    },
    Declaration {
        path: &["component", "source", "capture"],
        summary: "Capture an exact bounded local source snapshot without writing state or granting trust.",
        parameters: &[ROOT, SOURCE_PATH],
        handler: Handler::SourceCapture,
    },
    Declaration {
        path: &["component", "source", "parse"],
        summary: "Parse a bounded source address without filesystem access, network or provenance claims.",
        parameters: &[SOURCE, SOURCE_ROOT],
        handler: Handler::SourceAddress(false),
    },
    Declaration {
        path: &["component", "source", "resolve"],
        summary: "Pin a GitHub intent to a supplied exact commit without claiming remote verification.",
        parameters: &[
            SOURCE,
            Parameter {
                name: "commit",
                summary: "Full lowercase 40-character commit SHA; must agree with an already exact address.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: Handler::SourceAddress(true),
    },
    Declaration {
        path: &["component", "template", "render"],
        summary: "Render a bounded portable template with literal CommonMark code blocks.",
        parameters: &[
            Parameter {
                name: "template",
                summary: "Explicit UTF-8 authoring template, at most 64 KiB.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "harness",
                summary: "Concrete target harness.",
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
            },
            Parameter {
                name: "name",
                summary: "Lowercase component slug, at most 64 ASCII characters.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "component-root",
                summary: "Portable target-relative component path.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: Handler::TemplateRender,
    },
    Declaration {
        path: &["component", "version", "list"],
        summary: "Verify immutable version history and its next minor coordinate.",
        parameters: &[SNAPSHOT, SHA256, ID],
        handler: Handler::Versions,
    },
    Declaration {
        path: &["config", "show"],
        summary: "Read explicit configuration with invocation-only overrides and value sources.",
        parameters: &[
            CONFIG,
            Parameter {
                name: "set",
                summary: "Override a declared path=value for this invocation only.",
                kind: ParameterType::Strings,
                required: false,
            },
        ],
        handler: Handler::Config,
    },
    Declaration {
        path: &["config", "validate"],
        summary: "Validate explicit configuration without creating or updating any state.",
        parameters: &[CONFIG],
        handler: Handler::Config,
    },
    Declaration {
        path: &["environment", "requirements"],
        summary: "Verify exact setup prerequisites and variable presence without executing preparation.",
        parameters: &[
            SNAPSHOT,
            SHA256,
            Parameter {
                name: "project",
                summary: "Project identity already bound to the target in the snapshot.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "target",
                summary: "Absolute project target; a moved marker may reclaim only an absent root.",
                kind: ParameterType::Path,
                required: true,
            },
            Parameter {
                name: "setup",
                summary: "Exact setup id@X.Y; repeat for multiple setups.",
                kind: ParameterType::Strings,
                required: true,
            },
        ],
        handler: Handler::EnvironmentRequirements,
    },
    Declaration {
        path: &["help"],
        summary: "Describe implemented commands and their parameters.",
        parameters: &[
            Parameter {
                name: "agent",
                summary: "Request the machine command registry.",
                kind: ParameterType::Boolean,
                required: false,
            },
            Parameter {
                name: "path",
                summary: "Keep commands under this space-separated path.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "find",
                summary: "Filter command paths and summaries by text.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: Handler::Help,
    },
    Declaration {
        path: &["passport", "developer", "show"],
        summary: "Read the verified developer passport without creating an identity.",
        parameters: &[SNAPSHOT, SHA256],
        handler: Handler::Passport("developer"),
    },
    Declaration {
        path: &["passport", "device", "show"],
        summary: "Read the verified device passport without refreshing observations.",
        parameters: &[SNAPSHOT, SHA256],
        handler: Handler::Passport("device"),
    },
    Declaration {
        path: &["project", "discover"],
        summary: "Find projects and nested repositories with bounded traversal and no writes.",
        parameters: &[ROOT],
        handler: Handler::ProjectDiscover,
    },
    Declaration {
        path: &["project", "index"],
        summary: "Describe and hash bounded project files without following symlinks or reading credentials.",
        parameters: &[ROOT],
        handler: Handler::ProjectIndex,
    },
    Declaration {
        path: &["project", "technology", "inspect"],
        summary: "Observe bounded technology declarations and lock records without executing, installing or publishing anything.",
        parameters: &[ROOT],
        handler: Handler::ProjectTechnology,
    },
    Declaration {
        path: &["project", "symbols"],
        summary: "Summarize bounded source declarations with explicit syntax-tree or approximate line-scan evidence.",
        parameters: &[ROOT],
        handler: Handler::ProjectSymbols,
    },
    Declaration {
        path: &["registry", "search"],
        summary: "Read one live public catalog page with separate trust lanes and no account.",
        parameters: &[
            CONFIG,
            KIND,
            Parameter {
                name: "query",
                summary: "Search text, from 1 to 200 characters.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "cursor",
                summary: "Opaque next-page cursor returned by the catalog.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "limit",
                summary: "Page size from 1 to 100; defaults to 20.",
                kind: ParameterType::String,
                required: false,
            },
            Parameter {
                name: "include-experimental",
                summary: "Include experimental results in their separate lane.",
                kind: ParameterType::Boolean,
                required: false,
            },
        ],
        handler: Handler::CatalogSearch,
    },
    Declaration {
        path: &["registry", "show"],
        summary: "Read one public object, falling back to an explicit cache only on unavailability.",
        parameters: &[CONFIG, KIND, ID, CACHE, OFFLINE],
        handler: Handler::CatalogShow,
    },
    Declaration {
        path: &["registry", "version"],
        summary: "Read and verify an exact public version and preserve its cache observation time.",
        parameters: &[
            CONFIG,
            KIND,
            ID,
            CACHE,
            OFFLINE,
            Parameter {
                name: "version",
                summary: "Exact immutable X.Y version.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: Handler::CatalogVersion,
    },
    Declaration {
        path: &["registry", "acquire", "plan"],
        summary: "Capture an exact public setup graph and all declared projections for atomic local acquisition.",
        parameters: &[
            STATE_DIR,
            CONFIG,
            ID,
            Parameter {
                name: "version",
                summary: "Exact immutable setup X.Y version.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: Handler::CatalogAcquirePlan,
    },
    Declaration {
        path: &["select", "graph"],
        summary: "Resolve exact dependencies from isolated native state or an explicit verified snapshot, with deterministic ordering and complete refusals.",
        parameters: &[
            Parameter {
                required: false,
                ..STATE_DIR
            },
            Parameter {
                required: false,
                ..SNAPSHOT
            },
            Parameter {
                required: false,
                ..SHA256
            },
            Parameter {
                name: "member",
                summary: "Exact component or setup id@X.Y; repeat for multiple roots.",
                kind: ParameterType::Strings,
                required: false,
            },
            Parameter {
                name: "proposal",
                summary: "Existing proposal whose exact members are the graph roots.",
                kind: ParameterType::String,
                required: false,
            },
        ],
        handler: Handler::DependencyGraph,
    },
    Declaration {
        path: &["snapshot", "inspect"],
        summary: "Inspect an explicit schema-53 SQLite backup without opening live state.",
        parameters: &[SNAPSHOT, SHA256],
        handler: Handler::Snapshot,
    },
    Declaration {
        path: &["version"],
        summary: "Report the native preview build and its wire version.",
        parameters: &[],
        handler: Handler::Version,
    },
];

fn declarations() -> impl Iterator<Item = &'static Declaration> {
    COMMANDS
        .iter()
        .chain(local::COMMANDS)
        .chain(reports::COMMANDS)
        .chain(providers::COMMANDS)
        .chain(selections::COMMANDS)
}

fn children(parent: Command, prefix: &[&str]) -> Command {
    let mut names = std::collections::BTreeSet::new();
    let mut parent = parent;
    for declaration in declarations() {
        if !declaration.path.starts_with(prefix) || declaration.path.len() <= prefix.len() {
            continue;
        }
        let name = declaration.path[prefix.len()];
        if !names.insert(name) {
            continue;
        }
        let mut path = prefix.to_vec();
        path.push(name);
        let mut command = Command::new(name);
        if let Some(leaf) = declarations().find(|item| item.path == path) {
            command = command.about(leaf.summary);
            for parameter in leaf.parameters {
                command = command.arg(parameter.argument());
            }
        } else {
            command = command.subcommand_required(true);
        }
        parent = parent.subcommand(children(command, &path));
    }
    parent
}

pub fn parser() -> Command {
    children(
        Command::new("ai-stp-v2")
            .about("Native ai-stp preview: only implemented commands are advertised.")
            .disable_help_subcommand(true)
            .arg(JSON.argument().global(true)),
        &[],
    )
}

pub fn error_descriptors() -> Vec<Value> {
    let mut errors: Vec<_> = ErrorKind::ALL
        .into_iter()
        .map(ErrorKind::descriptor)
        .collect();
    errors.sort_by(|a, b| a["code"].as_str().cmp(&b["code"].as_str()));
    errors
}

fn descriptors() -> Vec<Value> {
    declarations().map(|item| json!({
        "path": item.path, "summary": item.summary,
        "mutability": mutability(item.handler),
        "confirmation": if mutability(item.handler) == "apply" { "plan_digest" } else { "none" },
        "parameters": item.parameters.iter().map(Parameter::descriptor).collect::<Vec<_>>(),
        "parameter_rules": [], "result_schema": null, "next_actions": []
    })).collect()
}

fn mutability(handler: Handler) -> &'static str {
    match handler {
        Handler::ScaffoldPlan | Handler::IdentityPlan | Handler::CatalogAcquirePlan => "plan",
        Handler::ScaffoldApply | Handler::IdentityApply => "apply",
        Handler::Local(handler) => handler.mutability(),
        Handler::Selection(handler) => handler.mutability(),
        Handler::Provider(providers::Handler::Plan) => "plan",
        _ => "read",
    }
}

pub fn digest() -> Result<String> {
    let errors: Vec<_> = error_descriptors()
        .into_iter()
        .map(|mut item| {
            if let Some(object) = item.as_object_mut() {
                object.remove("description");
            }
            item
        })
        .collect();
    digest::canonical(
        "ai-stp:cli-registry:v1",
        &json!({"global_options": [JSON.descriptor()], "commands": descriptors(), "error_codes": errors}),
    )
}

pub fn help(path: &str, find: &str) -> Result<Value> {
    let prefix: Vec<_> = path.split_whitespace().collect();
    let needle = find.to_lowercase();
    let commands: Vec<_> = declarations()
        .zip(descriptors())
        .filter_map(|(item, descriptor)| {
            (item.path.starts_with(&prefix)
                && format!("{} {}", item.path.join(" "), item.summary)
                    .to_lowercase()
                    .contains(&needle))
            .then_some(descriptor)
        })
        .collect();
    if commands.is_empty() {
        return Err(Failure::new(
            ErrorKind::NotFound,
            "no implemented command matches this help query",
        ));
    }
    Ok(
        json!({"schema_version": 1, "cli_version": VERSION, "registry_digest": digest()?,
        "global_options": [JSON.descriptor()], "commands": commands, "error_codes": error_descriptors()}),
    )
}

pub fn dispatch(matches: &ArgMatches) -> Result<Value> {
    let mut leaf = matches;
    let mut path = Vec::new();
    while let Some((name, child)) = leaf.subcommand() {
        path.push(name);
        leaf = child;
    }
    if path.is_empty() {
        return help("", "");
    }
    let declaration = declarations()
        .find(|item| item.path == path)
        .ok_or_else(|| Failure::new(ErrorKind::Internal, "parsed command has no handler"))?;
    match declaration.handler {
        Handler::Local(handler) => local::dispatch(handler, leaf),
        Handler::Report(handler) => reports::dispatch(handler, leaf),
        Handler::Provider(handler) => providers::dispatch(handler, leaf),
        Handler::Selection(handler) => selections::dispatch(handler, leaf),
        Handler::Version => Ok(json!({"schema_version": 1, "cli_version": VERSION,
            "wire_schema_version": 1, "runtime": "rust", "release_channel": "preview"})),
        Handler::Capabilities => Ok(json!({"schema_version": 1, "cli_version": VERSION,
            "wire_schema_version": 1, "registry_digest": digest()?, "release_channel": "preview",
            "command_paths": declarations().map(|item| item.path.join(" ")).collect::<Vec<_>>(),
            "task_intents": [], "supported_harnesses": [], "catalog_enabled": true, "sync_enabled": false,
            "state_access": "explicit_snapshot_and_isolated_authoring", "cache_access": "explicit_public_catalog_cache",
            "identity_access": "explicit_isolated_device",
            "authoring_access": "identity_bound_local_plans", "readable_local_schema_versions": [snapshot::SCHEMA_VERSION]})),
        Handler::Help => help(
            leaf.get_one::<String>("path").map_or("", String::as_str),
            leaf.get_one::<String>("find").map_or("", String::as_str),
        ),
        Handler::TemplateRender => templates::read(
            leaf.get_one::<std::path::PathBuf>("template")
                .ok_or_else(|| Failure::input("template is required"))?,
            leaf.get_one::<String>("harness")
                .ok_or_else(|| Failure::input("harness is required"))?,
            leaf.get_one::<String>("name")
                .ok_or_else(|| Failure::input("name is required"))?,
            leaf.get_one::<String>("component-root")
                .ok_or_else(|| Failure::input("component root is required"))?,
        ),
        Handler::ScaffoldPlan => {
            let text = |name| {
                leaf.get_one::<String>(name)
                    .cloned()
                    .ok_or_else(|| Failure::input("scaffold parameter is required"))
            };
            let plan = scaffold::plan(
                leaf.get_one::<std::path::PathBuf>("output")
                    .ok_or_else(|| Failure::input("output is required"))?,
                scaffold::Request {
                    component_type: text("type")?,
                    name: text("name")?,
                    language: text("language")?,
                },
            )?;
            Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
        }
        Handler::ScaffoldApply => scaffold::apply(
            &scaffold::read(
                leaf.get_one::<std::path::PathBuf>("plan")
                    .ok_or_else(|| Failure::input("plan is required"))?,
            )?,
            leaf.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("plan digest is required"))?,
        ),
        Handler::SourceInspect => source_project::inspect(
            leaf.get_one::<std::path::PathBuf>("root")
                .ok_or_else(|| Failure::input("source root is required"))?,
        ),
        Handler::PackageSourceFetch => crate::sources::package::fetch(
            leaf.get_one::<String>("ecosystem")
                .ok_or_else(|| Failure::input("ecosystem is required"))?,
            leaf.get_one::<String>("name")
                .ok_or_else(|| Failure::input("package name is required"))?,
            leaf.get_one::<String>("version")
                .ok_or_else(|| Failure::input("package version is required"))?,
            leaf.get_one::<String>("filename").map(String::as_str),
            leaf.get_one::<String>("platform").map(String::as_str),
        ),
        Handler::SourceFetch => crate::sources::github::fetch(
            leaf.get_one::<String>("source")
                .ok_or_else(|| Failure::input("source is required"))?,
        ),
        Handler::SourceCapture => crate::sources::local::capture(
            leaf.get_one::<std::path::PathBuf>("root")
                .ok_or_else(|| Failure::input("source root is required"))?,
            leaf.get_one::<String>("path")
                .ok_or_else(|| Failure::input("relative source path is required"))?,
        ),
        Handler::SourceAddress(resolve) => crate::sources::inspect(
            leaf.get_one::<String>("source")
                .ok_or_else(|| Failure::input("source is required"))?,
            if resolve {
                None
            } else {
                leaf.get_one::<std::path::PathBuf>("root")
                    .map(std::path::PathBuf::as_path)
            },
            if resolve {
                Some(
                    leaf.get_one::<String>("commit")
                        .ok_or_else(|| Failure::input("commit is required"))?
                        .as_str(),
                )
            } else {
                None
            },
        ),
        Handler::CatalogAcquirePlan => crate::authoring::runtime::plan(
            leaf.get_one::<std::path::PathBuf>("state-dir")
                .ok_or_else(|| Failure::input("state directory is required"))?,
            |_, identity, at| {
                catalog::acquisition::plan(
                    leaf.get_one::<std::path::PathBuf>("config")
                        .map(std::path::PathBuf::as_path),
                    leaf.get_one::<String>("id")
                        .ok_or_else(|| Failure::input("setup id is required"))?,
                    leaf.get_one::<String>("version")
                        .ok_or_else(|| Failure::input("setup version is required"))?,
                    identity,
                    at,
                )
            },
        ),
        Handler::IdentityPlan => {
            let storage = match leaf
                .get_one::<String>("credential-store")
                .map(String::as_str)
            {
                Some("os_keyring") => identity::Storage::OsKeyring,
                Some("file") => identity::Storage::File,
                _ => return Err(Failure::input("credential store is required")),
            };
            let plan = identity::plan(
                leaf.get_one::<std::path::PathBuf>("state-dir")
                    .ok_or_else(|| Failure::input("state directory is required"))?,
                storage,
                &format!("{:.3}", jiff::Timestamp::now()),
            )?;
            Ok(json!({"plan_digest": plan.digest()?, "plan": plan}))
        }
        Handler::IdentityApply => Ok(identity::apply(
            &identity::read_plan(
                leaf.get_one::<std::path::PathBuf>("plan")
                    .ok_or_else(|| Failure::input("plan is required"))?,
            )?,
            leaf.get_one::<String>("plan-digest")
                .ok_or_else(|| Failure::input("plan digest is required"))?,
            &format!("{:.3}", jiff::Timestamp::now()),
        )?
        .report()),
        Handler::IdentityShow => identity::current(
            leaf.get_one::<std::path::PathBuf>("state-dir")
                .ok_or_else(|| Failure::input("state directory is required"))?,
        )?
        .map(|identity| identity.report())
        .ok_or_else(|| {
            Failure::new(
                ErrorKind::NotFound,
                "the native preview identity has not been initialized",
            )
        }),
        Handler::Config => config::show(
            leaf.get_one::<std::path::PathBuf>("config")
                .map(|p| p.as_path()),
            &leaf
                .try_get_many::<String>("set")
                .ok()
                .flatten()
                .map(|values| values.cloned().collect::<Vec<_>>())
                .unwrap_or_default(),
        ),
        Handler::ProjectIndex
        | Handler::ProjectDiscover
        | Handler::ProjectSymbols
        | Handler::ProjectTechnology => {
            let root = leaf
                .get_one::<std::path::PathBuf>("root")
                .ok_or_else(|| Failure::input("root is required"))?;
            match declaration.handler {
                Handler::ProjectIndex => projects::index(root),
                Handler::ProjectSymbols => projects::symbols(root),
                Handler::ProjectTechnology => projects::technology::inspect(root),
                _ => projects::discover(root),
            }
        }
        Handler::CatalogSearch | Handler::CatalogShow | Handler::CatalogVersion => {
            let reader = catalog::Reader::new(
                leaf.get_one::<std::path::PathBuf>("config")
                    .map(|p| p.as_path()),
                leaf.try_get_one::<std::path::PathBuf>("cache-dir")
                    .ok()
                    .flatten()
                    .map(|p| p.as_path()),
                leaf.try_get_one::<bool>("offline")
                    .ok()
                    .flatten()
                    .copied()
                    .unwrap_or(false),
            )?;
            let kind = catalog::Kind::parse(
                leaf.get_one::<String>("kind")
                    .ok_or_else(|| Failure::input("kind is required"))?,
            )?;
            if matches!(declaration.handler, Handler::CatalogSearch) {
                reader.search(
                    kind,
                    leaf.get_one::<String>("query").map(String::as_str),
                    leaf.get_one::<String>("cursor").map(String::as_str),
                    leaf.get_one::<String>("limit").map(String::as_str),
                    leaf.get_flag("include-experimental"),
                )
            } else {
                reader.show(
                    kind,
                    leaf.get_one::<String>("id")
                        .ok_or_else(|| Failure::input("id is required"))?,
                    leaf.try_get_one::<String>("version")
                        .ok()
                        .flatten()
                        .map(String::as_str),
                )
            }
        }
        Handler::DependencyGraph => {
            let members = leaf
                .get_many::<String>("member")
                .map(|items| items.cloned().collect::<Vec<_>>())
                .unwrap_or_default();
            let proposal = leaf.get_one::<String>("proposal").map(String::as_str);
            match (
                leaf.get_one::<std::path::PathBuf>("state-dir"),
                leaf.get_one::<std::path::PathBuf>("snapshot"),
                leaf.get_one::<String>("sha256"),
            ) {
                (Some(parent), None, None) => selection::graph::local(parent, &members, proposal),
                (None, Some(path), Some(digest)) => selection::graph::read(
                    &snapshot::Snapshot::open(path, digest)?,
                    &members,
                    proposal,
                ),
                _ => Err(Failure::input(
                    "name either state-dir or both snapshot and sha256",
                )),
            }
        }
        Handler::Snapshot
        | Handler::Passport(_)
        | Handler::Versions
        | Handler::EnvironmentRequirements => {
            let path = leaf
                .get_one::<std::path::PathBuf>("snapshot")
                .ok_or_else(|| Failure::input("snapshot is required"))?;
            let digest = leaf
                .get_one::<String>("sha256")
                .ok_or_else(|| Failure::input("sha256 is required"))?;
            let state = snapshot::Snapshot::open(path, digest)?;
            match declaration.handler {
                Handler::EnvironmentRequirements => environment::requirements(
                    &state,
                    leaf.get_one::<String>("project")
                        .ok_or_else(|| Failure::input("project is required"))?,
                    leaf.get_one::<std::path::PathBuf>("target")
                        .ok_or_else(|| Failure::input("target is required"))?,
                    &leaf
                        .get_many::<String>("setup")
                        .ok_or_else(|| Failure::input("setup is required"))?
                        .cloned()
                        .collect::<Vec<_>>(),
                ),
                Handler::Passport(kind) => state.passport(
                    kind,
                    leaf.try_get_one::<String>("id")
                        .ok()
                        .flatten()
                        .map(String::as_str),
                ),
                Handler::Versions => state.versions(
                    leaf.get_one::<String>("id")
                        .ok_or_else(|| Failure::input("id is required"))?,
                ),
                _ => Ok(state.report()),
            }
        }
    }
}
