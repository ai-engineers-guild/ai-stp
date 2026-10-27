//! Disposable WASIp2 guest; this is not a product installation component.

use std::env;
use std::fs;
use std::hint::black_box;
use std::io::{self, Write};
use std::net::{SocketAddr, TcpStream, ToSocketAddrs, UdpSocket};
use std::process::Command;
use std::time::Duration;

fn denied<T>(name: &str, result: io::Result<T>) {
    let error = result
        .err()
        .unwrap_or_else(|| panic!("{name} unexpectedly succeeded"));
    assert!(
        matches!(
            error.kind(),
            io::ErrorKind::PermissionDenied | io::ErrorKind::NotFound
        ),
        "{name} failed for an unqualified reason: {error:?}"
    );
    println!("{{\"denied\":\"{name}\",\"kind\":\"{:?}\"}}", error.kind());
}

fn network_denied<T>(name: &str, result: io::Result<T>) {
    let error = result
        .err()
        .unwrap_or_else(|| panic!("{name} unexpectedly succeeded"));
    assert_eq!(
        error.kind(),
        io::ErrorKind::PermissionDenied,
        "{name}: {error:?}"
    );
    println!("{{\"network_denied\":\"{name}\"}}");
}

fn main() {
    let arguments: Vec<String> = env::args().skip(1).collect();
    match arguments.first().map(String::as_str) {
        Some("dns_positive") => {
            let addresses: Vec<_> = ("localhost", 80).to_socket_addrs().unwrap().collect();
            assert!(!addresses.is_empty());
            assert!(addresses.iter().all(|address| address.ip().is_loopback()));
            println!("{{\"guest_dns_positive\":true}}");
        }
        Some("spin") => {
            fs::write("/target/spin_started", b"started\n").unwrap();
            println!("{{\"spin_started\":true}}");
            io::stdout().flush().unwrap();
            let mut value = 1_u64;
            loop {
                value = black_box(value.wrapping_mul(3).wrapping_add(1));
            }
        }
        Some("memory") => {
            let mut positive = vec![0_u8; 1024 * 1024];
            positive.fill(42);
            assert_eq!(black_box(positive)[1023], 42);
            let mut excessive = Vec::<u8>::new();
            assert!(excessive.try_reserve_exact(128 * 1024 * 1024).is_err());
            fs::write("/target/memory_refused", b"refused\n").unwrap();
            println!("{{\"memory_positive_and_limit\":true}}");
        }
        Some("probe") => {
            assert_eq!(arguments.len(), 8);
            assert_eq!(fs::read("/target/canary").unwrap(), b"synthetic target\n");
            assert!(fs::read_dir("/target").unwrap().count() >= 2);
            fs::create_dir("/target/owned").unwrap();
            fs::write("/target/owned/temporary", b"guest publication\n").unwrap();
            fs::rename("/target/owned/temporary", "/target/owned/published").unwrap();
            assert_eq!(
                fs::read("/target/owned/published").unwrap(),
                b"guest publication\n"
            );
            fs::remove_file("/target/owned/published").unwrap();
            fs::remove_dir("/target/owned").unwrap();
            println!("{{\"target_io_and_publication\":true}}");

            for (label, path) in [
                ("host_absolute", arguments[1].as_str()),
                ("outside_namespace", "/outside/canary"),
                ("parent_traversal", "/target/../outside/canary"),
                ("symlink_escape", "/target/escape/canary"),
                ("synthetic_credentials", arguments[2].as_str()),
                ("symlink_credentials", "/target/escape/credentials"),
            ] {
                denied(&format!("{label}_read"), fs::read(path));
                denied(
                    &format!("{label}_write"),
                    fs::write(path, b"must not write\n"),
                );
            }
            denied("outside_enumeration", fs::read_dir("/target/escape"));
            assert_eq!(env::var("AI_STP_GUEST").unwrap(), "controlled");
            assert!(env::var_os("AI_STP_SYNTHETIC_SECRET").is_none());
            assert!(env::var_os("HOME").is_none());
            assert!(env::var_os("USERPROFILE").is_none());
            println!("{{\"explicit_environment_only\":true}}");

            for (label, argument) in [("tcp4", &arguments[3]), ("tcp6", &arguments[4])] {
                let address: SocketAddr = argument.parse().unwrap();
                network_denied(
                    label,
                    TcpStream::connect_timeout(&address, Duration::from_secs(1)),
                );
            }
            // No socket may be created, even before a packet can be sent.
            for (label, argument) in [("udp4", &arguments[5]), ("udp6", &arguments[6])] {
                let address: SocketAddr = argument.parse().unwrap();
                let local = if address.is_ipv4() {
                    "0.0.0.0:0"
                } else {
                    "[::]:0"
                };
                network_denied(
                    label,
                    UdpSocket::bind(local)
                        .and_then(|socket| socket.send_to(b"must not send", address)),
                );
            }
            // The pinned libc getaddrinfo layer erases the WASI permission code
            // into EAI_FAIL. The host first proves the same guest lookup with
            // only the explicit DNS grant enabled; do not call this EPERM.
            assert!(("localhost", 80).to_socket_addrs().is_err());
            println!("{{\"guest_dns_unavailable_without_grant\":true}}");
            let error = Command::new(&arguments[7])
                .arg("--version")
                .output()
                .unwrap_err();
            assert_eq!(error.kind(), io::ErrorKind::Unsupported);
            println!("{{\"host_process_api_absent\":true,\"executed_descendant\":false}}");
            fs::write("/target/probe_completed", b"completed\n").unwrap();
            println!("{{\"wasi_guest_probe\":\"passed\"}}");
        }
        _ => panic!("exact fixture mode required"),
    }
}
