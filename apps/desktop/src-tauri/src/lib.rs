use ai_stp_desktop_core::{
    CliLocator, CliRunner, CommandRegistry, Envelope, MachineHelp, RunError,
};
use serde::Serialize;
use std::collections::BTreeMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

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
    /// Contract fields the UI can route on (ADR-0222): operation tracking
    /// and retry/disposition hints ride along unmodified.
    #[serde(skip_serializing_if = "Option::is_none")]
    request_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    operation_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error_retryable: Option<bool>,
    /// `error.details` verbatim — `details.options` is the contract's
    /// one-retry repair channel (cli-json.md) and losing it here would make
    /// the shell thinner than the contract allows.
    #[serde(skip_serializing_if = "Option::is_none")]
    error_details: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    next_actions: Vec<serde_json::Value>,
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
            error_code: env.error.as_ref().map(|e| e.code.clone()),
            request_id: env.request_id,
            operation_id: env.operation_id,
            error_retryable: env.error.as_ref().map(|e| e.retryable),
            error_details: env.error.and_then(|e| {
                let d = e.details;
                // `details` is a required wire field that defaults to `{}` —
                // an empty object is no detail at all, so render nothing.
                (!d.is_null() && !d.as_object().is_some_and(|o| o.is_empty())).then_some(d)
            }),
            next_actions: env.next_actions,
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
            request_id: None,
            operation_id: None,
            error_retryable: None,
            error_details: None,
            next_actions: Vec::new(),
        }
    }
}

/// The frontend routes on stable codes; keep the closed set aligned with
/// the CLI's own (`AI_STP_NOT_FOUND`, `AI_STP_TIMEOUT_UNCONFIRMED`, …).
/// Codes this shell mints itself carry `DESKTOP_` — the `AI_STP_` namespace
/// is the CLI's published set and inventing members confuses any reader
/// checking a code against `help --agent`.
fn error_code_for(e: &RunError) -> &'static str {
    match e {
        RunError::NotFound(_) => "AI_STP_NOT_FOUND",
        RunError::TimeoutUnconfirmed => "AI_STP_TIMEOUT_UNCONFIRMED",
        _ => "DESKTOP_TRANSPORT",
    }
}

/// Shared shell state: the CLI runner, the cached command registry keyed
/// by `registry_digest`, and a mutation mutex serializing every write —
/// plan/apply, task-engine steps, and credential mutations.
struct AppState {
    runner: Mutex<Option<CliRunner>>,
    /// Cached descriptors + when the digest was last verified live. The
    /// lock guards the Option only — never held across a subprocess spawn.
    registry: Mutex<Option<(CommandRegistry, Instant)>>,
    /// Two mutating runs in flight could interleave writes against the same
    /// target or the CLI's own journal — every mutating command holds this
    /// for the whole run so mutations are ordered, not concurrent. Read
    /// commands stay lock-free.
    mutation_lock: Mutex<()>,
}

/// Digest re-verification interval: `capabilities` is a subprocess spawn,
/// so checking it on every gated call doubles spawn cost. The digest only
/// changes when the CLI binary is replaced mid-session — a 30 s TTL bounds
/// staleness well inside any realistic upgrade race.
const REGISTRY_TTL: Duration = Duration::from_secs(30);

impl AppState {
    fn new() -> Self {
        Self {
            runner: Mutex::new(None),
            registry: Mutex::new(None),
            mutation_lock: Mutex::new(()),
        }
    }

    fn runner(&self) -> Result<CliRunner, RunError> {
        let mut guard = self
            .runner
            .lock()
            .map_err(|_| RunError::Internal("state poisoned".into()))?;
        if let Some(r) = &*guard {
            return Ok(r.clone());
        }
        let bundled = bundled_cli_path();
        // `AI_STP_CLI` pins a configured override — dev installs where the
        // bundled tier is absent and PATH is minimal (e.g. macOS launchd).
        let configured = std::env::var_os("AI_STP_CLI")
            .map(PathBuf::from)
            .filter(|p| !p.as_os_str().is_empty());
        let r = CliRunner::system(&CliLocator {
            bundled,
            configured,
        })?;
        *guard = Some(r.clone());
        Ok(r)
    }

