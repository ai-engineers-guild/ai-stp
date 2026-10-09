use std::{error::Error, fs, process::Command};

use serde_json::Value;

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
    Ok(())
}
