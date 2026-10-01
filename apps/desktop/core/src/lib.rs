//! UI-agnostic core for the ai-stp desktop app (ADR-0222).
//!
//! Everything here is synchronous and transport-free: the Tauri shell pushes
//! calls off the async runtime (`tauri::async_runtime::spawn_blocking`), and
//! nothing in this crate talks to a WebView, a socket, or the network.

pub mod cli_runner;
pub mod commands;
pub mod envelope;
pub mod scope;

pub use cli_runner::{CliLocator, CliRunner, RunError};
pub use commands::{BuildError, CommandDescriptor, CommandRegistry, MachineHelp};
pub use envelope::{parse, Continuation, ContinuationActor, Envelope, ParseFailure};
pub use scope::Scope;
