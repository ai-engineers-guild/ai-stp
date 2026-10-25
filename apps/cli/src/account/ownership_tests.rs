//! Origin-qualified ownership with real vaults, SQLite, signatures and HTTP.

use super::*;
use crate::{
    account::access::Access,
    attestation,
    authoring::{embedded, runtime as authoring},
    publication::{self, contract::Visibility, runtime as publication_runtime},
    sync::{event::Event, runtime as sync_runtime},
};
use std::{
    collections::BTreeMap,
    sync::{Arc, Mutex},
};

pub(super) fn authorize(
    root: &Path,
    origin: &str,
    connection: Option<&str>,
    account: &str,
    token: &str,
    at: &str,
) -> std::result::Result<(), Box<dyn Error>> {
    let local = identity_at(root)?;
    let start = plan_for_connection(root, Action::Start, Some(origin), None, connection, at)?;
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
    Journal::for_connection(&local, state.plan.connection.as_ref(), true)?
        .ok_or("journal")?
        .write(&state)?;
    Ok(())
}

fn authorize_replacement(
    root: &Path,
    connection: &str,
) -> std::result::Result<String, Box<dyn Error>> {
    let at = format!("{:.3}", jiff::Timestamp::now());
    let start = plan_for_connection(root, Action::Start, None, None, Some(connection), &at)?;
    apply(&start, &start.digest()?, &at)?;
    let status = status_for_connection(
        root,
        Some(connection),
        &format!("{:.3}", jiff::Timestamp::now()),
    )?;
    let next = status["session"]["next_poll_at"]
        .as_str()
        .ok_or("poll time")?
        .parse::<jiff::Timestamp>()?;
    let wait = next.as_nanosecond() - jiff::Timestamp::now().as_nanosecond();
    assert!(wait < 5_000_000_000, "fixture polling exceeded its bound");
    if wait > 0 {
        thread::sleep(Duration::from_nanos(u64::try_from(wait)? + 10_000_000));
    }
    let at = format!("{:.3}", jiff::Timestamp::now());
    let poll = plan_for_connection(root, Action::Poll, None, None, Some(connection), &at)?;
    assert_eq!(apply(&poll, &poll.digest()?, &at)?["outcome"], "authorized");
    Ok(format!("{:.3}", jiff::Timestamp::now()))
}

struct Fixture {
    account: String,
    origin: String,
    tokens: BTreeMap<String, String>,
    metadata: Option<Value>,
    known_metadata: Option<Value>,
    known_plan: Option<Value>,
    events: Vec<Value>,
    publications: Vec<Value>,
    previous_key: Option<String>,
    lose: bool,
    stop: bool,
}

