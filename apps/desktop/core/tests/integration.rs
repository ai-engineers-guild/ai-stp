use ai_stp_desktop_core::cli_runner::{CliLocator, CliRunner, RunError};
use ai_stp_desktop_core::commands::{BuildError, CommandRegistry, MachineHelp};
#[cfg(unix)]
use ai_stp_desktop_core::envelope::Envelope;
use ai_stp_desktop_core::envelope::{parse, ParseFailure};
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

    // With no `action` at all the conditioned exactly_one{proposal,setup}
    // does not apply (contract: it only holds while action takes
    // install/update/remove) — bare `install plan` is legal argv; whether
    // it is meaningful is the CLI's semantic check, not the shell's.
    assert!(reg
        .build_argv("install plan", &BTreeMap::new(), &[], &BTreeMap::new())
        .is_ok());
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

    // Conditioned-off pair rule: on `backup`/`rollback` the
    // exactly_one{proposal,setup} relaxes to at_most_one — supplying
    // neither is legal (the CLI's own declaration, registry.py).
    let mut values = BTreeMap::new();
    values.insert("action".to_string(), "backup".to_string());
    assert!(
        reg.build_argv("install plan", &values, &[], &BTreeMap::new())
            .is_ok(),
        "conditioned-off exactly_one must not fire on action=backup"
    );

    // …but the conditioned at_most_one does fire: both is still refused.
    let mut values = BTreeMap::new();
    values.insert("action".to_string(), "backup".to_string());
    values.insert("proposal".to_string(), "p".to_string());
    values.insert("setup".to_string(), "s".to_string());
    assert!(reg
        .build_argv("install plan", &values, &[], &BTreeMap::new())
        .is_err());

    // `component` is forbidden_when action=backup — conditioned-on rule.
    let mut values = BTreeMap::new();
    values.insert("action".to_string(), "backup".to_string());
    values.insert("component".to_string(), "c".to_string());
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

#[test]
fn argv_repeated_and_positional_flags() {
    let help: MachineHelp = serde_json::from_slice(&fixture("machine-help.json")).unwrap();
    let reg = CommandRegistry::from_help(&help);

    // Repeated option emits one --flag per value, in order.
    let mut repeated = BTreeMap::new();
    repeated.insert(
        "allow-permission".to_string(),
        vec!["fs:read".to_string(), "net:fetch".to_string()],
    );
    let mut values = BTreeMap::new();
    values.insert("setup".to_string(), "setup_01ABC@1.0".to_string());
    values.insert("project".to_string(), "/tmp/p".to_string());
    values.insert("harness".to_string(), "claude-code".to_string());
    let argv = reg
        .build_argv("install plan", &values, &[], &repeated)
        .unwrap();
    let n = argv.iter().filter(|a| *a == "--allow-permission").count();
    assert_eq!(n, 2);

    // A positional-kind parameter passed as a flag is a violation, not a
    // silent drop.
    let fixture_has_argument = reg
        .all_descriptors()
        .iter()
        .flat_map(|d| d.parameters.iter())
        .any(|p| p.kind == "argument");
    if fixture_has_argument {
        let arg_path = reg
            .all_descriptors()
            .iter()
            .find(|d| d.parameters.iter().any(|p| p.kind == "argument"))
            .unwrap()
            .path_key();
        let arg_name = reg
            .descriptor(&arg_path)
            .unwrap()
            .parameters
            .iter()
            .find(|p| p.kind == "argument")
            .unwrap()
            .name
            .clone();
        assert!(reg
            .build_argv(&arg_path, &BTreeMap::new(), &[arg_name], &BTreeMap::new())
            .is_err());
    }
}

