use aistp_desktop_core::{CliLocator, CliRunner};
use serde::Serialize;
use std::path::PathBuf;

/// Every IPC reply is a typed result — the frontend renders `ok` or the
/// structured error; it never receives raw stderr.
#[derive(Serialize)]
struct CmdResult {
    ok: bool,
    data: Option<serde_json::Value>,
    warnings: Vec<String>,
    continuations: Vec<aistp_desktop_core::Continuation>,
    error: Option<String>,
}

impl CmdResult {
    fn from_envelope(env: aistp_desktop_core::Envelope) -> Self {
        Self {
            ok: env.ok,
            data: env.data,
            warnings: env.warnings,
            continuations: env.continuations,
            error: env.error.map(|e| format!("{}: {}", e.code, e.message)),
        }
    }
    fn failed(msg: impl ToString) -> Self {
        Self {
            ok: false,
            data: None,
            warnings: Vec::new(),
            continuations: Vec::new(),
            error: Some(msg.to_string()),
        }
    }
}

fn runner() -> Result<CliRunner, String> {
    let bundled = bundled_cli_path();
    CliRunner::system(&CliLocator {
        bundled,
        configured: None,
    })
    .map_err(|e| e.to_string())
}

fn bundled_cli_path() -> Option<PathBuf> {
    // externalBin resolves next to the app executable. The final bundled
    // name is decided by the runtime-distribution spike; until then the
    // system-installed CLI is the transport.
    let exe = std::env::current_exe().ok()?;
    let name = if cfg!(windows) { "ai-stp.exe" } else { "ai-stp" };
    let candidate = exe.parent()?.join(name);
    candidate.is_file().then_some(candidate)
}

fn run_cli(args: Vec<String>) -> CmdResult {
    match runner() {
        Ok(r) => match r.run(&args) {
            Ok(env) => CmdResult::from_envelope(env),
            Err(e) => CmdResult::failed(e),
        },
        Err(e) => CmdResult::failed(e),
    }
}

#[tauri::command]
async fn cli_version() -> CmdResult {
    tauri::async_runtime::spawn_blocking(|| run_cli(vec!["version".into()])).await
        .unwrap_or_else(|e| CmdResult::failed(e))
}

#[tauri::command]
async fn cli_capabilities() -> CmdResult {
    tauri::async_runtime::spawn_blocking(|| run_cli(vec!["capabilities".into()])).await
        .unwrap_or_else(|e| CmdResult::failed(e))
}

#[tauri::command]
async fn cli_doctor() -> CmdResult {
    tauri::async_runtime::spawn_blocking(|| run_cli(vec!["doctor".into()])).await
        .unwrap_or_else(|e| CmdResult::failed(e))
}

#[tauri::command]
async fn cli_auth_status() -> CmdResult {
    tauri::async_runtime::spawn_blocking(|| {
        run_cli(vec!["auth".into(), "status".into()])
    })
    .await
    .unwrap_or_else(|e| CmdResult::failed(e))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|_app, _args, _cwd| {}))
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .invoke_handler(tauri::generate_handler![
            cli_version,
            cli_capabilities,
            cli_doctor,
            cli_auth_status
        ])
        .run(tauri::generate_context!())
        .expect("error while running ai-stp desktop");
}
