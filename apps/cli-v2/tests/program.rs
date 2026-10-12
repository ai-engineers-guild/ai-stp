use ai_stp_cli_v2::{invoke, program};
use std::error::Error;

#[test]
fn user_managed_harnesses_have_no_mutation_commands() -> Result<(), Box<dyn Error>> {
    for words in [
        "program install plan",
        "program update apply",
        "program remove apply",
        "provider software acquire",
        "program inspect",
    ] {
        let mut args: Vec<std::ffi::OsString> = vec!["ai-stp-v2".into()];
        args.extend(words.split_whitespace().map(Into::into));
        args.push("--json".into());
        assert_eq!(invoke(args).envelope()["ok"], false);
    }
    let directory = tempfile::tempdir()?;
    let missing = directory.path().join("missing");
    assert_eq!(
        program::observe("codex", Some(&missing))?["state"],
        "missing"
    );
    assert!(!missing.exists());
    assert!(program::observe("codex", Some(std::path::Path::new("relative"))).is_err());
    #[cfg(unix)]
    {
        use std::{
            fs,
            os::unix::fs::{PermissionsExt, symlink},
            process::Command,
        };
        let path = directory.path().join("codex");
        let script = b"#!/bin/sh\ntest $# = 1 && test \"$1\" = --version || exit 20\ntest -z \"$AI_STP_TEST_SECRET\" || exit 21\nprintf 'codex-cli 1.2.3\\n'\n";
        fs::write(&path, script)?;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o755))?;
        symlink(&path, directory.path().join("alias"))?;
        let observed = program::observe("codex", Some(&directory.path().join("alias")))?;
        assert_eq!(observed["state"], "observed");
        assert_eq!(observed["version"], "1.2.3");
        assert_eq!(
            observed,
            program::observe("codex", Some(&directory.path().join("alias")))?
        );
        let output = Command::new(env!("CARGO_BIN_EXE_ai-stp-v2"))
            .args(["program", "status", "--harness", "codex", "--json"])
            .env("PATH", directory.path())
            .env("AI_STP_TEST_SECRET", "must-not-inherit")
            .output()?;
        assert!(output.status.success());
        let answer: serde_json::Value = serde_json::from_slice(&output.stdout)?;
        assert_eq!(answer["data"]["version"], "1.2.3");
        assert_eq!(fs::read(&path)?, script);
        fs::write(&path, b"#!/bin/sh\nprintf 'codex-cli 2.0.0\\n'\n")?;
        assert_ne!(
            observed["observation_digest"],
            program::observe("codex", Some(&directory.path().join("alias")))?["observation_digest"]
        );
        fs::write(&path, b"#!/bin/sh\nprintf 'unrecognized\\n'\n")?;
        assert_eq!(
            program::observe("codex", Some(&path))?["state"],
            "unknown_version"
        );
    }
    Ok(())
}
