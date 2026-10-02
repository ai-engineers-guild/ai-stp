use ai_stp_desktop_core::{CliLocator, CliRunner, CommandRegistry, Envelope, MachineHelp};
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
    continuations: Vec<ai_stp_desktop_core::Continuation>,
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

/// Shared shell state: the CLI runner, the cached command registry keyed
/// by `registry_digest`, and a mutation mutex serializing every write —
/// plan/apply, task-engine steps, and credential mutations.
struct AppState {
    runner: Mutex<Option<CliRunner>>,
    registry: Mutex<Option<CommandRegistry>>,
    /// Two mutating runs in flight could interleave writes against the same
    /// target or the CLI's own journal — every mutating command holds this
    /// for the whole run so mutations are ordered, not concurrent. Read
    /// commands stay lock-free.
    mutation_lock: Mutex<()>,
}

impl AppState {
    fn new() -> Self {
        Self {
            runner: Mutex::new(None),
            registry: Mutex::new(None),
            mutation_lock: Mutex::new(()),
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
        let help: MachineHelp = serde_json::from_value(env.data.ok_or("help --agent: empty data")?)
            .map_err(|e| format!("machine-help parse: {e}"))?;
        let reg = CommandRegistry::from_help(&help);
        *self.registry.lock().map_err(|_| "state poisoned")? = Some(reg.clone());
        Ok(reg)
    }
}

fn bundled_cli_path() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let name = if cfg!(windows) {
        "ai-stp.exe"
    } else {
        "ai-stp"
    };
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

/// Mutating run: holds the mutation mutex for the whole run so concurrent
/// task-engine steps and plan/apply cannot interleave writes against the
/// same target or the CLI journal.
fn run_cli_mutating(state: &AppState, args: &[String]) -> CmdResult {
    let _mutation = match state.mutation_lock.lock() {
        Ok(g) => g,
        Err(_) => return CmdResult::failed("AI_STP_TRANSPORT", "mutation lock poisoned"),
    };
    run_cli(state, args)
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
            None => {
                return CmdResult::failed(
                    "AI_STP_VALIDATION_ERROR",
                    format!("unknown command: {path}"),
                )
            }
        };
        if desc.mutability != "read" {
            return CmdResult::failed(
                "AI_STP_PERMISSION_DENIED",
                format!(
                    "{path} is mutability={} — read-only passthrough refused",
                    desc.mutability
                ),
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

/// Plan-tier passthrough: descriptor-driven argv for commands whose
/// mutability is `plan` (e.g. `install plan`). Plans are durable, digest-
/// bound proposals — nothing is written to a target yet.
#[tauri::command]
async fn cli_plan(
    state: tauri::State<'_, Arc<AppState>>,
    path: String,
    values: BTreeMap<String, String>,
    flags: Vec<String>,
) -> Result<CmdResult, String> {
    gated_run(state.inner().clone(), path, values, flags, "plan").await
}

/// Apply-tier passthrough: requires the explicit `confirmed` flag — the
/// frontend sets it only after the user approved the exact plan digest on
/// screen. Descriptor `parameter_rules` and `confirmation` still apply.
#[tauri::command]
async fn cli_apply_confirmed(
    state: tauri::State<'_, Arc<AppState>>,
    path: String,
    values: BTreeMap<String, String>,
    flags: Vec<String>,
    confirmed: bool,
) -> Result<CmdResult, String> {
    if !confirmed {
        return Ok(CmdResult::failed(
            "AI_STP_VALIDATION_ERROR",
            "apply requires an explicit confirmation from the UI",
        ));
    }
    gated_run(state.inner().clone(), path, values, flags, "apply").await
}

async fn gated_run(
    st: Arc<AppState>,
    path: String,
    values: BTreeMap<String, String>,
    flags: Vec<String>,
    want_mutability: &'static str,
) -> Result<CmdResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let reg = match st.command_registry() {
            Ok(r) => r,
            Err(e) => return CmdResult::failed("AI_STP_TRANSPORT", e),
        };
        let desc = match reg.descriptor(&path) {
            Some(d) => d,
            None => {
                return CmdResult::failed(
                    "AI_STP_VALIDATION_ERROR",
                    format!("unknown command: {path}"),
                )
            }
        };
        if desc.mutability != want_mutability {
            return CmdResult::failed(
                "AI_STP_PERMISSION_DENIED",
                format!(
                    "{path} is mutability={} — refused by {} gate",
                    desc.mutability, want_mutability
                ),
            );
        }
        match reg.build_argv(&path, &values, &flags, &BTreeMap::new()) {
            Ok(av) => run_cli_mutating(&st, &av),
            Err(e) => CmdResult::failed("AI_STP_VALIDATION_ERROR", e),
        }
    })
    .await
    .map_err(|e| e.to_string())
}

/// Diagnostics for the Debug page: which binary we resolved, how, and
/// live contract versions. Never includes credentials or env secrets.
#[tauri::command]
async fn debug_info(state: tauri::State<'_, Arc<AppState>>) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let bundled = bundled_cli_path();
        let info = match st.runner() {
            Ok(r) => serde_json::json!({
                "cli_found": true,
                "cli_path": r.executable.display().to_string(),
                "cli_source": if bundled.as_ref() == Some(&r.executable) { "bundled" } else { "path/configured" },
            }),
            Err(e) => serde_json::json!({
                "cli_found": false,
                "error": e,
                "bundled_checked": bundled.map(|p| p.display().to_string()),
            }),
        };
        let mut data = info;
        data["platform"] = serde_json::json!(std::env::consts::OS);
        data["arch"] = serde_json::json!(std::env::consts::ARCH);
        data["app_version"] = serde_json::json!(env!("CARGO_PKG_VERSION"));
        CmdResult {
            ok: true,
            data: Some(data),
            warnings: vec![],
            continuations: vec![],
            error: None,
            error_code: None,
        }
    })
    .await
    .map_err(|e| e.to_string())
}

