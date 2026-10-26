//! Actual platform vault sessions and same-account replacement over HTTP.

use super::{Error, owned_slot};
use ai_stp_cli::{
    account::{self, Action, connections, enrollment_recovery},
    digest, identity,
};
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    path::Path,
    thread,
    time::{Duration, Instant},
};

fn clock(at: &str, seconds: u64) -> Result<String, Box<dyn Error>> {
    Ok(format!(
        "{:.3}",
        at.parse::<jiff::Timestamp>()?
            .checked_add(Duration::from_secs(seconds))?
    ))
}

fn request(stream: &mut TcpStream) -> std::io::Result<(String, Value)> {
    stream.set_read_timeout(Some(Duration::from_secs(5)))?;
    let mut header = Vec::new();
    while !header.ends_with(b"\r\n\r\n") && header.len() < 32768 {
        let mut byte = [0];
        stream.read_exact(&mut byte)?;
        header.push(byte[0]);
    }
    if !header.ends_with(b"\r\n\r\n") {
        return Err(std::io::Error::other("bounded fixture header required"));
    }
    let header = String::from_utf8(header).map_err(std::io::Error::other)?;
    let length = header
        .lines()
        .filter_map(|line| line.split_once(':'))
        .find(|(name, _)| name.eq_ignore_ascii_case("content-length"))
        .map(|(_, value)| value.trim().parse::<usize>())
        .transpose()
        .map_err(std::io::Error::other)?
        .unwrap_or(0);
    if length > 65536 {
        return Err(std::io::Error::other("bounded fixture body required"));
    }
    let mut bytes = vec![0; length];
    stream.read_exact(&mut bytes)?;
    Ok((header, serde_json::from_slice(&bytes)?))
}

fn respond(stream: &mut TcpStream, status: u16, body: Value) -> std::io::Result<()> {
    let bytes = serde_json::to_vec(&body)?;
    write!(
        stream,
        "HTTP/1.1 {status} Fixture\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        bytes.len()
    )?;
    stream.write_all(&bytes)
}

fn authorize(root: &Path, connection: &str, at: &str) -> Result<(), Box<dyn Error>> {
    let start =
        account::plan_for_connection(root, Action::Start, None, None, Some(connection), at)?;
    account::apply(&start, &start.digest()?, at)?;
    let later = clock(at, 2)?;
    let poll =
        account::plan_for_connection(root, Action::Poll, None, None, Some(connection), &later)?;
    assert_eq!(
        account::apply(&poll, &poll.digest()?, &later)?["outcome"],
        "authorized"
    );
    Ok(())
}

