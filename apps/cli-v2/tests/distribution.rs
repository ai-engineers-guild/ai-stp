use serde_json::Value;
use std::{error::Error, fs, path::Path, process::Command};

fn invoke(binary: &Path, args: &[&str]) -> Result<Value, Box<dyn Error>> {
    let output = Command::new(binary).args(args).arg("--json").output()?;
    assert!(output.stderr.is_empty());
    Ok(serde_json::from_slice(&output.stdout)?)
}

#[test]
fn archive_ownership_replay_and_interrupted_publication() -> Result<(), Box<dyn Error>> {
    let binary = Path::new(env!("CARGO_BIN_EXE_ai-stp-v2"));
    let root = tempfile::tempdir()?;
    let prefix = root.path().join("native");
    let plan = invoke(
        binary,
        &[
            "cli",
            "install",
            "plan",
            "--prefix",
            prefix.to_str().ok_or("path")?,
        ],
    )?;
    assert_eq!(plan["ok"], true, "{plan}");
    assert!(!prefix.exists());
    let path = root.path().join("plan.json");
    fs::write(&path, serde_json::to_vec(&plan["data"]["plan"])?)?;
    let args = [
        "cli",
        "install",
        "apply",
        "--plan",
        path.to_str().ok_or("path")?,
        "--plan-digest",
        plan["data"]["plan_digest"].as_str().ok_or("digest")?,
    ];
    let receipt = invoke(binary, &args)?;
    assert_eq!(receipt["ok"], true, "{receipt}");
    let installed = prefix.join(if cfg!(windows) {
        "ai-stp.exe"
    } else {
        "ai-stp"
    });
    assert_eq!(invoke(&installed, &["version"])?["data"]["runtime"], "rust");
    assert_eq!(invoke(binary, &args)?["data"], receipt["data"]);
    // Durable boundary after binary replacement but before receipt publication.
    // This is a modeled checkpoint, not a claim of an OS crash in this test.
    fs::write(
        prefix.join("pending.json"),
        serde_json::to_vec(&plan["data"]["plan"])?,
    )?;
    fs::remove_file(prefix.join("release.json"))?;
    fs::remove_file(prefix.join("receipt.json"))?;
    assert_eq!(invoke(binary, &args)?["data"], receipt["data"]);
    assert!(!prefix.join("pending.json").exists());
    // The archive installer never takes over an unowned/shared bin directory.
    let foreign = root.path().join("foreign");
    fs::create_dir(&foreign)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&foreign, fs::Permissions::from_mode(0o700))?;
    }
    fs::write(foreign.join("ai-stp"), "package-manager-owned")?;
    let refused = invoke(
        binary,
        &[
            "cli",
            "install",
            "plan",
            "--prefix",
            foreign.to_str().ok_or("path")?,
        ],
    )?;
    assert_eq!(refused["ok"], false);
    assert_eq!(fs::read_dir(foreign)?.count(), 1);
    fs::write(&installed, "external modification")?;
    assert_eq!(invoke(binary, &args)?["ok"], false);
    Ok(())
}
