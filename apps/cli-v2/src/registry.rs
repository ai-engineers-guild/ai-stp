//! One command definition drives both the parser and its machine description.

use clap::{Arg, ArgAction, ArgMatches, Command, builder::ValueParser};
use serde_json::{Value, json};

use crate::{
    config, digest,
    error::{ErrorKind, Failure, Result},
    snapshot,
};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Clone, Copy)]
enum Handler {
    Version,
    Help,
    Capabilities,
    Snapshot,
    Config,
    Passport(&'static str),
    Versions,
}

#[derive(Clone, Copy)]
enum ParameterType {
    String,
    Boolean,
    Path,
    Strings,
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
            ParameterType::Path => argument.value_parser(ValueParser::path_buf()),
        }
    }

    fn descriptor(&self) -> Value {
        json!({"name": self.name, "kind": "option",
            "value_type": if matches!(self.kind, ParameterType::Boolean) { "boolean" } else { "string" },
            "required": self.required, "repeatable": matches!(self.kind, ParameterType::Strings), "summary": self.summary, "choices": []})
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

const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["capabilities"],
        summary: "List the capabilities implemented by this native preview.",
        parameters: &[],
        handler: Handler::Capabilities,
    },
    Declaration {
        path: &["component", "passport", "show"],
        summary: "Read and verify the current component passport from an explicit snapshot.",
        parameters: &[SNAPSHOT, SHA256, ID],
        handler: Handler::Passport("component"),
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

fn children(parent: Command, prefix: &[&str]) -> Command {
    let mut names = std::collections::BTreeSet::new();
    let mut parent = parent;
    for declaration in COMMANDS {
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
        if let Some(leaf) = COMMANDS.iter().find(|item| item.path == path) {
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
    COMMANDS.iter().map(|item| json!({
        "path": item.path, "summary": item.summary, "mutability": "read", "confirmation": "none",
        "parameters": item.parameters.iter().map(Parameter::descriptor).collect::<Vec<_>>(),
        "parameter_rules": [], "result_schema": null, "next_actions": []
    })).collect()
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
    let commands: Vec<_> = COMMANDS
        .iter()
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
    let declaration = COMMANDS
        .iter()
        .find(|item| item.path == path)
        .ok_or_else(|| Failure::new(ErrorKind::Internal, "parsed command has no handler"))?;
    match declaration.handler {
        Handler::Version => Ok(json!({"schema_version": 1, "cli_version": VERSION,
            "wire_schema_version": 1, "runtime": "rust", "release_channel": "preview"})),
        Handler::Capabilities => Ok(json!({"schema_version": 1, "cli_version": VERSION,
            "wire_schema_version": 1, "registry_digest": digest()?, "release_channel": "preview",
            "command_paths": COMMANDS.iter().map(|item| item.path.join(" ")).collect::<Vec<_>>(),
            "task_intents": [], "supported_harnesses": [], "catalog_enabled": false, "sync_enabled": false,
            "state_access": "explicit_snapshot_read_only", "readable_local_schema_versions": [snapshot::SCHEMA_VERSION]})),
        Handler::Help => help(
            leaf.get_one::<String>("path").map_or("", String::as_str),
            leaf.get_one::<String>("find").map_or("", String::as_str),
        ),
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
        Handler::Snapshot | Handler::Passport(_) | Handler::Versions => {
            let path = leaf
                .get_one::<std::path::PathBuf>("snapshot")
                .ok_or_else(|| Failure::input("snapshot is required"))?;
            let digest = leaf
                .get_one::<String>("sha256")
                .ok_or_else(|| Failure::input("sha256 is required"))?;
            let state = snapshot::Snapshot::open(path, digest)?;
            match declaration.handler {
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
