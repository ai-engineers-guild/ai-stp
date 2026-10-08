//! Headless native services. The executable only renders their result.

mod archive;
pub mod artifacts;
pub mod authoring;
pub mod bundle;
pub mod canonical;
pub mod catalog;
pub mod config;
pub mod digest;
pub mod environment;
pub mod error;
mod files;
pub mod harnesses;
mod http;
pub mod objects;
pub mod passport;
pub mod process;
pub mod projection;
pub mod projects;
pub mod provenance;
pub mod provider;
pub mod registry;
pub mod selection;
pub mod snapshot;
pub mod store;
mod wire;

use std::ffi::OsString;

use serde_json::{Value, json};

use error::{Failure, Result};

pub struct Invocation {
    pub result: Result<Value>,
    pub machine: bool,
    pub text: Option<String>,
}

impl Invocation {
    pub fn exit_code(&self) -> u8 {
        self.result
            .as_ref()
            .err()
            .map_or(0, |failure| failure.kind.exit_code())
    }

    pub fn envelope(&self) -> Value {
        let mut envelope = json!({"schema_version": 1, "ok": self.result.is_ok(),
            "request_id": format!("request_{}", ulid::Ulid::generate()), "operation_id": null,
            "next_actions": [], "continuations": []});
        match &self.result {
            Ok(data) => {
                envelope["data"] = data.clone();
                envelope["warnings"] = json!([]);
            }
            Err(failure) => {
                envelope["error"] = json!({"code": failure.kind.code(), "message": failure.message, "retryable": matches!(failure.kind, error::ErrorKind::Unavailable), "details": failure.details})
            }
        }
        envelope
    }
}

/// Arguments include argv[0]. No state, credentials or network initialization.
pub fn invoke(arguments: impl IntoIterator<Item = OsString>) -> Invocation {
    let arguments: Vec<_> = arguments.into_iter().collect();
    let machine = arguments
        .iter()
        .take_while(|item| *item != "--")
        .any(|item| item == "--json");
    let mut parser = registry::parser();
    match parser.try_get_matches_from_mut(arguments) {
        Ok(matches) => {
            let text = (matches.subcommand().is_none() && !machine)
                .then(|| parser.render_help().to_string());
            Invocation {
                result: registry::dispatch(&matches),
                machine,
                text,
            }
        }
        Err(error) if error.kind() == clap::error::ErrorKind::DisplayHelp => Invocation {
            result: registry::help("", ""),
            machine,
            text: Some(error.to_string()),
        },
        Err(_) => Invocation {
            result: Err(Failure::input(
                "invalid invocation; use help --json for accepted commands and parameters",
            )),
            machine,
            text: None,
        },
    }
}
