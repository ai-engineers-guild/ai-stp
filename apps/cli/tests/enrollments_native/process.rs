//! Separate executable processes retain native keys and revision-checked views.

use super::{Error, owned_slot};
use serde_json::Value;
use std::{
    fs,
    path::Path,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

fn run(home: &Path, args: &[&str], expected: i32) -> Result<Value, Box<dyn Error>> {
    let mut command = Command::new(env!("CARGO_BIN_EXE_ai-stp"));
    command
        .args(args)
        .arg("--json")
        .env_clear()
        .env("PATH", "")
        .env("HOME", home)
        .env("USERPROFILE", home)
        .env("XDG_DATA_HOME", home)
        .env("XDG_CONFIG_HOME", home)
        .env("XDG_CACHE_HOME", home)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(target_os = "macos")]
    // The User/login Keychain belongs to the existing macOS user session.
    // Keep its real home while every CLI state path and reviewed plan remains
    // explicit beneath the disposable fixture. Do not create another keychain.
    command.env(
        "HOME",
        std::env::var_os("HOME").ok_or("macOS vault fixture requires its existing user home")?,
    );
    for (name, value) in std::env::vars_os() {
        if [
            "SYSTEMROOT",
            "WINDIR",
            "TMP",
            "TEMP",
            "TMPDIR",
            "DBUS_SESSION_BUS_ADDRESS",
            "XDG_RUNTIME_DIR",
        ]
        .iter()
        .any(|allowed| name.to_string_lossy().eq_ignore_ascii_case(allowed))
        {
            command.env(name, value);
        }
    }
    let mut child = command.spawn()?;
    let deadline = Instant::now() + Duration::from_secs(15);
    while child.try_wait()?.is_none() {
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err("native profile process exceeded its deadline".into());
        }
        thread::sleep(Duration::from_millis(10));
    }
    let output = child.wait_with_output()?;
    assert!(output.stdout.len() <= 16384 && output.stderr.is_empty());
    let envelope: Value = serde_json::from_slice(&output.stdout)?;
    let operation = args
        .iter()
        .take_while(|argument| !argument.starts_with("--"))
        .copied()
        .collect::<Vec<_>>()
        .join(" ");
    assert_eq!(
        output.status.code(),
        Some(expected),
        "{operation}: {envelope}"
    );
    assert_eq!(envelope["ok"], expected == 0, "{envelope}");
    if expected == 0 {
        Ok(envelope["data"].clone())
    } else {
        assert_eq!(envelope["error"]["code"], "AI_STP_PRECONDITION_FAILED");
        Ok(envelope)
    }
}

fn apply(home: &Path, path: &[&str], plan: &Value, expected: i32) -> Result<Value, Box<dyn Error>> {
    let file = home.join("reviewed-plan.json");
    fs::write(&file, serde_json::to_vec(&plan["plan"])?)?;
    let mut args = path.to_vec();
    args.extend([
        "--plan",
        file.to_str().ok_or("plan path")?,
        "--plan-digest",
        plan["plan_digest"].as_str().ok_or("digest")?,
    ]);
    run(home, &args, expected)
}

