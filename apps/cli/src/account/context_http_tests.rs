//! Actual native vault and authenticated HTTP across retained organizations.

use super::*;

#[test]
fn retained_contexts_revalidate_membership_and_keep_revoked_offline_observations()
-> std::result::Result<(), Box<dyn Error>> {
    exercise_contexts(true)
}

#[test]
fn legacy_context_admission_preserves_the_original_key_session_and_journal()
-> std::result::Result<(), Box<dyn Error>> {
    exercise_contexts(false)
}

#[test]
fn equal_remote_ids_keep_original_origins_and_credentials_after_selecting_another_context()
-> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let local = identity::apply(&init, &init.digest()?, &at)?;
    let original = local.report();
    let account = format!("account_{}", ulid::Ulid::generate());
    let organization = format!("organization_{}", ulid::Ulid::generate());
    let listeners = [
        TcpListener::bind("127.0.0.1:0")?,
        TcpListener::bind("127.0.0.1:0")?,
    ];
    let origins = listeners
        .iter()
        .map(|listener| listener.local_addr().map(|a| format!("http://{a}")))
        .collect::<std::io::Result<Vec<_>>>()?;
    let tokens = [generated(), generated()];
    let mut workers = Vec::new();
    let mut retained = Vec::new();
    for (index, listener) in listeners.into_iter().enumerate() {
        let connection = connections::plan(
            root.path(),
            "Independent server",
            &origins[index],
            "github",
            &at,
        )?;
        connections::apply(&connection, &connection.digest()?, &at)?;
        super::ownership_tests::authorize(
            root.path(),
            &origins[index],
            Some(&connection.connection_id),
            &account,
            &tokens[index],
            &at,
        )?;
        let (remote_account, remote_device, remote_org, token, observed_at) = (
            account.clone(),
            connection.device_id.clone(),
            organization.clone(),
            tokens[index].clone(),
            at.clone(),
        );
        workers.push(thread::spawn(move || -> std::io::Result<()> {
            // Plan/apply each require three observations. Only the original
            // first server receives the later explicit refresh after switching.
            for _ in 0..if index == 0 { 9 } else { 6 } {
                let mut socket = accept(&listener)?;
                let (header, body) = receive(&mut socket)?;
                assert!(body.is_empty());
                let authorization = header
                    .lines()
                    .filter_map(|line| line.split_once(':'))
                    .find(|(name, _)| name.eq_ignore_ascii_case("authorization"))
                    .map(|(_, value)| value.trim());
                assert!(
                    authorization == Some(format!("Bearer {token}").as_str()),
                    "request used another server's credential"
                );
                let value = if header.starts_with("GET /v1/auth/me ") {
                    json!({"schema_version":1,"account_id":remote_account,"device_id":remote_device,"account_status":"active"})
                } else if header.starts_with("GET /v1/context ") {
                    let selected = header
                        .lines()
                        .filter_map(|line| line.split_once(':'))
                        .find(|(name, _)| name.eq_ignore_ascii_case("x-ai-stp-organization-id"))
                        .map(|(_, value)| value.trim());
                    assert!(selected == Some(remote_org.as_str()));
                    json!({"schema_version":1,"mode":"corporate","organization_id":remote_org,
                        "capabilities":{"schema_version":1,"registry_version":2,"mode":"corporate","context_kind":"corporate",
                        "organization_id":remote_org,"authorization_revision":"corporate:origin-fixture:1",
                        "issued_at":observed_at,"generated_at":observed_at,
                        "expires_at":after(&observed_at,300).map_err(std::io::Error::other)?,
                        "capabilities":["organization.read"],"unavailable":{}}})
                } else if header.starts_with("GET /v1/organizations ") {
                    json!({"schema_version":1,"items":[{"schema_version":1,"organization_id":remote_org,
                        "kind":"corporate","display_name":format!("Origin {index}"),"membership_revision":1}]})
                } else {
                    return Err(std::io::Error::other("unexpected origin fixture request"));
                };
                respond(&mut socket, 200, value)?;
            }
            Ok(())
        }));
        retained.push(connection);
    }
    let mut context_ids = Vec::new();
    for connection in &retained {
        let plan = contexts::create_plan(
            root.path(),
            "Same remote identifiers",
            Some(&connection.connection_id),
            Some(&organization),
            &at,
        )?;
        let result = contexts::apply(&plan, &plan.digest()?, &at)?;
        assert_eq!(result["harness_files_changed"], false);
        context_ids.push(result["context_id"].as_str().ok_or("context")?.to_owned());
    }
    assert_ne!(context_ids[0], context_ids[1]);
    let select = contexts::select_plan(root.path(), &context_ids[1], &at)?;
    contexts::apply(&select, &select.digest()?, &at)?;
    let before = contexts::show(root.path(), &context_ids[0], false)?;
    let refreshed = contexts::show(root.path(), &context_ids[0], true)?;
    assert_eq!(
        refreshed["current_organization"]["display_name"],
        "Origin 0"
    );
    assert_eq!(refreshed["context"], before["context"]);
    assert_eq!(before, contexts::show(root.path(), &context_ids[0], false)?);
    let listed = contexts::list(root.path())?;
    assert_eq!(listed["selected"]["context_id"], context_ids[1]);
    for (index, context) in context_ids.iter().enumerate() {
        let observed = contexts::show(root.path(), context, false)?;
        assert_eq!(
            observed["context"]["authority"]["account"]["origin"],
            origins[index]
        );
        assert_eq!(
            observed["context"]["authority"]["account"]["account_id"],
            account
        );
        assert_eq!(
            observed["context"]["authority"]["organization"]["organization_id"],
            organization
        );
        assert!(!observed.to_string().contains(&tokens[0]));
        assert!(!observed.to_string().contains(&tokens[1]));
    }
    assert_eq!(identity_at(root.path())?.report(), original);
    for worker in workers {
        worker.join().map_err(|_| "origin fixture worker")??;
    }
    Ok(())
}

