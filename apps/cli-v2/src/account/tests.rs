//! Real HTTP and private files, including a lost single-use exchange response.

use super::*;
#[path = "access_tests.rs"]
mod access_tests;
#[path = "attachment_tests.rs"]
mod attachment_tests;
#[path = "sync_recovery_tests.rs"]
mod sync_recovery_tests;
#[path = "sync_tests.rs"]
mod sync_tests;
use base64::engine::general_purpose::STANDARD;
use ed25519_dalek::{Signature, VerifyingKey};
use std::{
    error::Error,
    fs,
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    os::unix::fs::PermissionsExt,
    thread,
    time::{Duration, Instant},
};

fn receive(socket: &mut TcpStream) -> std::io::Result<(String, Vec<u8>)> {
    socket.set_read_timeout(Some(Duration::from_secs(5)))?;
    let mut header = Vec::new();
    while !header.ends_with(b"\r\n\r\n") && header.len() < 32768 {
        let mut b = [0];
        socket.read_exact(&mut b)?;
        header.push(b[0]);
    }
    let header = String::from_utf8(header).map_err(std::io::Error::other)?;
    let length = header
        .lines()
        .filter_map(|line| line.split_once(':'))
        .find(|(key, _)| key.eq_ignore_ascii_case("content-length"))
        .map(|(_, v)| v.trim().parse::<usize>())
        .transpose()
        .map_err(std::io::Error::other)?
        .unwrap_or(0);
    if length > 65536 {
        return Err(std::io::Error::other("fixture request too large"));
    }
    let mut body = vec![0; length];
    socket.read_exact(&mut body)?;
    Ok((header, body))
}

fn accept(listener: &TcpListener) -> std::io::Result<TcpStream> {
    listener.set_nonblocking(true)?;
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        match listener.accept() {
            Ok((socket, _)) => {
                // Accepted sockets inherit nonblocking mode on BSD platforms.
                socket.set_nonblocking(false)?;
                return Ok(socket);
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock && Instant::now() < deadline => {
                thread::sleep(Duration::from_millis(5))
            }
            Err(e) => return Err(e),
        }
    }
}

