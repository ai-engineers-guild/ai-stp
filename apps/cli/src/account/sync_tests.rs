use super::*;
use crate::{
    canonical, digest, passport,
    store::Store,
    sync::{
        client::Client,
        event::Event,
        ledger::{self, Scope},
        pages,
    },
};
use std::collections::BTreeSet;

#[test]
fn private_push_walks_parents_retries_before_new_versions_and_replays_tombstones()
-> std::result::Result<(), Box<dyn Error>> {
    use crate::store::{
        revisions::{self, Write},
        versions,
    };
    use crate::sync::runtime::{self, Request};
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let device = identity::apply(&init, &init.digest()?, &at)?;
    let context = device.context();
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let start = plan(root.path(), Action::Start, Some(&origin), None, &at)?;
    let token = generated();
    let state = State {
        plan: start.clone(),
        revision: start.operation_id.clone(),
        session: Session::Authorized {
            account_id: context.account_id.clone(),
            access_token: model::Secret(Zeroizing::new(token.clone())),
            refresh_token: model::Secret(Zeroizing::new(generated())),
            expires_at: after(&at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.clone(),
    };
    let journal = Journal::open(&device, true)?.ok_or("journal")?;
    journal.write(&state)?;
    drop(journal);
    let configuration = root.path().join("sync.yaml");
    fs::write(
        &configuration,
        "schema_version: 1\nsync:\n  enabled: true\n",
    )?;
    let id = format!("component_{}", ulid::Ulid::generate());
    let first = revisions::seal(
        &json!({"schema_version":1,"kind":"component","stable_id":id,
        "owner_id":context.account_id,"created_at":at,"facts":{"description":{"value":"first","origin":"declared","confirmation":"user_confirmed"}}}),
    )?;
    let mut second = first.clone();
    second["parent_revision_ids"] = json!([first["revision_id"]]);
    second["facts"]["description"]["value"] = "second".into();
    second = revisions::seal(&second)?;
    let mut store = Store::open(root.path(), true)?;
    store.transaction(|t| {
        revisions::commit(
            t,
            &first,
            &context.device_id,
            None,
            Write::Advance {
                expected_heads: &[],
            },
        )?;
        revisions::commit(
            t,
            &second,
            &context.device_id,
            None,
            Write::Advance {
                expected_heads: &[first["revision_id"].as_str().unwrap_or("").into()],
            },
        )?;
        Ok(())
    })?;
    drop(store);
    let service_context = context.clone();
    let first_revision = first["revision_id"].clone();
    let second_revision = second["revision_id"].clone();
    let service_id = id.clone();
    let server = thread::spawn(move || -> std::io::Result<()> {
        let mut head = Value::Null;
        let mut lost = None;
        let mut last_request = None;
        for phase in [
            "me",
            "me",
            "me",
            "root",
            "lost-child",
            "me",
            "me",
            "me",
            "retry-child",
            "new-closure",
            "me",
            "retry-closure",
            "me",
            "me",
            "tombstone",
        ] {
            let mut socket = accept(&listener)?;
            let (headers, body) = receive(&mut socket)?;
            let credential = headers
                .lines()
                .filter_map(|line| line.split_once(':'))
                .find(|(key, _)| key.eq_ignore_ascii_case("authorization"))
                .map(|(_, v)| v.trim());
            assert_eq!(credential, Some(format!("Bearer {token}").as_str()));
            if phase == "me" {
                assert!(headers.starts_with("GET /v1/auth/me "));
                respond(
                    &mut socket,
                    200,
                    json!({"schema_version":1,"account_id":service_context.account_id,
                    "device_id":service_context.device_id,"account_status":"active"}),
                )?;
                continue;
            }
            assert!(headers.starts_with("POST /v1/sync/push "));
            let wire: Value = serde_json::from_slice(&body)?;
            assert_eq!(wire["events"].as_array().map(Vec::len), Some(1));
            let request = &wire["events"][0];
            let event =
                Event::push(request, &service_context.account_id).map_err(std::io::Error::other)?;
            assert_eq!(event.entity_id, service_id);
            if phase.starts_with("retry-") {
                assert_eq!(Some(&body), lost.as_ref());
            } else {
                assert_eq!(request["expected_head_revision_id"], head);
                assert_eq!(
                    request["parent_revision_ids"],
                    if head.is_null() {
                        json!([])
                    } else {
                        json!([head])
                    }
                );
                if phase == "root" {
                    assert_eq!(event.payload["revision_id"], first_revision);
                } else if phase == "tombstone" {
                    assert_eq!(event.operation, "tombstone");
                    assert_eq!(event.payload, json!({}));
                } else {
                    assert_eq!(event.payload["revision_id"], second_revision);
                    assert_eq!(
                        event.payload["sync_released_versions"]
                            .as_array()
                            .map(Vec::len),
                        Some(if phase == "new-closure" { 1 } else { 0 })
                    );
                }
                if phase == "new-closure" {
                    let previous: &Value = last_request
                        .as_ref()
                        .ok_or_else(|| std::io::Error::other("previous request"))?;
                    assert_ne!(request["event_id"], previous["event_id"]);
                    assert_ne!(request["idempotency_key"], previous["idempotency_key"]);
                }
                head = request["revision_id"].clone();
                last_request = Some(request.clone());
            }
            if matches!(phase, "lost-child" | "new-closure") {
                lost = Some(body);
                continue;
            }
            respond(
                &mut socket,
                200,
                json!({"schema_version":1,"receipts":[{
                "schema_version":1,"event_id":event.event_id,"state":"accepted","revision_id":event.revision_id,
                "server_head_revision_id":event.revision_id,"cursor":null,"conflict":null,"conflicting_entity_id":null,"error_code":null}]}),
            )?;
        }
        Ok(())
    });
    let original = runtime::plan(
        root.path(),
        None,
        Some(&configuration),
        Request::Push { id: id.clone() },
        &at,
    )?;
    let hash = original.digest()?;
    assert!(runtime::apply(&original, "incorrect-digest", Some(&configuration), &at).is_err());
    let mut edited = serde_json::to_value(&original)?;
    edited["capture"]["steps"][0]["payload"]["facts"]["description"]["value"] =
        "invented-content".into();
    let edited: runtime::Plan = serde_json::from_value(edited)?;
    assert!(runtime::apply(&edited, &edited.digest()?, Some(&configuration), &at).is_err());
    let mut store = Store::open(root.path(), false)?;
    store.transaction(|t| {
        let count: i64 = t
            .query_row("SELECT count(*) FROM operation", [], |r| r.get(0))
            .map_err(crate::store::database)?;
        assert_eq!(count, 0); // Planning neither admits an operation nor binds an origin.
        Ok(())
    })?;
    drop(store);
    assert!(runtime::apply(&original, &hash, Some(&configuration), &at).is_err());
    let fixture: Value = serde_json::from_str(include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/resources/tests/golden/passports/component-version.json"
    )))?;
    let mut released = fixture["value"].clone();
    released["stable_id"] = id.clone().into();
    released["owner_id"] = context.account_id.clone().into();
    released["visibility"] = "private".into();
    released = revisions::seal(&released)?;
    let mut store = Store::open(root.path(), false)?;
    store.transaction(|t| versions::record(t, &released, &context.device_id, None, &at))?;
    drop(store);
    assert!(runtime::apply(&original, &hash, Some(&configuration), &at).is_err()); // Changed local closure is a new intent.
    let current = runtime::plan(
        root.path(),
        None,
        Some(&configuration),
        Request::Push { id: id.clone() },
        &at,
    )?;
    let hash = current.digest()?;
    assert!(runtime::apply(&current, &hash, Some(&configuration), &at).is_err());
    let result = runtime::apply(&current, &hash, Some(&configuration), &at)?;
    assert_eq!(result["result"]["state"], "accepted");
    assert_eq!(runtime::apply(&current, &hash, None, &at)?, result);
    let mut store = Store::open(root.path(), false)?;
    store.transaction(|t| {
        t.execute(
            "INSERT INTO tombstone(stable_id,reason,created_at) VALUES (?,'local_forget',?)",
            rusqlite::params![id, at],
        )
        .map(|_| ())
        .map_err(crate::store::database)
    })?;
    drop(store);
    let current = runtime::plan(
        root.path(),
        None,
        Some(&configuration),
        Request::Push { id: id.clone() },
        &at,
    )?;
    let hash = current.digest()?;
    let deleted = runtime::apply(&current, &hash, Some(&configuration), &at)?;
    assert_eq!(deleted["result"]["state"], "accepted");
    // No online session or enabled config is required for exact terminal replay.
    let journal = Journal::open(&device, false)?.ok_or("journal")?;
    let mut closed = state;
    closed.plan.action = Action::Logout;
    closed.outcome = Outcome::Closed;
    closed.session = Session::Closed {
        reason: "remote_sessions_revoked".into(),
    };
    journal.write(&closed)?;
    drop(journal);
    assert_eq!(
        runtime::apply(&current, &hash, None, &after(&at, 7200)?)?,
        deleted
    );
    server
        .join()
        .map_err(|_| "push fixture server panicked")??;
    Ok(())
}

