//! Real enrollment, signatures, private durable outbox and bounded HTTP.
use super::*;
use crate::account::heartbeats;
use std::sync::{Arc, Mutex};

const ORG: &str = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAV";

#[derive(Default)]
struct Control {
    stop: bool,
    revoked: bool,
    unavailable: bool,
    policy: u64,
    lose_reply: bool,
    reads: usize,
    payloads: Vec<Vec<u8>>,
}
struct Fixture {
    root: tempfile::TempDir,
    at: String,
    origin: String,
    context: String,
    control: Arc<Mutex<Control>>,
    worker: Option<thread::JoinHandle<std::io::Result<()>>>,
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if let Ok(mut control) = self.control.lock() {
            control.stop = true;
        }
        let _ = TcpStream::connect(self.origin.trim_start_matches("http://"));
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}
impl Fixture {
    fn new() -> std::result::Result<Self, Box<dyn Error>> {
        let root = tempfile::tempdir()?;
        let at = format!("{:.3}", jiff::Timestamp::now());
        let init = identity::plan(root.path(), identity::Storage::File, &at)?;
        identity::apply(&init, &init.digest()?, &at)?;
        let listener = TcpListener::bind("127.0.0.1:0")?;
        let origin = format!("http://{}", listener.local_addr()?);
        let connection = connections::plan(root.path(), "Heartbeat", &origin, "github", &at)?;
        connections::apply(&connection, &connection.digest()?, &at)?;
        let account = format!("account_{}", ulid::Ulid::generate());
        let token = generated();
        super::ownership_tests::authorize(
            root.path(),
            &origin,
            Some(&connection.connection_id),
            &account,
            &token,
            &at,
        )?;
        let enrollment =
            connections::enrollment(&identity_at(root.path())?, &connection.connection_id)?;
        let key = VerifyingKey::from_bytes(
            &STANDARD
                .decode(&enrollment.public_key)?
                .try_into()
                .map_err(|_| "key")?,
        )?;
        let control = Arc::new(Mutex::new(Control::default()));
        let (state, observed, device) = (control.clone(), at.clone(), connection.device_id.clone());
        let worker = thread::spawn(move || -> std::io::Result<()> {
            let deadline = Instant::now() + Duration::from_secs(60);
            for _ in 0..256 {
                let mut socket = accept_until(&listener, deadline)?;
                let mut state = state.lock().map_err(|_| std::io::Error::other("fixture"))?;
                if state.stop {
                    return Ok(());
                }
                let (header, bytes) = receive(&mut socket)?;
                state.reads += 1;
                let headers = header
                    .lines()
                    .filter_map(|line| line.split_once(':'))
                    .map(|(name, value)| (name.to_ascii_lowercase(), value.trim().to_owned()))
                    .collect::<std::collections::BTreeMap<_, _>>();
                assert_eq!(
                    headers.get("authorization"),
                    Some(&format!("Bearer {token}"))
                );
                let route = header
                    .lines()
                    .next()
                    .and_then(|v| v.split_whitespace().nth(1))
                    .ok_or_else(|| std::io::Error::other("route"))?;
                let (status, value) = if state.unavailable {
                    (
                        503,
                        json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_UNAVAILABLE"}}),
                    )
                } else if route == "/v1/auth/me" {
                    (
                        200,
                        json!({"schema_version":1,"account_id":account,"device_id":device,"account_status":"active"}),
                    )
                } else if route == "/v1/organizations" {
                    (
                        200,
                        json!({"schema_version":1,"items":[{"schema_version":1,"organization_id":ORG,"kind":"corporate","display_name":"Company","membership_revision":1}]}),
                    )
                } else if route == "/v1/context" {
                    if state.revoked {
                        (
                            403,
                            json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_PERMISSION_DENIED"}}),
                        )
                    } else {
                        (
                            200,
                            json!({"schema_version":1,"mode":"corporate","organization_id":ORG,"capabilities":{
                            "schema_version":1,"registry_version":2,"mode":"corporate","context_kind":"corporate","organization_id":ORG,
                            "authorization_revision":"corporate:heartbeat-fixture:1","issued_at":observed,"generated_at":observed,
                            "expires_at":after(&observed,300).map_err(std::io::Error::other)?,"capabilities":["organization.read"],"unavailable":{}}}),
                        )
                    }
                } else if route
                    == format!("/v1/corporate/organizations/{ORG}/telemetry/heartbeat/policy")
                {
                    (
                        200,
                        json!({"schema_version":1,"organization_id":ORG,"policy_version":state.policy,"enabled":true,
                        "interval_seconds":21600,"retry_base_seconds":60,"retry_max_seconds":3600,"stale_after_seconds":86400,
                        "usage_registration_required":false,"usage_collection_enabled":false,"inventory_scan_enabled":false}),
                    )
                } else {
                    assert_eq!(
                        route,
                        format!("/v1/corporate/organizations/{ORG}/telemetry/heartbeat")
                    );
                    assert!(header.starts_with("PUT "));
                    assert_eq!(
                        headers.get("x-ai-stp-organization-id").map(String::as_str),
                        Some(ORG)
                    );
                    let mut body: Value = serde_json::from_slice(&bytes)?;
                    let signature = body
                        .as_object_mut()
                        .and_then(|v| v.remove("signature"))
                        .and_then(|v| v.as_str().map(str::to_owned))
                        .ok_or_else(|| std::io::Error::other("signature"))?;
                    let signature = Signature::from_slice(
                        &URL_SAFE_NO_PAD
                            .decode(signature)
                            .map_err(std::io::Error::other)?,
                    )
                    .map_err(std::io::Error::other)?;
                    key.verify_strict(
                        &heartbeats::signature_message(ORG, &body)
                            .map_err(std::io::Error::other)?,
                        &signature,
                    )
                    .map_err(std::io::Error::other)?;
                    assert_eq!(body["capabilities"], json!(["cli.foreground-liveness"]));
                    assert_eq!(body["account_id"], account);
                    assert_eq!(body["device_id"], device);
                    state.payloads.push(bytes);
                    if state.lose_reply {
                        state.lose_reply = false;
                        continue;
                    }
                    (
                        200,
                        json!({"schema_version":1,"organization_id":ORG,"account_id":account,"device_id":device,
                        "cli_version":body["cli_version"],"capabilities":body["capabilities"],"last_sync_at":null,
                        "reported_state":"active","health_state":"active","checked_at":body["checked_at"],"received_at":observed,
                        "revision":1,"stale_after_seconds":86400}),
                    )
                };
                respond(&mut socket, status, value)?;
            }
            Err(std::io::Error::other("fixture request limit"))
        });
        let mut fixture = Self {
            root,
            at,
            origin,
            context: String::new(),
            control,
            worker: Some(worker),
        };
        let plan = contexts::create_plan(
            fixture.root.path(),
            "Heartbeat",
            Some(&connection.connection_id),
            Some(ORG),
            &fixture.at,
        )?;
        fixture.context = contexts::apply(&plan, &plan.digest()?, &fixture.at)?["context_id"]
            .as_str()
            .ok_or("context")?
            .into();
        Ok(fixture)
    }
    fn plan(&self) -> std::result::Result<(heartbeats::ConsentPlan, String), Box<dyn Error>> {
        let review = heartbeats::consent_plan(self.root.path(), &self.context, &self.at)?;
        let plan: heartbeats::ConsentPlan = serde_json::from_value(review["plan"].clone())?;
        Ok((plan, review["plan_digest"].as_str().ok_or("digest")?.into()))
    }
    fn enable(&self) -> std::result::Result<(), Box<dyn Error>> {
        let (plan, digest) = self.plan()?;
        assert_eq!(
            heartbeats::consent_apply(&plan, &digest, &self.at)?["enabled"],
            true
        );
        Ok(())
    }
    fn flush(&self, offset: u64) -> Result<Value> {
        let now = after(&self.at, offset)?;
        heartbeats::flush_with_clock(self.root.path(), &self.context, || now.clone())
    }
}

