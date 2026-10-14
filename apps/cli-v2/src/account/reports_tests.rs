//! Actual bounded HTTP and durable private files, including lost delivery.

use super::*;
use crate::account::reports;

#[test]
fn report_delivery_binds_exact_text_and_recovers_without_duplicate_effects()
-> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let device = identity::apply(&init, &init.digest()?, &at)?;
    let account = device.context().account_id;
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let start = plan(root.path(), Action::Start, Some(&origin), None, &at)?;
    let mut state = State {
        plan: start.clone(),
        revision: start.operation_id.clone(),
        session: Session::Authorized {
            account_id: account.clone(),
            access_token: model::Secret(Zeroizing::new(generated())),
            refresh_token: model::Secret(Zeroizing::new(generated())),
            expires_at: after(&at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.clone(),
    };
    let save = |state: &State| -> Result<()> {
        Journal::open(&device, true)?
            .ok_or_else(invalid)?
            .write(state)
    };
    save(&state)?;
    let input = root.path().join("request.json");
    let mut request = json!({"topic":"other","subject":"A client question","message":"Cafe\u{301}","idempotency_key":"native-report-original-01"});
    fs::write(&input, serde_json::to_vec(&request)?)?;
    let preview = reports::preview(root.path(), None, &input, &at)?;
    assert_eq!(preview["report"]["message"], "Cafe\u{301}");
    assert_ne!(
        preview["report"]["idempotency_key"],
        request["idempotency_key"]
    );
    assert_eq!(
        reports::preview(root.path(), None, &input, &after(&at, 1)?)?,
        preview
    );
    request["message"] = "Different".into();
    fs::write(&input, serde_json::to_vec(&request)?)?;
    assert!(reports::preview(root.path(), None, &input, &at).is_err());
    let id = preview["plan_id"].as_str().ok_or("missing plan")?;
    let hash = preview["plan_digest"].as_str().ok_or("missing digest")?;
    assert!(reports::confirm(root.path(), id, hash, false).is_err());
    assert!(
        reports::confirm(root.path(), id, &format!("sha256:{}", "0".repeat(64)), true).is_err()
    );
    assert!(reports::status(root.path(), None, "../outside").is_err());
    assert!(reports::list(root.path(), None, Some("&outside=true")).is_err());
    if let Session::Authorized { account_id, .. } = &mut state.session {
        *account_id = format!("account_{}", ulid::Ulid::generate());
    }
    save(&state)?;
    assert!(reports::confirm(root.path(), id, hash, true).is_err());
    if let Session::Authorized {
        account_id,
        expires_at,
        ..
    } = &mut state.session
    {
        *account_id = account.clone();
        *expires_at = "2000-01-01T00:00:00.000Z".into();
    }
    save(&state)?;
    assert!(reports::confirm(root.path(), id, hash, true).is_err());
    if let Session::Authorized { expires_at, .. } = &mut state.session {
        *expires_at = after(&at, 3600)?;
    }
    save(&state)?;
    let case_id = format!("report_{}", ulid::Ulid::generate());
    let response = json!({"schema_version":1,"case_id":case_id,"topic":"other","object_kind":"", "stable_id":"","version":"",
        "state":"submitted","vulnerability":false,"locale":"en","created_at":at,"staff_detail":"withheld"});
    let expected = preview["report"].clone();
    let case = response.clone();
    let observation = json!({"schema_version":1,"account_id":account,"device_id":device.context().device_id,"account_status":"active"});
    let server = thread::spawn(move || -> std::io::Result<()> {
        let mut first = None;
        for action in ["lost", "deliver", "status", "list", "next"] {
            let mut socket = accept(&listener)?;
            let (header, _) = receive(&mut socket)?;
            assert!(header.starts_with("GET /v1/auth/me "));
            respond(&mut socket, 200, observation.clone())?;
            let mut socket = accept(&listener)?;
            let (header, body) = receive(&mut socket)?;
            assert!(
                header
                    .to_ascii_lowercase()
                    .contains("authorization: bearer ")
            );
            if matches!(action, "lost" | "deliver") {
                assert!(header.starts_with("POST /v1/requests "));
                assert_eq!(serde_json::from_slice::<Value>(&body)?, expected);
                if action == "lost" {
                    first = Some(body);
                    continue;
                }
                assert_eq!(first.as_ref(), Some(&body));
                respond(&mut socket, 201, case.clone())?;
            } else if action == "status" {
                assert!(header.starts_with(&format!(
                    "GET /v1/requests/{} ",
                    case["case_id"].as_str().unwrap_or_default()
                )));
                let mut current = case.clone();
                current["state"] = "triaged".into();
                respond(&mut socket, 200, current)?;
            } else {
                assert!(header.starts_with(if action == "list" {
                    "GET /v1/requests?page_size=100 "
                } else {
                    "GET /v1/requests?page_size=100&cursor=next_page "
                }));
                respond(
                    &mut socket,
                    200,
                    json!({"schema_version":1,"items":if action=="list" {vec![case.clone()]}else{vec![]},
                    "page":{"schema_version":1,"page_size":100,"next_cursor":if action=="list"{Some("next_page")}else{None},"staff_detail":"withheld"},"staff_detail":"withheld"}),
                )?;
            }
        }
        Ok(())
    });
    assert!(reports::confirm(root.path(), id, hash, true).is_err());
    fs::remove_file(&input)?;
    let result = reports::confirm(root.path(), id, hash, true)?;
    assert_eq!(result["case"]["case_id"], case_id);
    assert!(result["case"].get("staff_detail").is_none());
    assert_eq!(
        reports::status(root.path(), None, &case_id)?["case"]["state"],
        "triaged"
    );
    let page = reports::list(root.path(), None, None)?;
    assert_eq!(page["response"]["page"]["next_cursor"], "next_page");
    assert!(!page.to_string().contains("staff_detail"));
    assert!(
        reports::list(root.path(), None, Some("next_page"))?["response"]["items"]
            .as_array()
            .ok_or("missing items")?
            .is_empty()
    );
    server.join().map_err(|_| "report server panicked")??;
    state.session = Session::Closed {
        reason: "remote_sessions_revoked".into(),
    };
    save(&state)?;
    let historical = reports::confirm(root.path(), id, hash, true)?;
    assert_eq!(historical["historical"], true);
    assert_eq!(historical["case"], result["case"]);
    assert!(reports::status(root.path(), None, &case_id).is_err());
    Ok(())
}