    /// Command registry, refreshed whenever the CLI's `registry_digest`
    /// changes (CLI upgrades invalidate cached descriptors).
    fn command_registry(&self) -> Result<CommandRegistry, RunError> {
        let runner = self.runner()?;
        let cached = self
            .registry
            .lock()
            .map_err(|_| RunError::Internal("state poisoned".into()))?
            .clone();
        if let Some((reg, checked_at)) = cached {
            let live = if checked_at.elapsed() < REGISTRY_TTL {
                true
            } else {
                // Cheap freshness probe outside the lock: `capabilities`
                // carries the live digest.
                match runner.run(&["capabilities".into()]) {
                    Ok(env) => {
                        env.ok
                            && env
                                .data
                                .as_ref()
                                .and_then(|d| d.get("registry_digest"))
                                .and_then(|d| d.as_str())
                                == Some(reg.registry_digest.as_str())
                    }
                    Err(_) => false,
                }
            };
            if live {
                let mut guard = self
                    .registry
                    .lock()
                    .map_err(|_| RunError::Internal("state poisoned".into()))?;
                *guard = Some((reg.clone(), Instant::now()));
                return Ok(reg);
            }
        }
        let env = runner.run(&["help".into(), "--agent".into()])?;
        if !env.ok {
            return Err(RunError::Internal(
                env.error
                    .map(|e| e.message)
                    .unwrap_or_else(|| "help --agent failed".into()),
            ));
        }
        let help: MachineHelp = serde_json::from_value(
            env.data
                .ok_or_else(|| RunError::Internal("help --agent: empty data".into()))?,
        )
        .map_err(|e| RunError::Internal(format!("machine-help parse: {e}")))?;
        let reg = CommandRegistry::from_help(&help);
        *self
            .registry
            .lock()
            .map_err(|_| RunError::Internal("state poisoned".into()))? =
            Some((reg.clone(), Instant::now()));
        Ok(reg)
    }
}

fn bundled_cli_path() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    // Named `ai-stp-desktop-cli` (not `ai-stp`) so a Linux package cannot
    // collide with the standalone CLI package's /usr/bin/ai-stp.
    let name = if cfg!(windows) {
        "ai-stp-desktop-cli.exe"
    } else {
        "ai-stp-desktop-cli"
    };
    let candidate = exe.parent()?.join(name);
    candidate.is_file().then_some(candidate)
}

fn run_cli(state: &AppState, args: &[String]) -> CmdResult {
    run_cli_within(state, args, None)
}

fn run_cli_within(state: &AppState, args: &[String], timeout: Option<Duration>) -> CmdResult {
    match state.runner() {
        Ok(mut r) => {
            if let Some(t) = timeout {
                r.timeout = t;
            }
            match r.run(args) {
                Ok(env) => CmdResult::from_envelope(env),
                Err(e) => CmdResult::failed(error_code_for(&e), e),
            }
        }
        Err(e) => CmdResult::failed(error_code_for(&e), e),
    }
}

/// Mutating run: holds the mutation mutex for the whole run so concurrent
/// task-engine steps and plan/apply cannot interleave writes against the
/// same target or the CLI journal. Mutating runs get the longer deadline —
/// the CLI's own provider-verification budget is 300 s.
fn run_cli_mutating(state: &AppState, args: &[String]) -> CmdResult {
    let _mutation = match state.mutation_lock.lock() {
        Ok(g) => g,
        Err(_) => return CmdResult::failed("DESKTOP_TRANSPORT", "mutation lock poisoned"),
    };
    run_cli_within(state, args, Some(ai_stp_desktop_core::MUTATING_TIMEOUT))
}

fn argv(path: &str) -> Vec<String> {
    path.split(' ').map(str::to_string).collect()
}