#[test]
fn heartbeat_restart_retries_exact_signed_bytes_without_following_selection()
-> std::result::Result<(), Box<dyn Error>> {
    let fixture = Fixture::new()?;
    let reads = fixture.control.lock().map_err(|_| "fixture")?.reads;
    assert_eq!(fixture.flush(0)?["enabled"], false);
    assert_eq!(fixture.control.lock().map_err(|_| "fixture")?.reads, reads);
    fixture.enable()?;
    fixture.control.lock().map_err(|_| "fixture")?.lose_reply = true;
    let uncertain = fixture.flush(0)?;
    assert_eq!(uncertain["last_outcome"], "unconfirmed");
    assert_eq!(uncertain["attempts"], 1);
    assert!(!serde_json::to_string(&uncertain)?.contains("signature"));
    let personal = contexts::create_plan(fixture.root.path(), "Personal", None, None, &fixture.at)?;
    let personal = contexts::apply(&personal, &personal.digest()?, &fixture.at)?;
    let selection = contexts::select_plan(
        fixture.root.path(),
        personal["context_id"].as_str().ok_or("context")?,
        &fixture.at,
    )?;
    contexts::apply(&selection, &selection.digest()?, &fixture.at)?;
    let reads = fixture.control.lock().map_err(|_| "fixture")?.reads;
    assert_eq!(fixture.flush(59)?["attempts"], 1);
    assert_eq!(fixture.control.lock().map_err(|_| "fixture")?.reads, reads);
    assert_eq!(fixture.flush(60)?["last_outcome"], "acknowledged");
    let state = fixture.control.lock().map_err(|_| "fixture")?;
    assert_eq!(state.payloads.len(), 2);
    assert_eq!(state.payloads[0], state.payloads[1]);
    Ok(())
}

