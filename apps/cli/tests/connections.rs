#![cfg(unix)]

//! Exercise the same machine command surface consumed by desktop.

use serde_json::Value;
use std::{error::Error, fs, path::Path, process::Command};

fn run(args: &[&str]) -> Result<Value, Box<dyn Error>> {
    let output = Command::new(env!("CARGO_BIN_EXE_ai-stp"))
        .args(args)
        .arg("--json")
        .output()?;
    assert!(
        output.status.success(),
        "native command failed: {}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(output.stderr.is_empty());
    let envelope: Value = serde_json::from_slice(&output.stdout)?;
    assert_eq!(envelope["ok"], true, "{envelope}");
    Ok(envelope["data"].clone())
}

fn apply(root: &Path, path: &[&str], plan: &Value) -> Result<Value, Box<dyn Error>> {
    let file = root.join("reviewed-plan.json");
    fs::write(&file, serde_json::to_vec(&plan["plan"])?)?;
    let mut args = path.to_vec();
    args.extend([
        "--plan",
        file.to_str().ok_or("plan path")?,
        "--plan-digest",
        plan["plan_digest"].as_str().ok_or("digest")?,
    ]);
    run(&args)
}

#[test]
fn machine_connections_and_context_views_preserve_the_legacy_session() -> Result<(), Box<dyn Error>>
{
    let root = tempfile::tempdir()?;
    let state_directory = root.path().join("state");
    let state = state_directory.to_str().ok_or("state path")?;
    let identity = run(&["init", "--state-dir", state, "--credential-store", "file"])?;
    let plan = run(&[
        "account",
        "connections",
        "plan",
        "--state-dir",
        state,
        "--label",
        "Personal",
        "--api-url",
        "https://account.example.test",
        "--provider",
        "github",
    ])?;
    assert_eq!(plan["plan"]["registry_schema_before"], 53);
    assert_eq!(plan["plan"]["registry_schema_after"], 55);
    let created = apply(root.path(), &["account", "connections", "apply"], &plan)?;
    let connection = created["connection"]["connection_id"]
        .as_str()
        .ok_or("connection")?;
    assert_eq!(
        apply(root.path(), &["account", "connections", "apply"], &plan)?,
        created
    );
    let status = run(&[
        "account",
        "status",
        "--state-dir",
        state,
        "--connection",
        connection,
    ])?;
    assert_eq!(status["origin"], "https://account.example.test");
    assert_eq!(status["session"]["state"], "absent");
    let local = run(&[
        "context",
        "create",
        "plan",
        "--state-dir",
        state,
        "--label",
        "Offline",
    ])?;
    let context = apply(root.path(), &["context", "apply"], &local)?;
    let context = context["context_id"].as_str().ok_or("context")?;
    let selection = run(&[
        "context",
        "select",
        "plan",
        "--state-dir",
        state,
        "--context",
        context,
    ])?;
    apply(root.path(), &["context", "apply"], &selection)?;
    assert_eq!(
        run(&["context", "list", "--state-dir", state])?["selected"]["context_id"],
        context
    );
    let legacy = run(&["account", "status", "--state-dir", state])?;
    assert_eq!(legacy["session"]["state"], "absent");
    assert!(legacy.get("connection_id").is_none());
    assert_eq!(run(&["device", "show", "--state-dir", state])?, identity);
    assert!(!state_directory.join("ai-stp-v2-account").exists());
    Ok(())
}
