//! Real disposable consumer processes; vendor programs and model APIs are unused.

use super::*;
use std::{
    error::Error,
    io::{BufRead, BufReader, Read, Write},
    path::Path,
    process::{Child, Command, Stdio},
    time::Duration,
};
const PROBE: &str = "AI_STP_NATIVE_CONSUMER_FIXTURE";
const CONFIRM: &str = "AI_STP_NATIVE_CONSUMER_CONFIRM";
#[test]
fn fixture_consumer() -> std::result::Result<(), Box<dyn Error>> {
    if std::env::var_os(PROBE).is_none() {
        return Ok(());
    }
    if let Some(path) = std::env::var_os(CONFIRM) {
        let mut handoff = Handoff::parse(crate::wire::parse(&std::fs::read(path)?)?)?;
        let confirmed = handoff.confirm()?;
        println!("CONFIRMED_SESSION:{}", serde_json::to_string(&confirmed)?);
        return Ok(());
    }
    println!("consumer-ready");
    std::io::stdout().flush()?;
    let mut line = String::new();
    std::io::stdin().read_line(&mut line)?;
    Ok(())
}
struct Consumer(Option<Child>);
impl Drop for Consumer {
    fn drop(&mut self) {
        if let Some(child) = self.0.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}
impl Consumer {
    fn finish(&mut self) -> std::result::Result<(), Box<dyn Error>> {
        let mut child = self.0.take().ok_or("consumer")?;
        child
            .stdin
            .as_mut()
            .ok_or("consumer stdin")?
            .write_all(b"finish\n")?;
        if !child.wait()?.success() {
            return Err("consumer failed".into());
        }
        Ok(())
    }
}
fn command(
    executable: &Path,
    home: &Path,
    project: &Path,
    definition: &harnesses::Definition,
    global: &Path,
) -> Command {
    let mut command = Command::new(executable);
    command.env_clear();
    for name in ["SYSTEMROOT", "WINDIR"] {
        if let Some(value) = std::env::var_os(name) {
            command.env(name, value);
        }
    }
    command
        .args([
            "--exact",
            "installation::activation::tests::fixture_consumer",
            "--nocapture",
        ])
        .env(PROBE, "yes")
        .env("HOME", home)
        .env("USERPROFILE", home)
        .env("XDG_CONFIG_HOME", home.join(".config"))
        .env("PRIVATE_PROCESS_CANARY", "test-only-value-never-retained")
        .current_dir(project)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(name) = &definition.root_override {
        command.env(name, global);
    }
    command
}
fn spawn(mut command: Command) -> std::result::Result<Consumer, Box<dyn Error>> {
    let mut consumer = Consumer(Some(command.spawn()?));
    let output = consumer
        .0
        .as_mut()
        .ok_or("consumer")?
        .stdout
        .take()
        .ok_or("stdout")?;
    for line in BufReader::new(output.take(8192)).lines().take(32) {
        if line? == "consumer-ready" {
            return Ok(consumer);
        }
    }
    Err("consumer never reached readiness".into())
}

#[test]
fn all_seven_native_consumers_require_stop_and_a_genuine_new_session()
-> std::result::Result<(), Box<dyn Error>> {
    let _guard = CONSUMERS.lock().map_err(|_| "consumer fixture lock")?;
    for definition in harnesses::definitions()?
        .iter()
        .filter(|d| d.harness_id != "undefined")
    {
        let temporary = tempfile::tempdir()?;
        let root = temporary.path().canonicalize()?;
        let home = root.join("home");
        let project = root.join("project");
        let user = home.join(".agents");
        let global = if definition.xdg_config {
            home.join(".config")
                .join(definition.config_root.as_deref().ok_or("global root")?)
        } else {
            home.join(definition.config_root.as_deref().ok_or("global root")?)
        };
        for path in [&project, &user, &global] {
            std::fs::create_dir_all(path)?;
        }
        let name = definition
            .executable
            .as_deref()
            .ok_or("harness executable")?;
        let executable = root.join(if cfg!(windows) {
            format!("{name}.exe")
        } else {
            name.to_owned()
        });
        if std::fs::hard_link(std::env::current_exe()?, &executable).is_err() {
            std::fs::copy(std::env::current_exe()?, &executable)?;
        }
        let targets = [
            Target::resolve(&global, ".ai-stp-native")?,
            Target::resolve(&user, ".ai-stp-native")?,
            Target::resolve(&project, ".ai-stp-native")?,
        ];
        let refs = targets.iter().collect::<Vec<_>>();
        let mut consumer = spawn(command(&executable, &home, &project, definition, &global))?;
        let mut handoff = Handoff::prepare(&definition.harness_id, &refs)?;
        let document = handoff.value()?;
        assert!(
            !document["sessions"]
                .as_array()
                .ok_or("sessions")?
                .is_empty(),
            "{}",
            definition.harness_id
        );
        let encoded = serde_json::to_string(&document)?;
        assert!(!encoded.contains("PRIVATE_PROCESS_CANARY"));
        assert!(!encoded.contains("test-only-value-never-retained"));
        assert!(!encoded.contains("fixture_consumer"));
        assert!(handoff.require_idle().is_err());
        assert!(handoff.published().is_err());
        consumer.finish()?;
        let idle = handoff.require_idle()?;
        idle.revalidate()?;
        handoff.published()?;
        assert!(
            handoff.confirm().is_err(),
            "a caller outside a new harness cannot confirm"
        );
        let review = root.join("handoff.json");
        std::fs::write(&review, serde_json::to_vec(&handoff.value()?)?)?;
        // A strictly later Linux scheduler tick removes timestamp ambiguity.
        std::thread::sleep(Duration::from_millis(30));
        let output = command(&executable, &home, &project, definition, &global)
            .env(CONFIRM, &review)
            .output()?;
        assert!(
            output.status.success(),
            "{}: {}",
            definition.harness_id,
            String::from_utf8_lossy(&output.stderr)
        );
        let stdout = std::str::from_utf8(&output.stdout)?;
        let session = stdout
            .lines()
            .find_map(|line| line.strip_prefix("CONFIRMED_SESSION:"))
            .ok_or("new session confirmation")?;
        let session: Session = serde_json::from_str(session)?;
        assert_eq!(session.harness_id, definition.harness_id);
        assert!(
            session
                .stamp
                .after(handoff.published.as_ref().ok_or("publication")?)?
        );
        assert!(!handoff.sessions.contains(&session));
        assert!(!global.join(".ai-stp-native").exists());
        assert!(!project.join(".ai-stp-native").exists());
    }
    Ok(())
}

#[test]
fn retained_handoff_preserves_full_native_stamps_and_refuses_open_frames()
-> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().canonicalize()?;
    let target = Target::resolve(&root, ".ai-stp-native")?;
    let mut handoff = Handoff {
        format: "ai-stp-native-handoff/1".into(),
        harness_id: "codex".into(),
        native_os: crate::platform::current()
            .and_then(|p| p.split_once('/'))
            .ok_or("native platform")?
            .0
            .into(),
        roots: vec![Root::capture(&target)?],
        sessions: vec![],
        published: None,
        confirmed: None,
    };
    let original = handoff.value()?;
    let mut changed = original.clone();
    changed["permission_granted"] = true.into();
    assert!(Handoff::parse(changed).is_err());
    handoff.native_os = "windows".into();
    handoff.roots[0].physical = DirectoryIdentity::Windows {
        volume: u64::MAX.to_string(),
        file_id: u128::MAX.to_string(),
    };
    handoff.sessions = vec![Session {
        pid: u32::MAX,
        harness_id: "codex".into(),
        stamp: Stamp::Windows {
            filetime: u64::MAX.to_string(),
        },
    }];
    let value = handoff.value()?;
    assert_eq!(Handoff::parse(value.clone())?.value()?, value);
    assert_eq!(
        value["sessions"][0]["stamp"]["filetime"],
        u64::MAX.to_string()
    );
    let mut changed = value;
    changed["sessions"][0]["stamp"]["filetime"] = "18446744073709551616".into();
    assert!(Handoff::parse(changed).is_err());
    Ok(())
}
