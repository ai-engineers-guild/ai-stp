use aistp_desktop_core::cli_runner::{CliLocator, CliRunner};
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
    assert_eq!(env.data.unwrap()["cli_version"].as_str().unwrap().len() > 0, true);
}

#[test]
fn parses_error_envelope_with_continuation() {
    let env = parse(&fixture("steering-error.json")).unwrap();
    assert!(!env.ok);
    let err = env.error.unwrap();
    assert_eq!(err.code, "AI_STP_VALIDATION_ERROR");
    assert!(!err.retryable);
    assert!(env.continuations.iter().any(|c| c.actor.as_deref() == Some("cli") && !c.argv.is_empty()));
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
            "install", "plan", "--setup", "setup_01ABC@1.0", "--project", "/tmp/proj",
            "--harness", "claude-code"
        ]
    );
}

#[test]
fn argv_refuses_undeclared_and_missing() {
    let help: MachineHelp = serde_json::from_slice(&fixture("machine-help.json")).unwrap();
    let reg = CommandRegistry::from_help(&help);

    let mut values = BTreeMap::new();
    values.insert("undeclared".to_string(), "x".to_string());
    assert!(reg.build_argv("install plan", &values, &[], &BTreeMap::new()).is_err());

    assert!(reg.build_argv("install plan", &BTreeMap::new(), &[], &BTreeMap::new()).is_err());
}

#[test]
fn argv_enforces_declared_rules() {
    let help: MachineHelp = serde_json::from_slice(&fixture("machine-help.json")).unwrap();
    let reg = CommandRegistry::from_help(&help);

    // install plan: `required_when` project while setup present — refuse without it.
    let mut values = BTreeMap::new();
    values.insert("setup".to_string(), "setup_01ABC@1.0".to_string());
    values.insert("harness".to_string(), "claude-code".to_string());
    assert!(reg.build_argv("install plan", &values, &[], &BTreeMap::new()).is_err());

    // exactly_one {proposal, setup} applies once action=install is conditioned.
    let mut values = BTreeMap::new();
    values.insert("project".to_string(), "/tmp/p".to_string());
    values.insert("harness".to_string(), "claude-code".to_string());
    values.insert("action".to_string(), "install".to_string());
    assert!(reg.build_argv("install plan", &values, &[], &BTreeMap::new()).is_err());

    // choice violation is refused up front.
    let mut values = BTreeMap::new();
    values.insert("setup".to_string(), "setup_01ABC@1.0".to_string());
    values.insert("project".to_string(), "/tmp/p".to_string());
    values.insert("harness".to_string(), "not-a-harness".to_string());
    assert!(reg.build_argv("install plan", &values, &[], &BTreeMap::new()).is_err());

    // target status: both required options present.
    let mut values = BTreeMap::new();
    values.insert("project".to_string(), "a".to_string());
    values.insert("harness".to_string(), "codex".to_string());
    assert!(reg.build_argv("target status", &values, &[], &BTreeMap::new()).is_ok());
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