fn exercise_contexts(named: bool) -> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let local = identity::apply(&init, &init.digest()?, &at)?;
    let original = local.report();
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let connection = if named {
        let connection =
            connections::plan(root.path(), "Work and personal", &origin, "github", &at)?;
        connections::apply(&connection, &connection.digest()?, &at)?;
        Some(connection)
    } else {
        None
    };
    let connection_id = connection
        .as_ref()
        .map(|value| value.connection_id.as_str());
    let remote_device = connection.as_ref().map_or_else(
        || local.context().device_id,
        |value| value.device_id.clone(),
    );
    let start = plan_for_connection(
        root.path(),
        Action::Start,
        Some(&origin),
        None,
        connection_id,
        &at,
    )?;
    assert_eq!(start.origin, origin);
    let enrollment = start.connection.clone();
    let account = format!("account_{}", ulid::Ulid::generate());
    let personal = format!("organization_{}", ulid::Ulid::generate());
    let corporate = format!("organization_{}", ulid::Ulid::generate());
    let credential = generated();
    let state = State {
        plan: start.clone(),
        revision: start.operation_id.clone(),
        session: Session::Authorized {
            account_id: account.clone(),
            access_token: model::Secret(Zeroizing::new(credential.clone())),
            refresh_token: model::Secret(Zeroizing::new(generated())),
            expires_at: after(&at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.clone(),
    };
    Journal::for_connection(&local, enrollment.as_ref(), true)?
        .ok_or("journal")?
        .write(&state)?;
    let (server_account, server_personal, server_corporate, server_device, server_token, server_at) = (
        account.clone(),
        personal.clone(),
        corporate.clone(),
        remote_device,
        credential.clone(),
        at.clone(),
    );
    let worker = thread::spawn(move || -> std::io::Result<()> {
        for step in 0..20 {
            let mut socket = accept(&listener)?;
            let (header, body) = receive(&mut socket)?;
            assert!(body.is_empty());
            let lower = header.to_ascii_lowercase();
            assert!(lower.contains(&format!(
                "authorization: bearer {}\r\n",
                server_token.to_ascii_lowercase()
            )));
            assert!(!lower.contains("x-ai-stp-product-mode:"));
            if step % 3 == 0 {
                assert!(header.starts_with("GET /v1/auth/me "));
                respond(
                    &mut socket,
                    200,
                    json!({"schema_version":1,"account_id":server_account,
                    "device_id":server_device,"account_status":"active"}),
                )?;
                continue;
            }
            let revision = if step < 9 { 1 } else { 2 };
            if step % 3 == 1 {
                assert!(header.starts_with("GET /v1/context "));
                let is_corporate = step >= 6;
                let org = if is_corporate {
                    &server_corporate
                } else {
                    &server_personal
                };
                let mode = if is_corporate {
                    "corporate"
                } else {
                    "personal"
                };
                if is_corporate || step == 4 {
                    assert!(lower.contains(&format!(
                        "x-ai-stp-organization-id: {}\r\n",
                        org.to_ascii_lowercase()
                    )));
                } else {
                    assert!(!lower.contains("x-ai-stp-organization-id:"));
                }
                if step == 19 {
                    respond(
                        &mut socket,
                        403,
                        json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_PERMISSION_DENIED"}}),
                    )?;
                    continue;
                }
                respond(
                    &mut socket,
                    200,
                    json!({"schema_version":1,"mode":mode,"organization_id":org,
                    "capabilities":{"schema_version":1,"registry_version":2,"mode":mode,"context_kind":mode,"organization_id":org,
                    "authorization_revision":format!("{mode}:{org}:{revision}"),"issued_at":server_at,"generated_at":server_at,
                    "expires_at":after(&server_at,300).map_err(std::io::Error::other)?,"capabilities":["organization.read"],"unavailable":{},
                    "future_token":"discard"},"future_private_field":"discard"}),
                )?;
            } else {
                assert!(header.starts_with("GET /v1/organizations "));
                assert!(!lower.contains("x-ai-stp-organization-id:"));
                respond(
                    &mut socket,
                    200,
                    json!({"schema_version":1,"items":[
                    {"schema_version":1,"organization_id":server_personal,"kind":"personal","display_name":"Personal","membership_revision":1},
                    {"schema_version":1,"organization_id":server_corporate,"kind":"corporate","display_name":"Company","membership_revision":revision}]}),
                )?;
            }
        }
        Ok(())
    });
    let credential_path = root
        .path()
        .join("ai-stp-v2-account")
        .join(format!("account-{}", local.context().device_id));
    let legacy_bytes = if named {
        None
    } else {
        Some(crate::digest::sha256(&fs::read(&credential_path)?))
    };
    let create = |label: &str, org: Option<&str>| {
        if named {
            contexts::create_plan(root.path(), label, connection_id, org, &at)
        } else {
            contexts::create_legacy_plan(root.path(), label, org, &at)
        }
    };
    let personal_plan = create("Personal", None)?;
    contexts::apply(&personal_plan, &personal_plan.digest()?, &at)?;
    let stale = create("Company", Some(&corporate))?;
    assert!(contexts::apply(&stale, &stale.digest()?, &at).is_err());
    let corporate_plan = create("Company", Some(&corporate))?;
    let completed = contexts::apply(&corporate_plan, &corporate_plan.digest()?, &at)?;
    let personal_id = match &personal_plan.change {
        contexts::Change::Create { context, .. } => context.context_id.clone(),
        _ => return Err("create".into()),
    };
    let corporate_id = match &corporate_plan.change {
        contexts::Change::Create { context, .. } => context.context_id.clone(),
        _ => return Err("create".into()),
    };
    for id in [&personal_id, &corporate_id] {
        let select = contexts::select_plan(root.path(), id, &at)?;
        contexts::apply(&select, &select.digest()?, &at)?;
    }
    let before = contexts::show(root.path(), &corporate_id, false)?;
    assert_eq!(before["online_verified"], false);
    assert!(contexts::show(root.path(), &corporate_id, true).is_err());
    worker.join().map_err(|_| "HTTP fixture")??;
    assert_eq!(before, contexts::show(root.path(), &corporate_id, false)?);
    assert_eq!(
        completed,
        contexts::apply(
            &corporate_plan,
            &corporate_plan.digest()?,
            &corporate_plan.expires_at
        )?
    );
    let listed = contexts::list(root.path())?;
    assert_eq!(listed["contexts"].as_array().ok_or("contexts")?.len(), 2);
    assert_eq!(listed["selected"]["context_id"], corporate_id);
    assert!(!listed.to_string().contains(&credential));
    assert!(!listed.to_string().contains("future_token"));
    assert_eq!(
        status(root.path(), &at)?["session"]["state"],
        if named { "absent" } else { "authorized" }
    );
    if let Some(before) = legacy_bytes {
        assert_eq!(before, crate::digest::sha256(&fs::read(&credential_path)?));
        assert!(!root.path().join("ai-stp-v2-connections").exists());
    }
    assert_eq!(identity_at(root.path())?.report(), original);
    Ok(())
}
