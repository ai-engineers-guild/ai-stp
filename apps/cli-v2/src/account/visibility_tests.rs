//! Real account credentials and HTTP; the selected-source server owns replay.

use super::*;
use crate::account::visibility;

#[test]
fn visibility_binds_confirmation_and_reconciles_without_repeating_historical_effects()
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
    let request = json!({"object_kind":"component", "stable_id":format!("component_{}",ulid::Ulid::generate()),
        "version":"1.0","visibility":"public","idempotency_key":"visibility-test-original-01"});
    let remote = json!({"schema_version":1,"plan_id":format!("plan_{}",ulid::Ulid::generate()),
        "plan_hash":format!("sha256:{}","a".repeat(64)),"state":"planned",
        "object_kind":request["object_kind"],"stable_id":request["stable_id"],"version":"1.0",
        "passport_digest":format!("sha256:{}","b".repeat(64)),"previous_visibility":"private",
        "visibility":"public","actor_id":account,"device_id":device.context().device_id,
        "expires_at":after(&at,1800)?,"effects":["set distribution visibility to public"]});
    let input = root.path().join("request.json");
    fs::write(&input, canonical::bytes(&request)?)?;
    assert!(visibility::status(root.path(), None, "../../outside").is_err());
    let observation = json!({"schema_version":1,"account_id":account,
        "device_id":device.context().device_id,"account_status":"active"});
    let expected = remote.clone();
    let server = thread::spawn(move || -> std::io::Result<()> {
        for action in [
            "plan",
            "changed",
            "lost",
            "plan",
            "applied",
            "refused",
            "expired",
            "wrong_actor",
            "wrong_device",
            "wrong_id",
            "status",
        ] {
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
            let mut value = remote.clone();
            value["unexpected_credential"] = "withheld".into();
            if action == "plan" {
                assert!(header.starts_with("POST /v1/access/visibility/plans "));
                let mut request = request.clone();
                request["schema_version"] = 1.into();
                request["device_id"] = remote["device_id"].clone();
                assert_eq!(
                    crate::wire::parse(&body).map_err(std::io::Error::other)?,
                    request
                );
            } else {
                assert!(header.starts_with(&format!(
                    "GET /v1/access/visibility/plans/{} ",
                    remote["plan_id"].as_str().unwrap_or_default()
                )));
                match action {
                    "changed" => value["plan_hash"] = format!("sha256:{}", "c".repeat(64)).into(),
                    "applied" | "refused" | "expired" => value["state"] = action.into(),
                    "wrong_actor" => {
                        value["actor_id"] = format!("account_{}", ulid::Ulid::generate()).into()
                    }
                    "wrong_device" => {
                        value["device_id"] = format!("device_{}", ulid::Ulid::generate()).into()
                    }
                    "wrong_id" => {
                        value["plan_id"] = format!("plan_{}", ulid::Ulid::generate()).into()
                    }
                    "status" => {
                        value["state"] = "applied".into();
                        value["device_id"] = format!("device_{}", ulid::Ulid::generate()).into();
                    }
                    _ => {}
                }
            }
            respond(&mut socket, 200, value)?;
            if action == "lost" {
                let mut socket = accept(&listener)?;
                let (header, body) = receive(&mut socket)?;
                assert!(header.starts_with(&format!(
                    "POST /v1/access/visibility/plans/{}/confirm ",
                    remote["plan_id"].as_str().unwrap_or_default()
                )));
                assert_eq!(
                    crate::wire::parse(&body).map_err(std::io::Error::other)?,
                    json!({"schema_version":1,"plan_hash":remote["plan_hash"],"confirmed":true,"idempotency_key":request["idempotency_key"]})
                );
                // The server commits but its confirmation response is lost.
            }
        }
        Ok(())
    });
    let first = visibility::plan(root.path(), None, &input, &at)?;
    let hash = first.digest()?;
    let path = root.path().join("plan.json");
    fs::write(&path, canonical::bytes(&serde_json::to_value(&first)?)?)?;
    let first = visibility::read_plan(&path)?;
    assert_eq!(first.digest()?, hash);
    assert!(!serde_json::to_string(&first)?.contains("withheld"));
    assert!(visibility::apply(&first, &hash, false, &at).is_err());
    assert!(visibility::apply(&first, "sha256:wrong", true, &at).is_err());
    assert!(visibility::apply(&first, &hash, true, &after(&at, 900)?).is_err());
    assert!(visibility::apply(&first, &hash, true, &at).is_err());
    assert!(matches!(
        visibility::apply(&first, &hash, true, &at),
        Err(Failure {
            kind: ErrorKind::Unavailable,
            ..
        })
    ));
    state.revision = format!("operation_{}", ulid::Ulid::generate());
    state.plan.operation_id = state.revision.clone();
    write_state(&state)?;
    assert!(visibility::apply(&first, &hash, true, &at).is_err());
    let refreshed = visibility::plan(root.path(), None, &input, &at)?;
    assert_eq!(serde_json::to_value(&refreshed)?["remote"], expected);
    for outcome in ["applied", "refused", "expired"] {
        let result = visibility::apply(&refreshed, &refreshed.digest()?, true, &at)?;
        assert_eq!(result["response"]["state"], outcome);
        assert!(!result.to_string().contains("withheld"));
    }
    for _ in 0..3 {
        assert!(visibility::apply(&refreshed, &refreshed.digest()?, true, &at).is_err());
    }
    let historical = visibility::status(
        root.path(),
        None,
        expected["plan_id"].as_str().ok_or("plan ID")?,
    )?;
    assert_eq!(historical["response"]["state"], "applied");
    assert!(!historical.to_string().contains("withheld"));
    server.join().map_err(|_| "server thread")??;
    Ok(())
}