#[test]
fn heartbeat_consent_replay_cannot_reenable_after_offline_disable()
-> std::result::Result<(), Box<dyn Error>> {
    let fixture = Fixture::new()?;
    let (plan, digest) = fixture.plan()?;
    assert_eq!(
        heartbeats::consent_apply(&plan, &digest, &fixture.at)?["enabled"],
        true
    );
    fixture.control.lock().map_err(|_| "fixture")?.unavailable = true;
    assert_eq!(
        heartbeats::disable(fixture.root.path(), &fixture.context)?["enabled"],
        false
    );
    let reads = fixture.control.lock().map_err(|_| "fixture")?.reads;
    assert_eq!(
        heartbeats::consent_apply(&plan, &digest, &after(&fixture.at, 601)?)?["enabled"],
        false
    );
    assert_eq!(fixture.flush(0)?["enabled"], false);
    assert_eq!(fixture.control.lock().map_err(|_| "fixture")?.reads, reads);
    Ok(())
}

#[test]
fn heartbeat_expiry_and_policy_change_do_not_resign_retained_observations()
-> std::result::Result<(), Box<dyn Error>> {
    let fixture = Fixture::new()?;
    fixture.enable()?;
    fixture.control.lock().map_err(|_| "fixture")?.lose_reply = true;
    fixture.flush(0)?;
    let reads = fixture.control.lock().map_err(|_| "fixture")?.reads;
    assert_eq!(fixture.flush(240)?["last_outcome"], "expired");
    assert_eq!(fixture.control.lock().map_err(|_| "fixture")?.reads, reads);
    assert_eq!(
        fixture
            .control
            .lock()
            .map_err(|_| "fixture")?
            .payloads
            .len(),
        1
    );
    let (plan, digest) = fixture.plan()?;
    fixture.control.lock().map_err(|_| "fixture")?.policy = 1;
    assert!(heartbeats::consent_apply(&plan, &digest, &fixture.at).is_err());
    fixture.enable()?;
    fixture.control.lock().map_err(|_| "fixture")?.policy = 2;
    assert_eq!(fixture.flush(0)?["last_outcome"], "policy_changed");
    assert_eq!(
        fixture
            .control
            .lock()
            .map_err(|_| "fixture")?
            .payloads
            .len(),
        1
    );
    Ok(())
}

