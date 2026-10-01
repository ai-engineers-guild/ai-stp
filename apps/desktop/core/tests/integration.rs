use aistp_desktop_core::cli_runner::{CliLocator, CliRunner, RunError};
use aistp_desktop_core::commands::{CommandRegistry, MachineHelp};
use aistp_desktop_core::envelope::{parse, ParseFailure};
use std::collections::BTreeMap;

fn fixture(name: &str) -> Vec<u8> {
    let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join(name);
    std::fs::read(p).unwrap_or_else(|e| panic!("fixture {name}: {e}"))
}

#[test]
fn parses_success_envelope() {
    let env = parse(&fixture("version-ok.json")).unwrap();
    assert!(env.ok);
    assert_eq!(env.schema_version, 1);
    assert!(!env.data.unwrap()["cli_version"]
        .as_str()
        .unwrap()
        .is_empty());
}

#[test]
fn parses_error_envelope_with_continuation() {
    let env = parse(&fixture("steering-error.json")).unwrap();
    assert!(!env.ok);
    let err = env.error.unwrap();
    assert_eq!(err.code, "AI_STP_VALIDATION_ERROR");
    assert!(!err.retryable);
    assert!(env
        .continuations
        .iter()
        .any(|c| c.actor.as_deref() == Some("cli") && !c.argv.is_empty()));
}

#[test]
fn rejects_non_json_stdout() {
    match parse(b"installing...\n").unwrap_err() {
        ParseFailure::NotJson(_) => {}
        other => panic!("expected NotJson, got {other:?}"),
    }
}

#[test]
fn rejects_unsupported_schema_major() {
    let bytes = br#"{"schema_version": 2, "ok": true, "data": {}}"#;
    match parse(bytes).unwrap_err() {
        ParseFailure::UnsupportedSchema(2) => {}
        other => panic!("expected UnsupportedSchema(2), got {other:?}"),
    }
}

#[test]
fn argv_built_from_descriptors() {
    let help: MachineHelp = serde_json::from_slice(&fixture("machine-help.json")).unwrap();
    let reg = CommandRegistry::from_help(&help);

    let mut values = BTreeMap::new();
    values.insert("setup".to_string(), "setup_01ABC@1.0".to_string());
    values.insert("project".to_string(), "/tmp/proj".to_string());
    values.insert("harness".to_string(), "claude-code".to_string());
    let argv = reg
        .build_argv("install plan", &values, &[], &BTreeMap::new())
        .unwrap();
    assert_eq!(
        argv,
        vec![
            "install",
            "plan",
            "--setup",
            "setup_01ABC@1.0",
            "--project",
            "/tmp/proj",
            "--harness",
            "claude-code"
        ]
    );
}

#[test]
fn argv_refuses_undeclared_and_missing() {
    let help: MachineHelp = serde_json::from_slice(&fixture("machine-help.json")).unwrap();
    let reg = CommandRegistry::from_help(&help);

    let mut values = BTreeMap::new();
    values.insert("undeclared".to_string(), "x".to_string());
    assert!(reg
        .build_argv("install plan", &values, &[], &BTreeMap::new())
        .is_err());

    assert!(reg
        .build_argv("install plan", &BTreeMap::new(), &[], &BTreeMap::new())
        .is_err());
}

#[test]
fn argv_enforces_declared_rules() {
    let help: MachineHelp = serde_json::from_slice(&fixture("machine-help.json")).unwrap();
    let reg = CommandRegistry::from_help(&help);

    // install plan: `required_when` project while setup present — refuse without it.
    let mut values = BTreeMap::new();
    values.insert("setup".to_string(), "setup_01ABC@1.0".to_string());
    values.insert("harness".to_string(), "claude-code".to_string());
    assert!(reg
        .build_argv("install plan", &values, &[], &BTreeMap::new())
        .is_err());

    // exactly_one {proposal, setup} applies once action=install is conditioned.
    let mut values = BTreeMap::new();
    values.insert("project".to_string(), "/tmp/p".to_string());
    values.insert("harness".to_string(), "claude-code".to_string());
    values.insert("action".to_string(), "install".to_string());
    assert!(reg
        .build_argv("install plan", &values, &[], &BTreeMap::new())
        .is_err());

    // choice violation is refused up front.
    let mut values = BTreeMap::new();
    values.insert("setup".to_string(), "setup_01ABC@1.0".to_string());
    values.insert("project".to_string(), "/tmp/p".to_string());
    values.insert("harness".to_string(), "not-a-harness".to_string());
    assert!(reg
        .build_argv("install plan", &values, &[], &BTreeMap::new())
        .is_err());

    // target status: both required options present.
    let mut values = BTreeMap::new();
    values.insert("project".to_string(), "a".to_string());
    values.insert("harness".to_string(), "codex".to_string());
    assert!(reg
        .build_argv("target status", &values, &[], &BTreeMap::new())
        .is_ok());
}

