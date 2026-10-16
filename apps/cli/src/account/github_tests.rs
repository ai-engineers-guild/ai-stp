//! Real account credentials and HTTP; the selected-source server owns replay.

use super::*;
use crate::account::github;

#[test]
fn selected_source_keeps_exact_request_across_lost_reply_and_session_refresh()
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
    let write_state = |state: &State| -> Result<()> {
        let journal = Journal::open(&device, true)?.ok_or_else(invalid)?;
        journal.write(state)
    };
    write_state(&state)?;
    let fixture: Value = serde_json::from_str(include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/resources/packages/contracts/src/ai_stp_contracts/fixtures/v1/github_connector.json"
    )))?;
    let prepared = &fixture["cases"][3];
    let request = prepared["request"]["body"].clone();
    let expected = prepared["body"].clone();
    let input = root.path().join("request.json");
    fs::write(&input, canonical::bytes(&request)?)?;
    for subpath in ["../outside", "a//b", "\\absolute", "cafe\u{301}"] {
        let mut wrong = request.clone();
        wrong["subpath"] = subpath.into();
        fs::write(&input, serde_json::to_vec(&wrong)?)?;
        assert!(github::plan(root.path(), None, &input, &at).is_err());
    }
    fs::write(&input, canonical::bytes(&request)?)?;
    assert!(github::plan(root.path(), Some("http://127.0.0.1:1"), &input, &at).is_err());
    let observation = json!({"schema_version":1,"account_id":account,
        "device_id":device.context().device_id,"account_status":"active"});
    let expected_response = expected.clone();
    let server = thread::spawn(move || -> std::io::Result<()> {
        // Status, first plan, lost apply, refreshed plan, successful replay,
        // server denial and an indeterminate malformed success response.
        for action in [
            "status",
            "plan",
            "lost",
            "plan",
            "success",
            "denied",
            "malformed",
            "noncanonical",
        ] {
            let mut socket = accept(&listener)?;
            let (header, _) = receive(&mut socket)?;
            assert!(header.starts_with("GET /v1/auth/me "));
            assert!(
                header
                    .to_ascii_lowercase()
                    .contains("authorization: bearer ")
            );
            respond(&mut socket, 200, observation.clone())?;
            if action == "plan" {
                continue;
            }
            let mut socket = accept(&listener)?;
            let (header, body) = receive(&mut socket)?;
            if action == "status" {
                assert!(header.starts_with("GET /v1/connectors/github "));
                let repository = json!({"installation_id":1001,"repository_id":2002,"owner_id":3003,
                    "full_name":"example/repository","html_url":"https://github.com/example/repository",
                    "owner_type":"User","private":true,"can_administer":false,"permission":"read",
                    "platform_objects":[],"unexpected_credential":"withheld"});
                let installation = json!({"installation_id":1001,"account_id":3003,"account_login":"example",
                    "account_type":"User","account_html_url":"https://github.com/example",
                    "repository_selection":"selected","repositories":[repository.clone()],"unexpected_credential":"withheld"});
                respond(
                    &mut socket,
                    200,
                    json!({"connections":[{"purpose":"source","configured":true,
                    "state":"connected","expires_at":null,"reason":null,"repositories":[repository],
                    "installations":[installation],"unexpected_credential":"withheld"}],"unexpected_credential":"withheld"}),
                )?;
                continue;
            }
            assert!(header.starts_with("POST /v1/connectors/github/sources "));
            assert_eq!(
                crate::wire::parse(&body).map_err(std::io::Error::other)?,
                request
            );
            if action == "lost" {
                continue;
            }
            if action == "denied" {
                respond(
                    &mut socket,
                    403,
                    json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_PERMISSION_DENIED"}}),
                )?;
                continue;
            }
            let mut response = expected.clone();
            response["unexpected_credential"] = "withheld".into();
            if action == "malformed" {
                response["artifact_inventory"] = json!(["../outside"]);
            }
            if action == "noncanonical" {
                response["artifact_inventory"] = json!(["cafe\u{301}.md"]);
            }
            respond(&mut socket, 200, response)?;
        }
        Ok(())
    });
    let observed = github::status(root.path(), None)?;
    assert_eq!(
        observed["response"]["connections"][0]["repositories"][0]["repository_id"],
        2002
    );
    assert!(!observed.to_string().contains("withheld"));
    let first = github::plan(root.path(), None, &input, &at)?;
    let hash = first.digest()?;
    let path = root.path().join("plan.json");
    fs::write(&path, canonical::bytes(&serde_json::to_value(&first)?)?)?;
    let first = github::read_plan(&path)?;
    assert_eq!(first.digest()?, hash);
    assert!(github::apply(&first, "sha256:wrong", &at).is_err());
    assert!(github::apply(&first, &hash, &after(&at, 901)?).is_err());
    assert!(matches!(
        github::apply(&first, &hash, &at),
        Err(Failure {
            kind: ErrorKind::Unavailable,
            ..
        })
    ));
    state.revision = format!("operation_{}", ulid::Ulid::generate());
    state.plan.operation_id = state.revision.clone();
    if let Session::Authorized { access_token, .. } = &mut state.session {
        *access_token = model::Secret(Zeroizing::new(generated()));
    }
    write_state(&state)?;
    assert!(github::apply(&first, &hash, &at).is_err());
    let refreshed = github::plan(root.path(), None, &input, &at)?;
    let mut moved = serde_json::to_value(&refreshed)?;
    moved["account"]["root_identity"] = json!(["0", "0"]);
    let moved: github::Plan = serde_json::from_value(moved)?;
    assert!(github::apply(&moved, &moved.digest()?, &at).is_err());
    let result = github::apply(&refreshed, &refreshed.digest()?, &at)?;
    assert_eq!(result["response"], expected_response);
    let refused = github::apply(&refreshed, &refreshed.digest()?, &at)
        .err()
        .ok_or("denial")?;
    assert_eq!(refused.details["reason"], "permission_denied");
    assert!(matches!(
        github::apply(&refreshed, &refreshed.digest()?, &at),
        Err(Failure {
            kind: ErrorKind::Unavailable,
            ..
        })
    ));
    assert!(matches!(
        github::apply(&refreshed, &refreshed.digest()?, &at),
        Err(Failure {
            kind: ErrorKind::Unavailable,
            ..
        })
    ));
    if let Session::Authorized { account_id, .. } = &mut state.session {
        *account_id = format!("account_{}", ulid::Ulid::generate());
    }
    write_state(&state)?;
    assert!(github::apply(&refreshed, &refreshed.digest()?, &at).is_err());
    Journal::open(&device, false)?.ok_or("journal")?.retire()?;
    assert!(github::status(root.path(), None).is_err());
    server.join().map_err(|_| "server thread")??;
    Ok(())
}