#[test]
fn heartbeat_authority_outage_is_paced_and_revocation_stops_delivery()
-> std::result::Result<(), Box<dyn Error>> {
    let fixture = Fixture::new()?;
    fixture.enable()?;
    fixture.control.lock().map_err(|_| "fixture")?.unavailable = true;
    assert_eq!(fixture.flush(0)?["last_outcome"], "authority_unavailable");
    let reads = fixture.control.lock().map_err(|_| "fixture")?.reads;
    fixture.flush(59)?;
    assert_eq!(fixture.control.lock().map_err(|_| "fixture")?.reads, reads);
    fixture.control.lock().map_err(|_| "fixture")?.unavailable = false;
    fixture.control.lock().map_err(|_| "fixture")?.revoked = true;
    assert_eq!(fixture.flush(60)?["enabled"], false);
    assert!(
        fixture
            .control
            .lock()
            .map_err(|_| "fixture")?
            .payloads
            .is_empty()
    );
    Ok(())
}

#[test]
fn heartbeat_session_refresh_retires_the_old_payload_without_resigning()
-> std::result::Result<(), Box<dyn Error>> {
    let fixture = Fixture::new()?;
    fixture.enable()?;
    fixture.control.lock().map_err(|_| "fixture")?.lose_reply = true;
    fixture.flush(0)?;
    let context = contexts::resolve(fixture.root.path(), Some(&fixture.context))?;
    let contexts::Authority::Remote { account, .. } = context.authority else {
        return Err("context".into());
    };
    let local = identity_at(fixture.root.path())?;
    let journal =
        Journal::for_connection(&local, account.connection.as_deref(), false)?.ok_or("journal")?;
    let mut state = journal.state()?.ok_or("session")?;
    state.revision = format!("operation_{}", ulid::Ulid::generate());
    state.plan.operation_id = state.revision.clone();
    journal.write(&state)?;
    drop(journal);
    let result = fixture.flush(60)?;
    assert_eq!(result["last_outcome"], "interrupted");
    assert_eq!(result["pending"], false);
    assert_eq!(
        fixture
            .control
            .lock()
            .map_err(|_| "fixture")?
            .payloads
            .len(),
        1
    );
    Ok(())
}

#[test]
fn heartbeat_foreground_maintenance_retires_expired_bytes_without_personal_reporting()
-> std::result::Result<(), Box<dyn Error>> {
    let fixture = Fixture::new()?;
    fixture.enable()?;
    fixture.control.lock().map_err(|_| "fixture")?.lose_reply = true;
    fixture.flush(0)?;
    let personal = contexts::create_plan(fixture.root.path(), "Personal", None, None, &fixture.at)?;
    let personal = contexts::apply(&personal, &personal.digest()?, &fixture.at)?;
    let id = personal["context_id"].as_str().ok_or("context")?;
    let selection = contexts::select_plan(fixture.root.path(), id, &fixture.at)?;
    contexts::apply(&selection, &selection.digest()?, &fixture.at)?;
    let reads = fixture.control.lock().map_err(|_| "fixture")?.reads;
    assert!(heartbeats::flush(fixture.root.path(), id).is_err());
    let result = heartbeats::maintain_at(fixture.root.path(), &after(&fixture.at, 240)?)?;
    assert_eq!(result["expired_payloads_retired"], 1);
    assert_eq!(result["network_requests"], 0);
    assert_eq!(
        heartbeats::status(fixture.root.path(), &fixture.context)?["pending"],
        false
    );
    let retained = fs::read_to_string(
        fixture
            .root
            .path()
            .join("ai-stp-v2-heartbeats")
            .join(format!("{}.json", fixture.context)),
    )?;
    assert!(!retained.contains("signature"));
    assert_eq!(fixture.control.lock().map_err(|_| "fixture")?.reads, reads);
    Ok(())
}
