//! Real bounded HTTP for publication, without claiming worker/catalog acceptance.

use super::*;
use crate::store::Store;
use crate::{
    authoring::embedded,
    publication::{
        self,
        client::Client,
        contract::{Create, Options, Visibility},
        journal::Attempt,
    },
};

#[test]
fn publication_transport_keeps_exact_requests_and_refuses_unbound_evidence()
-> std::result::Result<(), Box<dyn Error>> {
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
    let binding = client.binding().clone();
    assert!(
        Create::new(
            snapshot,
            binding.clone(),
            Options::default(),
            "publication-create-01"
        )
        .is_err(),
        "missing publication source admitted"
    );
    let options = Options {
        source_binding_id: Some("source_binding_01".into()),
        ..Options::default()
    };
    let request = Create::new(
        snapshot,
        binding.clone(),
        options.clone(),
        "publication-create-01",
    )?;
    assert_eq!(request.body()["visibility"], "private");
    let public = Create::new(
        snapshot,
        binding.clone(),
        Options {
            visibility: Visibility::Public,
            ..options.clone()
        },
        "publication-create-02",
    )?;
    assert_eq!(public.body()["visibility"], "public");
    assert_eq!(public.body()["passport"], request.body()["passport"]);
    let both = Options {
        gitlab_source_binding_id: Some("gitlab_binding_01".into()),
        ..options.clone()
    };
    assert!(Create::new(snapshot, binding.clone(), both, "publication-create-01").is_err());
    let mut signed = json!({"schema_version":1,"object_digest":snapshot.artifact.digest,
        "subject":{"stable_id":snapshot.passport["stable_id"],"version":"1.0","passport_digest":snapshot.passport_digest,"variant_id":null},
        "check_id":"runtime","policy_version":"safety-3","tool_versions":{},"harness_id":"codex","harness_version":"1.0",
        "provider_version":"1.0","test_case_ids":["publication-fixture"],"result":"passed",
        "account_id":binding.account_id,"device_id":binding.device_id,"attested_at":at});
    let hash = crate::digest::canonical("ai-stp:attestation:v1", &signed)?;
    signed["signature"] = STANDARD.encode(device.sign(hash.as_bytes())?).into();
    // Omitted model defaults must reproduce the same signed payload.
    signed
        .as_object_mut()
        .ok_or("record")?
        .remove("schema_version");
    signed
        .as_object_mut()
        .ok_or("record")?
        .remove("tool_versions");
    signed["subject"]
        .as_object_mut()
        .ok_or("subject")?
        .remove("variant_id");
    signed["scope"] = Value::Null;
    let signed_options = Options {
        attestations: vec![signed.clone()],
        ..options.clone()
    };
    Create::new(
        snapshot,
        binding.clone(),
        signed_options.clone(),
        "publication-create-01",
    )?;
    let mut other_policy = signed.clone();
    other_policy["policy_version"] = "other-policy".into();
    let fields = other_policy.as_object_mut().ok_or("record")?;
    fields.remove("signature");
    fields.remove("scope");
    fields.insert("schema_version".into(), 1.into());
    fields.insert("tool_versions".into(), json!({}));
    other_policy["subject"]["variant_id"] = Value::Null;
    let hash = crate::digest::canonical("ai-stp:attestation:v1", &other_policy)?;
    other_policy["signature"] = STANDARD.encode(device.sign(hash.as_bytes())?).into();
    assert!(
        Create::new(
            snapshot,
            binding.clone(),
            Options {
                attestations: vec![other_policy],
                ..options.clone()
            },
            "publication-create-01"
        )
        .is_err(),
        "a valid signature for another policy was admitted"
    );
    let duplicate = Options {
        attestations: vec![signed.clone(), signed.clone()],
        ..options.clone()
    };
    assert!(
        Create::new(
            snapshot,
            binding.clone(),
            duplicate,
            "publication-create-01"
        )
        .is_err()
    );
    signed["result"] = "failed".into();
    assert!(
        Create::new(
            snapshot,
            binding.clone(),
            Options {
                attestations: vec![signed],
                ..options.clone()
            },
            "publication-create-01"
        )
        .is_err()
    );

    let mut response = request.body().clone();
    let fields = response.as_object_mut().ok_or("response")?;
    for name in ["passport", "attestations", "idempotency_key"] {
        fields.remove(name);
    }
    fields.extend(
        json!({"plan_id":"plan_publication_fixture","plan_hash":"plan_fixed_publication_hash",
        "state":"draft","actor_id":context.account_id,"expires_at":after(&at,3600)?,
        "component_verified":false,"evidence":[],"effects":[]})
        .as_object()
        .ok_or("fields")?
        .clone(),
    );
    request.response(&response, None)?;
    assert!(
        client
            .bind(&request, &response, None, b"different")
            .is_err()
    );
    assert!(
        client
            .bind(&request, &response, Some("sha256:unknown"), &payload)
            .is_err()
    );
    let mut wrong = request.clone();
    wrong.account.origin = "http://127.0.0.1:1".into();
    assert!(client.create(&wrong).is_err());
    let original = request.bytes()?;
    let server_response = response.clone();
    let server_payload = payload.clone();
    let service_context = context.clone();
    let route = format!(
        "/v1/catalog/components/{}/versions/1.0",
        snapshot.passport["stable_id"].as_str().ok_or("id")?
    );
    let metadata = json!({"schema_version":1,"visibility":"private","lifecycle":"active",
        "published_at":at,"passport":snapshot.passport,"passport_digest":snapshot.passport_digest,
        "trust":{"author_verified":true,"component_verified":false,"trust_lane":"local_owner_or_pinned"}});
    let attempt = Attempt::new(Create::new(
        snapshot,
        binding,
        options,
        "publication-journal-create-01",
    )?)?;
    let journal_body = attempt.request.bytes()?;
    let mut journal_response = response.clone();
    journal_response["plan_id"] = "plan_publication_journal".into();
    let journal_confirmation = crate::canonical::bytes(
        &attempt
            .request
            .confirmation(&journal_response, &attempt.confirmation_key)?,
    )?;
    let server = thread::spawn(move || -> std::io::Result<()> {
        let mut confirmation = None;
        for phase in [
            "lost-create",
            "wrong-actor",
            "create",
            "wrong-hash",
            "status",
            "lost-bind",
            "bind",
            "projection",
            "lost-confirm",
            "confirm",
            "published",
            "catalog-absent",
            "catalog-private",
            "catalog-tampered",
            "catalog-public",
        ] {
            let mut socket = accept(&listener)?;
            let (headers, _) = receive(&mut socket)?;
            assert!(headers.starts_with("GET /v1/auth/me "));
            assert!(headers.lines().any(|line| {
                line.eq_ignore_ascii_case(&format!("Authorization: Bearer {token}"))
            }));
            respond(
                &mut socket,
                200,
                json!({"schema_version":1,"account_id":service_context.account_id,
                "device_id":service_context.device_id,"account_status":"active"}),
            )?;
            let mut socket = accept(&listener)?;
            let (headers, body) = receive(&mut socket)?;
            if phase.starts_with("catalog-") {
                assert!(headers.starts_with(&format!("GET {route} ")));
                assert!(!headers.to_ascii_lowercase().contains("authorization:"));
                if phase == "catalog-public" {
                    let mut value = metadata.clone();
                    value
                        .as_object_mut()
                        .ok_or_else(|| std::io::Error::other("catalog shape"))?
                        .remove("visibility");
                    value["distribution_visibility"] = "public".into();
                    value["trust"]["trust_lane"] = "experimental".into();
                    value["support"] = json!({"state":"missing","tier":"primary","evidence":[]});
                    value["target_matrix"] = json!({"exact":[]});
                    respond(&mut socket, 200, value)?;
                    continue;
                }
                respond(&mut socket, 404, json!({}))?;
                if phase == "catalog-absent" {
                    continue;
                }
                let mut socket = accept(&listener)?;
                let (headers, _) = receive(&mut socket)?;
                assert!(headers.starts_with(&format!("GET {route}/private ")));
                assert!(headers.lines().any(|line| {
                    line.eq_ignore_ascii_case(&format!("Authorization: Bearer {token}"))
                }));
                let mut value = metadata.clone();
                if phase == "catalog-tampered" {
                    value["passport"]["description"] = "changed".into();
                }
                respond(&mut socket, 200, value)?;
                continue;
            }
            assert!(headers.lines().any(|line| {
                line.eq_ignore_ascii_case(&format!("Authorization: Bearer {token}"))
            }));
            let mut reply = server_response.clone();
            match phase {
                "lost-create" | "wrong-actor" | "create" => {
                    assert!(headers.starts_with("POST /v1/publications/plans "));
                    assert_eq!(body, original);
                    if phase == "lost-create" {
                        continue;
                    }
                    if phase == "wrong-actor" {
                        reply["actor_id"] = format!("account_{}", ulid::Ulid::generate()).into();
                    }
                }
                "lost-bind" | "bind" | "projection" => {
                    assert!(headers.starts_with(
                        "PUT /v1/publications/plans/plan_publication_fixture/artifact"
                    ));
                    assert!(headers.lines().any(|l| {
                        l.eq_ignore_ascii_case("Content-Type: application/octet-stream")
                    }));
                    assert_eq!(body, server_payload);
                    if phase == "lost-bind" {
                        continue;
                    }
                    reply["state"] = "ready".into();
                }
                "lost-confirm" | "confirm" => {
                    assert!(headers.starts_with(
                        "POST /v1/publications/plans/plan_publication_fixture/confirm "
                    ));
                    if phase == "lost-confirm" {
                        confirmation = Some(body);
                        continue;
                    }
                    assert_eq!(Some(body), confirmation);
                    reply["state"] = "validating".into();
                }
                "wrong-hash" | "status" | "published" => {
                    assert!(
                        headers.starts_with("GET /v1/publications/plans/plan_publication_fixture ")
                    );
                    if phase == "wrong-hash" {
                        reply["plan_hash"] = "plan_changed_publication_hash".into();
                    }
                    if phase == "published" {
                        reply["state"] = "published".into();
                    }
                }
                _ => unreachable!(),
            }
            respond(&mut socket, 200, reply)?;
        }
        for phase in [
            "admit",
            "admit",
            "create-lost",
            "admit",
            "create",
            "bind",
            "confirm-lost",
            "admit",
            "queued",
            "admit",
            "published",
            "readback-absent",
            "admit",
            "published",
            "readback",
        ] {
            let mut socket = accept(&listener)?;
            let (headers, _) = receive(&mut socket)?;
            assert!(headers.starts_with("GET /v1/auth/me "));
            assert!(headers.lines().any(|line| {
                line.eq_ignore_ascii_case(&format!("Authorization: Bearer {token}"))
            }));
            respond(
                &mut socket,
                200,
                json!({"schema_version":1,"account_id":service_context.account_id,
                "device_id":service_context.device_id,"account_status":"active"}),
            )?;
            if phase == "admit" {
                continue;
            }
            let mut socket = accept(&listener)?;
            let (headers, body) = receive(&mut socket)?;
            if phase.starts_with("readback") {
                assert!(headers.starts_with(&format!("GET {route} ")));
                assert!(!headers.to_ascii_lowercase().contains("authorization:"));
                respond(&mut socket, 404, json!({}))?;
                let mut socket = accept(&listener)?;
                let (headers, _) = receive(&mut socket)?;
                assert!(headers.starts_with(&format!("GET {route}/private ")));
                assert!(headers.lines().any(|line| {
                    line.eq_ignore_ascii_case(&format!("Authorization: Bearer {token}"))
                }));
                if phase == "readback-absent" {
                    respond(&mut socket, 404, json!({}))?;
                } else {
                    respond(&mut socket, 200, metadata.clone())?;
                }
                continue;
            }
            assert!(headers.lines().any(|line| {
                line.eq_ignore_ascii_case(&format!("Authorization: Bearer {token}"))
            }));
            let mut reply = journal_response.clone();
            match phase {
                "create-lost" | "create" => {
                    assert!(headers.starts_with("POST /v1/publications/plans "));
                    assert_eq!(body, journal_body);
                    if phase == "create-lost" {
                        continue;
                    }
                }
                "bind" => {
                    assert!(headers.starts_with(
                        "PUT /v1/publications/plans/plan_publication_journal/artifact "
                    ));
                    assert_eq!(body, server_payload);
                    reply["state"] = "ready".into();
                }
                "confirm-lost" => {
                    assert!(headers.starts_with(
                        "POST /v1/publications/plans/plan_publication_journal/confirm "
                    ));
                    assert_eq!(body, journal_confirmation);
                    continue;
                }
                "queued" | "published" => {
                    assert!(
                        headers.starts_with("GET /v1/publications/plans/plan_publication_journal ")
                    );
                    reply["state"] = if phase == "queued" {
                        "validating"
                    } else {
                        "published"
                    }
                    .into();
                }
                _ => unreachable!(),
            }
            respond(&mut socket, 200, reply)?;
        }
        Ok(())
    });
    for _ in 0..2 {
        assert!(matches!(
            client.create(&request).err().ok_or("missing refusal")?.kind,
            crate::error::ErrorKind::Unavailable
        ));
    }
    let plan = client.create(&request)?;
    assert!(matches!(
        client
            .status(&request, &plan)
            .err()
            .ok_or("missing refusal")?
            .kind,
        crate::error::ErrorKind::Unavailable
    ));
    let plan = client.status(&request, &plan)?;
    assert!(client.bind(&request, &plan, None, &payload).is_err());
    let plan = client.bind(&request, &plan, None, &payload)?;
    let plan = client.bind(&request, &plan, Some(&snapshot.artifact.digest), &payload)?;
    assert!(
        client
            .confirm(&request, &plan, "publication-confirm-01")
            .is_err()
    );
    let plan = client.confirm(&request, &plan, "publication-confirm-01")?;
    assert_eq!(plan["state"], "validating");
    assert_eq!(plan["component_verified"], false);
    let plan = client.status(&request, &plan)?;
    assert_eq!(plan["state"], "published");
    // This is a wire observation, not a verified catalog result or local receipt.
    assert_eq!(plan["component_verified"], false);
    assert!(client.catalog(snapshot, Visibility::Public)?.is_none());
    let observed = client
        .catalog(snapshot, Visibility::Private)?
        .ok_or("private readback")?;
    observed.validate(snapshot, Visibility::Private, client.binding())?;
    assert!(
        observed
            .validate(snapshot, Visibility::Public, client.binding())
            .is_err()
    );
    assert_eq!(observed.document["trust"]["author_verified"], true);
    assert_eq!(observed.document["trust"]["component_verified"], false);
    assert!(client.catalog(snapshot, Visibility::Private).is_err());
    let observed = client
        .catalog(snapshot, Visibility::Public)?
        .ok_or("public readback")?;
    assert_eq!(observed.document["passport"], snapshot.passport);
    observed.validate(snapshot, Visibility::Private, client.binding())?;

    let mut wrong_inventory = snapshot.clone();
    wrong_inventory.artifact_inventory = vec!["different-file".into()];
    let rejected = Attempt::new(Create::new(
        &wrong_inventory,
        attempt.request.account.clone(),
        Options {
            source_binding_id: Some("source_binding_01".into()),
            ..Options::default()
        },
        "publication-invalid-inventory-01",
    )?)?;
    assert!(rejected.advance(&mut client).is_err());
    let store = Store::planning(root.path())?;
    let admitted: bool = store.connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM operation WHERE operation_id=?)",
        [&rejected.operation_id],
        |r| r.get(0),
    )?;
    assert!(
        !admitted,
        "changed inventory admitted before exact local preparation"
    );
    drop(store);
    assert!(attempt.advance(&mut client).is_err());
    let store = Store::planning(root.path())?;
    let retained = Attempt::load(&store.connection, &attempt.operation_id)?;
    assert!(
        retained == attempt,
        "original admission changed after a lost reply"
    );
    assert!(retained.completed(&store)?.is_none());
    drop(store);
    let mut changed = retained.clone();
    changed.confirmation_key.push_str("-changed");
    assert!(changed.advance(&mut client).is_err());
    assert!(retained.advance(&mut client).is_err());
    let store = Store::planning(root.path())?;
    let retained = Attempt::load(&store.connection, &attempt.operation_id)?;
    assert!(
        retained == attempt,
        "confirmation intent changed after a lost reply"
    );
    drop(store);
    let queued = retained.advance(&mut client)?;
    assert_eq!(queued["state"], "waiting");
    assert_eq!(queued["plan"]["state"], "validating");
    assert!(retained.advance(&mut client).is_err());
    let store = Store::planning(root.path())?;
    assert!(retained.completed(&store)?.is_none());
    let finished: Option<String> = store.connection.query_row(
        "SELECT finished_at FROM operation WHERE operation_id=?",
        [&retained.operation_id],
        |r| r.get(0),
    )?;
    assert!(
        finished.is_none(),
        "publication settled before catalog readback"
    );
    drop(store);
    let settled = retained.advance(&mut client)?;
    assert_eq!(settled["state"], "published");
    assert_eq!(
        settled["outcome"]["catalog"]["document"]["passport"],
        snapshot.passport
    );
    assert_eq!(
        settled["outcome"]["catalog"]["document"]["trust"]["component_verified"],
        false
    );
    server.join().map_err(|_| "publication server panicked")??;
    drop(client);
    // Historical receipt replay needs neither a connected client nor a server.
    let store = Store::planning(root.path())?;
    let retained = Attempt::load(&store.connection, &attempt.operation_id)?;
    assert_eq!(
        retained.completed(&store)?.ok_or("settled receipt")?,
        settled
    );
    Ok(())
}