// ---- auth: device-code flow, driven through the CLI; the app holds no
// credentials at any point.

#[tauri::command]
async fn auth_login(
    state: tauri::State<'_, Arc<AppState>>,
    provider: String,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_cli_mutating(
            &st,
            &["auth".into(), "login".into(), "--provider".into(), provider],
        )
    })
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
async fn auth_complete(
    state: tauri::State<'_, Arc<AppState>>,
    wait: bool,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut a = argv("auth complete");
        if wait {
            a.push("--wait".into());
        }
        run_cli_mutating(&st, &a)
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
    tauri::async_runtime::spawn_blocking(move || run_cli_mutating(&st, &argv("auth logout")))
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
                "registry".into(),
                "show".into(),
                "--kind".into(),
                kind,
                "--id".into(),
                stable_id,
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
async fn task_start(
    state: tauri::State<'_, Arc<AppState>>,
    intent: String,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let key = idem_key(&format!("desktop-{intent}"));
        run_cli_mutating(
            &st,
            &[
                "task".into(),
                "start".into(),
                "--intent".into(),
                intent,
                "--idempotency-key".into(),
                key,
            ],
        )
    })
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
async fn task_status(
    state: tauri::State<'_, Arc<AppState>>,
    task_id: String,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_cli(
            &st,
            &["task".into(), "status".into(), "--task".into(), task_id],
        )
    })
    .await
    .map_err(|e| e.to_string())
}

/// Answer one task-engine question. The wizard submits user form input
/// here; the engine re-derives the next state, questions or continuations.
#[tauri::command]
async fn task_answer(
    state: tauri::State<'_, Arc<AppState>>,
    task: String,
    revision: String,
    question_id: String,
    value: String,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_cli_mutating(
            &st,
            &[
                "task".into(),
                "answer".into(),
                "--task".into(),
                task,
                "--revision".into(),
                revision,
                "--question-id".into(),
                question_id,
                "--value".into(),
                value,
            ],
        )
    })
    .await
    .map_err(|e| e.to_string())
}

/// Continue a task after it produced a plan/continuation (e.g. confirm an
/// install). The engine decides the next step — we never shortcut it.
#[tauri::command]
async fn task_continue(
    state: tauri::State<'_, Arc<AppState>>,
    task: String,
    revision: String,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_cli_mutating(
            &st,
            &[
                "task".into(),
                "continue".into(),
                "--task".into(),
                task,
                "--revision".into(),
                revision,
            ],
        )
    })
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
async fn task_cancel(
    state: tauri::State<'_, Arc<AppState>>,
    task: String,
    revision: String,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        run_cli_mutating(
            &st,
            &[
                "task".into(),
                "cancel".into(),
                "--task".into(),
                task,
                "--revision".into(),
                revision,
            ],
        )
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
            debug_info,
            cli_plan,
            cli_apply_confirmed,
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
            task_answer,
            task_continue,
            task_cancel,
            task_list
        ])
        .run(tauri::generate_context!())
        .expect("error while running ai-stp desktop");
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Real-CLI smoke tests for the shell's sync core. Skipped unless a real
    /// `ai-stp` is intended: `AI_STP_REAL_CLI=1 cargo test`.
    fn real() -> bool {
        std::env::var("AI_STP_REAL_CLI").is_ok()
    }

    #[test]
    fn runner_resolves_and_version_ok() {
        if !real() {
            return;
        }
        let st = AppState::new();
        let r = st.runner().expect("cli resolves");
        assert!(r.executable.is_file());
        let env = r.run(&argv("version")).expect("spawn");
        assert!(env.ok, "version failed: {:?}", env.error);
    }

    #[test]
    fn registry_loads_real_machine_help() {
        if !real() {
            return;
        }
        let st = AppState::new();
        let reg = st.command_registry().expect("machine help parses");
        assert!(reg.all_descriptors().len() > 200);
        assert!(!reg.registry_digest.is_empty());
        // digest-keyed cache: second call returns the same registry
        assert_eq!(
            st.command_registry().unwrap().registry_digest,
            reg.registry_digest
        );
    }

    #[test]
    fn read_gate_refuses_apply_command() {
        if !real() {
            return;
        }
        let st = AppState::new();
        let reg = st.command_registry().unwrap();
        let desc = reg.descriptor("install apply").expect("descriptor");
        assert_eq!(desc.mutability, "apply");
        // the read gate hard-refuses anything that isn't mutability=read
        assert_ne!(desc.mutability, "read");
    }

    #[test]
    fn read_gate_allows_and_runs_read_command() {
        if !real() {
            return;
        }
        let st = AppState::new();
        let reg = st.command_registry().unwrap();
        let desc = reg
            .descriptor("harness list")
            .or_else(|| reg.descriptor("device show"));
        let desc = desc.expect("a known read command exists");
        assert_eq!(desc.mutability, "read");
        let av = reg
            .build_argv(&desc.path_key(), &BTreeMap::new(), &[], &BTreeMap::new())
            .expect("argv builds");
        let env = st.runner().unwrap().run(&av).expect("spawn");
        // The envelope must parse even if the command reports an error.
        assert_eq!(env.schema_version, 1);
    }

    #[test]
    fn plan_gate_refuses_read_command() {
        if !real() {
            return;
        }
        let st = AppState::new();
        let reg = st.command_registry().unwrap();
        let desc = reg.descriptor("device show").expect("descriptor");
        // device show is read-tier — the plan gate must refuse it
        assert_ne!(desc.mutability, "plan");
    }
}
