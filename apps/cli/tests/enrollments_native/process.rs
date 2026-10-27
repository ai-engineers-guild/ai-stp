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
    assert_eq!(ai_stp_cli::digest::sha256(&local_slot.secret()?), local_key);
    assert_eq!(ai_stp_cli::digest::sha256(&slots[1].secret()?), other_key);
    slots[0].remove()?;
    apply(
        home,
        &["account", "connections", "apply"],
        &connections[0].0,
        4,
    )?;
    assert!(slots[0].bytes()?.is_none());
    assert_eq!(
        run(home, &["context", "list", "--state-dir", state], 0)?,
        selected
    );
    assert_eq!(ai_stp_cli::digest::sha256(&slots[1].secret()?), other_key);
    assert!(!state_directory.join("ai-stp-v2-account").exists());
    Ok(())
}
