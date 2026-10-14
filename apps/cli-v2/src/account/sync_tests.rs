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
fn private_sync_retries_exact_bytes_after_loss_and_commits_only_checked_pages()
-> std::result::Result<(), Box<dyn Error>> {
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
            "me", "lost", "me", "invalid", "accepted", "pull", "foreign", "revoked",
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
    let empty = BTreeSet::new();
    assert_eq!(client.pull(10, &empty)?["cursor"], "pull_position");
    assert!(client.pull(10, &empty).is_err());
    let error = client
        .pull(10, &empty)
        .err()
        .ok_or("revoked device accepted")?;
    assert_eq!(error.details["reason"], "device_revoked");
    drop(client);
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