/// Synthetic registry exercising rules the shipped fixture does not have:
/// repeatable-with-choices, `when_parameter` fed through `repeated`, and a
/// multi-name `required_when`.
fn synthetic_help() -> MachineHelp {
    serde_json::from_value(serde_json::json!({
        "schema_version": 1,
        "cli_version": "0.0.0-test",
        "registry_digest": "digest_test",
        "global_options": {"json": "emit the machine envelope"},
        "error_codes": [{"code": "AI_STP_TEST", "handling": "fail"}],
        "commands": [{
            "path": ["probe", "run"],
            "summary": "synthetic",
            "mutability": "read",
            "confirmation": "none",
            "next_actions": ["probe status"],
            "parameters": [
                {"name": "tag", "kind": "option", "value_type": "string",
                 "repeatable": true, "choices": ["a", "b"]},
                {"name": "mode", "kind": "option", "value_type": "string",
                 "repeatable": true},
                {"name": "first", "kind": "option", "value_type": "string"},
                {"name": "second", "kind": "option", "value_type": "string"}
            ],
            "parameter_rules": [
                {"kind": "required_when", "parameters": ["first", "second"],
                 "when_parameter": "mode", "when_values": ["deep"]}
            ]
        }]
    }))
    .unwrap()
}

#[test]
fn argv_choices_enforced_on_repeated_values() {
    let reg = CommandRegistry::from_help(&synthetic_help());
    let mut repeated = BTreeMap::new();
    repeated.insert("tag".to_string(), vec!["a".to_string(), "b".to_string()]);
    assert!(reg
        .build_argv("probe run", &BTreeMap::new(), &[], &repeated)
        .is_ok());

    repeated.insert("tag".to_string(), vec!["a".to_string(), "z".to_string()]);
    assert!(matches!(
        reg.build_argv("probe run", &BTreeMap::new(), &[], &repeated),
        Err(BuildError::ChoiceViolation { .. })
    ));
}

#[test]
fn argv_when_parameter_reads_repeated_values() {
    let reg = CommandRegistry::from_help(&synthetic_help());
    // `mode` is repeatable — `mode=deep` arrives through `repeated` and must
    // condition the required_when rule exactly as a scalar value would.
    let mut repeated = BTreeMap::new();
    repeated.insert("mode".to_string(), vec!["shallow".to_string()]);
    assert!(reg
        .build_argv("probe run", &BTreeMap::new(), &[], &repeated)
        .is_ok());

    repeated.insert("mode".to_string(), vec!["deep".to_string()]);
    assert!(reg
        .build_argv("probe run", &BTreeMap::new(), &[], &repeated)
        .is_err());
}

#[test]
fn argv_required_when_needs_every_named_parameter() {
    let reg = CommandRegistry::from_help(&synthetic_help());
    let mut repeated = BTreeMap::new();
    repeated.insert("mode".to_string(), vec!["deep".to_string()]);
    // One of two named parameters is not enough.
    let mut values = BTreeMap::new();
    values.insert("first".to_string(), "1".to_string());
    assert!(reg
        .build_argv("probe run", &values, &[], &repeated)
        .is_err());
    values.insert("second".to_string(), "2".to_string());
    assert!(reg.build_argv("probe run", &values, &[], &repeated).is_ok());
}

#[test]
fn machine_help_preserves_full_wire() {
    let reg = CommandRegistry::from_help(&synthetic_help());
    assert_eq!(reg.cli_version, "0.0.0-test");
    assert_eq!(reg.registry_digest, "digest_test");
    assert!(reg.error_codes.is_array() && !reg.error_codes.as_array().unwrap().is_empty());
    assert!(reg.global_options.is_object());
    let desc = reg.descriptor("probe run").unwrap();
    assert_eq!(desc.next_actions, vec!["probe status".to_string()]);
}

