//! Real TCP/SQLite group ordering and recovery; the server is a controlled fixture.

use super::*;
use crate::{
    authoring::{embedded, setups},
    publication::{self, Snapshot, contract::Visibility, runtime},
    store::Store,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::{Arc, Mutex},
};

fn moment() -> String {
    format!("{:.3}", jiff::Timestamp::now())
}
fn string(value: &Value, key: &str) -> std::result::Result<String, Box<dyn Error>> {
    Ok(value[key].as_str().ok_or("field")?.into())
}

fn authorize(
    root: &std::path::Path,
    origin: &str,
    account: &str,
    token: &str,
) -> std::result::Result<(), Box<dyn Error>> {
    let at = moment();
    let device = identity_at(root)?;
    let start = plan(root, Action::Start, Some(origin), None, &at)?;
    let state = State {
        revision: start.operation_id.clone(),
        plan: start,
        session: Session::Authorized {
            account_id: account.into(),
            access_token: model::Secret(Zeroizing::new(token.into())),
            refresh_token: model::Secret(Zeroizing::new(generated())),
            expires_at: after(&at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at,
    };
    let journal = Journal::open(&device, true)?.ok_or("journal")?;
    journal.write(&state)?;
    journal.complete(&state)?;
    Ok(())
}

struct Server {
    account: String,
    device: String,
    token: String,
    snapshots: BTreeMap<String, Snapshot>,
    payloads: BTreeMap<String, Vec<u8>>,
    published: BTreeSet<String>,
    plans: BTreeMap<String, Value>,
    creates: BTreeMap<String, Value>,
    confirmations: BTreeMap<String, Value>,
    writes: Vec<(String, String)>,
    hold: Option<String>,
    refuse: Option<String>,
    lose_confirmation: Option<String>,
    revoked: bool,
    stop: bool,
    at: String,
}

impl Server {
    fn serve(
        &mut self,
        socket: &mut TcpStream,
        headers: &str,
        bytes: &[u8],
    ) -> std::io::Result<()> {
        let first = headers
            .lines()
            .next()
            .ok_or_else(|| std::io::Error::other("request"))?;
        let words: Vec<_> = first.split_whitespace().collect();
        let method = words[0];
        let path = words[1];
        let parts: Vec<_> = path.split('/').filter(|p| !p.is_empty()).collect();
        if path == "/v1/auth/device/refresh" {
            if self.revoked {
                return respond(
                    socket,
                    403,
                    json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_DEVICE_REVOKED"}}),
                );
            }
            self.token = generated();
            return respond(
                socket,
                200,
                json!({"schema_version":1,"account_id":self.account,"device_id":self.device,
                "access_token":self.token,"refresh_token":generated(),"token_type":"Bearer","expires_in":3600}),
            );
        }
        let public = parts.get(1) == Some(&"catalog") && parts.last() != Some(&"private");
        if public {
            assert!(!headers.to_ascii_lowercase().contains("authorization:"));
        } else {
            assert!(
                headers
                    .lines()
                    .any(|l| l
                        .eq_ignore_ascii_case(&format!("Authorization: Bearer {}", self.token)))
            );
        }
        if path == "/v1/auth/me" {
            return respond(
                socket,
                200,
                json!({"schema_version":1,"account_id":self.account,"device_id":self.device,"account_status":"active"}),
            );
        }
        if path == "/v1/auth/logout" {
            return respond(socket, 200, json!({"schema_version":1,"revoked":true}));
        }
        if parts.get(1) == Some(&"catalog") {
            let id = parts[3];
            if public || !self.published.contains(id) {
                return respond(socket, 404, json!({}));
            }
            let snapshot = self
                .snapshots
                .get(id)
                .ok_or_else(|| std::io::Error::other("snapshot"))?;
            return respond(
                socket,
                200,
                json!({"schema_version":1,"visibility":"private","lifecycle":"active","published_at":self.at,
                "passport":snapshot.passport,"passport_digest":snapshot.passport_digest,
                "trust":{"author_verified":true,"component_verified":false,"trust_lane":"local_owner_or_pinned"}}),
            );
        }
        assert_eq!(&parts[..3], &["v1", "publications", "plans"]);
        if parts.len() == 3 {
            assert_eq!(method, "POST");
            let body: Value = serde_json::from_slice(bytes)?;
            let id = body["stable_id"]
                .as_str()
                .ok_or_else(|| std::io::Error::other("id"))?
                .to_owned();
            let key = body["idempotency_key"]
                .as_str()
                .ok_or_else(|| std::io::Error::other("key"))?
                .to_owned();
            if let Some(previous) = self.creates.get(&key) {
                assert_eq!(previous, &body);
            }
            self.creates.insert(key.clone(), body.clone());
            let plan_id = format!("plan_{key}");
            if !self.plans.contains_key(&plan_id) {
                let snapshot = &self.snapshots[&id];
                assert_eq!(body["passport"], snapshot.passport);
                let mut reply = body;
                let fields = reply
                    .as_object_mut()
                    .ok_or_else(|| std::io::Error::other("body"))?;
                for name in ["passport", "attestations", "idempotency_key"] {
                    fields.remove(name);
                }
                fields.extend(json!({"plan_id":plan_id,"plan_hash":format!("hash_{key}"),"state":"draft",
                    "actor_id":self.account,"expires_at":after(&self.at,3600).map_err(std::io::Error::other)?,"component_verified":false,"evidence":[],"effects":[]})
                    .as_object().ok_or_else(||std::io::Error::other("reply"))?.clone());
                self.plans.insert(plan_id.clone(), reply);
            }
            self.writes.push(("create".into(), id));
            return respond(socket, 200, self.plans[&plan_id].clone());
        }
        let plan_id = parts[3];
        let reply = self
            .plans
            .get_mut(plan_id)
            .ok_or_else(|| std::io::Error::other("plan"))?;
        let id = reply["stable_id"]
            .as_str()
            .ok_or_else(|| std::io::Error::other("id"))?
            .to_owned();
        if method == "GET" {
            return respond(socket, 200, reply.clone());
        }
        if method == "PUT" {
            let address = if parts[4] == "artifact" {
                reply["content_digest"]
                    .as_str()
                    .ok_or_else(|| std::io::Error::other("digest"))?
            } else {
                parts[5]
            };
            assert_eq!(bytes, self.payloads[address]);
            reply["state"] = "ready".into();
            self.writes.push(("bind".into(), id));
        } else {
            assert_eq!(parts[4], "confirm");
            let body: Value = serde_json::from_slice(bytes)?;
            assert_eq!(body["plan_hash"], reply["plan_hash"]);
            if let Some(previous) = self.confirmations.get(plan_id) {
                assert_eq!(previous, &body);
            }
            self.confirmations.insert(plan_id.into(), body);
            let state = if self.refuse.as_deref() == Some(&id) {
                "failed"
            } else if self.hold.as_deref() == Some(&id) {
                "validating"
            } else {
                "published"
            };
            reply["state"] = state.into();
            self.writes.push(("confirm".into(), id.clone()));
            if state == "published" {
                self.published.insert(id.clone());
            }
            if self.lose_confirmation.as_deref() == Some(&id) {
                self.lose_confirmation = None;
                return Ok(());
            }
        }
        respond(socket, 200, reply.clone())
    }
}

#[test]
fn publication_groups_preserve_order_partial_progress_and_replacement_ancestry()
-> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = moment();
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let device = identity::apply(&init, &init.digest()?, &at)?;
    let context = device.context();
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let address = listener.local_addr()?;
    let origin = format!("http://{address}");
    let token = generated();
    authorize(root.path(), &origin, &context.account_id, &token)?;
    let mut store = Store::open(root.path(), true)?;
    let mut members = Vec::new();
    let mut owned = Vec::new();
    let mut snapshots = BTreeMap::new();
    let mut payloads = BTreeMap::new();
    let mut foreign = String::new();
    for name in ["alpha", "beta", "foreign"] {
        let source = root.path().join(name);
        fs::create_dir(&source)?;
        fs::write(
            source.join("SKILL.md"),
            format!("---\nname: {name}\ndescription: Inspect changes.\n---\nReport defects.\n"),
        )?;
        let owner = if name == "foreign" {
            crate::authoring::Identity {
                account_id: format!("account_{}", ulid::Ulid::generate()),
                device_id: format!("device_{}", ulid::Ulid::generate()),
            }
        } else {
            context.clone()
        };
        let authored = embedded::plan(
            &mut store,
            embedded::Request {
                directory: source,
                harness_id: "codex".into(),
                component_type: "skill".into(),
                name: name.into(),
                license_spdx: "MIT".into(),
            },
            owner.clone(),
            &at,
        )?;
        embedded::apply(&mut store, &authored, &authored.digest()?, &owner, &at)?;
        let id = string(&authored.component, "stable_id")?;
        let snapshot = publication::prepare(&mut store, &id, "1.0", None, None)?.remove(0);
        if name == "foreign" {
            foreign = id.clone();
        } else {
            owned.push(id.clone());
        }
        members.push(setups::Member {
            stable_id: id.clone(),
            version: "1.0".into(),
            passport_digest: snapshot.passport_digest.clone(),
        });
        for item in std::iter::once(&snapshot.artifact).chain(&snapshot.projections) {
            payloads.insert(
                item.digest.clone(),
                store.transaction(|t| snapshot.payload(t, &item.digest))?,
            );
        }
        snapshots.insert(id, snapshot);
    }
    let mut setups_ids = Vec::new();
    for name in ["complete", "refused", "interrupted"] {
        let setup = setups::plan(
            &mut store,
            setups::Request {
                harness_id: "codex".into(),
                name: name.into(),
                description: "Inspect a change.".into(),
                purpose: "Review".into(),
                members: members.clone(),
                requirements: None,
            },
            context.clone(),
            &at,
        )?;
        let setup = setups::apply(&mut store, &setup, &setup.digest()?, &context, &at)?;
        let id = string(&setup, "stable_id")?;
        let snapshot = publication::prepare(&mut store, &id, "1.0", None, None)?
            .pop()
            .ok_or("setup")?;
        payloads.insert(
            snapshot.artifact.digest.clone(),
            store.transaction(|t| snapshot.payload(t, &snapshot.artifact.digest))?,
        );
        snapshots.insert(id.clone(), snapshot);
        setups_ids.push(id);
    }
    drop(store);
    let shared = Arc::new(Mutex::new(Server {
        account: context.account_id.clone(),
        device: context.device_id.clone(),
        token,
        snapshots,
        payloads,
        published: BTreeSet::from([foreign.clone()]),
        plans: BTreeMap::new(),
        creates: BTreeMap::new(),
        confirmations: BTreeMap::new(),
        writes: Vec::new(),
        hold: None,
        refuse: None,
        lose_confirmation: None,
        revoked: false,
        stop: false,
        at: at.clone(),
    }));
    let fixture = shared.clone();
    let server = thread::spawn(move || -> std::io::Result<()> {
        let deadline = Instant::now() + Duration::from_secs(180);
        for _ in 0..1000 {
            // Offline journal validation and the previous executable may keep
            // this fixture idle; bound the journey, not those local pauses.
            let mut socket = loop {
                match accept(&listener) {
                    Ok(socket) => break socket,
                    Err(e)
                        if e.kind() == std::io::ErrorKind::WouldBlock
                            && Instant::now() < deadline => {}
                    Err(e) => return Err(e),
                }
            };
            if fixture
                .lock()
                .map_err(|_| std::io::Error::other("fixture"))?
                .stop
            {
                return Ok(());
            }
            let (headers, body) = receive(&mut socket)?;
            fixture
                .lock()
                .map_err(|_| std::io::Error::other("fixture"))?
                .serve(&mut socket, &headers, &body)?;
        }
        Err(std::io::Error::other("request bound"))
    });
    let journey = (|| -> std::result::Result<(), Box<dyn Error>> {
        let request = |id: &str, evidence: BTreeMap<String, runtime::Evidence>| runtime::Request {
            stable_id: id.into(),
            version: "1.0".into(),
            visibility: Visibility::Private,
            component_root: None,
            evidence,
        };
        let public_request = || {
            let mut value = request(
                &owned[0],
                BTreeMap::from([(
                    owned[0].clone(),
                    runtime::Evidence {
                        source_binding_id: Some("source_binding_fixture".into()),
                        ..runtime::Evidence::default()
                    },
                )]),
            );
            value.visibility = Visibility::Public;
            value
        };
        let public = runtime::plan(root.path(), None, public_request(), &moment())?;
        shared
            .lock()
            .map_err(|_| "fixture")?
            .published
            .insert(owned[0].clone());
        assert!(runtime::apply(&public, &public.digest()?, &moment()).is_err());
        assert!(runtime::plan(root.path(), None, public_request(), &moment()).is_err());
        assert!(shared.lock().map_err(|_| "fixture")?.writes.is_empty());
        shared
            .lock()
            .map_err(|_| "fixture")?
            .published
            .remove(&owned[0]);
        let evidence = owned
            .iter()
            .map(|id| {
                (
                    id.clone(),
                    runtime::Evidence {
                        source_binding_id: Some("source_binding_fixture".into()),
                        ..runtime::Evidence::default()
                    },
                )
            })
            .collect();
        let publication = runtime::plan(
            root.path(),
            None,
            request(&setups_ids[0], evidence),
            &moment(),
        )?;
        let serialized = serde_json::to_value(&publication)?;
        let competing_evidence = owned
            .iter()
            .map(|id| {
                (
                    id.clone(),
                    runtime::Evidence {
                        source_binding_id: Some("source_binding_fixture".into()),
                        ..runtime::Evidence::default()
                    },
                )
            })
            .collect();
        let competing = runtime::plan(
            root.path(),
            None,
            request(&setups_ids[0], competing_evidence),
            &moment(),
        )?;
        let operation = string(&serialized["intent"], "operation_id")?;
        let first = serialized["intent"]["members"]
            .as_array()
            .ok_or("members")?
            .iter()
            .find(|m| m["delivery"] == "publish")
            .ok_or("attempt")?["attempt"]["request"]["body"]["stable_id"]
            .as_str()
            .ok_or("id")?
            .to_owned();
        shared.lock().map_err(|_| "fixture")?.hold = Some(first.clone());
        shared
            .lock()
            .map_err(|_| "fixture")?
            .published
            .remove(&foreign);
        assert!(runtime::apply(&publication, &publication.digest()?, &moment()).is_err());
        assert!(shared.lock().map_err(|_| "fixture")?.writes.is_empty());
        shared
            .lock()
            .map_err(|_| "fixture")?
            .published
            .insert(foreign.clone());
        let mut changed = serialized.clone();
        changed["intent"]["members"]
            .as_array_mut()
            .ok_or("members")?
            .remove(0);
        let changed: runtime::Plan = serde_json::from_value(changed)?;
        assert!(runtime::apply(&changed, &changed.digest()?, &moment()).is_err());
        // Count-only rows model other unfinished requests in this isolated registry.
        let capacity = |count: usize| -> std::result::Result<(), Box<dyn Error>> {
            let mut store = Store::open(root.path(), false)?;
            store.transaction(|t| {
            t.execute("DELETE FROM operation WHERE operation_id LIKE 'capacity_%'", [])
                .map_err(crate::store::database)?;
            for index in 0..count {
                t.execute(
                    "INSERT INTO operation(operation_id,kind,state,started_at) VALUES (?,'sync.run','applying',?)",
                    rusqlite::params![format!("capacity_{index}"), at],
                ).map_err(crate::store::database)?;
            }
            Ok(())
        })?;
            Ok(())
        };
        capacity(127)?;
        assert!(runtime::apply(&publication, &publication.digest()?, &moment()).is_err());
        assert!(shared.lock().map_err(|_| "fixture")?.writes.is_empty());
        capacity(126)?;
        let waiting = runtime::apply(&publication, &publication.digest()?, &moment())?;
        assert_eq!(waiting["state"], "waiting");
        let pending = runtime::status(root.path(), None)?;
        assert_eq!(
            pending["operations"].as_array().ok_or("operations")?.len(),
            1
        );
        assert_eq!(pending["operations"][0]["operation_id"], operation);
        let local = runtime::status(root.path(), Some(&operation))?;
        assert_eq!(local["observation"], "local_journal");
        assert_eq!(
            local["operations"][0]["members"]
                .as_array()
                .ok_or("members")?
                .len(),
            4
        );
        {
            let mut client = publication::client::Client::connect(root.path(), None)?;
            for member in serialized["intent"]["members"]
                .as_array()
                .ok_or("members")?
            {
                if member["delivery"] != "publish" {
                    continue;
                }
                let attempt: publication::journal::Attempt =
                    serde_json::from_value(member["attempt"].clone())?;
                let before = shared.lock().map_err(|_| "fixture")?.writes.len();
                if member["attempt"]["request"]["body"]["stable_id"] == first {
                    assert_eq!(attempt.advance(&mut client)?["state"], "waiting");
                } else {
                    assert!(attempt.advance(&mut client).is_err());
                }
                assert_eq!(shared.lock().map_err(|_| "fixture")?.writes.len(), before);
            }
        }
        capacity(0)?;
        let writes_before_competitor = shared.lock().map_err(|_| "fixture")?.writes.len();
        assert!(runtime::apply(&competing, &competing.digest()?, &moment()).is_err());
        assert_eq!(
            shared.lock().map_err(|_| "fixture")?.writes.len(),
            writes_before_competitor
        );
        assert!(
            shared
                .lock()
                .map_err(|_| "fixture")?
                .writes
                .iter()
                .all(|(_, id)| id == &first)
        );
        assert!(
            runtime::plan(
                root.path(),
                None,
                request(&setups_ids[0], BTreeMap::new()),
                &moment()
            )
            .is_err()
        );
        let resume = runtime::resume(root.path(), None, &operation, &moment())?;
        let refresh = plan(root.path(), Action::Refresh, None, None, &moment())?;
        apply(&refresh, &refresh.digest()?, &moment())?;
        let count = shared.lock().map_err(|_| "fixture")?.writes.len();
        assert!(runtime::apply(&resume, &resume.digest()?, &moment()).is_err());
        assert_eq!(shared.lock().map_err(|_| "fixture")?.writes.len(), count);
        let resumed = runtime::resume(root.path(), None, &operation, &moment())?;
        assert_eq!(
            serde_json::to_value(&resumed)?["intent"],
            serialized["intent"]
        );
        {
            let mut fixture = shared.lock().map_err(|_| "fixture")?;
            fixture.hold = None;
            fixture.published.insert(first.clone());
            for plan in fixture.plans.values_mut() {
                if plan["stable_id"] == first {
                    plan["state"] = "published".into();
                }
            }
        }
        let complete = runtime::apply(&resumed, &resumed.digest()?, &moment())?;
        assert_eq!(complete["state"], "published");
        assert_eq!(
            complete["outcome"]["catalogs"]
                .as_array()
                .ok_or("catalogs")?
                .len(),
            4
        );
        assert!(
            shared
                .lock()
                .map_err(|_| "fixture")?
                .writes
                .iter()
                .all(|(_, id)| id != &foreign)
        );
        assert_eq!(
            shared
                .lock()
                .map_err(|_| "fixture")?
                .writes
                .last()
                .ok_or("write")?
                .1,
            setups_ids[0]
        );
        shared.lock().map_err(|_| "fixture")?.refuse = Some(setups_ids[1].clone());
        let refused = runtime::plan(
            root.path(),
            None,
            request(&setups_ids[1], BTreeMap::new()),
            &moment(),
        )?;
        let result = runtime::apply(&refused, &refused.digest()?, &moment())?;
        assert_eq!(result["state"], "refused");
        assert_eq!(result["outcome"]["index"], 3);
        assert_eq!(
            result["outcome"]["catalogs"]
                .as_array()
                .ok_or("catalogs")?
                .len(),
            3
        );
        {
            let mut fixture = shared.lock().map_err(|_| "fixture")?;
            fixture.refuse = None;
            fixture.hold = Some(setups_ids[2].clone());
            fixture.lose_confirmation = Some(setups_ids[2].clone());
        }
        let interrupted = runtime::plan(
            root.path(),
            None,
            request(&setups_ids[2], BTreeMap::new()),
            &moment(),
        )?;
        let original = serde_json::to_value(&interrupted)?;
        let interrupted_id = string(&original["intent"], "operation_id")?;
        let lost = runtime::apply(&interrupted, &interrupted.digest()?, &moment())
            .err()
            .ok_or("fixture must drop confirmation")?;
        assert_eq!(lost.details["operation_id"], interrupted_id);
        if let Some(binary) = std::env::var_os("AI_STP_TEST_OLD_PUBLICATION_SET_BINARY") {
            let result = std::process::Command::new(binary)
                .args(["device", "show", "--state-dir"])
                .arg(root.path())
                .arg("--json")
                .output()?;
            assert!(result.status.success());
            assert_eq!(serde_json::from_slice::<Value>(&result.stdout)?["ok"], true);
        }
        shared.lock().map_err(|_| "fixture")?.revoked = true;
        let refresh = plan(root.path(), Action::Refresh, None, None, &moment())?;
        assert_eq!(
            apply(&refresh, &refresh.digest()?, &moment())?["outcome"],
            "revoked"
        );
        let replacement = plan(root.path(), Action::Recover, None, None, &moment())?;
        let held = serde_json::to_value(&replacement)?;
        let checkpoints = held["recovery"]["interrupted_publications"]
            .as_array()
            .ok_or("checkpoints")?;
        assert_eq!(checkpoints.len(), 2);
        assert!(checkpoints.iter().any(|c| c["kind"] == "set"));
        assert_eq!(
            apply(&replacement, &replacement.digest()?, &moment())?["outcome"],
            "device_replaced"
        );
        if let Some(binary) = std::env::var_os("AI_STP_TEST_OLD_PUBLICATION_SET_BINARY") {
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
        let receipt = runtime::apply(&interrupted, &interrupted.digest()?, &moment())?;
        assert_eq!(receipt["state"], "interrupted");
        assert_eq!(receipt["remote_outcome"], "unknown");
        let token = generated();
        authorize(root.path(), &origin, &context.account_id, &token)?;
        {
            let mut fixture = shared.lock().map_err(|_| "fixture")?;
            fixture.token = token;
            fixture.device = identity_at(root.path())?.context().device_id;
            fixture.revoked = false;
        }
        let writes = shared.lock().map_err(|_| "fixture")?.writes.len();
        let observed = runtime::reconcile(root.path(), None, &interrupted_id)?;
        assert_eq!(observed["members"][3]["remote_outcome"], "validating");
        assert_eq!(shared.lock().map_err(|_| "fixture")?.writes.len(), writes);
        assert_eq!(
            runtime::apply(&interrupted, &interrupted.digest()?, &moment())?,
            receipt
        );
        let logout = plan(root.path(), Action::Logout, None, None, &moment())?;
        assert_eq!(
            apply(&logout, &logout.digest()?, &moment())?["outcome"],
            "closed"
        );
        assert_eq!(
            runtime::apply(&publication, &publication.digest()?, &moment())?,
            complete
        );
        assert_eq!(
            runtime::apply(&refused, &refused.digest()?, &moment())?,
            result
        );
        assert_eq!(
            runtime::status(root.path(), Some(&operation))?["operations"][0]["state"],
            "published"
        );
        assert_eq!(
            runtime::status(root.path(), Some(&interrupted_id))?["operations"][0]["state"],
            "interrupted"
        );
        let refused_status = runtime::status(
            root.path(),
            Some(result["operation_id"].as_str().ok_or("operation")?),
        )?;
        assert_eq!(
            refused_status["operations"][0]["members"][3]["delivery"]["plan"]["state"],
            "failed"
        );
        assert_eq!(runtime::status(root.path(), None)?["operations"], json!([]));
        Ok(())
    })();
    shared.lock().map_err(|_| "fixture")?.stop = true;
    let _wake = TcpStream::connect(address);
    server
        .join()
        .map_err(|_| "publication group fixture panicked")??;
    journey
}