/// Regression: a child emitting more than a pipe buffer's worth of stdout
/// (typical for `help --agent`) must not deadlock the runner. The previous
/// implementation read stdout only after exit; the child blocked on write
/// and hit the deadline every time.
#[cfg(unix)]
#[test]
fn large_stdout_does_not_deadlock() {
    use std::io::Write;
    use std::os::unix::fs::PermissionsExt;

    let dir = std::env::temp_dir().join(format!("aistp-test-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let exe = dir.join("fake-ai-stp");
    {
        let mut f = std::fs::File::create(&exe).unwrap();
        // ~200KB JSON envelope — far beyond the 64KB pipe buffer.
        writeln!(
            f,
            "#!/bin/sh\nprintf '{{\"schema_version\":1,\"ok\":true,\"request_id\":null,\"operation_id\":null,\"data\":{{\"blob\":\"%s\"}},\"warnings\":[],\"next_actions\":[],\"continuations\":[],\"error\":null}}' \"$(head -c 150000 /dev/zero | tr '\\0' 'x')\""
        )
        .unwrap();
    }
    std::fs::set_permissions(&exe, std::fs::Permissions::from_mode(0o755)).unwrap();

    let runner = CliRunner::system(&CliLocator {
        bundled: Some(exe.clone()),
        configured: None,
    })
    .unwrap();
    let env = runner
        .run(&["anything".to_string()])
        .expect("spawn + drain");
    assert!(env.ok);
    assert_eq!(env.data.unwrap()["blob"].as_str().unwrap().len(), 150_000);
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn locator_missing_pinned_path_is_error_not_fallback() {
    // A pinned path that does not exist must fail closed — silently using
    // PATH would mask a tampered or half-installed bundle.
    for locator in [
        CliLocator {
            bundled: Some(std::path::PathBuf::from("/definitely/missing/ai-stp")),
            configured: None,
        },
        CliLocator {
            bundled: None,
            configured: Some(std::path::PathBuf::from("/definitely/missing/ai-stp")),
        },
    ] {
        match locator.resolve() {
            Err(RunError::NotFound(m)) => assert!(m.contains("pinned path")),
            other => panic!("expected NotFound, got {other:?}"),
        }
    }
}

#[test]
fn locator_bundled_wins_over_path() {
    let exe = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("machine-help.json"); // any existing file proves selection order
    let loc = CliLocator {
        bundled: Some(exe.clone()),
        configured: Some(std::path::PathBuf::from("/other")),
    };
    // bundled is Some → configured is never consulted even if missing.
    assert_eq!(loc.resolve().unwrap(), exe);
}

#[test]
fn continuation_actor_classification_fail_closed() {
    use aistp_desktop_core::envelope::{Continuation, ContinuationActor};
    let mk = |actor: Option<&str>| Continuation {
        kind: "advance".into(),
        path: vec![],
        arguments: serde_json::Value::Null,
        missing: vec![],
        argv: vec![],
        actor: actor.map(str::to_string),
    };
    assert_eq!(mk(Some("cli")).actor_kind(), ContinuationActor::Cli);
    assert_eq!(
        mk(Some("external")).actor_kind(),
        ContinuationActor::External
    );
    // absent / unknown / empty actors never auto-run.
    assert_eq!(mk(None).actor_kind(), ContinuationActor::Human);
    assert_eq!(mk(Some("agent")).actor_kind(), ContinuationActor::Human);
    assert_eq!(mk(Some("")).actor_kind(), ContinuationActor::Human);
}

#[test]
fn warnings_and_nonzero_exit_envelope() {
    let bytes = br#"{
        "schema_version": 1, "ok": false,
        "warnings": ["catalog cache stale"],
        "error": {"code": "AI_STP_CONFLICT", "message": "rev", "retryable": false, "details": {}}
    }"#;
    let env = parse(bytes).unwrap();
    assert!(!env.ok);
    assert_eq!(env.warnings, vec!["catalog cache stale"]);
    assert_eq!(env.error.unwrap().code, "AI_STP_CONFLICT");
}

#[cfg(unix)]
fn fake_cli(body: &str) -> (std::path::PathBuf, std::path::PathBuf) {
    use std::io::Write;
    use std::os::unix::fs::PermissionsExt;
    let dir =
        std::env::temp_dir().join(format!("aistp-test-{}-{}", std::process::id(), body.len()));
    std::fs::create_dir_all(&dir).unwrap();
    let exe = dir.join("fake-ai-stp");
    std::fs::File::create(&exe)
        .unwrap()
        .write_all(body.as_bytes())
        .unwrap();
    std::fs::set_permissions(&exe, std::fs::Permissions::from_mode(0o755)).unwrap();
    (dir, exe)
}

#[cfg(unix)]
#[test]
fn error_envelope_on_nonzero_exit_is_parsed() {
    let (dir, exe) = fake_cli(
        "#!/bin/sh\nprintf '%s' '{\"schema_version\":1,\"ok\":false,\"error\":{\"code\":\"X\",\"message\":\"m\",\"retryable\":true},\"warnings\":[],\"continuations\":[]}'; exit 1",
    );
    let runner = CliRunner::system(&CliLocator {
        bundled: Some(exe),
        configured: None,
    })
    .unwrap();
    let env = runner.run(&[]).unwrap();
    assert!(!env.ok);
    assert!(env.error.unwrap().retryable);
    let _ = std::fs::remove_dir_all(&dir);
}

#[cfg(unix)]
#[test]
fn garbage_stdout_reports_exit_and_stderr() {
    let (dir, exe) = fake_cli("#!/bin/sh\necho boom >&2\necho not-json\nexit 3");
    let runner = CliRunner::system(&CliLocator {
        bundled: Some(exe),
        configured: None,
    })
    .unwrap();
    match runner.run(&[]) {
        Err(RunError::NoEnvelope { exit, stderr }) => {
            assert_eq!(exit, Some(3));
            assert!(stderr.contains("boom"));
        }
        other => panic!("expected NoEnvelope, got {other:?}"),
    }
    let _ = std::fs::remove_dir_all(&dir);
}

#[cfg(unix)]
#[test]
fn hanging_child_is_killed_as_unconfirmed() {
    let (dir, exe) = fake_cli("#!/bin/sh\nsleep 30");
    let mut runner = CliRunner::system(&CliLocator {
        bundled: Some(exe),
        configured: None,
    })
    .unwrap();
    runner.timeout = std::time::Duration::from_millis(300);
    match runner.run(&[]) {
        Err(RunError::TimeoutUnconfirmed) => {}
        other => panic!("expected TimeoutUnconfirmed, got {other:?}"),
    }
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn argv_boolean_flags_and_repeatables() {
    let help: MachineHelp = serde_json::from_slice(&fixture("machine-help.json")).unwrap();
    let reg = CommandRegistry::from_help(&help);

    let mut values = BTreeMap::new();
    values.insert("setup".to_string(), "s@1.0".to_string());
    values.insert("project".to_string(), "/p".to_string());
    values.insert("harness".to_string(), "claude-code".to_string());
    let mut repeated = BTreeMap::new();
    repeated.insert(
        "component".to_string(),
        vec!["a@1".to_string(), "b@2".to_string()],
    );
    let argv = reg
        .build_argv(
            "install plan",
            &values,
            &["unverified-provider".to_string()],
            &repeated,
        )
        .unwrap();
    assert!(argv.contains(&"--unverified-provider".to_string()));
    let comp: Vec<_> = argv
        .iter()
        .zip(argv.iter().skip(1))
        .filter(|(a, _)| a.as_str() == "--component")
        .map(|(_, b)| b.clone())
        .collect();
    assert_eq!(comp, vec!["a@1", "b@2"]);

    // a non-boolean parameter is not a flag.
    assert!(reg
        .build_argv(
            "install plan",
            &values,
            &["setup".to_string()],
            &BTreeMap::new()
        )
        .is_err());
}

#[test]
fn argv_unknown_command_is_refused() {
    let help: MachineHelp = serde_json::from_slice(&fixture("machine-help.json")).unwrap();
    let reg = CommandRegistry::from_help(&help);
    assert!(matches!(
        reg.build_argv("does not exist", &BTreeMap::new(), &[], &BTreeMap::new()),
        Err(aistp_desktop_core::commands::BuildError::UnknownCommand(_))
    ));
}

#[test]
#[ignore = "requires ai-stp on PATH; run explicitly"]
fn runs_real_cli_version() {
    let runner = CliRunner::system(&CliLocator {
        bundled: None,
        configured: None,
    })
    .unwrap();
    let env = runner
        .run(&["version".to_string()])
        .expect("ai-stp version --json");
    assert!(env.ok);
}
