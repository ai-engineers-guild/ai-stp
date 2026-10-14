use std::{error::Error, fs, path::Path, process::Command};

use serde_json::Value;

fn run(home: &Path, state: Option<&Path>, args: &[&str]) -> Result<Value, Box<dyn Error>> {
    let mut command = Command::new(env!("CARGO_BIN_EXE_ai-stp-v2"));
    command
        .args(args)
        .arg("--json")
        .env("HOME", home)
        .env("USERPROFILE", home)
        .env("XDG_DATA_HOME", home.join("data"))
        .env_remove("AI_STP_STATE_DIR");
    if let Some(state) = state {
        command.env("AI_STP_STATE_DIR", state);
    }
    let output = command.output()?;
    assert!(output.stderr.is_empty());
    Ok(serde_json::from_slice(&output.stdout)?)
}

#[test]
fn first_run_is_explicit_and_existing_python_identity_is_never_replaced()
-> Result<(), Box<dyn Error>> {
    let home = tempfile::tempdir()?;
    let state = home.path().join("data/ai-stp");
    for args in [
        &["version"][..],
        &["capabilities"],
        &["doctor"],
        &["state", "path"],
    ] {
        assert_eq!(run(home.path(), None, args)?["ok"], true);
        assert!(!state.exists(), "read initialized state");
    }
    if cfg!(windows) {
        assert_eq!(
            run(home.path(), None, &["init", "--credential-store", "file"])?["ok"],
            false
        );
        assert!(!state.exists());
        return Ok(());
    }
    let initialized = run(home.path(), None, &["init", "--credential-store", "file"])?;
    assert_eq!(initialized["ok"], true, "{initialized}");
    assert_eq!(
        initialized["data"],
        run(home.path(), None, &["init", "--credential-store", "file"])?["data"]
    );
    assert_eq!(
        initialized["data"],
        run(home.path(), None, &["device", "show"])?["data"]
    );
    let legacy = home.path().join("legacy");
    fs::create_dir(&legacy)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&legacy, fs::Permissions::from_mode(0o700))?;
    }
    fs::write(legacy.join("device.json"), "original legacy identity")?;
    let refused = run(
        home.path(),
        Some(&legacy),
        &["init", "--credential-store", "file"],
    )?;
    assert_eq!(refused["ok"], false);
    assert_eq!(
        fs::read_to_string(legacy.join("device.json"))?,
        "original legacy identity"
    );
    assert_eq!(fs::read_dir(legacy)?.count(), 1);
    Ok(())
}
