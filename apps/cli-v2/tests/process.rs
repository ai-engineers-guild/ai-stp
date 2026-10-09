use std::{
    env,
    error::Error,
    ffi::OsString,
    fs,
    io::Write,
    path::Path,
    process::Command,
    thread,
    time::{Duration, Instant},
};

use ai_stp_cli_v2::process::{self, Request};

// The test executable is also the child fixture; no shell or installed runtime.
#[test]
fn child_fixture() -> Result<(), Box<dyn Error>> {
    let Ok(mode) = env::var("AI_STP_CHILD_MODE") else {
        return Ok(());
    };
    match mode.as_str() {
        "output" => {
            assert!(env::var_os("AI_STP_PARENT_ONLY").is_none());
            assert_eq!(env::var("AI_STP_LITERAL")?, "$(touch injected); & | >");
            let writer = thread::spawn(|| std::io::stderr().write_all(&vec![b'e'; 120_000]));
            std::io::stdout().write_all(&vec![b'o'; 120_000])?;
            writer.join().map_err(|_| "stderr worker failed")??;
        }
        "sleep" => thread::sleep(Duration::from_secs(30)),
        "descendant" => {
            let mut child = Command::new(env::current_exe()?)
                .args(["--exact", "child_fixture", "--nocapture"])
                .env("AI_STP_CHILD_MODE", "delayed-write")
                .spawn()?;
            let ready = env::var_os("AI_STP_READY").ok_or("missing ready path")?;
            let until = Instant::now() + Duration::from_secs(10);
            while !Path::new(&ready).exists() {
                if Instant::now() > until || child.try_wait()?.is_some() {
                    return Err("descendant failed to start".into());
                }
                thread::sleep(Duration::from_millis(5));
            }
            // Deliberately leave a descendant holding both output pipes.
        }
        "delayed-write" => {
            fs::write(
                env::var_os("AI_STP_READY").ok_or("missing ready path")?,
                b"ready",
            )?;
            thread::sleep(Duration::from_secs(1));
            fs::write(
                env::var_os("AI_STP_ESCAPE").ok_or("missing escape path")?,
                b"escaped",
            )?;
            thread::sleep(Duration::from_secs(30));
        }
        _ => return Err("unknown child mode".into()),
    }
    Ok(())
}

#[test]
fn bounded_output_deadline_and_descendant_cleanup() -> Result<(), Box<dyn Error>> {
    let directory = tempfile::tempdir()?;
    let executable = env::current_exe()?;
    let arguments = ["--exact", "child_fixture", "--nocapture"].map(OsString::from);
    let base: Vec<_> = env::vars_os()
        .filter(|(name, _)| {
            name.to_str().is_some_and(|name| {
                ["SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"]
                    .iter()
                    .any(|allowed| name.eq_ignore_ascii_case(allowed))
            })
        })
        .collect();
    let invoke = |mode: &str, limit, timeout| {
        let mut environment = base.clone();
        environment.extend([
            ("AI_STP_CHILD_MODE".into(), mode.into()),
            ("AI_STP_LITERAL".into(), "$(touch injected); & | >".into()),
            (
                "AI_STP_READY".into(),
                directory.path().join("ready").into_os_string(),
            ),
            (
                "AI_STP_ESCAPE".into(),
                directory.path().join("escape").into_os_string(),
            ),
        ]);
        process::run(Request {
            executable: &executable,
            arguments: &arguments,
            directory: directory.path(),
            environment: &environment,
            timeout,
            output_limit: limit,
        })
    };
    let output = invoke("output", 256_000, Duration::from_secs(10))?;
    assert!(output.status.success());
    assert!(output.stdout.iter().filter(|&&byte| byte == b'o').count() >= 120_000);
    assert!(output.stderr.len() >= 120_000);
    assert!(!directory.path().join("injected").exists());
    let overflow = invoke("output", 1024, Duration::from_secs(10));
    assert!(overflow.is_err_and(|failure| failure.message.contains("byte limit")));
    let started = Instant::now();
    assert!(invoke("sleep", 4096, Duration::from_millis(250)).is_err());
    assert!(started.elapsed() < Duration::from_secs(5));
    let output = invoke("descendant", 4096, Duration::from_secs(10))?;
    assert!(output.status.success());
    thread::sleep(Duration::from_millis(1200));
    assert!(
        !directory.path().join("escape").exists(),
        "descendant survived its command"
    );
    Ok(())
}
