use super::*;
use crate::{
    canonical,
    store::{
        Store, database,
        revisions::{self, Write},
    },
    sync::{
        event::Event,
        ledger::{self, Scope},
        runtime::{self, Request},
    },
};
use std::{
    collections::BTreeSet,
    sync::{Arc, Mutex},
};

#[test]
fn replaced_device_interrupts_exact_commands_and_preserves_unknown_requests()
-> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let initialization = identity::plan(root.path(), identity::Storage::File, &at)?;
    let device = identity::apply(&initialization, &initialization.digest()?, &at)?;
    let context = device.context();
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let start = plan(root.path(), Action::Start, Some(&origin), None, &at)?;
    let state = State {
        revision: start.operation_id.clone(),
        plan: start,
        session: Session::Authorized {
            account_id: context.account_id.clone(),
            access_token: model::Secret(Zeroizing::new(generated())),
            refresh_token: model::Secret(Zeroizing::new(generated())),
            expires_at: after(&at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.clone(),
    };
    let journal = Journal::open(&device, true)?.ok_or("journal")?;
    journal.write(&state)?;
    journal.complete(&state)?;
    drop(journal);
    let configuration = root.path().join("sync.yaml");
    fs::write(
        &configuration,
        "schema_version: 1\nsync:\n  enabled: true\n",
    )?;
    let ids: Vec<_> = (0..2)
        .map(|_| format!("component_{}", ulid::Ulid::generate()))
        .collect();
    let mut store = Store::open(root.path(), true)?;
    for id in &ids {
        let document = revisions::seal(
            &json!({"schema_version":1,"kind":"component","stable_id":id,"owner_id":context.account_id,"created_at":at,"facts":{}}),
        )?;
        store.transaction(|t| {
            revisions::commit(
                t,
                &document,
                &context.device_id,
                None,
                Write::Advance {
                    expected_heads: &[],
                },
            )
        })?;
    }
    drop(store);
    let current_device = Arc::new(Mutex::new(context.device_id.clone()));
    let requests = Arc::new(Mutex::new(Vec::<Value>::new()));
    let server_device = current_device.clone();
    let server_requests = requests.clone();
    let account = context.account_id.clone();
    let server = thread::spawn(move || -> std::io::Result<()> {
        for phase in [
            "me", "me", "lost", "me", "me", "lost", "me", "revoked", "me", "me", "me", "me", "me",
            "me", "pull", "me", "me", "new",
        ] {
            let mut socket = accept(&listener)?;
            let (headers, body) = receive(&mut socket)?;
            match phase {
                "me" => {
                    assert!(headers.starts_with("GET /v1/auth/me "));
                    respond(
                        &mut socket,
                        200,
                        json!({"schema_version":1,"account_id":account,"device_id":*server_device.lock().map_err(|_|std::io::Error::other("device lock"))?,"account_status":"active"}),
                    )?;
                }
                "revoked" => {
                    assert!(headers.starts_with("POST /v1/auth/device/refresh "));
                    respond(
                        &mut socket,
                        403,
                        json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_DEVICE_REVOKED"}}),
                    )?;
                }
                "pull" => {
                    assert!(headers.starts_with("GET /v1/sync/pull?"));
                    let mut accepted = server_requests
                        .lock()
                        .map_err(|_| std::io::Error::other("request lock"))?[0]
                        .clone();
                    accepted
                        .as_object_mut()
                        .ok_or_else(|| std::io::Error::other("event"))?
                        .remove("idempotency_key");
                    accepted
                        .as_object_mut()
                        .ok_or_else(|| std::io::Error::other("event"))?
                        .remove("expected_head_revision_id");
                    accepted["sequence"] = 1.into();
                    respond(
                        &mut socket,
                        200,
                        json!({"schema_version":1,"items":[accepted],"page":{"schema_version":1,"page_size":10,"next_cursor":"retired_event_delivered"}}),
                    )?;
                }
                _ => {
                    assert!(headers.starts_with("POST /v1/sync/push "));
                    let body: Value = serde_json::from_slice(&body)?;
                    let request = body["events"][0].clone();
                    let event = Event::push(&request, &account).map_err(std::io::Error::other)?;
                    assert_eq!(
                        event.device_id,
                        *server_device
                            .lock()
                            .map_err(|_| std::io::Error::other("device lock"))?
                    );
                    if phase == "lost" {
                        server_requests
                            .lock()
                            .map_err(|_| std::io::Error::other("request lock"))?
                            .push(request);
                    } else {
                        let old = &server_requests
                            .lock()
                            .map_err(|_| std::io::Error::other("request lock"))?[1];
                        assert_ne!(request["device_id"], old["device_id"]);
                        assert_ne!(request["event_id"], old["event_id"]);
                        assert_ne!(request["idempotency_key"], old["idempotency_key"]);
                        assert_eq!(request["payload"], old["payload"]);
                        assert_eq!(request["parent_revision_ids"], old["parent_revision_ids"]);
                        assert_eq!(
                            request["expected_head_revision_id"],
                            old["expected_head_revision_id"]
                        );
                        respond(
                            &mut socket,
                            200,
                            json!({"schema_version":1,"receipts":[{"schema_version":1,"event_id":event.event_id,"state":"accepted","revision_id":event.revision_id,"server_head_revision_id":event.revision_id,"cursor":null,"conflict":null,"conflicting_entity_id":null,"error_code":null}]}),
                        )?;
                    }
                }
            }
        }
        Ok(())
    });
    let mut pushes = Vec::new();
    for id in &ids {
        let push = runtime::plan(
            root.path(),
            None,
            Some(&configuration),
            Request::Push { id: id.clone() },
            &at,
        )?;
        assert!(runtime::apply(&push, &push.digest()?, Some(&configuration), &at).is_err());
        pushes.push(push);
    }
    let original = requests.lock().map_err(|_| "requests")?.clone();
    let first_id = original[0]["event_id"].as_str().ok_or("event")?;
    assert!(
        runtime::plan(
            root.path(),
            None,
            Some(&configuration),
            Request::Recover {
                event_id: first_id.into()
            },
            &at
        )
        .is_err()
    );
    let refresh = plan(root.path(), Action::Refresh, None, None, &at)?;
    assert_eq!(
        apply(&refresh, &refresh.digest()?, &at)?["outcome"],
        "revoked"
    );
    let at = format!("{:.3}", jiff::Timestamp::now());
    let replacement = plan(root.path(), Action::Recover, None, None, &at)?;
    assert_eq!(
        replacement
            .recovery
            .as_ref()
            .ok_or("intent")?
            .interrupted_sync
            .len(),
        2
    );
    let mut forged = replacement.clone();
    forged
        .recovery
        .as_mut()
        .ok_or("intent")?
        .interrupted_sync
        .clear();
    assert!(apply(&forged, &forged.digest()?, &at).is_err());
    assert_eq!(
        identity_at(root.path())?.context().device_id,
        context.device_id
    );

    // Simulate process loss after exact interruption, before replacing the key.
    let journal = Journal::open(&device, false)?.ok_or("journal")?;
    journal.admit(&Pending {
        plan: replacement.clone(),
        requested_at: at.clone(),
    })?;
    let mut store = Store::open(root.path(), false)?;
    store.fence_retired_devices()?;
    journal.fence()?;
    store.transaction(|t| {
        crate::sync::interruption::apply(t, &replacement, &format!("{:.3}", jiff::Timestamp::now()))
    })?;
    drop(store);
    drop(journal);
    let replaced = apply(&replacement, &replacement.digest()?, &at)?;
    assert_eq!(replaced["outcome"], "device_replaced");
    assert_eq!(apply(&replacement, &replacement.digest()?, &at)?, replaced);
    for push in &pushes {
        let interrupted = runtime::apply(push, &push.digest()?, None, &at)?;
        assert_eq!(interrupted["result"]["state"], "interrupted");
        assert_eq!(interrupted["result"]["remote_outcome"], "unknown");
    }
    // An optional external evidence run exercises the previously qualified
    // executable too; ordinary CI has no dependency on a downloaded old build.
    if let Some(binary) = std::env::var_os("AI_STP_TEST_OLD_SYNC_BINARY") {
        let result = std::process::Command::new(binary)
            .args(["device", "show", "--state-dir"])
            .arg(root.path())
            .arg("--json")
            .output()?;
        assert_eq!(result.status.code(), Some(4));
        let output: Value = serde_json::from_slice(&result.stdout)?;
        assert_eq!(output["ok"], false);
    }
    let device = identity_at(root.path())?;
    *current_device.lock().map_err(|_| "device")? = device.context().device_id;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let login = plan(root.path(), Action::Start, None, None, &at)?;
    let state = State {
        revision: login.operation_id.clone(),
        plan: login,
        session: Session::Authorized {
            account_id: context.account_id.clone(),
            access_token: model::Secret(Zeroizing::new(generated())),
            refresh_token: model::Secret(Zeroizing::new(generated())),
            expires_at: after(&at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.clone(),
    };
    let journal = Journal::open(&device, true)?.ok_or("journal")?;
    journal.write(&state)?;
    journal.complete(&state)?;
    drop(journal);
    let mut recoveries = Vec::new();
    for request in &original {
        let recovery = runtime::plan(
            root.path(),
            None,
            Some(&configuration),
            Request::Recover {
                event_id: request["event_id"].as_str().ok_or("event")?.into(),
            },
            &at,
        )?;
        let result = runtime::apply(&recovery, &recovery.digest()?, Some(&configuration), &at)?;
        assert_eq!(result["result"]["state"], "retired_device");
        assert_eq!(result["result"]["remote_outcome"], "unknown");
        assert_eq!(
            runtime::apply(&recovery, &recovery.digest()?, None, &at)?,
            result
        );
        recoveries.push((recovery, result));
    }
    let scope = Scope::new(&context.account_id, &origin)?;
    let mut store = Store::open(root.path(), false)?;
    store.transaction(|t| {
        for request in &original {
            let held = ledger::retain(t, &scope, request)?;
            assert_eq!(held.state, "failed");
            assert_eq!(held.request, *request);
            assert!(held.receipt.is_none()); // Local retirement is not a remote receipt.
            assert!(
                ledger::pending(
                    t,
                    &scope,
                    request["entity_id"].as_str().ok_or_else(invalid)?
                )?
                .is_none()
            );
        }
        Ok(())
    })?;
    let tampered: crate::error::Result<()> = store.transaction(|t| {
        t.execute(
            "UPDATE sync_event SET receipt_json='{}' WHERE event_id=?",
            [first_id],
        )
        .map_err(database)?;
        assert!(ledger::retain(t, &scope, &original[0]).is_err());
        Err(crate::error::Failure::input("rollback proof mutation"))
    });
    assert!(tampered.is_err());
    drop(store);
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
    runtime::apply(&pull, &pull.digest()?, Some(&configuration), &at)?;
    let push = runtime::plan(
        root.path(),
        None,
        Some(&configuration),
        Request::Push { id: ids[1].clone() },
        &at,
    )?;
    assert_eq!(
        runtime::apply(&push, &push.digest()?, Some(&configuration), &at)?["result"]["state"],
        "accepted"
    );
    let mut store = Store::open(root.path(), false)?;
    store.transaction(|t| {
        for (n, request) in original.iter().enumerate() {
            let held = ledger::retain(t, &scope, request)?;
            assert_eq!(held.state, if n == 0 { "accepted" } else { "failed" });
            assert_eq!(canonical::bytes(&held.request)?, canonical::bytes(request)?);
        }
        Ok(())
    })?;
    drop(store);
    let journal = Journal::open(&device, false)?.ok_or("journal")?;
    let mut closed = state;
    closed.plan.action = Action::Logout;
    closed.outcome = Outcome::Closed;
    closed.session = Session::Closed {
        reason: "remote_sessions_revoked".into(),
    };
    journal.write(&closed)?;
    drop(journal);
    for (recovery, result) in recoveries {
        assert_eq!(
            runtime::apply(&recovery, &recovery.digest()?, None, &after(&at, 7200)?)?,
            result
        );
    }
    server.join().map_err(|_| "recovery server")??;
    Ok(())
}