/// Regression: a child emitting more than a pipe buffer's worth of stdout
/// (typical for `help --agent`) must not deadlock the runner. The previous
/// implementation read stdout only after exit; the child blocked on write
/// and hit the deadline every time.
#[cfg(unix)]
#[test]
fn large_stdout_does_not_deadlock() {
    // ~200KB JSON envelope — far beyond the 64KB pipe buffer.
    let (dir, exe) = fake_cli(
        "#!/bin/sh\nprintf '{\"schema_version\":1,\"ok\":true,\"request_id\":null,\"operation_id\":null,\"data\":{\"blob\":\"%s\"},\"warnings\":[],\"next_actions\":[],\"continuations\":[],\"error\":null}' \"$(head -c 150000 /dev/zero | tr '\\0' 'x')\"",
    );
    let env = run_fake(&exe, 30_000).expect("spawn + drain");
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
    use ai_stp_desktop_core::envelope::{Continuation, ContinuationActor};
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
    // `agent` is its own actor in the contract — modeled, still never
    // auto-run; absent / unknown / empty actors never auto-run either.
    assert_eq!(mk(None).actor_kind(), ContinuationActor::Human);
    assert_eq!(mk(Some("agent")).actor_kind(), ContinuationActor::Agent);
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
    use std::sync::atomic::{AtomicUsize, Ordering};
    static SEQ: AtomicUsize = AtomicUsize::new(0);
    let dir = std::env::temp_dir().join(format!(
        "ai-stp-test-{}-{}",
        std::process::id(),
        SEQ.fetch_add(1, Ordering::Relaxed)
    ));
    std::fs::create_dir_all(&dir).unwrap();
    let exe = dir.join("fake-ai-stp");
    std::fs::File::create(&exe)
        .unwrap()
        .write_all(body.as_bytes())
        .unwrap();
    std::fs::set_permissions(&exe, std::fs::Permissions::from_mode(0o755)).unwrap();
    (dir, exe)
}