#[test]
#[cfg_attr(
    target_os = "linux",
    ignore = "requires the isolated CI Secret Service bus"
)]
fn executable_restarts_preserve_native_connections_and_refuse_stale_context_selection()
-> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let home = root.path();
    let state_directory = home.join("native state é");
    fs::create_dir(&state_directory)?;
    let state = state_directory.to_str().ok_or("state path")?;
    let initialize = run(
        home,
        &[
            "device",
            "initialize",
            "plan",
            "--state-dir",
            state,
            "--credential-store",
            "os_keyring",
        ],
        0,
    )?;
    let local_slot = owned_slot(&format!(
        "device-key.{}",
        initialize["plan"]["device_id"].as_str().ok_or("device")?
    ))?;
    let identity = apply(home, &["device", "initialize", "apply"], &initialize, 0)?;
    assert_eq!(identity["credential_store"], "os_keyring");
    assert_eq!(
        apply(home, &["device", "initialize", "apply"], &initialize, 0)?,
        identity
    );
    assert!(local_slot.exists()?);
    #[cfg(not(target_os = "macos"))]
    let local_key = ai_stp_cli::digest::sha256(&local_slot.secret()?);

    let mut slots = Vec::new();
    let mut connections = Vec::new();
    for label in ["Personal", "Corporate"] {
        let planned = run(
            home,
            &[
                "account",
                "connections",
                "plan",
                "--state-dir",
                state,
                "--label",
                label,
                "--api-url",
                "https://same-origin.example.test",
                "--provider",
                "github",
            ],
            0,
        )?;
        slots.push(owned_slot(&format!(
            "device-key.{}",
            planned["plan"]["device_id"]
                .as_str()
                .ok_or("enrollment device")?
        ))?);
        let created = apply(home, &["account", "connections", "apply"], &planned, 0)?;
        assert_eq!(created["connection"]["credential_store"], "os_keyring");
        assert_eq!(
            apply(home, &["account", "connections", "apply"], &planned, 0)?,
            created
        );
        connections.push((planned, created));
    }
    assert_ne!(
        connections[0].1["connection"]["public_key"],
        connections[1].1["connection"]["public_key"]
    );
    assert!(slots[1].exists()?);
    #[cfg(not(target_os = "macos"))]
    let other_key = ai_stp_cli::digest::sha256(&slots[1].secret()?);
    let retained = run(
        home,
        &["account", "connections", "list", "--state-dir", state],
        0,
    )?;
    let mut contexts = Vec::new();
    for label in ["Offline", "Another local view"] {
        let planned = run(
            home,
            &[
                "context",
                "create",
                "plan",
                "--state-dir",
                state,
                "--label",
                label,
            ],
            0,
        )?;
        contexts.push(apply(home, &["context", "apply"], &planned, 0)?);
    }
    let first = contexts[0]["context_id"].as_str().ok_or("first context")?;
    let second = contexts[1]["context_id"].as_str().ok_or("second context")?;
    let select = |context| {
        run(
            home,
            &[
                "context",
                "select",
                "plan",
                "--state-dir",
                state,
                "--context",
                context,
            ],
            0,
        )
    };
    let initial = select(first)?;
    let stale = select(second)?;
    let receipt = apply(home, &["context", "apply"], &initial, 0)?;
    apply(home, &["context", "apply"], &stale, 4)?;
    apply(home, &["context", "apply"], &select(second)?, 0)?;
    let selected = run(home, &["context", "list", "--state-dir", state], 0)?;
    assert_eq!(selected["selected"]["context_id"], second);
    assert_eq!(apply(home, &["context", "apply"], &initial, 0)?, receipt);
    assert_eq!(
        run(home, &["context", "list", "--state-dir", state], 0)?,
        selected
    );
    assert_eq!(
        run(
            home,
            &["account", "connections", "list", "--state-dir", state],
            0
        )?,
        retained
    );
    assert_eq!(
        run(home, &["device", "show", "--state-dir", state], 0)?,
        identity
    );
    #[cfg(not(target_os = "macos"))]
    {
        assert_eq!(ai_stp_cli::digest::sha256(&local_slot.secret()?), local_key);
        assert_eq!(ai_stp_cli::digest::sha256(&slots[1].secret()?), other_key);
    }
    assert!(local_slot.exists()?);
    assert!(slots[1].exists()?);
    slots[0].remove()?;
    apply(
        home,
        &["account", "connections", "apply"],
        &connections[0].0,
        4,
    )?;
    assert!(!slots[0].exists()?);
    assert_eq!(
        run(home, &["context", "list", "--state-dir", state], 0)?,
        selected
    );
    assert_eq!(
        apply(
            home,
            &["account", "connections", "apply"],
            &connections[1].0,
            0
        )?,
        connections[1].1
    );
    assert!(slots[1].exists()?);
    #[cfg(not(target_os = "macos"))]
    assert_eq!(ai_stp_cli::digest::sha256(&slots[1].secret()?), other_key);
    assert!(!state_directory.join("ai-stp-v2-account").exists());
    Ok(())
}