#[test]
fn private_sync_retries_exact_bytes_after_loss_and_commits_only_checked_pages()
-> std::result::Result<(), Box<dyn Error>> {
    use crate::sync::runtime::{self, Request};
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let device = identity::apply(&init, &init.digest()?, &at)?;
    let account = device.context().account_id;
    let device_id = device.context().device_id;
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    // Disabled sync stops before session access, network or registry writes.
    assert!(Client::open(root.path(), Some(&origin), None).is_err());
    assert!(!root.path().join("ai-stp-v2-state").exists());
    let configuration = root.path().join("sync.yaml");
    fs::write(
        &configuration,
        "schema_version: 1\nsync:\n  enabled: true\n",
    )?;
    let start = plan(root.path(), Action::Start, Some(&origin), None, &at)?;
    let access = generated();
    let state = State {
        plan: start.clone(),
        revision: start.operation_id.clone(),
        session: Session::Authorized {
            account_id: account.clone(),
            access_token: model::Secret(Zeroizing::new(access.clone())),
            refresh_token: model::Secret(Zeroizing::new(generated())),
            expires_at: after(&at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.clone(),
    };
    let journal = Journal::open(&device, true)?.ok_or("journal")?;
    journal.write(&state)?;
    drop(journal);
    let fixtures: Vec<Value> =
        serde_json::from_str(include_str!("../../tests/fixtures/sync-events.json"))?;
    let mut request = fixtures[3].clone();
    request["device_id"] = device_id.clone().into();
    request["entity_id"] = device_id.clone().into();
    request["actor_id"] = account.clone().into();
    request["revision_id"] =
        passport::revision_id(&serde_json::from_value::<Event>(request.clone())?.sealed())?.into();
    request["content_digest"] =
        digest::canonical("ai-stp:revision:v1", &request["payload"])?.into();
    let accepted = json!({"schema_version":1,"event_id":request["event_id"],"state":"accepted",
        "revision_id":request["revision_id"],"server_head_revision_id":request["revision_id"],
        "cursor":"push_only","conflict":null,"conflicting_entity_id":null,"error_code":null});
    let mut streamed = serde_json::to_value(Event::push(&request, &account)?)?;
    streamed["sequence"] = 1.into();
    let page = json!({"schema_version":1,"items":[streamed],
        "page":{"schema_version":1,"page_size":10,"next_cursor":"pull_position"}});
    let me = json!({"schema_version":1,"account_id":account,"device_id":device_id,"account_status":"active"});
    let expected = canonical::bytes(&json!({"schema_version":1,"events":[request]}))?;
    let receipt = accepted.clone();
    let token = access.clone();
    let server = thread::spawn(move || -> std::io::Result<()> {
        let check = |headers: &str| {
            let authorization = headers
                .lines()
                .filter_map(|line| line.split_once(':'))
                .find(|(key, _)| key.eq_ignore_ascii_case("authorization"))
                .map(|(_, value)| value.trim());
            assert_eq!(authorization, Some(format!("Bearer {token}").as_str()));
        };
        for route in [
            "me", "lost", "me", "invalid", "accepted", "me", "me", "pull", "me", "me", "foreign",
            "me", "revoked",
        ] {
            let mut socket = accept(&listener)?;
            let (headers, body) = receive(&mut socket)?;
            check(&headers);
            match route {
                "me" => {
                    assert!(headers.starts_with("GET /v1/auth/me "));
                    assert!(body.is_empty());
                    respond(&mut socket, 200, me.clone())?;
                }
                "lost" | "invalid" | "accepted" => {
                    assert!(headers.starts_with("POST /v1/sync/push "));
                    assert_eq!(body, expected);
                    if route == "lost" {
                        // The API accepted the body, but the response was lost.
                        continue;
                    }
                    let mut value = receipt.clone();
                    if route == "invalid" {
                        value["event_id"] = "event_wrong_receipt".into();
                    }
                    respond(
                        &mut socket,
                        200,
                        json!({"schema_version":1,"receipts":[value]}),
                    )?;
                }
                "pull" | "foreign" | "revoked" => {
                    let suffix = if route == "pull" {
                        ""
                    } else {
                        "&cursor=pull_position"
                    };
                    assert!(
                        headers.starts_with(&format!("GET /v1/sync/pull?page_size=10{suffix} "))
                    );
                    assert!(body.is_empty());
                    if route == "revoked" {
                        respond(
                            &mut socket,
                            403,
                            json!({"schema_version":1,"ok":false,
                            "error":{"code":"AI_STP_DEVICE_REVOKED"}}),
                        )?;
                    } else {
                        let mut value = page.clone();
                        if route == "foreign" {
                            value["items"][0]["actor_id"] =
                                format!("account_{}", ulid::Ulid::generate()).into();
                            value["page"]["next_cursor"] = "wrong_account_position".into();
                        }
                        respond(&mut socket, 200, value)?;
                    }
                }
                _ => unreachable!(),
            }
        }
        Ok(())
    });
    let scope = Scope::new(&account, &origin)?;
    let mut client = Client::open(root.path(), Some(&origin), Some(&configuration))?;
    let error = client
        .deliver(&request)
        .err()
        .ok_or("lost reply accepted")?;
    assert!(matches!(error.kind, crate::error::ErrorKind::Unavailable));
    assert!(!error.message.contains(&access));
    drop(client);
    let mut store = Store::open(root.path(), false)?;
    store.transaction(|t| {
        assert_eq!(
            ledger::pending(t, &scope, &device_id)?
                .ok_or_else(|| Failure::input("pending"))?
                .request,
            request
        );
        assert!(pages::cursor(t, &scope)?.is_none());
        Ok(())
    })?;
    drop(store);
    let mut client = Client::open(root.path(), None, Some(&configuration))?;
    assert!(client.deliver(&request).is_err());
    assert_eq!(client.deliver(&request)?, accepted);
    assert_eq!(client.deliver(&request)?, accepted); // No fourth POST.
    drop(client);
    let pull = runtime::plan(
        root.path(),
        None,
        Some(&configuration),
        Request::Pull {
            page_size: 10,
            skip_event_ids: BTreeSet::new(),
        },
        &at,
    )?;
    let hash = pull.digest()?;
    let pulled = runtime::apply(&pull, &hash, Some(&configuration), &at)?;
    assert_eq!(pulled["result"]["cursor"], "pull_position");
    assert_eq!(runtime::apply(&pull, &hash, None, &at)?, pulled);
    let pull = runtime::plan(
        root.path(),
        None,
        Some(&configuration),
        Request::Pull {
            page_size: 10,
            skip_event_ids: BTreeSet::new(),
        },
        &at,
    )?;
    let hash = pull.digest()?;
    assert!(runtime::apply(&pull, &hash, Some(&configuration), &at).is_err());
    let error = runtime::apply(&pull, &hash, Some(&configuration), &at)
        .err()
        .ok_or("revoked device accepted")?;
    assert_eq!(error.details["reason"], "device_revoked");
    server
        .join()
        .map_err(|_| "sync fixture server panicked")??;
    let mut store = Store::open(root.path(), false)?;
    store.transaction(|t| {
        assert_eq!(pages::cursor(t, &scope)?.as_deref(), Some("pull_position"));
        assert!(ledger::pending(t, &scope, &device_id)?.is_none());
        let bodies: String = t
            .query_row(
                "SELECT request_json FROM sync_event WHERE account_id=?",
                [&account],
                |r| r.get(0),
            )
            .map_err(|_| Failure::input("retained request"))?;
        assert!(!bodies.contains(&access));
        Ok(())
    })?;
    Ok(())
}
