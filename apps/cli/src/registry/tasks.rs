//! Durable task command adapters; all effects belong to native application services.

use std::path::PathBuf;

use clap::ArgMatches;
use serde_json::{Value, json};

use super::{Declaration, Parameter, ParameterType, STATE_DIR};
use crate::{
    error::{Failure, Result},
    files, tasks,
};

#[derive(Clone, Copy)]
pub(super) enum Handler {
    Intents,
    InputSchema,
    Start,
    Answer,
    Continue,
    Status,
    Cancel,
    List,
}

impl Handler {
    pub fn mutability(self) -> &'static str {
        match self {
            Self::Intents | Self::InputSchema | Self::Status | Self::List => "read",
            _ => "apply",
        }
    }
}

const TASK: Parameter = Parameter {
    name: "task",
    summary: "Exact durable task identity; omission requires exactly one unsettled task.",
    kind: ParameterType::String,
    required: false,
};
const REVISION: Parameter = Parameter {
    name: "revision",
    summary: "Exact current task revision from its last response.",
    kind: ParameterType::String,
    required: true,
};

pub(super) const COMMANDS: &[Declaration] = &[
    Declaration {
        path: &["task", "input-schema"],
        summary: "Read the exact embedded input schema for one implemented task intent without local state.",
        parameters: &[Parameter {
            name: "intent",
            summary: "Implemented native task intent.",
            kind: ParameterType::Choice(tasks::INTENTS),
            required: true,
        }],
        handler: super::Handler::Task(Handler::InputSchema),
    },
    Declaration {
        path: &["task", "intents"],
        summary: "List only completed native task services and their accepted input fields.",
        parameters: &[],
        handler: super::Handler::Task(Handler::Intents),
    },
    Declaration {
        path: &["task", "start"],
        summary: "Start or recover an exact idempotent native task in the explicit isolated registry.",
        parameters: &[
            STATE_DIR,
            Parameter {
                name: "intent",
                summary: "Implemented business intent.",
                kind: ParameterType::Choice(tasks::INTENTS),
                required: true,
            },
            Parameter {
                name: "idempotency-key",
                summary: "Stable original-request key: 16 to 128 ASCII letters, digits, '.', '_', '~' or '-'.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "input",
                summary: "Closed intent input JSON file, at most 16 KiB; omission starts with questions.",
                kind: ParameterType::Path,
                required: false,
            },
        ],
        handler: super::Handler::Task(Handler::Start),
    },
    Declaration {
        path: &["task", "answer"],
        summary: "Answer one current task question against its exact revision and continue in-process.",
        parameters: &[
            STATE_DIR,
            TASK,
            REVISION,
            Parameter {
                name: "question-id",
                summary: "Exact current question identifier.",
                kind: ParameterType::String,
                required: true,
            },
            Parameter {
                name: "value",
                summary: "Literal string answer; never evaluated as a shell command.",
                kind: ParameterType::String,
                required: true,
            },
        ],
        handler: super::Handler::Task(Handler::Answer),
    },
    Declaration {
        path: &["task", "continue"],
        summary: "Recover the retained child plan or return the exact settled task result.",
        parameters: &[STATE_DIR, TASK, REVISION],
        handler: super::Handler::Task(Handler::Continue),
    },
    Declaration {
        path: &["task", "status"],
        summary: "Read a task without advancing effects or opening the source directory.",
        parameters: &[STATE_DIR, TASK],
        handler: super::Handler::Task(Handler::Status),
    },
    Declaration {
        path: &["task", "cancel"],
        summary: "Cancel before publication or recover the original committed outcome; partially published configuration requires forward recovery.",
        parameters: &[STATE_DIR, TASK, REVISION],
        handler: super::Handler::Task(Handler::Cancel),
    },
    Declaration {
        path: &["task", "list"],
        summary: "List unsettled tasks without exposing source payloads or credentials.",
        parameters: &[STATE_DIR],
        handler: super::Handler::Task(Handler::List),
    },
];

pub(super) fn dispatch(handler: Handler, args: &ArgMatches) -> Result<Value> {
    if matches!(handler, Handler::Intents) {
        return tasks::intents();
    }
    if matches!(handler, Handler::InputSchema) {
        return tasks::input_schema(
            args.get_one::<String>("intent")
                .ok_or_else(|| Failure::input("intent is required"))?,
        );
    }
    let parent = args
        .get_one::<PathBuf>("state-dir")
        .ok_or_else(|| Failure::input("state directory is required"))?;
    if !parent.is_absolute() {
        return Err(Failure::input("task state directory must be absolute"));
    }
    let text = |name: &str| {
        args.get_one::<String>(name)
            .map(String::as_str)
            .ok_or_else(|| Failure::input("required task argument is absent"))
    };
    match handler {
        Handler::Intents => tasks::intents(),
        Handler::InputSchema => tasks::input_schema(text("intent")?),
        Handler::Start => {
            let input = args
                .get_one::<PathBuf>("input")
                .map(|path| {
                    files::read(path, 16 * 1024).and_then(|bytes| crate::wire::parse(&bytes))
                })
                .transpose()?
                .unwrap_or_else(|| json!({}));
            tasks::start(parent, text("intent")?, text("idempotency-key")?, input)
        }
        Handler::List => tasks::list(parent),
        Handler::Status => {
            tasks::status(parent, args.get_one::<String>("task").map(String::as_str))
        }
        Handler::Answer | Handler::Continue | Handler::Cancel => {
            let revision = text("revision")?
                .parse::<i64>()
                .ok()
                .filter(|v| *v > 0)
                .ok_or_else(|| Failure::input("task revision must be a positive integer"))?;
            let answer = if matches!(handler, Handler::Answer) {
                Some((text("question-id")?, text("value")?))
            } else {
                None
            };
            tasks::advance(
                parent,
                args.get_one::<String>("task").map(String::as_str),
                revision,
                answer,
                matches!(handler, Handler::Cancel),
            )
        }
    }
}

pub(super) fn continuations(matches: &ArgMatches, result: &Result<Value>) -> Vec<Value> {
    let Some(("task", family)) = matches.subcommand() else {
        return Vec::new();
    };
    let Some((_, leaf)) = family.subcommand() else {
        return Vec::new();
    };
    let Some(parent) = leaf.try_get_one::<PathBuf>("state-dir").ok().flatten() else {
        return Vec::new();
    };
    result
        .as_ref()
        .map_or_else(|_| Vec::new(), |data| tasks::continuations(parent, data))
}