/// This test uses the real OS-user coordinator, not an environment-selected copy.
/// Explicit CI invocation confines that persistent metadata to a disposable user.
#[test]
#[ignore = "requires a disposable native CI OS-user and its existing credential vault"]
fn public_native_configuration_keeps_original_context_across_cli_restarts()
-> Result<(), Box<dyn Error>> {
    assert_eq!(std::env::var("GITHUB_ACTIONS").as_deref(), Ok("true"));
    let runner = std::env::var("RUNNER_OS")?;
    assert!(["macOS", "Windows"].contains(&runner.as_str()));
    use ai_stp_cli::{digest, installation::custody::Custody};
    use serde_json::json;
    assert!(
        Custody::existing_user()?.is_none(),
        "disposable user must start without native custody"
    );
    let temporary = tempfile::tempdir()?;
    let home = temporary.path().canonicalize()?;
    let state = home.join("native state é");
    let target = home.join("target");
    let source = home.join("source");
    for directory in [&state, &target, &source] {
        fs::create_dir(directory)?;
    }
    fs::write(
        source.join("guide.md"),
        b"# Native setup\nVerify affected behavior.\n",
    )?;
    fs::write(target.join("user-note"), b"unowned data stays\n")?;
    let state_path = state.to_str().ok_or("state path")?;
    let initial = run(
        &home,
        &[
            "device",
            "initialize",
            "plan",
            "--state-dir",
            state_path,
            "--credential-store",
            "os_keyring",
        ],
        0,
    )?;
    let _slot = owned_slot(&format!(
        "device-key.{}",
        initial["plan"]["device_id"].as_str().ok_or("device")?
    ))?;
    apply(&home, &["device", "initialize", "apply"], &initial, 0)?;
    let execute = |arguments: &[&str]| -> Result<Value, Box<dyn Error>> {
        let mut env: Vec<(std::ffi::OsString, std::ffi::OsString)> =
            vec![("PATH".into(), "".into())];
        for (name, value) in std::env::vars_os() {
            if [
                "SYSTEMROOT",
                "WINDIR",
                "TMP",
                "TEMP",
                "TMPDIR",
                "HOME",
                "USERPROFILE",
                "DBUS_SESSION_BUS_ADDRESS",
                "XDG_RUNTIME_DIR",
            ]
            .iter()
            .any(|allowed| name.to_string_lossy().eq_ignore_ascii_case(allowed))
            {
                env.push((name, value));
            }
        }
        let mut args = arguments
            .iter()
            .map(std::ffi::OsString::from)
            .collect::<Vec<_>>();
        if arguments.get(..2) != Some(&["context", "apply"][..]) {
            args.extend(["--state-dir".into(), state.as_os_str().into()]);
        }
        args.push("--json".into());
        let output = ai_stp_cli::process::run(ai_stp_cli::process::Request {
            executable: Path::new(env!("CARGO_BIN_EXE_ai-stp")),
            arguments: &args,
            directory: &home,
            environment: &env,
            timeout: Duration::from_secs(30),
            output_limit: 8 * 1024 * 1024,
        })?;
        assert!(output.stderr.is_empty(), "unexpected native CLI stderr");
        let envelope: Value = serde_json::from_slice(&output.stdout)?;
        assert!(output.status.success(), "{envelope}");
        assert_eq!(envelope["ok"], true, "{envelope}");
        Ok(envelope["data"].clone())
    };
    let enact = |data: &Value, command: &[&str]| -> Result<Value, Box<dyn Error>> {
        let file = home.join("native-reviewed.json");
        fs::write(&file, serde_json::to_vec(&data["plan"])?)?;
        let mut args = command.to_vec();
        args.extend([
            "--plan",
            file.to_str().ok_or("plan path")?,
            "--plan-digest",
            data["plan_digest"].as_str().ok_or("plan digest")?,
        ]);
        execute(&args)
    };
    let mut contexts = Vec::new();
    for label in ["Original native context", "Another view"] {
        let plan = execute(&["context", "create", "plan", "--label", label])?;
        contexts.push(
            plan["plan"]["change"]["context"]["context_id"]
                .as_str()
                .ok_or("context")?
                .to_owned(),
        );
        enact(&plan, &["context", "apply"])?;
    }
    let input = home.join("author-input.json");
    fs::write(
        &input,
        serde_json::to_vec(
            &json!({"schema_version":1,"directory":source,"harness_id":"codex",
        "component_type":"instruction","name":"native-cli-platform-fixture","license_spdx":"MIT"}),
        )?,
    )?;
    let author = execute(&[
        "task",
        "start",
        "--intent",
        "author",
        "--idempotency-key",
        "native-platform-author-0001",
        "--input",
        input.to_str().ok_or("author input")?,
    ])?;
    assert_eq!(author["state"], "completed", "{author}");
    let setup = author["outcome"]["setup_id"].as_str().ok_or("setup")?;
    let version = execute(&[
        "local",
        "version",
        "show",
        "--kind",
        "setup",
        "--id",
        setup,
        "--version",
        "1.0",
    ])?;
    fn passport<'a>(value: &'a Value, id: &str) -> Option<&'a Value> {
        let object = value.as_object()?;
        if value["kind"] == "setup" && value["stable_id"] == id {
            return Some(value);
        }
        object.values().find_map(|value| passport(value, id))
    }
    let passport = passport(&version, setup).ok_or("exact setup passport")?;
    let input = home.join("native-input.json");
    fs::write(
        &input,
        serde_json::to_vec(
            &json!({"schema_version":1,"setup":{"stable_id":setup,"version":"1.0",
        "passport_digest":digest::canonical("ai-stp:passport:v1",passport)?},"harness_id":"codex","operation":"install","roots":{"global":target}}),
        )?,
    )?;
    let review = execute(&[
        "configuration",
        "native",
        "plan",
        "--context",
        &contexts[0],
        "--input",
        input.to_str().ok_or("native input")?,
    ])?;
    assert_eq!(review["configuration_changed"], false);
    let operation = review["plan"]["operation_id"].as_str().ok_or("operation")?;
    let expected = review["plan_digest"].as_str().ok_or("review digest")?;
    let selection = execute(&["context", "select", "plan", "--context", &contexts[1]])?;
    enact(&selection, &["context", "apply"])?;
    enact(&review, &["configuration", "native", "prepare"])?;
    let pending = execute(&["configuration", "native", "pending"])?;
    assert_eq!(
        pending["pending"]["original_context"]["context_id"],
        contexts[0]
    );
    let receipt = execute(&[
        "configuration",
        "native",
        "apply",
        "--operation",
        operation,
        "--plan-digest",
        expected,
    ])?;
    assert_eq!(receipt["original_context"]["context_id"], contexts[0]);
    assert_eq!(receipt["load_state"], "not_observed");
    assert_eq!(receipt["configuration_changed"], true);
    assert_eq!(
        execute(&[
            "configuration",
            "native",
            "apply",
            "--operation",
            operation,
            "--plan-digest",
            expected
        ])?,
        receipt
    );
    assert!(target.join("AGENTS.md").is_file());
    assert_eq!(
        execute(&["context", "list"])?["selected"]["context_id"],
        contexts[1]
    );
    assert_eq!(
        execute(&[
            "configuration",
            "native",
            "effective",
            "--context",
            &contexts[1]
        ])?["setups"],
        json!([])
    );
    let owned = execute(&[
        "configuration",
        "native",
        "effective",
        "--context",
        &contexts[0],
    ])?;
    assert_eq!(owned["setups"][0]["ownership_state"], "matching");
    let remove = execute(&[
        "configuration",
        "native",
        "remove",
        "plan",
        "--operation",
        operation,
        "--plan-digest",
        expected,
    ])?;
    enact(&remove, &["configuration", "native", "prepare"])?;
    let removal = execute(&[
        "configuration",
        "native",
        "apply",
        "--operation",
        remove["plan"]["operation_id"].as_str().ok_or("removal")?,
        "--plan-digest",
        remove["plan_digest"].as_str().ok_or("removal digest")?,
    ])?;
    assert_eq!(removal["operation"], "remove");
    assert!(!target.join("AGENTS.md").exists());
    assert_eq!(fs::read(target.join("user-note"))?, b"unowned data stays\n");
    assert_eq!(
        execute(&[
            "configuration",
            "native",
            "effective",
            "--context",
            &contexts[0]
        ])?["setups"],
        json!([])
    );
    assert!(execute(&["configuration", "native", "pending"])?["pending"].is_null());
    Ok(())
}