#[test]
#[cfg_attr(
    target_os = "linux",
    ignore = "requires the isolated CI Secret Service bus"
)]
fn native_vault_recovery_preserves_other_sessions_and_uses_same_account_key_constraints()
-> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = clock(&format!("{:.3}", jiff::Timestamp::now()), 60)?;
    let init = identity::plan(root.path(), identity::Storage::OsKeyring, &at)?;
    let _native = owned_slot(&format!("device-key.{}", init.device_id))?;
    let local = identity::apply(&init, &init.digest()?, &at)?;
    let original = local.report();
    let listener = TcpListener::bind("127.0.0.1:0")?;
    listener.set_nonblocking(true)?;
    let origin = format!("http://{}", listener.local_addr()?);
    let first = connections::plan(root.path(), "First", &origin, "github", &at)?;
    let first_key = owned_slot(&format!("device-key.{}", first.device_id))?;
    let first_session = owned_slot(&format!("account-{}", first.device_id))?;
    let created = connections::apply(&first, &first.digest()?, &at)?;
    let second = connections::plan(root.path(), "Second", &origin, "github", &at)?;
    let _second_key = owned_slot(&format!("device-key.{}", second.device_id))?;
    let second_session = owned_slot(&format!("account-{}", second.device_id))?;
    connections::apply(&second, &second.digest()?, &at)?;
    let account = format!("account_{}", ulid::Ulid::generate());
    let other = format!("account_{}", ulid::Ulid::generate());
    let old_public = created["connection"]["public_key"]
        .as_str()
        .ok_or("key")?
        .to_owned();
    let old_device = first.device_id.clone();
    let other_device = second.device_id.clone();
    let service_origin = origin.clone();
    let service_account = account.clone();
    let service_other = other.clone();
    let native_public = original["public_key"].clone();
    let worker = thread::spawn(move || -> std::io::Result<()> {
        let deadline = Instant::now() + Duration::from_secs(60);
        let mut previous_public = Value::String(old_public);
        for _ in 0..10 {
            let mut stream = loop {
                match listener.accept() {
                    Ok((stream, _)) => break stream,
                    Err(e)
                        if e.kind() == std::io::ErrorKind::WouldBlock
                            && Instant::now() < deadline =>
                    {
                        thread::sleep(Duration::from_millis(10))
                    }
                    Err(e) => return Err(e),
                }
            };
            // Winsock inherits the listener's nonblocking mode after accept.
            stream.set_nonblocking(false)?;
            stream.set_write_timeout(Some(Duration::from_secs(5)))?;
            let (header, body) = request(&mut stream)?;
            if header.starts_with("POST /v1/auth/device HTTP/") {
                respond(
                    &mut stream,
                    201,
                    json!({"schema_version":1,"device_code":"native_keyring_device_code_0123456789",
                    "user_code":"ABCD-1234","verification_uri":format!("{service_origin}/en/device-login"),
                    "verification_uri_complete":format!("{service_origin}/en/device-login?user_code=ABCD-1234"),"expires_in":600,"interval":1}),
                )?;
            } else if header.starts_with("POST /v1/auth/device/token HTTP/") {
                let device = body["device_id"]
                    .as_str()
                    .ok_or_else(|| std::io::Error::other("device"))?;
                let account = if device == other_device {
                    &service_other
                } else {
                    &service_account
                };
                if device != old_device && device != other_device {
                    assert_eq!(body["expected_account_id"], service_account);
                    assert_eq!(body["revoked_public_key"], previous_public);
                    assert_ne!(body["public_key"], previous_public);
                    assert_ne!(body["public_key"], native_public);
                    previous_public = body["public_key"].clone();
                }
                respond(
                    &mut stream,
                    200,
                    json!({"schema_version":1,"access_token":format!("native-access-{device}"),
                    "refresh_token":format!("native-refresh-{device}"),"token_type":"Bearer","expires_in":3600,
                    "account_id":account,"device_id":device}),
                )?;
            } else if header.starts_with("POST /v1/auth/device/refresh HTTP/") {
                assert_eq!(body["device_id"], old_device);
                respond(
                    &mut stream,
                    403,
                    json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_DEVICE_REVOKED"}}),
                )?;
            } else if header.starts_with("POST /v1/auth/logout HTTP/") {
                assert!(header.contains(&format!("Bearer native-access-{other_device}")));
                respond(&mut stream, 200, json!({"schema_version":1,"revoked":true}))?;
            } else {
                return Err(std::io::Error::other("unexpected fixture request"));
            }
        }
        Ok(())
    });
    authorize(root.path(), &first.connection_id, &at)?;
    authorize(root.path(), &second.connection_id, &clock(&at, 4)?)?;
    let refresh = account::plan_for_connection(
        root.path(),
        Action::Refresh,
        None,
        None,
        Some(&first.connection_id),
        &clock(&at, 8)?,
    )?;
    assert_eq!(
        account::apply(&refresh, &refresh.digest()?, &clock(&at, 8)?)?["outcome"],
        "revoked"
    );
    let old_session = digest::sha256(&first_session.secret()?);
    let old_key = digest::sha256(first_key.password()?.as_bytes());
    let other_session = digest::sha256(&second_session.secret()?);
    let plan = enrollment_recovery::plan(
        root.path(),
        &first.connection_id,
        "Replacement",
        &clock(&at, 10)?,
    )?;
    let replacement_key = owned_slot(&format!("device-key.{}", plan.replacement.device_id))?;
    let replacement_session = owned_slot(&format!("account-{}", plan.replacement.device_id))?;
    enrollment_recovery::apply(&plan, &plan.digest()?, &clock(&at, 10)?)?;
    authorize(
        root.path(),
        &plan.replacement.connection_id,
        &clock(&at, 12)?,
    )?;
    assert_eq!(
        enrollment_recovery::list(root.path())?["recoveries"][0]["state"],
        "authorized"
    );
    assert_eq!(digest::sha256(&first_session.secret()?), old_session);
    assert_eq!(digest::sha256(first_key.password()?.as_bytes()), old_key);
    assert_eq!(digest::sha256(&second_session.secret()?), other_session);
    let replacement_before = digest::sha256(&replacement_session.secret()?);
    replacement_key.remove()?;
    let missing = enrollment_recovery::plan(
        root.path(),
        &plan.replacement.connection_id,
        "Missing-key replacement",
        &clock(&at, 16)?,
    )?;
    assert_eq!(missing.schema_version, 2);
    assert!(missing.revoked_receipt_digest.is_none());
    assert!(missing.missing_key.is_some());
    let _missing_key = owned_slot(&format!("device-key.{}", missing.replacement.device_id))?;
    let _missing_session = owned_slot(&format!("account-{}", missing.replacement.device_id))?;
    enrollment_recovery::apply(&missing, &missing.digest()?, &clock(&at, 16)?)?;
    authorize(
        root.path(),
        &missing.replacement.connection_id,
        &clock(&at, 18)?,
    )?;
    assert_eq!(
        digest::sha256(&replacement_session.secret()?),
        replacement_before
    );
    assert!(replacement_key.bytes()?.is_none());
    assert!(
        enrollment_recovery::list(root.path())?["recoveries"]
            .as_array()
            .ok_or("recoveries")?
            .iter()
            .all(|recovery| recovery["state"] == "authorized")
    );
    let logout = account::plan_for_connection(
        root.path(),
        Action::Logout,
        None,
        None,
        Some(&second.connection_id),
        &clock(&at, 22)?,
    )?;
    account::apply(&logout, &logout.digest()?, &clock(&at, 22)?)?;
    let status = account::status_for_connection(
        root.path(),
        Some(&missing.replacement.connection_id),
        &clock(&at, 24)?,
    )?;
    assert_eq!(status["session"]["state"], "authorized");
    assert_eq!(status["session"]["account_id"], account);
    assert_eq!(
        identity::current(root.path())?.ok_or("identity")?.report(),
        original
    );
    worker
        .join()
        .map_err(|_| "native credential HTTP fixture panicked")??;
    Ok(())
}
