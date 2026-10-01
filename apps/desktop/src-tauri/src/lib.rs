use aistp_desktop_core::{CliLocator, CliRunner, CommandRegistry, Envelope, MachineHelp};
use serde::Serialize;
use std::collections::BTreeMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

/// Every IPC reply is a typed result — the frontend renders `ok` or the
/// structured error; it never receives raw stderr.
#[derive(Serialize)]
struct CmdResult {
    ok: bool,
    data: Option<serde_json::Value>,
    warnings: Vec<String>,
    continuations: Vec<aistp_desktop_core::Continuation>,
    error: Option<String>,
    /// Stable machine code when the CLI produced one — the frontend keys
    /// on this, never on the message text.
    error_code: Option<String>,
}

impl CmdResult {
    fn from_envelope(env: Envelope) -> Self {
        Self {
            ok: env.ok,
            data: env.data,
            warnings: env.warnings,
            continuations: env.continuations,
            error: env
                .error
                .as_ref()
                .map(|e| format!("{}: {}", e.code, e.message)),
            error_code: env.error.map(|e| e.code),
        }
    }
    fn failed(code: &str, msg: impl ToString) -> Self {
        Self {
            ok: false,
            data: None,
            warnings: Vec::new(),
            continuations: Vec::new(),
            error: Some(msg.to_string()),
            error_code: Some(code.into()),
        }
    }
}

/// Shared shell state: the CLI runner and the cached command registry
/// keyed by `registry_digest`.
struct AppState {
    runner: Mutex<Option<CliRunner>>,
    registry: Mutex<Option<CommandRegistry>>,
}

impl AppState {
    fn new() -> Self {
        Self {
            runner: Mutex::new(None),
            registry: Mutex::new(None),
        }
    }

    fn runner(&self) -> Result<CliRunner, String> {
        let mut guard = self.runner.lock().map_err(|_| "state poisoned")?;
        if let Some(r) = &*guard {
            return Ok(r.clone());
        }
        let bundled = bundled_cli_path();
        let r = CliRunner::system(&CliLocator {
            bundled,
            configured: None,
        })
        .map_err(|e| e.to_string())?;
        *guard = Some(r.clone());
        Ok(r)
    }

    /// Command registry, refreshed whenever the CLI's `registry_digest`
    /// changes (CLI upgrades invalidate cached descriptors).
    fn command_registry(&self) -> Result<CommandRegistry, String> {
        let runner = self.runner()?;
        {
            if let Some(reg) = &*self.registry.lock().map_err(|_| "state poisoned")? {
                // Cheap freshness: capabilities carries the live digest.
                if let Ok(env) = runner.run(&["capabilities".into()]) {
                    if env.ok
                        && env
                            .data
                            .as_ref()
                            .and_then(|d| d.get("registry_digest"))
                            .and_then(|d| d.as_str())
                            == Some(reg.registry_digest.as_str())
                    {
                        return Ok(reg.clone());
                    }
                }
            }
        }
        let env = runner
            .run(&["help".into(), "--agent".into()])
            .map_err(|e| e.to_string())?;
        if !env.ok {
            return Err(env
                .error
                .map(|e| e.message)
                .unwrap_or_else(|| "help --agent failed".into()));
        }
        let help: MachineHelp = serde_json::from_value(
            env.data.ok_or("help --agent: empty data")?,
        )
        .map_err(|e| format!("machine-help parse: {e}"))?;
        let reg = CommandRegistry::from_help(&help);
        *self.registry.lock().map_err(|_| "state poisoned")? = Some(reg.clone());
        Ok(reg)
    }
}

fn bundled_cli_path() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let name = if cfg!(windows) { "ai-stp.exe" } else { "ai-stp" };
    let candidate = exe.parent()?.join(name);
    candidate.is_file().then_some(candidate)
}

fn run_cli(state: &AppState, args: &[String]) -> CmdResult {
    match state.runner() {
        Ok(r) => match r.run(args) {
            Ok(env) => CmdResult::from_envelope(env),
            Err(e) => CmdResult::failed("AI_STP_TRANSPORT", e),
        },
        Err(e) => CmdResult::failed("AI_STP_NOT_FOUND", e),
    }
}

fn argv(path: &str) -> Vec<String> {
    path.split(' ').map(str::to_string).collect()
}

fn idem_key(prefix: &str) -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or_default();
    format!("{prefix}-{nanos:x}")
}

// ---------------------------------------------------------------- commands

#[tauri::command]
async fn cli_version(state: tauri::State<'_, Arc<AppState>>) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || run_cli(&st, &argv("version")))
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn cli_capabilities(state: tauri::State<'_, Arc<AppState>>) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || run_cli(&st, &argv("capabilities")))
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn cli_doctor(state: tauri::State<'_, Arc<AppState>>) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || run_cli(&st, &argv("doctor")))
        .await
        .map_err(|e| e.to_string())
}

/// `help --agent --json` — the full command registry for the frontend's
/// command palette and parameter forms.
#[tauri::command]
async fn machine_help(state: tauri::State<'_, Arc<AppState>>) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || match st.command_registry() {
        Ok(reg) => CmdResult {
            ok: true,
            data: Some(serde_json::json!({
                "registry_digest": reg.registry_digest,
                "commands": reg.all_descriptors(),
            })),
            warnings: vec![],
            continuations: vec![],
            error: None,
            error_code: None,
        },
        Err(e) => CmdResult::failed("AI_STP_TRANSPORT", e),
    })
    .await
    .map_err(|e| e.to_string())
}