fn respond(socket: &mut TcpStream, status: u16, value: Value) -> std::io::Result<()> {
    let body = serde_json::to_vec(&value)?;
    write!(
        socket,
        "HTTP/1.1 {status} Result\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    )?;
    socket.write_all(&body)
}

fn generated() -> String {
    format!("{}{}", ulid::Ulid::generate(), ulid::Ulid::generate())
}

#[test]
fn account_journal_stays_with_the_authenticated_physical_parent()
-> std::result::Result<(), Box<dyn Error>> {
    let sandbox = tempfile::tempdir()?;
    let root = sandbox.path().join("state");
    let displaced = sandbox.path().join("displaced");
    fs::create_dir(&root)?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let initialization = identity::plan(&root, identity::Storage::File, &at)?;
    let device = identity::apply(&initialization, &initialization.digest()?, &at)?;
    let loaded = identity_at(&root)?;
    let intent = plan(&root, Action::Start, None, None, &at)?;

    // Replace the path after identity validation but before journal admission.
    fs::rename(&root, &displaced)?;
    fs::create_dir(&root)?;
    for identity in [&device, &loaded] {
        let journal = Journal::open(identity, true)?.ok_or("journal absent")?;
        journal.admit(&Pending {
            plan: intent.clone(),
            requested_at: at.clone(),
        })?;
        assert!(!root.join("ai-stp-v2-account").exists());
        assert!(displaced.join("ai-stp-v2-account/pending.json").is_file());
        assert_eq!(
            journal.pending()?.ok_or("intent absent")?.plan.digest()?,
            intent.digest()?
        );
    }

    // Returning the same inode restores access; copying it would not.
    fs::remove_dir(&root)?;
    fs::rename(&displaced, &root)?;
    assert_eq!(
        status(&root, &at)?["pending_operation"]["plan_digest"],
        intent.digest()?
    );
    Ok(())
}

#[test]
fn server_device_revocation_clears_credentials_and_has_a_distinct_receipt()
-> std::result::Result<(), Box<dyn Error>> {
    for action in [Action::Poll, Action::Refresh] {
        for interruption in 0..=5 {
            check_server_revocation(action, interruption)?;
        }
    }
    Ok(())
}

fn check_server_revocation(
    action: Action,
    interruption: u8,
) -> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    // Keep the fixture's logical clock independent of runner scheduling.
    let at = after(&format!("{:.3}", jiff::Timestamp::now()), 3600)?;
    let initialization = identity::plan(root.path(), identity::Storage::File, &at)?;
    let device = identity::apply(&initialization, &initialization.digest()?, &at)?;
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let access = generated();
    let refresh = generated();
    let device_code = generated();
    let mut responses = vec![
        (
            201,
            json!({"schema_version":1,"device_code":device_code,"user_code":"ABCD-1234","verification_uri":format!("{origin}/en/device-login"),"verification_uri_complete":format!("{origin}/en/device-login?user_code=ABCD-1234"),"expires_in":600,"interval":1}),
        ),
        (
            200,
            json!({"schema_version":1,"access_token":access,"refresh_token":refresh,"token_type":"Bearer","expires_in":600,"account_id":format!("account_{}",ulid::Ulid::generate()),"device_id":device.context().device_id}),
        ),
        (
            403,
            json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_DEVICE_REVOKED"}}),
        ),
    ];
    if action == Action::Poll {
        responses.remove(1);
    }
    let worker = thread::spawn(move || -> std::io::Result<()> {
        for (route, (status, response)) in ["device", "device/token", "device/refresh"]
            .into_iter()
            .zip(responses)
        {
            let mut socket = accept(&listener)?;
            let (header, _) = receive(&mut socket)?;
            assert!(header.starts_with(&format!("POST /v1/auth/{route} HTTP/1.1")));
            respond(&mut socket, status, response)?;
        }
        Ok(())
    });
    let start = plan(root.path(), Action::Start, Some(&origin), None, &at)?;
    apply(&start, &start.digest()?, &at)?;
    let clock = after(&at, 2)?;
    let poll = plan(root.path(), Action::Poll, None, None, &clock)?;
    let revoked_plan = if action == Action::Refresh {
        apply(&poll, &poll.digest()?, &clock)?;
        plan(root.path(), Action::Refresh, None, None, &clock)?
    } else {
        poll
    };
    let revoked = apply(&revoked_plan, &revoked_plan.digest()?, &clock)?;
    worker.join().map_err(|_| "revocation fixture failed")??;
    assert_eq!(revoked["outcome"], "revoked");
    assert_eq!(
        status(root.path(), &clock)?["session"],
        json!({"state":"closed","reason":"device_revoked"})
    );
    assert!(plan(root.path(), Action::Refresh, None, None, &clock).is_err());
    assert_eq!(
        apply(&revoked_plan, &revoked_plan.digest()?, &clock)?,
        revoked
    );
    assert_eq!(identity_at(root.path())?.report(), device.report());
    for entry in fs::read_dir(root.path().join("ai-stp-v2-account"))? {
        let entry = entry?;
        if entry.file_type()?.is_file() {
            let content = fs::read(entry.path())?;
            for secret in [&access, &refresh, &device_code] {
                assert!(
                    !content
                        .windows(secret.len())
                        .any(|v| v == secret.as_bytes())
                );
            }
        }
    }
    let owner_before = authoring::runtime::owner(root.path())?;
    let recovery = plan(root.path(), Action::Recover, None, None, &clock)?;
    let intent = recovery.recovery.as_ref().ok_or("recovery intent")?;
    assert_eq!(intent.account_id.is_some(), action == Action::Refresh);
    assert_eq!(intent.owner_id, device.context().account_id);
    let later = after(&clock, 3600)?;
    assert!(apply(&recovery, &recovery.digest()?, &later).is_err());
    assert_eq!(identity_at(root.path())?.report(), device.report());
    if interruption > 0 {
        let journal = Journal::open(&device, false)?.ok_or("journal")?;
        journal.admit(&Pending {
            plan: recovery.clone(),
            requested_at: clock.clone(),
        })?;
        if interruption > 1 {
            let store = crate::store::Store::open_at(device.root_directory(), true)?;
            let mut replacement = identity::recovery::Replacement::open(&recovery)?;
            store.fence_retired_devices()?;
            journal.fence()?;
            replacement.admit(&recovery)?;
            if interruption > 2 {
                replacement.replace(&recovery, &clock)?;
            }
            if interruption > 3 {
                journal.retire()?;
            }
            if interruption > 4 {
                let entry = replacement.completed(&recovery, &clock)?;
                journal.complete_receipt(&model::Receipt {
                    plan: recovery.clone(),
                    plan_digest: recovery.digest()?,
                    outcome: Outcome::DeviceReplaced,
                    completed_at: entry.completed_at,
                    account_id: intent.account_id.clone(),
                })?;
            }
        }
        drop(journal);
        assert_eq!(
            status(root.path(), &later)?["pending_operation"]["plan_digest"],
            recovery.digest()?
        );
    }
    let recovered = apply(
        &recovery,
        &recovery.digest()?,
        if interruption == 0 { &clock } else { &later },
    )?;
    assert_eq!(recovered["outcome"], "device_replaced");
    let current = identity_at(root.path())?;
    assert_eq!(current.context().account_id, device.context().account_id);
    assert_eq!(current.context().device_id, intent.device_id);
    assert_ne!(
        current.report()["public_key"],
        device.report()["public_key"]
    );
    assert_eq!(
        current.report()["retired_device_ids"],
        json!([device.context().device_id])
    );
    assert!(device.sign(b"retired").is_err());
    assert!(owner_before.planning().is_err());
    assert!(
        !root
            .path()
            .join("ai-stp-v2-identity")
            .join(format!("device-key.{}", device.context().device_id))
            .exists()
    );
    assert!(
        !root
            .path()
            .join("ai-stp-v2-account")
            .join(format!("account-{}", device.context().device_id))
            .exists()
    );
    assert_eq!(apply(&recovery, &recovery.digest()?, &later)?, recovered);
    assert_eq!(
        apply(&revoked_plan, &revoked_plan.digest()?, &later)?,
        revoked
    );
    assert_eq!(
        identity::apply_public(&initialization, &initialization.digest()?, &later)?,
        device.report()
    );
    assert_eq!(status(root.path(), &later)?["session"]["state"], "absent");
    let next = plan(root.path(), Action::Start, None, None, &later)?;
    assert_eq!(next.origin, origin);
    assert_eq!(next.expected_account_id, intent.account_id);
    assert_eq!(next.revoked_public_key, Some(recovery.public_key.clone()));
    assert!(
        plan(
            root.path(),
            Action::Start,
            Some("https://example.org"),
            None,
            &later
        )
        .is_err()
    );
    Ok(())
}