/// Run a fake CLI, tolerating a transient ETXTBSY: on loaded CI filesystems
/// the exec can race the just-written file's page-cache flush.
#[cfg(unix)]
fn run_fake(exe: &std::path::Path, timeout_ms: u64) -> Result<Envelope, RunError> {
    let mut runner = CliRunner::system(&CliLocator {
        bundled: Some(exe.to_path_buf()),
        configured: None,
    })
    .unwrap();
    runner.timeout = std::time::Duration::from_millis(timeout_ms);
    let mut last = None;
    for _ in 0..5 {
        match runner.run(&[]) {
            Err(RunError::Spawn(e)) if e.raw_os_error() == Some(26) => {
                last = Some(RunError::Spawn(e));
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            other => return other,
        }
    }
    Err(last.unwrap())
}

#[cfg(unix)]
#[test]
fn error_envelope_on_nonzero_exit_is_parsed() {
    let (dir, exe) = fake_cli(
        "#!/bin/sh\nprintf '%s' '{\"schema_version\":1,\"ok\":false,\"error\":{\"code\":\"X\",\"message\":\"m\",\"retryable\":true},\"warnings\":[],\"continuations\":[]}'; exit 1",
    );
    let env = run_fake(&exe, 30_000).unwrap();
    assert!(!env.ok);
    assert!(env.error.unwrap().retryable);
    let _ = std::fs::remove_dir_all(&dir);
}

#[cfg(unix)]
#[test]
fn garbage_stdout_reports_exit_and_stderr() {
    let (dir, exe) = fake_cli("#!/bin/sh\necho boom >&2\necho not-json\nexit 3");
    match run_fake(&exe, 30_000) {
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
    match run_fake(&exe, 300) {
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
        Err(ai_stp_desktop_core::commands::BuildError::UnknownCommand(_))
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

/// Fake CLI that reports the env it was spawned under inside `data`.
/// Never mutate `std::env` in these tests: `child_env` is pure and covered
/// by unit tests in `cli_runner.rs`, so an env-mutating test here would
/// race parallel tests calling `std::env::temp_dir()`.
#[cfg(unix)]
fn env_probe_cli() -> (std::path::PathBuf, std::path::PathBuf) {
    fake_cli(concat!(
        "#!/bin/sh\n",
        "printf '%s' '{\"schema_version\":1,\"ok\":true,\"request_id\":null,\"operation_id\":null,",
        "\"data\":{",
        "\"TMPDIR\":\"'\"${TMPDIR-}\"'\",",
        "\"AI_STP_PROBE\":\"'\"${AI_STP_PROBE-}\"'\"",
        "},\"warnings\":[],\"continuations\":[],\"error\":null}'"
    ))
}

/// End-to-end env wiring without mutating the process env: managed
/// overrides (runner.env) must reach the spawned child through
/// env_clear, and an `AI_STP_*` key exercises both the override path and
/// the prefix passthrough.
#[cfg(unix)]
#[test]
fn spawned_child_receives_runner_env_overrides() {
    let (dir, exe) = env_probe_cli();
    let mut runner = CliRunner::system(&CliLocator {
        bundled: Some(exe.clone()),
        configured: None,
    })
    .unwrap();
    runner.timeout = std::time::Duration::from_secs(30);
    runner
        .env
        .push(("TMPDIR".into(), "/ai-stp-override".into()));
    runner.env.push(("AI_STP_PROBE".into(), "sentinel".into()));
    let env = runner.run(&[]).expect("spawn");
    let data = env.data.unwrap();
    assert_eq!(data["TMPDIR"].as_str().unwrap(), "/ai-stp-override");
    assert_eq!(data["AI_STP_PROBE"].as_str().unwrap(), "sentinel");
    let _ = std::fs::remove_dir_all(&dir);
}

/// The inherited-env list itself must name the Windows temp/profile keys
/// and unix TMPDIR so a future trim fails fast here, not in an installed
/// bundle.
#[test]
fn passthrough_env_lists_temp_and_profile_keys() {
    for k in [
        "TMP",
        "TEMP",
        "USERPROFILE",
        "TMPDIR",
        "APPDATA",
        "LOCALAPPDATA",
        "SystemRoot",
        "WINDIR",
        "PATHEXT",
        "PATH",
        "HOME",
    ] {
        assert!(
            ai_stp_desktop_core::cli_runner::PASSTHROUGH_ENV.contains(&k),
            "missing {k}"
        );
    }
}

/// The field signature of the real bug: the PyInstaller bootloader prints
/// its PYI error on stderr and exits -1/255 without an envelope — the
/// runner must surface it as NoEnvelope carrying the stderr text.
#[cfg(unix)]
#[test]
fn pyi_temp_failure_surfaces_as_no_envelope_with_stderr() {
    let (dir, exe) = fake_cli(
        "#!/bin/sh\necho '[PYI-12345:ERROR] Could not create temporary directory!' >&2\nexit 255",
    );
    match run_fake(&exe, 30_000) {
        Err(RunError::NoEnvelope { exit, stderr }) => {
            assert_eq!(exit, Some(255));
            assert!(stderr.contains("Could not create temporary directory"));
        }
        other => panic!("expected NoEnvelope, got {other:?}"),
    }
    let _ = std::fs::remove_dir_all(&dir);
}

/// Spawn the real PyInstaller sidecar through the full `CliRunner::run`
/// path — including `env_clear` + the passthrough whitelist. CI sets
/// `AI_STP_SIDECAR_EXE` right after building the sidecar, so this is a
/// faithful repro of the installed-app spawn on every OS. Inert without
/// the env var.
#[test]
fn bundled_sidecar_spawns_under_runner_env() {
    let Some(exe) = std::env::var_os("AI_STP_SIDECAR_EXE").map(std::path::PathBuf::from) else {
        return;
    };
    let runner = CliRunner::system(&CliLocator {
        bundled: Some(exe),
        configured: None,
    })
    .unwrap();
    let env = runner
        .run(&["version".to_string()])
        .expect("sidecar spawn under runner env");
    assert!(env.ok, "sidecar failed: {:?}", env.error);
    // `version` only proves the bootloader ran; `doctor` walks the lazily
    // loaded surface (nacl→_cffi_backend, secrets store, registry open)
    // whose missing hidden imports have killed past frozen builds. HOME is
    // in PASSTHROUGH_ENV, so the probe reaches a real per-user state dir.
    let env = runner
        .run(&["doctor".to_string()])
        .expect("sidecar doctor under runner env");
    assert!(env.ok, "sidecar doctor failed: {:?}", env.error);
}
