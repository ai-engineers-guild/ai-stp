//! Real anonymous HTTP reads with no identity, state directory or credential store.

use super::*;
use std::{
    error::Error,
    io::{Read, Write},
    net::TcpListener,
    thread,
    time::Duration,
};

type ResponseServer = (String, thread::JoinHandle<std::io::Result<()>>);

fn serve(
    status: u16,
    body: &str,
    header: &str,
) -> std::result::Result<ResponseServer, Box<dyn Error>> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let body = body.to_owned();
    let header = header.to_owned();
    let worker = thread::spawn(move || {
        listener.set_nonblocking(true)?;
        let deadline = std::time::Instant::now() + Duration::from_secs(5);
        let mut stream = loop {
            match listener.accept() {
                Ok((stream, _)) => break stream,
                Err(error)
                    if error.kind() == std::io::ErrorKind::WouldBlock
                        && std::time::Instant::now() < deadline =>
                {
                    thread::sleep(Duration::from_millis(5))
                }
                Err(error) => return Err(error),
            }
        };
        stream.set_nonblocking(false)?;
        stream.set_read_timeout(Some(Duration::from_secs(5)))?;
        let mut request = Vec::new();
        while !request.ends_with(b"\r\n\r\n") {
            let mut byte = [0];
            stream.read_exact(&mut byte)?;
            request.push(byte[0]);
            assert!(request.len() < 32768);
        }
        let request = String::from_utf8(request).map_err(std::io::Error::other)?;
        assert!(request.starts_with("GET /v1/auth/providers HTTP/1.1\r\n"));
        assert!(!request.to_ascii_lowercase().contains("authorization:"));
        assert!(!request.to_ascii_lowercase().contains("cookie:"));
        write!(
            stream,
            "HTTP/1.1 {status} Result\r\nContent-Length: {}\r\nConnection: close\r\n{header}\r\n{body}",
            body.len()
        )
    });
    Ok((origin, worker))
}

#[test]
fn configured_providers_are_bounded_anonymous_and_origin_qualified()
-> std::result::Result<(), Box<dyn Error>> {
    for providers in [vec!["authentik", "keycloak", "gitlab", "saml"], vec![]] {
        let body =
            json!({"schema_version":1,"providers":providers,"future_field":true}).to_string();
        let (origin, worker) = serve(200, &body, "")?;
        let response = read(Some(&origin))?;
        worker.join().map_err(|_| "HTTP fixture")??;
        assert_eq!(response["origin"], origin);
        assert_eq!(response["providers"], json!(providers));
    }
    for body in [
        r#"{"schema_version":2,"providers":["github"]}"#,
        r#"{"schema_version":1,"providers":["github","github"]}"#,
        r#"{"schema_version":1,"providers":["unknown"]}"#,
        r#"{"schema_version":1,"providers":"github"}"#,
    ] {
        let (origin, worker) = serve(200, body, "")?;
        assert!(read(Some(&origin)).is_err());
        worker.join().map_err(|_| "HTTP fixture")??;
    }
    let (origin, worker) = serve(302, "", "Location: https://example.test/\r\n")?;
    assert!(read(Some(&origin)).is_err());
    worker.join().map_err(|_| "HTTP fixture")??;
    Ok(())
}

#[test]
fn provider_choices_match_the_shared_device_authorization_contract()
-> std::result::Result<(), Box<dyn Error>> {
    let schema: Value = serde_json::from_str(include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/resources/schemas/v1/auth-device-authorization-request.schema.json"
    )))?;
    assert_eq!(json!(IDS), schema["$defs"]["OAuthProvider"]["enum"]);
    Ok(())
}