fn new_idem_key(prefix: &str) -> String {
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
                "cli_version": reg.cli_version,
                "global_options": reg.global_options,
                "error_codes": reg.error_codes,
                "commands": reg.all_descriptors(),
            })),
            warnings: vec![],
            continuations: vec![],
            error: None,
            error_code: None,
            request_id: None,
            operation_id: None,
            error_retryable: None,
            error_details: None,
            next_actions: vec![],
        },
        Err(e) => CmdResult::failed(error_code_for(&e), e),
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
    repeated: Option<BTreeMap<String, Vec<String>>>,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let reg = match st.command_registry() {
            Ok(r) => r,
            Err(e) => return CmdResult::failed(error_code_for(&e), e),
        };
        let desc = match reg.descriptor(&path) {
            Some(d) => d,
            None => {
                return CmdResult::failed(
                    "DESKTOP_UNKNOWN_COMMAND",
                    format!("unknown command: {path}"),
                );
            }
        };
        if desc.mutability != "read" {
            return CmdResult::failed(
                "DESKTOP_PERMISSION_DENIED",
                format!(
                    "{path} is mutability={} — read-only passthrough refused",
                    desc.mutability
                ),
            );
        }
        let repeated = repeated.unwrap_or_default();
        match reg.build_argv(&path, &values, &flags, &repeated) {
            Ok(av) => run_cli(&st, &av),
            Err(e) => CmdResult::failed("DESKTOP_USAGE", e),
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
    repeated: Option<BTreeMap<String, Vec<String>>>,
) -> Result<CmdResult, String> {
    gated_run(state.inner().clone(), path, values, flags, repeated, "plan").await
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
    repeated: Option<BTreeMap<String, Vec<String>>>,
) -> Result<CmdResult, String> {
    if !confirmed {
        return Ok(CmdResult::failed(
            "DESKTOP_CONFIRMATION_REQUIRED",
            "apply requires an explicit confirmation from the UI",
        ));
    }
    gated_run(
        state.inner().clone(),
        path,
        values,
        flags,
        repeated,
        "apply",
    )
    .await
}

async fn gated_run(
    st: Arc<AppState>,
    path: String,
    values: BTreeMap<String, String>,
    flags: Vec<String>,
    repeated: Option<BTreeMap<String, Vec<String>>>,
    want_mutability: &'static str,
) -> Result<CmdResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let reg = match st.command_registry() {
            Ok(r) => r,
            Err(e) => return CmdResult::failed(error_code_for(&e), e),
        };
        let desc = match reg.descriptor(&path) {
            Some(d) => d,
            None => {
                return CmdResult::failed(
                    "DESKTOP_UNKNOWN_COMMAND",
                    format!("unknown command: {path}"),
                );
            }
        };
        if desc.mutability != want_mutability {
            return CmdResult::failed(
                "DESKTOP_PERMISSION_DENIED",
                format!(
                    "{path} is mutability={} — refused by {} gate",
                    desc.mutability, want_mutability
                ),
            );
        }
        let repeated = repeated.unwrap_or_default();
        match reg.build_argv(&path, &values, &flags, &repeated) {
            Ok(av) => run_cli_mutating(&st, &av),
            Err(e) => CmdResult::failed("DESKTOP_USAGE", e),
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
                "error": e.to_string(),
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
            request_id: None,
            operation_id: None,
            error_retryable: None,
            error_details: None,
            next_actions: vec![],
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
    idem_key: Option<String>,
) -> Result<CmdResult, String> {
    let st = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        // The UI supplies one key per logical start attempt so a timeout-
        // and-retry hits the CLI's idempotency dedup instead of forking a
        // second task; absent a key we mint one per call.
        let key = idem_key
            .filter(|k| !k.is_empty())
            .unwrap_or_else(|| new_idem_key("desktop"));
        // `--input` is deliberately not exposed here: the CLI reads it as a
        // JSON/YAML file path or `-` for stdin, and this runner's stdin is
        // sealed — an inline blob would arrive as a path that cannot exist.
        // Wizard answers go through `task answer`, the channel the engine
        // actually reads.
        let a = vec![
            "task".into(),
            "start".into(),
            "--intent".into(),
            intent,
            "--idempotency-key".into(),
            key,
        ];
        run_cli_mutating(&st, &a)
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
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // A second launch raises the existing window instead of
            // silently exiting — otherwise a minimized app looks dead.
            use tauri::Manager;
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        // Persist size/maximized but not POSITION: a stored position on a
        // since-disconnected monitor reopens the window off-screen with no
        // visible recovery path.
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_state_flags({
                    let mut f = tauri_plugin_window_state::StateFlags::all();
                    f.remove(tauri_plugin_window_state::StateFlags::POSITION);
                    f
                })
                .build(),
        )
        .plugin(tauri_plugin_opener::init())
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
