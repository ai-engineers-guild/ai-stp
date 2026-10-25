//! Two accounts at one origin retain independent journals, keys and credentials.

use super::*;

#[test]
fn retained_enrollments_sign_refresh_and_logout_only_their_own_session()
-> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = after(&format!("{:.3}", jiff::Timestamp::now()), 60)?;
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let local = identity::apply(&init, &init.digest()?, &at)?;
    let original = local.report();
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let first = connections::plan(root.path(), "Personal", &origin, "github", &at)?;
    let first_created = connections::apply(&first, &first.digest()?, &at)?;
    let second = connections::plan(root.path(), "Company", &origin, "keycloak", &at)?;
    let second_created = connections::apply(&second, &second.digest()?, &at)?;
    let devices = [first.device_id.clone(), second.device_id.clone()];
    let public = [
        first_created["connection"]["public_key"]
            .as_str()
            .ok_or("public key")?
            .to_owned(),
        second_created["connection"]["public_key"]
            .as_str()
            .ok_or("public key")?
            .to_owned(),
    ];
    let accounts = [
        format!("account_{}", ulid::Ulid::generate()),
        format!("account_{}", ulid::Ulid::generate()),
    ];
    let codes = [generated(), generated()];
    let tokens = [
        generated(),
        generated(),
        generated(),
        generated(),
        generated(),
        generated(),
    ];
    let (
        service_origin,
        service_devices,
        service_public,
        service_accounts,
        service_codes,
        service_tokens,
    ) = (
        origin.clone(),
        devices.clone(),
        public.clone(),
        accounts.clone(),
        codes.clone(),
        tokens.clone(),
    );
    let worker = thread::spawn(move || -> std::io::Result<()> {
        for step in 0..6 {
            let mut socket = accept(&listener)?;
            let (header, body) = receive(&mut socket)?;
            let request: Value = serde_json::from_slice(&body)?;
            match step {
                0 | 1 => {
                    assert!(header.starts_with("POST /v1/auth/device HTTP/1.1"));
                    assert_eq!(
                        request["provider"],
                        if step == 0 { "github" } else { "keycloak" }
                    );
                    let user_code = if step == 0 { "BCDF-GHJK" } else { "PQRS-TVWX" };
                    respond(
                        &mut socket,
                        201,
                        json!({"schema_version":1,"device_code":service_codes[step],"user_code":user_code,
                        "verification_uri":format!("{service_origin}/en/device-login"),
                        "verification_uri_complete":format!("{service_origin}/en/device-login?user_code={user_code}"),"expires_in":600,"interval":1}),
                    )?;
                }
                2 | 3 => {
                    let index = step - 2;
                    assert!(header.starts_with("POST /v1/auth/device/token HTTP/1.1"));
                    assert_eq!(request["device_id"], service_devices[index]);
                    assert_eq!(request["public_key"], service_public[index]);
                    assert_eq!(request["device_code"], service_codes[index]);
                    respond(
                        &mut socket,
                        200,
                        json!({"schema_version":1,"access_token":service_tokens[index*2],"refresh_token":service_tokens[index*2+1],
                        "token_type":"Bearer","expires_in":3600,"account_id":service_accounts[index],"device_id":service_devices[index]}),
                    )?;
                }
                4 => {
                    assert!(header.starts_with("POST /v1/auth/device/refresh HTTP/1.1"));
                    assert!(header.contains(&format!("Bearer {}", service_tokens[1])));
                    assert_eq!(request["device_id"], service_devices[0]);
                    let message = format!(
                        "ai-stp:device-refresh:v1\n{}\n{}",
                        service_devices[0],
                        request["checked_at"]
                            .as_str()
                            .ok_or_else(|| std::io::Error::other("timestamp"))?
                    );
                    let public: [u8; 32] = STANDARD
                        .decode(&service_public[0])
                        .map_err(std::io::Error::other)?
                        .try_into()
                        .map_err(|_| std::io::Error::other("key size"))?;
                    let signature = URL_SAFE_NO_PAD
                        .decode(
                            request["signature"]
                                .as_str()
                                .ok_or_else(|| std::io::Error::other("signature"))?,
                        )
                        .map_err(std::io::Error::other)?;
                    VerifyingKey::from_bytes(&public)
                        .map_err(std::io::Error::other)?
                        .verify_strict(
                            message.as_bytes(),
                            &Signature::from_slice(&signature).map_err(std::io::Error::other)?,
                        )
                        .map_err(std::io::Error::other)?;
                    respond(
                        &mut socket,
                        200,
                        json!({"schema_version":1,"access_token":service_tokens[4],"refresh_token":service_tokens[5],
                        "token_type":"Bearer","expires_in":3600,"account_id":service_accounts[0],"device_id":service_devices[0]}),
                    )?;
                }
                _ => {
                    assert!(header.starts_with("POST /v1/auth/logout HTTP/1.1"));
                    assert!(header.contains(&format!("Bearer {}", service_tokens[2])));
                    respond(&mut socket, 200, json!({"schema_version":1,"revoked":true}))?;
                }
            }
        }
        Ok(())
    });
    for connection in [&first.connection_id, &second.connection_id] {
        let start = plan_for_connection(
            root.path(),
            Action::Start,
            None,
            None,
            Some(connection),
            &at,
        )?;
        assert_eq!(apply(&start, &start.digest()?, &at)?["outcome"], "pending");
    }
    let later = after(&at, 5)?;
    for (connection, account) in [
        (&first.connection_id, &accounts[0]),
        (&second.connection_id, &accounts[1]),
    ] {
        let poll = plan_for_connection(
            root.path(),
            Action::Poll,
            None,
            None,
            Some(connection),
            &later,
        )?;
        assert_eq!(
            apply(&poll, &poll.digest()?, &later)?["account_id"],
            *account
        );
    }
    let mut crossed = plan_for_connection(
        root.path(),
        Action::Refresh,
        None,
        None,
        Some(&first.connection_id),
        &later,
    )?;
    crossed
        .connection
        .as_mut()
        .ok_or("connection")?
        .connection_id = second.connection_id.clone();
    assert!(apply(&crossed, &crossed.digest()?, &later).is_err());
    let refresh = plan_for_connection(
        root.path(),
        Action::Refresh,
        None,
        None,
        Some(&first.connection_id),
        &later,
    )?;
    assert_eq!(
        apply(&refresh, &refresh.digest()?, &later)?["outcome"],
        "authorized"
    );
    let logout = plan_for_connection(
        root.path(),
        Action::Logout,
        None,
        None,
        Some(&second.connection_id),
        &later,
    )?;
    assert_eq!(
        apply(&logout, &logout.digest()?, &later)?["outcome"],
        "closed"
    );
    worker.join().map_err(|_| "HTTP fixture")??;
    let personal = status_for_connection(root.path(), Some(&first.connection_id), &later)?;
    let company = status_for_connection(root.path(), Some(&second.connection_id), &later)?;
    assert_eq!(personal["session"]["state"], "authorized");
    assert_eq!(personal["session"]["account_id"], accounts[0]);
    assert_eq!(personal["device_id"], devices[0]);
    assert_eq!(company["session"]["state"], "closed");
    assert_eq!(status(root.path(), &later)?["session"]["state"], "absent");
    assert_eq!(identity_at(root.path())?.report(), original);
    let public = json!([personal, company, connections::list(root.path())?]).to_string();
    for secret in tokens.iter().chain(codes.iter()) {
        assert!(!public.contains(secret));
    }
    assert!(
        plan_for_connection(
            root.path(),
            Action::Refresh,
            Some("https://foreign.example.test"),
            None,
            Some(&first.connection_id),
            &later
        )
        .is_err()
    );
    Ok(())
}
