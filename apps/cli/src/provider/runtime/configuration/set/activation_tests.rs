//! Observe only test-owned consumers and roots; no harness or model is launched.

use super::*;
use std::{
    error::Error,
    ffi::OsStr,
    process::{Command, Stdio},
    result::Result,
};

struct Consumer(std::process::Child);

impl Drop for Consumer {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn consumer(root: &Path, override_root: Option<&OsStr>) -> Result<Consumer, Box<dyn Error>> {
    let home = root.join("home");
    let project = root.join("project");
    fs::create_dir_all(&home)?;
    fs::create_dir_all(&project)?;
    let executable = root.join("claude");
    if !executable.exists() {
        std::os::unix::fs::symlink("/bin/sh", &executable)?;
    }
    let mut command = Command::new(&executable);
    command
        .args(["-c", "printf 'consumer-ready\\n'; read -r fixture_input"])
        .env_clear()
        .env("HOME", &home)
        .current_dir(project)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped());
    if let Some(path) = override_root {
        command.env("CLAUDE_CONFIG_DIR", path);
    }
    let mut child = Consumer(command.spawn()?);
    let output = child.0.stdout.take().ok_or("consumer stdout")?;
    let mut ready = String::new();
    BufReader::new(output.take(64)).read_line(&mut ready)?;
    if ready != "consumer-ready\n" {
        return Err("consumer did not reach its readiness boundary".into());
    }
    Ok(child)
}

#[test]
fn claude_consumer_uses_its_explicit_configuration_root() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path();
    let configured = root.join("corporate-config");
    let default = root.join("home/.claude");
    fs::create_dir_all(&configured)?;
    fs::create_dir_all(&default)?;
    let child = consumer(root, Some(configured.as_os_str()))?;
    let definition = harnesses::definition("claude-code")?;
    let pid = child.0.id();
    let process = process(pid)?.ok_or("consumer exited")?;
    let executable = fs::read_link(format!("/proc/{pid}/exe"))?;
    assert!(matches(definition, &process, &executable, &[]));

    let observed = context(pid, definition)?;
    assert!(overlaps(&observed, &[Target::open(&configured)?])?);
    assert!(!overlaps(&observed, &[Target::open(&default)?])?);
    assert!(observed.contains(&root.join("home/.agents")));
    assert!(observed.contains(&root.join("project")));
    Ok(())
}

#[test]
fn claude_consumer_without_an_override_uses_the_default_root() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path();
    let default = root.join("home/.claude");
    fs::create_dir_all(&default)?;
    for value in [None, Some(OsStr::new(""))] {
        let child = consumer(root, value)?;
        let observed = context(child.0.id(), harnesses::definition("claude-code")?)?;
        assert!(overlaps(&observed, &[Target::open(&default)?])?);
    }
    Ok(())
}

#[test]
fn claude_consumer_with_an_invalid_override_cannot_imply_quiescence() -> Result<(), Box<dyn Error>>
{
    let temporary = tempfile::tempdir()?;
    let oversized = format!("/{}", "x".repeat(4096));
    for value in [OsStr::new("relative-config"), OsStr::new(&oversized)] {
        let child = consumer(temporary.path(), Some(value))?;
        assert!(context(child.0.id(), harnesses::definition("claude-code")?).is_err());
    }
    Ok(())
}

#[test]
fn explicit_claude_configuration_root_requires_staged_activation() -> Result<(), Box<dyn Error>> {
    const PROBE: &str = "AI_STP_TEST_CLAUDE_INACTIVE_ROOT";
    if let Some(path) = std::env::var_os(PROBE) {
        let target = Target::open(Path::new(&path))?;
        let refused = super::super::super::apply::require_inactive(&target)
            .err()
            .ok_or("custom Claude root bypassed staged activation")?;
        assert!(matches!(refused.kind, ErrorKind::Precondition));
        println!("custom-claude-root-refused");
        return Ok(());
    }

    let temporary = tempfile::tempdir()?;
    let root = temporary.path();
    let configured = root.join("corporate-config");
    let home = root.join("home");
    let project = root.join("project");
    for directory in [&configured, &home, &project] {
        fs::create_dir(directory)?;
    }
    let module = module_path!().split_once("::").ok_or("test module")?.1;
    let output = Command::new(std::env::current_exe()?)
        .args([
            "--exact",
            &format!("{module}::explicit_claude_configuration_root_requires_staged_activation"),
            "--nocapture",
        ])
        .env_clear()
        .env("HOME", home)
        .env("CLAUDE_CONFIG_DIR", &configured)
        .env(PROBE, &configured)
        .current_dir(project)
        .output()?;
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("custom-claude-root-refused"));
    Ok(())
}
