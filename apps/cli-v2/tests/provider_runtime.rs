use std::{error::Error, fs, process::Command};

use serde_json::Value;

#[cfg(target_os = "linux")]
#[test]
fn mounted_target_is_verified_before_provider_execution() -> Result<(), Box<dyn Error>> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let root = tempfile::tempdir()?;
    let target = root.path().join("target");
    fs::create_dir(&target)?;
    fs::write(target.join("marker"), b"exact\n")?;
    let provider = root.path().join("provider");
    fs::write(
        &provider,
        br##"#!/bin/sh
test "$1" = status || exit 20
test "$HOME" = /home && test -z "$PATH" || exit 21
test ! -e /etc/passwd || exit 22
read -r value < /target/marker
test "$value" = exact || exit 23
for entry in /proc/self/fd/*; do
    test ! -d "$entry" || exit 24
done
if { printf changed > /target/marker; } 2>/dev/null; then exit 25; fi
if { printf created > /target/new; } 2>/dev/null; then exit 26; fi
printf provider-ran
"##,
    )?;
    fs::set_permissions(&provider, fs::Permissions::from_mode(0o500))?;
    let metadata = target.metadata()?;
    let run = |read_only: bool, device: u64, inode: u64| {
        Command::new("/usr/bin/bwrap")
            .args([
                "--unshare-all",
                "--die-with-parent",
                "--new-session",
                "--cap-drop",
                "ALL",
                "--ro-bind",
                "/usr",
                "/usr",
                "--ro-bind-try",
                "/lib",
                "/lib",
                "--ro-bind-try",
                "/lib64",
                "/lib64",
                "--ro-bind-try",
                "/bin",
                "/bin",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--ro-bind",
            ])
            .arg(&provider)
            .args([
                "/run/provider",
                "--ro-bind",
                env!("CARGO_BIN_EXE_ai-stp-v2"),
                "/run/entry",
            ])
            .arg(if read_only { "--ro-bind" } else { "--bind" })
            .arg(&target)
            .args(["/target", "--", "/run/entry", "--ai-stp-target-entry"])
            .arg(device.to_string())
            .arg(inode.to_string())
            .args(["/target", "status"])
            .env_clear()
            .env("HOME", "/home")
            .env("PATH", "")
            .output()
    };
    let control = run(true, metadata.dev(), metadata.ino());
    let Ok(control) = control else {
        eprintln!("Host launcher unavailable; no positive target-mount evidence claimed");
        return Ok(());
    };
    // Launcher refusal is distinct from entry refusal (70), which is a failure here.
    if control.status.code() == Some(1) && control.stdout.is_empty() {
        eprintln!("Host namespaces unavailable; no positive target-mount evidence claimed");
        return Ok(());
    }
    assert!(control.status.success());
    assert_eq!(control.stdout, b"provider-ran");
    assert!(control.stderr.is_empty());
    for (read_only, device, inode) in [
        (true, metadata.dev(), metadata.ino() ^ 1),
        (true, metadata.dev() ^ 1, metadata.ino()),
        (false, metadata.dev(), metadata.ino()),
    ] {
        let output = run(read_only, device, inode)?;
        assert_eq!(output.status.code(), Some(70));
        assert!(output.stdout.is_empty() && output.stderr.is_empty());
    }
    assert_eq!(fs::read_dir(&target)?.count(), 1);
    assert_eq!(fs::read(target.join("marker"))?, b"exact\n");
    Ok(())
}

#[test]
fn network_observation_is_measured_or_explicitly_unavailable() -> Result<(), Box<dyn Error>> {
    let home = tempfile::tempdir()?;
    let output = Command::new(env!("CARGO_BIN_EXE_ai-stp-v2"))
        .args(["provider", "network", "--json"])
        .env("PATH", "")
        .env("HOME", home.path())
        .env("XDG_DATA_HOME", home.path())
        .env("AI_STP_PARENT_ONLY", "must-not-be-inherited")
        .output()?;
    assert!(output.stderr.is_empty());
    let envelope: Value = serde_json::from_slice(&output.stdout)?;
    assert!(!output.status.success() || std::env::consts::OS == "linux");
    if output.status.success() {
        assert_eq!(envelope["ok"], true);
        let report = &envelope["data"];
        assert_eq!(report["enforcement"], "enforced");
        assert_eq!(report["isolated"], "denied");
        assert_eq!(report["launcher"], "bubblewrap");
        assert_eq!(report["filesystem"], "declared_runtime_only");
        assert_eq!(report["positive_control"].as_array().map(Vec::len), Some(3));
        assert!(
            report["launcher_digest"]
                .as_str()
                .is_some_and(|s| s.len() == 71)
        );
    } else {
        // Unprivileged namespaces may be disabled by the host, including CI.
        // Refusal is not positive evidence of isolation; live evidence is separate.
        assert_eq!(output.status.code(), Some(5));
        assert_eq!(envelope["ok"], false);
        assert_eq!(envelope["error"]["code"], "AI_STP_DEPENDENCY_UNAVAILABLE");
    }
    assert_eq!(fs::read_dir(home.path())?.count(), 0);
    Ok(())
}

#[cfg(target_os = "linux")]
#[test]
fn private_probe_reaches_real_listeners_and_rejects_invalid_inputs() -> Result<(), Box<dyn Error>> {
    use std::{
        io::Read,
        net::{TcpListener, UdpSocket},
        time::Duration,
    };
    let tcp4 = TcpListener::bind("127.0.0.1:0")?;
    let tcp6 = TcpListener::bind("[::1]:0")?;
    let udp = UdpSocket::bind("127.0.0.1:0")?;
    tcp4.set_nonblocking(true)?;
    tcp6.set_nonblocking(true)?;
    udp.set_read_timeout(Some(Duration::from_secs(1)))?;
    let nonce = "01M4G0A87QK78WG7SGXXDD2CJ3";
    let invoke = |args: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_ai-stp-v2"))
            .arg("--internal-provider-network-probe")
            .args(args)
            .env_clear()
            .output()
    };
    let output = invoke(&[
        &tcp4.local_addr()?.port().to_string(),
        &tcp6.local_addr()?.port().to_string(),
        &udp.local_addr()?.port().to_string(),
        nonce,
    ])?;
    assert!(output.status.success());
    assert!(output.stderr.is_empty());
    assert_eq!(
        serde_json::from_slice::<Value>(&output.stdout)?["sent"],
        serde_json::json!([true, true, true])
    );
    for listener in [tcp4, tcp6] {
        let (mut socket, _) = listener.accept()?;
        socket.set_read_timeout(Some(Duration::from_secs(1)))?;
        let mut bytes = Vec::new();
        Read::by_ref(&mut socket).take(64).read_to_end(&mut bytes)?;
        assert_eq!(bytes, nonce.as_bytes());
    }
    let mut bytes = [0u8; 64];
    let (size, _) = udp.recv_from(&mut bytes)?;
    assert_eq!(&bytes[..size], nonce.as_bytes());
    for args in [
        vec![],
        vec!["0", "1", "2", nonce],
        vec!["1", "2", "65536", nonce],
        vec!["1", "2", "3", "secret-argument"],
        vec!["1", "2", "3", nonce, "extra"],
    ] {
        let output = invoke(&args)?;
        assert_eq!(output.status.code(), Some(2));
        assert!(output.stdout.is_empty() && output.stderr.is_empty());
    }
    for args in [
        vec!["--ai-stp-target-entry"],
        vec!["--ai-stp-target-entry", "secret", "0", "/tmp", "status"],
        vec!["--ai-stp-target-entry", "0", "0", "/", "status"],
        vec!["--ai-stp-provider-worker"],
        vec![
            "--ai-stp-provider-worker",
            "ai-stp-provider-01ARZ3NDEKTSV4RRFFQ69G5FAV.service",
        ],
        vec!["--ai-stp-provider-worker", "secret-argument", "extra"],
    ] {
        let output = Command::new(env!("CARGO_BIN_EXE_ai-stp-v2"))
            .args(args)
            .env_clear()
            .output()?;
        assert_eq!(output.status.code(), Some(70));
        assert!(output.stdout.is_empty() && output.stderr.is_empty());
    }
    Ok(())
}