#[test]
fn account_flow_keeps_secrets_private_and_recovers_without_reexchanging()
-> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = after(&format!("{:.3}", jiff::Timestamp::now()), 3600)?;
    let id_plan = identity::plan(root.path(), identity::Storage::File, &at)?;
    let device = identity::apply(&id_plan, &id_plan.digest()?, &at)?;
    let initial_device = device.report();
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let code = generated();
    let access = generated();
    let refresh_token = generated();
    let account_id = format!("account_{}", ulid::Ulid::generate());
    let (
        service_origin,
        service_code,
        service_access,
        service_refresh,
        service_account,
        service_device,
    ) = (
        origin.clone(),
        code.clone(),
        access.clone(),
        refresh_token.clone(),
        account_id.clone(),
        device.context().device_id,
    );
    let public: [u8; 32] = STANDARD
        .decode(
            initial_device["public_key"]
                .as_str()
                .ok_or("public key absent")?,
        )?
        .try_into()
        .map_err(|_| "invalid public key")?;
    let worker = thread::spawn(move || -> std::io::Result<()> {
        for step in 0..6 {
            let mut socket = accept(&listener)?;
            let (header, body) = receive(&mut socket)?;
            let request: Value = serde_json::from_slice(&body)?;
            let route = match step {
                0 => "device",
                1..=3 => "device/token",
                4 => "device/refresh",
                _ => "logout",
            };
            assert!(header.starts_with(&format!("POST /v1/auth/{route} HTTP/1.1")));
            let (status, response) = match step {
                0 => (
                    201,
                    json!({"schema_version":1,"device_code":service_code,"user_code":"ABCD-1234","verification_uri":format!("{service_origin}/en/device-login"),"verification_uri_complete":format!("{service_origin}/en/device-login?user_code=ABCD-1234"),"expires_in":600,"interval":1}),
                ),
                1 | 2 => {
                    assert!(request["device_code"].as_str() == Some(service_code.as_str()));
                    (
                        400,
                        json!({"schema_version":1,"ok":false,"error":{"code":if step==1 {"AI_STP_AUTHORIZATION_PENDING"} else {"AI_STP_RATE_LIMITED"}}}),
                    )
                }
                3..=4 => {
                    if step >= 4 {
                        assert!(header.to_ascii_lowercase().contains(&format!(
                            "authorization: bearer {}",
                            service_refresh.to_ascii_lowercase()
                        )));
                        let message = format!(
                            "ai-stp:device-refresh:v1\n{service_device}\n{}",
                            request["checked_at"]
                                .as_str()
                                .ok_or_else(|| std::io::Error::other("checked_at missing"))?
                        );
                        let bytes = URL_SAFE_NO_PAD
                            .decode(
                                request["signature"]
                                    .as_str()
                                    .ok_or_else(|| std::io::Error::other("signature missing"))?,
                            )
                            .map_err(std::io::Error::other)?;
                        VerifyingKey::from_bytes(&public)
                            .map_err(std::io::Error::other)?
                            .verify_strict(
                                message.as_bytes(),
                                &Signature::from_slice(&bytes).map_err(std::io::Error::other)?,
                            )
                            .map_err(std::io::Error::other)?;
                    }
                    assert_eq!(request["device_id"], service_device);
                    (
                        200,
                        json!({"schema_version":1,"access_token":service_access,"refresh_token":service_refresh,"token_type":"Bearer","expires_in":600,"account_id":service_account,"device_id":service_device}),
                    )
                }
                _ => {
                    assert!(header.to_ascii_lowercase().contains(&format!(
                        "authorization: bearer {}",
                        service_access.to_ascii_lowercase()
                    )));
                    (200, json!({"schema_version":1,"revoked":true}))
                }
            };
            respond(&mut socket, status, response)?;
        }
        Ok(())
    });
    assert!(
        plan(
            root.path(),
            Action::Start,
            Some("http://192.0.2.1"),
            None,
            &at
        )
        .is_err()
    );
    let start = plan(root.path(), Action::Start, Some(&origin), None, &at)?;
    assert!(!root.path().join("ai-stp-v2-account").exists());
    assert!(apply(&start, "wrong", &at).is_err());
    let receipt = apply(&start, &start.digest()?, &at)?;
    assert_eq!(receipt["outcome"], "pending");
    assert_eq!(apply(&start, &start.digest()?, &at)?, receipt);
    let pending = status(root.path(), &at)?;
    assert_eq!(pending["session"]["user_code"], "ABCD-1234");
    assert!(plan(root.path(), Action::Poll, None, None, &at).is_err());
    assert!(
        plan(
            root.path(),
            Action::Start,
            Some("https://example.com"),
            None,
            &at
        )
        .is_err()
    );
    let mut clock = after(&at, 2)?;
    for expected in ["pending", "rate_limited", "authorized"] {
        let poll = plan(root.path(), Action::Poll, None, None, &clock)?;
        assert_eq!(apply(&poll, &poll.digest()?, &clock)?["outcome"], expected);
        clock = after(&clock, 7)?;
    }
    let active = status(root.path(), &clock)?;
    assert_eq!(active["session"]["account_id"], account_id);
    assert_eq!(active["owner_attached"], false);
    for action in [Action::Refresh, Action::Logout] {
        let p = plan(root.path(), action, None, None, &clock)?;
        let r = apply(&p, &p.digest()?, &clock)?;
        assert_eq!(
            r["outcome"],
            if action == Action::Refresh {
                "authorized"
            } else {
                "closed"
            }
        );
        assert_eq!(apply(&p, &p.digest()?, &clock)?, r);
    }
    worker.join().map_err(|_| "account HTTP fixture failed")??;
    assert_eq!(identity_at(root.path())?.context(), device.context());
    assert_eq!(identity_at(root.path())?.report(), initial_device);
    assert_eq!(apply(&start, &start.digest()?, &clock)?, receipt);
    assert_eq!(status(root.path(), &clock)?["session"]["state"], "closed");
    let directory = root.path().join("ai-stp-v2-account");
    assert_eq!(
        fs::metadata(&directory)?.permissions().mode() & 0o777,
        0o700
    );
    for file in fs::read_dir(&directory)? {
        let file = file?;
        let bytes = fs::read(file.path())?;
        assert_eq!(file.metadata()?.permissions().mode() & 0o077, 0);
        for secret in [&code, &access, &refresh_token] {
            assert!(!bytes.windows(secret.len()).any(|w| w == secret.as_bytes()));
        }
    }

    // Lose the exchange response at the transport boundary. A restarted apply
    // records uncertainty and cannot redeem the single-use code a second time.
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let service_origin = origin.clone();
    let worker = thread::spawn(move || -> std::io::Result<()> {
        let mut socket = accept(&listener)?;
        let (_, original) = receive(&mut socket)?;
        drop(socket);
        let mut socket = accept(&listener)?;
        let (_, repeated) = receive(&mut socket)?;
        assert_eq!(original, repeated);
        respond(
            &mut socket,
            201,
            json!({"schema_version":1,"device_code":generated(),"user_code":"WXYZ-5678","verification_uri":format!("{service_origin}/en/device-login"),"verification_uri_complete":format!("{service_origin}/en/device-login?user_code=WXYZ-5678"),"expires_in":60,"interval":1}),
        )?;
        drop(socket);
        let mut socket = accept(&listener)?;
        let (header, _) = receive(&mut socket)?;
        assert!(header.starts_with("POST /v1/auth/device/token "));
        drop(socket);
        // No listener remains: an accidental retry cannot return a receipt.
        Ok(())
    });
    let start = plan(root.path(), Action::Start, Some(&origin), None, &clock)?;
    let grant_expiry = after(&clock, 60)?;
    assert!(apply(&start, &start.digest()?, &clock).is_err());
    clock = after(&clock, 10)?;
    apply(&start, &start.digest()?, &clock)?;
    assert_eq!(
        status(root.path(), &clock)?["session"]["expires_at"],
        grant_expiry
    );
    clock = after(&clock, 2)?;
    let poll = plan(root.path(), Action::Poll, None, None, &clock)?;
    assert!(apply(&poll, &poll.digest()?, &clock).is_err());
    worker
        .join()
        .map_err(|_| "exchange loss fixture failed")??;
    assert!(plan(root.path(), Action::Logout, None, None, &clock).is_err());
    assert_eq!(
        status(root.path(), &clock)?["pending_operation"]["plan_digest"],
        poll.digest()?
    );
    assert_eq!(
        apply(&poll, &poll.digest()?, &clock)?["outcome"],
        "exchange_unknown"
    );
    assert_eq!(
        status(root.path(), &clock)?["session"]["reason"],
        "exchange_response_unknown"
    );
    assert!(plan(root.path(), Action::Start, None, None, &clock).is_ok());

    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let server_origin = origin.clone();
    let server_device = device.context().device_id;
    let offline_access = generated();
    let offline_refresh = generated();
    let (server_access, server_refresh) = (offline_access.clone(), offline_refresh.clone());
    let worker = thread::spawn(move || -> std::io::Result<()> {
        let mut socket = accept(&listener)?;
        receive(&mut socket)?;
        respond(
            &mut socket,
            201,
            json!({"schema_version":1,"device_code":generated(),"user_code":"JKMN-6789","verification_uri":format!("{server_origin}/en/device-login"),"verification_uri_complete":format!("{server_origin}/en/device-login?user_code=JKMN-6789"),"expires_in":60,"interval":1}),
        )?;
        drop(socket);
        let mut socket = accept(&listener)?;
        receive(&mut socket)?;
        respond(
            &mut socket,
            200,
            json!({"schema_version":1,"access_token":server_access,"refresh_token":server_refresh,"token_type":"Bearer","expires_in":600,"account_id":format!("account_{}",ulid::Ulid::generate()),"device_id":server_device}),
        )
    });
    let start = plan(root.path(), Action::Start, Some(&origin), None, &clock)?;
    apply(&start, &start.digest()?, &clock)?;
    clock = after(&clock, 2)?;
    let poll = plan(root.path(), Action::Poll, None, None, &clock)?;
    apply(&poll, &poll.digest()?, &clock)?;
    worker
        .join()
        .map_err(|_| "offline logout fixture failed")??;
    assert!(plan(root.path(), Action::Refresh, None, None, &at).is_err());
    let logout = plan(root.path(), Action::Logout, None, None, &clock)?;
    let result = apply(&logout, &logout.digest()?, &clock);
    assert_eq!(
        result
            .as_ref()
            .map_err(|_| "offline logout did not complete")?["outcome"],
        "locally_closed_unconfirmed"
    );
    let path = root.path().join("logout.json");
    fs::write(&path, serde_json::to_vec(&logout)?)?;
    let parsed = crate::registry::parser().try_get_matches_from([
        "ai-stp-v2",
        "account",
        "apply",
        "--plan",
        path.to_str().ok_or("plan path")?,
        "--plan-digest",
        &logout.digest()?,
    ])?;
    let warnings = crate::registry::warnings(&parsed, &result);
    let invocation = crate::Invocation {
        continuations: Vec::new(),
        result,
        machine: true,
        text: None,
        warnings,
    };
    assert_eq!(invocation.exit_code(), 0);
    assert_eq!(
        invocation.envelope()["warnings"],
        json!(["remote_logout_unconfirmed"])
    );
    assert_eq!(status(root.path(), &clock)?["session"]["state"], "closed");
    let stored = fs::read(directory.join(format!("account-{}", device.context().device_id)))?;
    for secret in [&offline_access, &offline_refresh] {
        assert!(!stored.windows(secret.len()).any(|v| v == secret.as_bytes()));
    }
    Ok(())
}
