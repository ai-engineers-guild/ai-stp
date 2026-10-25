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

struct Fixture {
    account: String,
    tokens: BTreeMap<String, String>,
    metadata: Option<Value>,
    events: Vec<Value>,
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
            return respond(
                socket,
                200,
                self.metadata
                    .clone()
                    .ok_or_else(|| std::io::Error::other("metadata"))?,
            );
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
        tokens: BTreeMap::from([(token, local.context().device_id)]),
        metadata: None,
        events: vec![],
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
        shared.lock().map_err(|_| "fixture")?.metadata = Some(json!({"schema_version":1,
            "visibility":"private","lifecycle":"active","published_at":at,
            "passport":snapshot.passport,"passport_digest":snapshot.passport_digest,
            "trust":{"author_verified":false,"component_verified":false,"trust_lane":"local_owner_or_pinned"}}));
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
                evidence: BTreeMap::new(),
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