/// Read-only generic passthrough: any command whose declared mutability is
/// `read` may run here. plan/apply/destructive never pass this gate.
#[tauri::command]
async fn cli_run_read(
    state: tauri::State<'_, Arc<AppState>>,
    path: String,
    values: BTreeMap<String, String>,
    flags: Vec<String>,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let reg = match st.command_registry() {
            Ok(r) => r,
            Err(e) => return CmdResult::failed("AI_STP_TRANSPORT", e),
        };
        let desc = match reg.descriptor(&path) {
            Some(d) => d,
            None => return CmdResult::failed("AI_STP_VALIDATION_ERROR", format!("unknown command: {path}")),
        };
        if desc.mutability != "read" {
            return CmdResult::failed(
                "AI_STP_PERMISSION_DENIED",
                format!("{path} is mutability={} — read-only passthrough refused", desc.mutability),
            );
        }
        match reg.build_argv(&path, &values, &flags, &BTreeMap::new()) {
            Ok(av) => run_cli(&st, &av),
            Err(e) => CmdResult::failed("AI_STP_VALIDATION_ERROR", e),
        }
    })
    .await
    .map_err(|e| e.to_string())
}

// ---- auth: device-code flow, driven through the CLI; the app holds no
// credentials at any point.

#[tauri::command]
async fn auth_login(state: tauri::State<'_, Arc<AppState>>, provider: String) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_cli(&st, &["auth".into(), "login".into(), "--provider".into(), provider])
    })
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
async fn auth_complete(state: tauri::State<'_, Arc<AppState>>, wait: bool) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut a = argv("auth complete");
        if wait {
            a.push("--wait".into());
        }
        run_cli(&st, &a)
    })
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
async fn auth_status(state: tauri::State<'_, Arc<AppState>>) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || run_cli(&st, &argv("auth status")))
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn auth_logout(state: tauri::State<'_, Arc<AppState>>) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || run_cli(&st, &argv("auth logout")))
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn device_show(state: tauri::State<'_, Arc<AppState>>) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || run_cli(&st, &argv("device show")))
        .await
        .map_err(|e| e.to_string())
}

// ---- catalog: proxied through the CLI (`registry *`), so private
// acquisition reuses the CLI's credential store and the app never handles
// a Bearer token.

#[tauri::command]
async fn catalog_search(
    state: tauri::State<'_, Arc<AppState>>,
    kind: String,
    query: String,
    include_experimental: bool,
    cursor: Option<String>,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut a = argv("registry search");
        a.extend(["--kind".into(), kind]);
        if !query.is_empty() {
            a.extend(["--query".into(), query]);
        }
        if include_experimental {
            a.push("--include-experimental".into());
        }
        if let Some(c) = cursor {
            a.extend(["--cursor".into(), c]);
        }
        run_cli(&st, &a)
    })
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
async fn catalog_show(
    state: tauri::State<'_, Arc<AppState>>,
    kind: String,
    stable_id: String,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_cli(
            &st,
            &[
                "registry".into(), "show".into(), "--kind".into(), kind,
                "--id".into(), stable_id,
            ],
        )
    })
    .await
    .map_err(|e| e.to_string())
}

// ---- tasks: the durable journey surface (SPEC-080).

#[tauri::command]
async fn task_intents(state: tauri::State<'_, Arc<AppState>>) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || run_cli(&st, &argv("task intents")))
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn task_start(state: tauri::State<'_, Arc<AppState>>, intent: String) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let key = idem_key(&format!("desktop-{intent}"));
        run_cli(
            &st,
            &[
                "task".into(), "start".into(), "--intent".into(), intent,
                "--idempotency-key".into(), key,
            ],
        )
    })
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
async fn task_status(state: tauri::State<'_, Arc<AppState>>, task_id: String) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_cli(&st, &["task".into(), "status".into(), "--task".into(), task_id])
    })
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
async fn task_list(state: tauri::State<'_, Arc<AppState>>) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || run_cli(&st, &argv("task list")))
        .await
        .map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Arc::new(AppState::new()))
        .plugin(tauri_plugin_single_instance::init(|_app, _args, _cwd| {}))
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .invoke_handler(tauri::generate_handler![
            cli_version,
            cli_capabilities,
            cli_doctor,
            machine_help,
            cli_run_read,
            auth_login,
            auth_complete,
            auth_status,
            auth_logout,
            device_show,
            catalog_search,
            catalog_show,
            task_intents,
            task_start,
            task_status,
            task_list
        ])
        .run(tauri::generate_context!())
        .expect("error while running ai-stp desktop");
}