impl Fixture {
    fn serve(&mut self, socket: &mut TcpStream) -> std::io::Result<()> {
        let (headers, body) = receive(socket)?;
        let route = headers
            .lines()
            .next()
            .ok_or_else(|| std::io::Error::other("route"))?
            .split_whitespace()
            .nth(1)
            .ok_or_else(|| std::io::Error::other("path"))?;
        if route == "/v1/auth/device/refresh" {
            return respond(
                socket,
                403,
                json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_DEVICE_REVOKED"}}),
            );
        }
        if route == "/v1/auth/device" {
            return respond(
                socket,
                201,
                json!({"schema_version":1,
                "device_code":"named_recovery_fixture_code_0123456789","user_code":"ABCD-1234",
                "verification_uri":format!("{}/en/device-login",self.origin),
                "verification_uri_complete":format!("{}/en/device-login?user_code=ABCD-1234",self.origin),
                "expires_in":600,"interval":1}),
            );
        }
        if route == "/v1/auth/device/token" {
            let wire: Value = serde_json::from_slice(&body)?;
            assert_eq!(wire["expected_account_id"], self.account);
            assert_eq!(
                wire["revoked_public_key"].as_str(),
                self.previous_key.as_deref()
            );
            assert_ne!(wire["public_key"], wire["revoked_public_key"]);
            let device = wire["device_id"]
                .as_str()
                .ok_or_else(|| std::io::Error::other("device"))?;
            let token = generated();
            self.tokens.insert(token.clone(), device.to_owned());
            self.previous_key = wire["public_key"].as_str().map(str::to_owned);
            return respond(
                socket,
                200,
                json!({"schema_version":1,"access_token":token,
                "refresh_token":generated(),"token_type":"Bearer","expires_in":3600,
                "account_id":self.account,"device_id":device}),
            );
        }
        if route.starts_with("/v1/catalog/") && !route.ends_with("/private") {
            assert!(!headers.to_ascii_lowercase().contains("authorization:"));
            return respond(socket, 404, json!({}));
        }
        let token = headers
            .lines()
            .filter_map(|line| line.split_once(':'))
            .find(|(key, _)| key.eq_ignore_ascii_case("authorization"))
            .and_then(|(_, value)| value.trim().strip_prefix("Bearer "))
            .ok_or_else(|| std::io::Error::other("credential"))?;
        let device = self
            .tokens
            .get(token)
            .ok_or_else(|| std::io::Error::other("session"))?;
        if route == "/v1/auth/me" {
            return respond(
                socket,
                200,
                json!({"schema_version":1,"account_id":self.account,
                "device_id":device,"account_status":"active"}),
            );
        }
        if route.starts_with("/v1/catalog/") {
            if let Some(metadata) = &self.known_metadata
                && metadata["passport"]["stable_id"]
                    .as_str()
                    .is_some_and(|id| route.contains(id))
                && self
                    .known_plan
                    .as_ref()
                    .is_some_and(|plan| plan["state"] == "published")
            {
                return respond(socket, 200, metadata.clone());
            }
            return match &self.metadata {
                Some(metadata) => respond(socket, 200, metadata.clone()),
                None => respond(socket, 404, json!({})),
            };
        }
        if route == "/v1/publications/plans" {
            let wire: Value = serde_json::from_slice(&body)?;
            self.publications.push(wire.clone());
            if self
                .known_metadata
                .as_ref()
                .is_some_and(|metadata| metadata["passport"]["stable_id"] == wire["stable_id"])
            {
                let mut reply = wire;
                let fields = reply
                    .as_object_mut()
                    .ok_or_else(|| std::io::Error::other("publication"))?;
                for name in ["passport", "attestations", "idempotency_key"] {
                    fields.remove(name);
                }
                fields.extend(json!({"plan_id":"plan_named_recovery","plan_hash":"plan_named_recovery_hash",
                    "state":"draft","actor_id":self.account,"expires_at":after(&format!("{:.3}",jiff::Timestamp::now()),3600).map_err(std::io::Error::other)?,
                    "component_verified":false,"evidence":[],"effects":[]}).as_object().ok_or_else(||std::io::Error::other("plan"))?.clone());
                self.known_plan = Some(reply.clone());
                return respond(socket, 200, reply);
            }
            return Ok(()); // Retain an unknown result after the write was received.
        }
        if route.starts_with("/v1/publications/plans/plan_named_recovery") {
            let plan = self
                .known_plan
                .as_mut()
                .ok_or_else(|| std::io::Error::other("known plan"))?;
            if route.ends_with("/artifact") {
                assert!(headers.starts_with("PUT ") && !body.is_empty());
                plan["state"] = "ready".into();
            } else if route.ends_with("/confirm") {
                assert!(headers.starts_with("POST "));
                plan["state"] = "published".into();
                return Ok(()); // Confirm reached the server; its response was lost.
            } else {
                assert!(headers.starts_with("GET "));
            }
            return respond(socket, 200, plan.clone());
        }
        assert_eq!(route, "/v1/sync/push");
        let wire: Value = serde_json::from_slice(&body)?;
        let request = wire["events"]
            .as_array()
            .and_then(|items| items.first())
            .ok_or_else(|| std::io::Error::other("event"))?;
        let event = Event::push(request, &self.account).map_err(std::io::Error::other)?;
        assert_eq!(&event.device_id, device);
        if event.entity_kind == "device_summary" {
            assert_eq!(event.entity_id, *device);
        }
        self.events.push(request.clone());
        if self.lose {
            self.lose = false;
            return Ok(());
        }
        respond(
            socket,
            200,
            json!({"schema_version":1,"receipts":[{
            "schema_version":1,"event_id":event.event_id,"state":"accepted",
            "revision_id":event.revision_id,"server_head_revision_id":event.revision_id,
            "cursor":null,"conflict":null,"conflicting_entity_id":null,"error_code":null}]}),
        )
    }
}

