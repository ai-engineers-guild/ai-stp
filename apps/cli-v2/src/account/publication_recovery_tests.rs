//! Device replacement preserves publication uncertainty and permits only fresh reads.

use super::*;
use crate::{
    authoring::embedded,
    publication::{
        self,
        client::Client,
        contract::{Create, Options},
        journal::Attempt,
    },
    store::Store,
};
use std::sync::{Arc, Mutex};

fn authorize_fixture(
    root: &std::path::Path,
    origin: &str,
    account: &str,
    token: &str,
    at: &str,
) -> std::result::Result<(), Box<dyn Error>> {
    let device = identity_at(root)?;
    let start = plan(root, Action::Start, Some(origin), None, at)?;
    let state = State {
        revision: start.operation_id.clone(),
        plan: start,
        session: Session::Authorized {
            account_id: account.into(),
            access_token: model::Secret(Zeroizing::new(token.into())),
            refresh_token: model::Secret(Zeroizing::new(generated())),
            expires_at: after(at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.into(),
    };
    let journal = Journal::open(&device, true)?.ok_or("journal")?;
    journal.write(&state)?;
    journal.complete(&state)?;
    Ok(())
}

#[test]
fn replaced_device_preserves_publication_intent_and_reconciles_without_old_writes()
-> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let device = identity::apply(&init, &init.digest()?, &at)?;
    let context = device.context();
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let token = generated();
    authorize_fixture(root.path(), &origin, &context.account_id, &token, &at)?;
    let source = root.path().join("source");
    fs::create_dir(&source)?;
    fs::write(
        source.join("SKILL.md"),
        "---\nname: inspect\ndescription: Inspect changes.\n---\nReport defects.\n",
    )?;
    let mut store = Store::open(root.path(), true)?;
    let authored = embedded::plan(
        &mut store,
        embedded::Request {
            directory: source,
            harness_id: "codex".into(),
            component_type: "skill".into(),
            name: "inspect".into(),
            license_spdx: "MIT".into(),
        },
        context.clone(),
        &at,
    )?;
    embedded::apply(&mut store, &authored, &authored.digest()?, &context, &at)?;
    let prepared = publication::prepare(
        &mut store,
        authored.component["stable_id"].as_str().ok_or("id")?,
        "1.0",
        None,
        None,
    )?;
    let snapshot = &prepared[0];
    let payload = store.transaction(|t| snapshot.payload(t, &snapshot.artifact.digest))?;
    drop(store);
    let mut client = Client::connect(root.path(), Some(&origin))?;
    let mut attempts = Vec::new();
    for key in ["publication-lost-create-01", "publication-lost-confirm-01"] {
        attempts.push(Attempt::new(Create::new(
            snapshot,
            client.binding().clone(),
            Options {
                source_binding_id: Some("source_binding_01".into()),
                ..Options::default()
            },
            key,
        )?)?);
    }
    let original = attempts.clone();
    let mut response = attempts[1].request.body().clone();
    let fields = response.as_object_mut().ok_or("response")?;
    for name in ["passport", "attestations", "idempotency_key"] {
        fields.remove(name);
    }
    fields.extend(
        json!({"plan_id":"plan_publication_recovery","plan_hash":"plan_publication_recovery_hash",
        "state":"draft","actor_id":context.account_id,"expires_at":after(&at,3600)?,
        "component_verified":false,"evidence":[],"effects":[]})
        .as_object()
        .ok_or("fields")?
        .clone(),
    );
    let expected_confirmation = crate::canonical::bytes(
        &attempts[1]
            .request
            .confirmation(&response, &attempts[1].confirmation_key)?,
    )?;
    let creates = attempts
        .iter()
        .map(|a| a.request.bytes())
        .collect::<crate::error::Result<Vec<_>>>()?;
    let current = Arc::new(Mutex::new((context.device_id.clone(), token)));
    let server_current = current.clone();
    let account = context.account_id.clone();
    let route = format!(
        "/v1/catalog/components/{}/versions/1.0",
        snapshot.passport["stable_id"].as_str().ok_or("id")?
    );
    let metadata = json!({"schema_version":1,"visibility":"private","lifecycle":"active","published_at":at,
        "passport":snapshot.passport,"passport_digest":snapshot.passport_digest,
        "trust":{"author_verified":true,"component_verified":false,"trust_lane":"local_owner_or_pinned"}});
    let server = thread::spawn(move || -> std::io::Result<()> {
        let phases = [
            "lost-create",
            "create",
            "bind",
            "lost-confirm",
            "revoke",
            "public-absent",
            "private-absent",
            "status-waiting",
            "public-absent",
            "private-absent",
            "status-published",
            "public-absent",
            "private-published",
            "revoke",
            "status-published",
            "public-absent",
            "private-published",
        ];
        let mut next = 0;
        for _ in 0..50 {
            let mut socket = accept(&listener)?;
            let (headers, body) = receive(&mut socket)?;
            let (device, token) = server_current
                .lock()
                .map_err(|_| std::io::Error::other("identity"))?
                .clone();
            if headers.starts_with("GET /v1/auth/me ") {
                assert!(headers.lines().any(|l| {
                    l.eq_ignore_ascii_case(&format!("Authorization: Bearer {token}"))
                }));
                respond(
                    &mut socket,
                    200,
                    json!({"schema_version":1,"account_id":account,
                    "device_id":device,"account_status":"active"}),
                )?;
                continue;
            }
            let phase = phases[next];
            if !matches!(phase, "revoke" | "public-absent") {
                assert!(headers.lines().any(|l| {
                    l.eq_ignore_ascii_case(&format!("Authorization: Bearer {token}"))
                }));
            }
            let mut reply = response.clone();
            match phase {
                "lost-create" | "create" => {
                    assert!(headers.starts_with("POST /v1/publications/plans "));
                    assert_eq!(body, creates[usize::from(phase == "create")]);
                    if phase == "create" {
                        respond(&mut socket, 200, reply)?;
                    }
                }
                "bind" => {
                    assert!(headers.starts_with(
                        "PUT /v1/publications/plans/plan_publication_recovery/artifact "
                    ));
                    assert_eq!(body, payload);
                    reply["state"] = "ready".into();
                    respond(&mut socket, 200, reply)?;
                }
                "lost-confirm" => {
                    assert!(headers.starts_with(
                        "POST /v1/publications/plans/plan_publication_recovery/confirm "
                    ));
                    assert_eq!(body, expected_confirmation);
                }
                "revoke" => {
                    assert!(headers.starts_with("POST /v1/auth/device/refresh "));
                    respond(
                        &mut socket,
                        403,
                        json!({"schema_version":1,"ok":false,
                        "error":{"code":"AI_STP_DEVICE_REVOKED"}}),
                    )?;
                }
                "status-waiting" | "status-published" => {
                    assert!(
                        headers
                            .starts_with("GET /v1/publications/plans/plan_publication_recovery ")
                    );
                    reply["state"] = if phase == "status-waiting" {
                        "validating"
                    } else {
                        "published"
                    }
                    .into();
                    respond(&mut socket, 200, reply)?;
                }
                "public-absent" => {
                    assert!(headers.starts_with(&format!("GET {route} ")));
                    assert!(!headers.to_ascii_lowercase().contains("authorization:"));
                    respond(&mut socket, 404, json!({}))?;
                }
                "private-absent" | "private-published" => {
                    assert!(headers.starts_with(&format!("GET {route}/private ")));
                    if phase == "private-absent" {
                        respond(&mut socket, 404, json!({}))?;
                    } else {
                        respond(&mut socket, 200, metadata.clone())?;
                    }
                }
                _ => unreachable!(),
            }
            next += 1;
            if next == phases.len() {
                return Ok(());
            }
        }
        Err(std::io::Error::other(
            "publication recovery fixture exceeded its request bound",
        ))
    });
    for attempt in &attempts {
        assert!(attempt.advance(&mut client).is_err());
    }
    assert!(attempts[0].reconcile(&mut client).is_err());
    drop(client);
    let refresh = plan(root.path(), Action::Refresh, None, None, &at)?;
    assert_eq!(
        apply(&refresh, &refresh.digest()?, &at)?["outcome"],
        "revoked"
    );
    let at = format!("{:.3}", jiff::Timestamp::now());
    let recovery = plan(root.path(), Action::Recover, None, None, &at)?;
    let intent = recovery.recovery.as_ref().ok_or("recovery")?;
    assert_eq!(intent.interrupted_publications.len(), 2);
    assert!(intent.interrupted_sync.is_empty());
    let mut changed = recovery.clone();
    changed
        .recovery
        .as_mut()
        .ok_or("recovery")?
        .interrupted_publications
        .clear();
    assert!(apply(&changed, &changed.digest()?, &at).is_err());
    assert_eq!(
        identity_at(root.path())?.context().device_id,
        context.device_id
    );

    // Lose the process after durable interruption but before replacing its key.
    let journal = Journal::open(&device, false)?.ok_or("journal")?;
    journal.admit(&Pending {
        plan: recovery.clone(),
        requested_at: at.clone(),
    })?;
    let mut store = Store::open(root.path(), false)?;
    store.fence_retired_devices()?;
    journal.fence()?;
    store.transaction(|t| publication::interruption::apply(t, &recovery))?;
    drop(store);
    drop(journal);
    let replacement = apply(&recovery, &recovery.digest()?, &at)?;
    assert_eq!(replacement["outcome"], "device_replaced");
    assert_eq!(apply(&recovery, &recovery.digest()?, &at)?, replacement);
    if let Some(binary) = std::env::var_os("AI_STP_TEST_OLD_PUBLICATION_BINARY") {
        let result = std::process::Command::new(binary)
            .args(["device", "show", "--state-dir"])
            .arg(root.path())
            .arg("--json")
            .output()?;
        assert_eq!(result.status.code(), Some(4));
        assert_eq!(
            serde_json::from_slice::<Value>(&result.stdout)?["ok"],
            false
        );
    }
    let store = Store::planning(root.path())?;
    let receipts = attempts
        .iter()
        .map(|a| {
            a.completed(&store)?
                .ok_or_else(|| crate::error::Failure::input("receipt"))
        })
        .collect::<crate::error::Result<Vec<_>>>()?;
    for (attempt, receipt) in attempts.iter().zip(&receipts) {
        assert_eq!(receipt["state"], "interrupted");
        assert_eq!(receipt["remote_outcome"], "unknown");
        assert!(Attempt::load(&store.connection, &attempt.operation_id)? == *attempt);
    }
    drop(store);
    let next_token = generated();
    authorize_fixture(
        root.path(),
        &origin,
        &context.account_id,
        &next_token,
        &format!("{:.3}", jiff::Timestamp::now()),
    )?;
    *current.lock().map_err(|_| "identity")? =
        (identity_at(root.path())?.context().device_id, next_token);
    let mut client = Client::connect(root.path(), None)?;
    for (attempt, receipt) in attempts.iter().zip(&receipts) {
        assert_eq!(attempt.advance(&mut client)?, *receipt);
        assert!(client.create(&attempt.request).is_err());
    }
    let unknown = attempts[0].reconcile(&mut client)?;
    assert_eq!(unknown["remote_outcome"], "unknown");
    assert!(unknown["plan"].is_null() && unknown["catalog"].is_null());
    let queued = attempts[1].reconcile(&mut client)?;
    assert_eq!(queued["remote_outcome"], "validating");
    assert!(queued["catalog"].is_null());
    let published = attempts[1].reconcile(&mut client)?;
    assert_eq!(published["remote_outcome"], "published");
    assert_eq!(
        published["catalog"]["document"]["passport"],
        snapshot.passport
    );
    assert_eq!(
        published["catalog"]["document"]["trust"]["component_verified"],
        false
    );
    drop(client);

    // A later replacement must preserve the first interruption's exact ancestry.
    let at = format!("{:.3}", jiff::Timestamp::now());
    let refresh = plan(root.path(), Action::Refresh, None, None, &at)?;
    assert_eq!(
        apply(&refresh, &refresh.digest()?, &at)?["outcome"],
        "revoked"
    );
    let at = format!("{:.3}", jiff::Timestamp::now());
    let second = plan(root.path(), Action::Recover, None, None, &at)?;
    assert!(
        second
            .recovery
            .as_ref()
            .ok_or("recovery")?
            .interrupted_publications
            .is_empty()
    );
    assert_eq!(
        apply(&second, &second.digest()?, &at)?["outcome"],
        "device_replaced"
    );
    let next_token = generated();
    authorize_fixture(
        root.path(),
        &origin,
        &context.account_id,
        &next_token,
        &format!("{:.3}", jiff::Timestamp::now()),
    )?;
    *current.lock().map_err(|_| "identity")? =
        (identity_at(root.path())?.context().device_id, next_token);
    let mut client = Client::connect(root.path(), None)?;
    let observed = attempts[1].reconcile(&mut client)?;
    assert_eq!(observed["remote_outcome"], "published");
    assert_eq!(
        observed["catalog"]["document"],
        published["catalog"]["document"]
    );
    server
        .join()
        .map_err(|_| "publication recovery server panicked")??;
    drop(client);
    let store = Store::planning(root.path())?;
    for ((attempt, original), receipt) in attempts.iter().zip(&original).zip(&receipts) {
        assert!(Attempt::load(&store.connection, &attempt.operation_id)? == *original);
        assert_eq!(attempt.completed(&store)?.ok_or("receipt")?, *receipt);
    }
    Ok(())
}