#[test]
fn named_owner_operations_keep_native_actor_remote_sender_and_original_origin()
-> std::result::Result<(), Box<dyn Error>> {
    owner_journey(false)
}

#[test]
fn named_recovery_interrupts_only_its_delivery_and_reconciles_with_same_account_ancestry()
-> std::result::Result<(), Box<dyn Error>> {
    owner_journey(true)
}

fn owner_journey(recover: bool) -> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let local = identity::apply(&init, &init.digest()?, &at)?;
    let original = local.report();
    let account = format!("account_{}", ulid::Ulid::generate());
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let address = listener.local_addr()?;
    let origin = format!("http://{address}");
    let token = generated();
    authorize(root.path(), &origin, None, &account, &token, &at)?;
    let shared = Arc::new(Mutex::new(Fixture {
        account: account.clone(),
        origin: origin.clone(),
        tokens: BTreeMap::from([(token, local.context().device_id)]),
        metadata: None,
        known_metadata: None,
        known_plan: None,
        events: vec![],
        publications: vec![],
        previous_key: None,
        lose: true,
        stop: false,
    }));
    let fixture = shared.clone();
    let server = thread::spawn(move || -> std::io::Result<()> {
        let deadline = Instant::now() + Duration::from_secs(90);
        for _ in 0..100 {
            let mut socket = accept_until(&listener, deadline)?;
            let mut fixture = fixture
                .lock()
                .map_err(|_| std::io::Error::other("fixture"))?;
            if fixture.stop {
                return Ok(());
            }
            fixture.serve(&mut socket)?;
        }
        Err(std::io::Error::other("request bound"))
    });
    let mut phase = "attachment";
    let journey = (|| -> std::result::Result<(), Box<dyn Error>> {
        let attach = plan(root.path(), Action::Attach, None, None, &at)?;
        apply(&attach, &attach.digest()?, &at)?;
        let connection =
            connections::plan(root.path(), "Independent device", &origin, "github", &at)?;
        connections::apply(&connection, &connection.digest()?, &at)?;
        let named_token = generated();
        authorize(
            root.path(),
            &origin,
            Some(&connection.connection_id),
            &account,
            &named_token,
            &at,
        )?;
        shared
            .lock()
            .map_err(|_| "fixture")?
            .tokens
            .insert(named_token, connection.device_id.clone());
        if recover {
            let journal = Journal::for_connection(
                &local,
                Some(&connections::enrollment(&local, &connection.connection_id)?),
                false,
            )?
            .ok_or("journal")?;
            journal.complete(&journal.state()?.ok_or("session")?)?;
        }
        assert_ne!(connection.device_id, local.context().device_id);
        phase = "local authoring";
        let owner = authoring::owner(root.path())?;
        assert_eq!(owner.account_id, account);
        assert_eq!(owner.device_id, local.context().device_id);
        let source = root.path().join("source");
        fs::create_dir(&source)?;
        fs::write(
            source.join("SKILL.md"),
            "---\nname: inspect\ndescription: Inspect changes.\n---\nReport defects.\n",
        )?;
        let mut store = owner.open(true)?;
        let authored = embedded::plan(
            &mut store,
            embedded::Request {
                directory: source,
                harness_id: "codex".into(),
                component_type: "skill".into(),
                name: "inspect".into(),
                license_spdx: "MIT".into(),
            },
            owner.clone(),
            &at,
        )?;
        embedded::apply(&mut store, &authored, &authored.digest()?, &owner, &at)?;
        phase = "native device passport";
        let device_plan = crate::passport::device::plan(&mut store, owner.clone(), &at)?;
        crate::passport::device::apply(
            &mut store,
            &device_plan,
            &device_plan.digest()?,
            &owner,
            &at,
        )?;
        let id = authored.component["stable_id"]
            .as_str()
            .ok_or("component")?
            .to_owned();
        let snapshot = publication::prepare(&mut store, &id, "1.0", None, None)?
            .pop()
            .ok_or("snapshot")?;
        let metadata = json!({"schema_version":1,
            "visibility":"private","lifecycle":"active","published_at":at,
            "passport":snapshot.passport,"passport_digest":snapshot.passport_digest,
            "trust":{"author_verified":false,"component_verified":false,"trust_lane":"local_owner_or_pinned"}});
        if !recover {
            shared.lock().map_err(|_| "fixture")?.metadata = Some(metadata);
        }
        drop(store);
        phase = "named attestation";
        let signing = attestation::plan_for_connection(
            root.path(),
            None,
            Some(&connection.connection_id),
            attestation::Request {
                stable_id: id.clone(),
                version: "1.0".into(),
                evidence: json!({
                "check_id":"fixture","policy_version":"fixture-1","tool_versions":{},
                "harness_id":"codex","harness_version":"fixture","provider_version":"fixture",
                "test_case_ids":["qualified-owner"],"result":"passed","attested_at":at}),
            },
            &root.path().join("attestation.json"),
            &at,
        )?;
        let signed = attestation::apply(&signing, &signing.digest()?, &at)?;
        assert_eq!(signed["attestation"]["device_id"], connection.device_id);
        attestation::contract::verify(
            &signed["attestation"],
            &connections::enrollment(&local, &connection.connection_id)?.public_key,
        )?;
        assert!(
            attestation::contract::verify(
                &signed["attestation"],
                original["public_key"].as_str().ok_or("key")?
            )
            .is_err()
        );
        phase = "named publication planning";
        let publication = publication_runtime::plan_for_connection(
            root.path(),
            None,
            Some(&connection.connection_id),
            publication_runtime::Request {
                stable_id: id.clone(),
                version: "1.0".into(),
                visibility: Visibility::Private,
                component_root: None,
                evidence: if recover {
                    BTreeMap::from([(
                        id.clone(),
                        publication_runtime::Evidence {
                            source_binding_id: Some("source_binding_01".into()),
                            ..Default::default()
                        },
                    )])
                } else {
                    BTreeMap::new()
                },
            },
            &at,
        )?;
        let configuration = root.path().join("sync.yaml");
        fs::write(
            &configuration,
            "schema_version: 1\nsync:\n  enabled: true\n",
        )?;
        phase = "named sync";
        let sync = sync_runtime::plan_for_connection(
            root.path(),
            None,
            Some(&connection.connection_id),
            Some(&configuration),
            sync_runtime::Request::Push {
                id: local.context().device_id,
            },
            &at,
        )?;
        assert!(sync_runtime::apply(&sync, &sync.digest()?, Some(&configuration), &at).is_err());
        if recover {
            phase = "named delivery recovery";
            assert!(publication_runtime::apply(&publication, &publication.digest()?, &at).is_err());
            let source = root.path().join("known-source");
            fs::create_dir(&source)?;
            fs::write(
                source.join("SKILL.md"),
                "---\nname: verify\ndescription: Verify changes.\n---\nCheck evidence.\n",
            )?;
            let mut store = owner.open(true)?;
            let known = embedded::plan(
                &mut store,
                embedded::Request {
                    directory: source,
                    harness_id: "codex".into(),
                    component_type: "skill".into(),
                    name: "verify".into(),
                    license_spdx: "MIT".into(),
                },
                owner.clone(),
                &at,
            )?;
            embedded::apply(&mut store, &known, &known.digest()?, &owner, &at)?;
            let known_id = known.component["stable_id"]
                .as_str()
                .ok_or("known component")?
                .to_owned();
            let snapshot = publication::prepare(&mut store, &known_id, "1.0", None, None)?
                .pop()
                .ok_or("known snapshot")?;
            drop(store);
            shared.lock().map_err(|_| "fixture")?.known_metadata = Some(json!({"schema_version":1,
                "visibility":"private","lifecycle":"active","published_at":at,
                "passport":snapshot.passport,"passport_digest":snapshot.passport_digest,
                "trust":{"author_verified":false,"component_verified":false,"trust_lane":"local_owner_or_pinned"}}));
            let known = publication_runtime::plan_for_connection(
                root.path(),
                None,
                Some(&connection.connection_id),
                publication_runtime::Request {
                    stable_id: known_id.clone(),
                    version: "1.0".into(),
                    visibility: Visibility::Private,
                    component_root: None,
                    evidence: BTreeMap::from([(
                        known_id,
                        publication_runtime::Evidence {
                            source_binding_id: Some("source_binding_01".into()),
                            ..Default::default()
                        },
                    )]),
                },
                &at,
            )?;
            assert!(publication_runtime::apply(&known, &known.digest()?, &at).is_err());
            let other = connections::plan(root.path(), "Unrelated", &origin, "github", &at)?;
            connections::apply(&other, &other.digest()?, &at)?;
            let token = generated();
            authorize(
                root.path(),
                &origin,
                Some(&other.connection_id),
                &account,
                &token,
                &at,
            )?;
            {
                let mut fixture = shared.lock().map_err(|_| "fixture")?;
                fixture.tokens.insert(token, other.device_id.clone());
                fixture.lose = true;
            }
            let other_sync = sync_runtime::plan_for_connection(
                root.path(),
                None,
                Some(&other.connection_id),
                Some(&configuration),
                sync_runtime::Request::Push {
                    id: local.context().device_id,
                },
                &at,
            )?;
            assert!(
                sync_runtime::apply(
                    &other_sync,
                    &other_sync.digest()?,
                    Some(&configuration),
                    &at
                )
                .is_err()
            );
            let retained_events = shared.lock().map_err(|_| "fixture")?.events.clone();
            assert_eq!(retained_events.len(), 2);
            let original_event = shared.lock().map_err(|_| "fixture")?.events[0].clone();
            let retained_publications = shared.lock().map_err(|_| "fixture")?.publications.clone();
            assert_eq!(retained_publications.len(), 2);
            let at = format!("{:.3}", jiff::Timestamp::now());
            let refresh = plan_for_connection(
                root.path(),
                Action::Refresh,
                None,
                None,
                Some(&connection.connection_id),
                &at,
            )?;
            assert_eq!(
                apply(&refresh, &refresh.digest()?, &at)?["outcome"],
                "revoked"
            );
            let at = format!("{:.3}", jiff::Timestamp::now());
            phase = "named recovery plan";
            let recovery =
                enrollment_recovery::plan(root.path(), &connection.connection_id, "Recovered", &at)
                    .map_err(|failure| format!("{failure:?}"))?;
            assert_eq!(recovery.schema_version, 3);
            assert_eq!(recovery.interrupted_publications.len(), 4);
            assert_eq!(recovery.interrupted_sync.len(), 1);
            let mut incomplete = recovery.clone();
            incomplete.interrupted_publications.pop();
            assert!(enrollment_recovery::apply(&incomplete, &incomplete.digest()?, &at).is_err());
            phase = "named recovery admission";
            let prepared = enrollment_recovery::apply(&recovery, &recovery.digest()?, &at)?;
            assert_eq!(prepared["state"], "sign_in_required");
            let interrupted = sync_runtime::apply(&sync, &sync.digest()?, None, &at)?;
            assert_eq!(interrupted["result"]["state"], "interrupted");
            assert_eq!(interrupted["result"]["remote_outcome"], "unknown");
            let stopped = publication_runtime::apply(&publication, &publication.digest()?, &at)?;
            assert_eq!(stopped["state"], "interrupted");
            let stopped_known = publication_runtime::apply(&known, &known.digest()?, &at)?;
            assert_eq!(stopped_known["state"], "interrupted");
            let old_public = connections::enrollment(&local, &connection.connection_id)?.public_key;
            shared.lock().map_err(|_| "fixture")?.previous_key = Some(old_public);
            let child = &recovery.replacement.connection_id;
            phase = "named replacement sign-in";
            let later = authorize_replacement(root.path(), child)?;
            let operation = serde_json::to_value(&publication)?["intent"]["operation_id"]
                .as_str()
                .ok_or("operation")?
                .to_owned();
            phase = "named publication readback";
            let reconciled = publication_runtime::reconcile_for_connection(
                root.path(),
                None,
                Some(child),
                &operation,
            )?;
            assert!(
                reconciled["members"]
                    .as_array()
                    .ok_or("members")?
                    .iter()
                    .all(|member| member["remote_outcome"] == "unknown")
            );
            let known_operation = serde_json::to_value(&known)?["intent"]["operation_id"]
                .as_str()
                .ok_or("known operation")?
                .to_owned();
            let known_readback = publication_runtime::reconcile_for_connection(
                root.path(),
                None,
                Some(child),
                &known_operation,
            )?;
            assert!(
                known_readback["members"]
                    .as_array()
                    .ok_or("known members")?
                    .iter()
                    .all(|member| member["remote_outcome"] == "published")
            );
            let event = original_event["event_id"].as_str().ok_or("event")?;
            phase = "named sync retirement";
            let retirement_at = format!("{:.3}", jiff::Timestamp::now());
            let retire = sync_runtime::plan_for_connection(
                root.path(),
                None,
                Some(child),
                Some(&configuration),
                sync_runtime::Request::Recover {
                    event_id: event.into(),
                },
                &retirement_at,
            )?;
            let retired = sync_runtime::apply(
                &retire,
                &retire.digest()?,
                Some(&configuration),
                &retirement_at,
            )?;
            assert_eq!(retired["result"]["remote_outcome"], "unknown");
            let unrelated_event = retained_events[1]["event_id"]
                .as_str()
                .ok_or("unrelated event")?;
            assert!(
                sync_runtime::plan_for_connection(
                    root.path(),
                    None,
                    Some(child),
                    Some(&configuration),
                    sync_runtime::Request::Recover {
                        event_id: unrelated_event.into()
                    },
                    &retirement_at
                )
                .is_err()
            );
            phase = "successive named recovery";
            let refresh = plan_for_connection(
                root.path(),
                Action::Refresh,
                None,
                None,
                Some(child),
                &later,
            )?;
            assert_eq!(
                apply(&refresh, &refresh.digest()?, &later)?["outcome"],
                "revoked"
            );
            let next_at = format!("{:.3}", jiff::Timestamp::now());
            let next = enrollment_recovery::plan(root.path(), child, "Next replacement", &next_at)?;
            assert!(next.interrupted_publications.is_empty() && next.interrupted_sync.is_empty());
            enrollment_recovery::apply(&next, &next.digest()?, &next_at)?;
            let next_child = &next.replacement.connection_id;
            let poll_at = authorize_replacement(root.path(), next_child)?;
            let latest = publication_runtime::reconcile_for_connection(
                root.path(),
                None,
                Some(next_child),
                &operation,
            )?;
            assert_eq!(latest, reconciled);
            let mut latest_known = publication_runtime::reconcile_for_connection(
                root.path(),
                None,
                Some(next_child),
                &known_operation,
            )?;
            let mut earlier_known = known_readback.clone();
            for (earlier, latest) in earlier_known["members"]
                .as_array_mut()
                .ok_or("earlier members")?
                .iter_mut()
                .zip(
                    latest_known["members"]
                        .as_array_mut()
                        .ok_or("latest members")?,
                )
            {
                assert!(
                    latest["catalog"]["checked_at"]
                        .as_str()
                        .ok_or("latest check")?
                        >= earlier["catalog"]["checked_at"]
                            .as_str()
                            .ok_or("earlier check")?
                );
                earlier["catalog"]
                    .as_object_mut()
                    .ok_or("earlier catalog")?
                    .remove("checked_at");
                latest["catalog"]
                    .as_object_mut()
                    .ok_or("latest catalog")?
                    .remove("checked_at");
            }
            assert_eq!(
                crate::digest::canonical("ai-stp:plan:v1", &latest_known)?,
                crate::digest::canonical("ai-stp:plan:v1", &earlier_known)?
            );
            assert_eq!(
                publication_runtime::apply(&known, &known.digest()?, &poll_at)?,
                stopped_known
            );
            assert_eq!(
                enrollment_recovery::apply(&recovery, &recovery.digest()?, &recovery.expires_at)?["state"],
                "authorized"
            );
            assert_eq!(
                enrollment_recovery::apply(&next, &next.digest()?, &next.expires_at)?["state"],
                "authorized"
            );
            let store = owner.planning()?;
            let scope = crate::sync::ledger::Scope::new(&account, &origin)?;
            let unrelated = crate::sync::ledger::pending(
                &store.connection,
                &scope,
                retained_events[1]["entity_id"]
                    .as_str()
                    .ok_or("unrelated entity")?,
            )?
            .ok_or("retained unrelated request")?;
            assert_eq!(unrelated.state, "pending");
            assert_eq!(unrelated.request, retained_events[1]);
            assert!(unrelated.receipt.is_none());
            drop(store);
            assert_eq!(
                sync_runtime::apply(&retire, &retire.digest()?, None, &later)?,
                retired
            );
            assert_eq!(
                publication_runtime::apply(&publication, &publication.digest()?, &later)?,
                stopped
            );
            assert_eq!(
                sync_runtime::apply(&sync, &sync.digest()?, None, &later)?,
                interrupted
            );
            let fixture = shared.lock().map_err(|_| "fixture")?;
            assert_eq!(fixture.events, retained_events);
            assert_eq!(fixture.publications, retained_publications);
            assert_eq!(local.report(), original);
            return Ok(());
        }
        let offline = contexts::create_plan(root.path(), "Offline", None, None, &at)?;
        let offline = contexts::apply(&offline, &offline.digest()?, &at)?;
        let select = contexts::select_plan(
            root.path(),
            offline["context_id"].as_str().ok_or("context")?,
            &at,
        )?;
        contexts::apply(&select, &select.digest()?, &at)?;
        let result = sync_runtime::apply(&sync, &sync.digest()?, Some(&configuration), &at)?;
        assert_eq!(result["result"]["stable_id"], connection.device_id);
        let events = shared.lock().map_err(|_| "fixture")?.events.clone();
        assert_eq!(events.len(), 2);
        assert_eq!(
            events[0], events[1],
            "lost-reply retry changed the sender or exact wire request"
        );
        assert_eq!(events[0]["device_id"], connection.device_id);
        assert_eq!(events[0]["actor_id"], account);
        phase = "named publication apply";
        let completed = publication_runtime::apply(&publication, &publication.digest()?, &at)?;
        assert_eq!(completed["state"], "published");
        let access =
            Access::for_connection(root.path(), None, Some(&connection.connection_id), false)?;
        let store = owner.planning()?;
        assert!(access.owns_registry(&store.connection)?);
        drop(store);
        drop(access);
        // Equal account IDs at another server, and another account at the same
        // server, cannot inherit this registry's original transfer authority.
        for (other_origin, other_account) in [
            ("https://other.example.test", account.as_str()),
            (origin.as_str(), "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
        ] {
            let other = connections::plan(root.path(), "Other", other_origin, "github", &at)?;
            connections::apply(&other, &other.digest()?, &at)?;
            authorize(
                root.path(),
                other_origin,
                Some(&other.connection_id),
                other_account,
                &generated(),
                &at,
            )?;
            let access =
                Access::for_connection(root.path(), None, Some(&other.connection_id), false)?;
            let store = owner.planning()?;
            assert!(!access.owns_registry(&store.connection)?);
            assert!(access.check_registry_owner(&store.connection).is_err());
        }
        Journal::for_connection(
            &local,
            Some(&connections::enrollment(&local, &connection.connection_id)?),
            false,
        )?
        .ok_or("journal")?
        .retire()?;
        assert_eq!(
            sync_runtime::apply(&sync, &sync.digest()?, Some(&configuration), &at)?,
            result
        );
        assert_eq!(
            publication_runtime::apply(&publication, &publication.digest()?, &at)?,
            completed
        );
        assert_eq!(local.report(), original);
        assert_eq!(status(root.path(), &at)?["session"]["state"], "authorized");
        Ok(())
    })();
    shared.lock().map_err(|_| "fixture")?.stop = true;
    let _wake = TcpStream::connect(address)?;
    let served = server.join().map_err(|_| "server thread")?;
    journey.map_err(|error| format!("{phase}: {error}"))?;
    served?;
    Ok(())
}
