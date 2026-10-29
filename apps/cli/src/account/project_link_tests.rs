//! Real account journals, private passports, Git and an independent HTTP peer.

use super::*;
use crate::{
    account::project_links,
    projects::passports,
    store::{CHECKOUT_LINK_SCHEMA, Store},
};
use std::{
    collections::BTreeMap,
    os::unix::fs::PermissionsExt,
    path::{Path, PathBuf},
    process::Command,
    sync::{Arc, Mutex},
};

const FIRST: &str = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const SECOND: &str = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAW";

#[derive(Default)]
struct Peer {
    stop: bool,
    lose_request: bool,
    lose_confirmation: bool,
    hide_outcome: bool,
    reject_confirmation: bool,
    settlement: Option<String>,
    writes: Vec<(String, String, Value)>,
    reads: Vec<(String, String)>,
    plans: BTreeMap<String, Value>,
    links: BTreeMap<String, Value>,
}

fn peer(
    socket: &mut TcpStream,
    peer: &Mutex<Peer>,
    account: &str,
    device: &str,
    token: &str,
    at: &str,
) -> std::io::Result<()> {
    let (header, bytes) = receive(socket)?;
    let line = header
        .lines()
        .next()
        .ok_or_else(|| std::io::Error::other("request"))?;
    let method = line
        .split_whitespace()
        .next()
        .ok_or_else(|| std::io::Error::other("method"))?;
    let path = line
        .split_whitespace()
        .nth(1)
        .ok_or_else(|| std::io::Error::other("path"))?;
    let headers: BTreeMap<_, _> = header
        .lines()
        .filter_map(|s| s.split_once(':'))
        .map(|(key, value)| (key.to_ascii_lowercase(), value.trim().to_owned()))
        .collect();
    if path == "/v1/auth/device/refresh" {
        return respond(
            socket,
            403,
            json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_DEVICE_REVOKED"}}),
        );
    }
    assert_eq!(
        headers.get("authorization").map(String::as_str),
        Some(format!("Bearer {token}").as_str())
    );
    if path == "/v1/auth/me" {
        return respond(
            socket,
            200,
            json!({"schema_version":1,"account_id":account,"device_id":device,"account_status":"active"}),
        );
    }
    if path == "/v1/organizations" {
        return respond(
            socket,
            200,
            json!({"schema_version":1,"items":[
            {"schema_version":1,"organization_id":FIRST,"kind":"corporate","display_name":"First","membership_revision":1},
            {"schema_version":1,"organization_id":SECOND,"kind":"corporate","display_name":"Second","membership_revision":1}]}),
        );
    }
    let organization = headers
        .get("x-ai-stp-organization-id")
        .ok_or_else(|| std::io::Error::other("organization"))?;
    assert!([FIRST, SECOND].contains(&organization.as_str()));
    let policy = format!("corporate:{organization}:1");
    if path == "/v1/context" {
        return respond(
            socket,
            200,
            json!({"schema_version":1,"mode":"corporate","organization_id":organization,
            "capabilities":{"schema_version":1,"registry_version":2,"mode":"corporate","context_kind":"corporate",
            "organization_id":organization,"authorization_revision":policy,"issued_at":at,"generated_at":at,
            "expires_at":after(at,3600).map_err(std::io::Error::other)?,"capabilities":["organization.read","project.link"],"unavailable":{}}}),
        );
    }
    let mut peer = peer.lock().map_err(|_| std::io::Error::other("peer"))?;
    if method == "GET" {
        peer.reads.push((organization.clone(), path.into()));
    }
    if path.contains("/project-link-targets/") {
        return respond(
            socket,
            200,
            json!({"schema_version":1,"organization_id":organization,
            "remote_project_id":path.rsplit('/').next(),"remote_revision":"initial","authorization_revision":policy,
            "providers":[],"observed_at":at,"observation_only":true,"future_private":"discard-this-canary"}),
        );
    }
    if method == "POST" && path.ends_with("/project-link-plans") {
        let body: Value = serde_json::from_slice(&bytes)?;
        peer.writes
            .push((organization.clone(), path.into(), body.clone()));
        let key = body["idempotency_key"]
            .as_str()
            .ok_or_else(|| std::io::Error::other("key"))?;
        let plan_id = format!("link_plan_{}", ulid::Ulid::generate());
        let mut values = body
            .as_object()
            .ok_or_else(|| std::io::Error::other("body"))?
            .clone();
        values.remove("schema_version");
        values.remove("idempotency_key");
        values.insert("organization_id".into(), organization.clone().into());
        values.insert("actor_account_id".into(), account.into());
        values.insert("device_id".into(), device.into());
        values.insert(
            "expires_at".into(),
            after(at, 900).map_err(std::io::Error::other)?.into(),
        );
        let ordered: BTreeMap<_, _> = values.iter().collect();
        let hash = crate::digest::sha256(&serde_json::to_vec(&ordered)?);
        values.remove("actor_account_id");
        values.remove("device_id");
        values.insert("schema_version".into(), 1.into());
        values.insert("plan_id".into(), plan_id.into());
        values.insert("plan_digest".into(), hash.into());
        let plan = Value::Object(values);
        peer.plans.insert(key.into(), plan.clone());
        if peer.lose_request {
            peer.lose_request = false;
            return Ok(());
        }
        return respond(socket, 201, plan);
    }
    if path.contains("/project-link-plans/") && path.ends_with("/settlement") {
        if peer.settlement.as_deref() == Some("unsupported") {
            return respond(
                socket,
                404,
                json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_NOT_FOUND"}}),
            );
        }
        let id = path
            .split('/')
            .nth_back(1)
            .ok_or_else(|| std::io::Error::other("plan"))?;
        let plan = peer
            .plans
            .values()
            .find(|plan| plan["plan_id"] == id)
            .ok_or_else(|| std::io::Error::other("plan"))?;
        let link = peer.links.get(id);
        let expired = peer.settlement.as_deref() == Some("expired");
        return respond(
            socket,
            200,
            json!({"schema_version":1,"plan":plan,
            "state":if link.is_some(){"applied"}else if expired{"expired"}else{"ready"},"link":link,
            "authorization_revision":policy,"observed_at":if expired {after(plan["expires_at"].as_str().ok_or_else(|| std::io::Error::other("expiry"))?,1).map_err(std::io::Error::other)?}else{format!("{:.3}",jiff::Timestamp::now())},"observation_only":true}),
        );
    }
    if path.contains("/project-link-plan-requests/") {
        let key = path
            .rsplit('/')
            .next()
            .ok_or_else(|| std::io::Error::other("key"))?;
        if peer.hide_outcome || !peer.plans.contains_key(key) {
            return respond(
                socket,
                404,
                json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_NOT_FOUND"}}),
            );
        }
        let plan = peer
            .plans
            .get(key)
            .ok_or_else(|| std::io::Error::other("plan"))?;
        assert_eq!(plan["organization_id"], organization.as_str());
        let link = peer.links.get(
            plan["plan_id"]
                .as_str()
                .ok_or_else(|| std::io::Error::other("plan"))?,
        );
        return respond(
            socket,
            200,
            json!({"schema_version":1,"plan":plan,"state":if link.is_some(){"applied"}else{"ready"},"link":link,
            "authorization_revision":policy,"observed_at":format!("{:.3}",jiff::Timestamp::now()),"observation_only":true}),
        );
    }
    if method == "POST" && path == "/v1/projects/links" {
        let body: Value = serde_json::from_slice(&bytes)?;
        peer.writes
            .push((organization.clone(), path.into(), body.clone()));
        let plan = peer
            .plans
            .values()
            .find(|p| p["plan_id"] == body["plan_id"])
            .ok_or_else(|| std::io::Error::other("plan"))?;
        assert_eq!(body["plan_digest"], plan["plan_digest"]);
        let link = json!({"schema_version":1,"link_id":format!("project_link_{}",ulid::Ulid::generate()),
            "plan_id":plan["plan_id"],"plan_digest":plan["plan_digest"],"organization_id":organization,
            "local_project_id":plan["local_project_id"],"remote_project_id":plan["remote_project_id"],"provider_project_id":plan["provider_project_id"],
            "state":"linked","local_revision":plan["local_revision"],"remote_revision":plan["remote_revision"],"provider_revision":plan["provider_revision"],
            "conflict_server_revision":null,"conflict_client_revision":null,"conflict_common_ancestor":null,"revision":1,"updated_at":at});
        let id = plan["plan_id"]
            .as_str()
            .ok_or_else(|| std::io::Error::other("plan"))?
            .to_owned();
        if peer.reject_confirmation {
            return respond(socket, 503, json!({}));
        }
        peer.links.insert(id, link.clone());
        if peer.lose_confirmation {
            peer.lose_confirmation = false;
            return Ok(());
        }
        return respond(socket, 201, link);
    }
    Err(std::io::Error::other("unexpected native checkout route"))
}

fn git_executable() -> std::result::Result<PathBuf, Box<dyn Error>> {
    std::env::split_paths(&std::env::var_os("PATH").ok_or("PATH")?)
        .map(|p| p.join("git"))
        .find(|p| p.is_file())
        .ok_or_else(|| "Git is required".into())
}

fn git(root: &Path, arguments: &[&str]) -> std::result::Result<(), Box<dyn Error>> {
    let result = Command::new(git_executable()?)
        .current_dir(root)
        .env_clear()
        .env("PATH", std::env::var_os("PATH").ok_or("PATH")?)
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_CONFIG_GLOBAL", "/dev/null")
        .args([
            "-c",
            "user.name=Checkout fixture",
            "-c",
            "user.email=fixture@example.invalid",
        ])
        .args(arguments)
        .output()?;
    assert!(result.status.success(), "fixture Git failed");
    Ok(())
}

#[test]
fn checkout_intents_preserve_unknown_effects_context_and_physical_reservations()
-> std::result::Result<(), Box<dyn Error>> {
    checkout_journey(true)
}

#[test]
fn root_checkout_recovery_captures_original_intent_before_constructing_replacement()
-> std::result::Result<(), Box<dyn Error>> {
    checkout_journey(false)
}

#[test]
fn unknown_checkout_request_retirement_keeps_remote_outcome_unknown_and_fences_replay()
-> std::result::Result<(), Box<dyn Error>> {
    for named in [true, false] {
        checkout_case(named, Some(RetirementCase::UnknownRequest))?;
    }
    Ok(())
}

#[test]
fn checkout_confirmation_retirement_requires_fresh_expired_barrier_and_no_binding()
-> std::result::Result<(), Box<dyn Error>> {
    for named in [true, false] {
        checkout_case(named, Some(RetirementCase::ExpiredConfirmation))?;
    }
    Ok(())
}

fn checkout_journey(named: bool) -> std::result::Result<(), Box<dyn Error>> {
    checkout_case(named, None)
}

#[derive(Clone, Copy)]
enum RetirementCase {
    UnknownRequest,
    ExpiredConfirmation,
}

fn relocation_preview(
    local: &identity::Identity,
    checkout: &Path,
    moved: &Path,
    at: &str,
) -> std::result::Result<passports::Plan, Box<dyn Error>> {
    fs::rename(checkout, moved)?;
    let planned = (|| {
        let mut store = Store::open_at(local.root_directory(), false)?;
        Ok(passports::plan(&mut store, moved, local.context(), at)?)
    })();
    fs::rename(moved, checkout)?;
    planned
}

fn reserved_relocation_refuses(
    local: &identity::Identity,
    root: &Path,
    checkout: &Path,
    held: &passports::Plan,
    adoption: &project_links::Plan,
    at: &str,
) -> std::result::Result<(), Box<dyn Error>> {
    let adoption = serde_json::to_value(adoption)?;
    let binding = adoption["operation_id"].as_str().ok_or("adoption")?;
    let (_, before) = project_links::binding::capture(root, binding)?;
    let marker = checkout.join(".ai-stp-v2-project/project-id");
    let marker_before = fs::read(&marker)?;
    let canary_before = fs::read(checkout.join(".env"))?;
    let mode_before = fs::metadata(checkout.join(".env"))?.permissions().mode();
    let operations = || -> std::result::Result<i64, Box<dyn Error>> {
        Ok(Store::planning_at(local.root_directory())?
            .connection
            .query_row("SELECT count(*) FROM operation", [], |row| row.get(0))?)
    };
    let operations_before = operations()?;
    fs::rename(checkout, &held.root)?;
    let results = (|| -> std::result::Result<(bool, bool), Box<dyn Error>> {
        let mut store = Store::open_at(local.root_directory(), false)?;
        let planned = passports::plan(&mut store, &held.root, local.context(), at);
        if let Ok(current) = &planned {
            // The otherwise-valid earlier plan differs only in operation ID.
            assert_eq!(current.root_identity, held.root_identity);
            assert_eq!(current.previous_root, held.previous_root);
            assert_eq!(current.expected_heads, held.expected_heads);
            assert_eq!(current.passport, held.passport);
        }
        let applied = passports::apply(&mut store, held, &held.digest()?, &local.context(), at);
        for refusal in [planned.as_ref().err(), applied.as_ref().err()]
            .into_iter()
            .flatten()
        {
            assert_eq!(refusal.kind.code(), "AI_STP_PRECONDITION_FAILED");
            assert_eq!(
                refusal.details.get("reason"),
                Some(&json!("corporate_checkout_reserved"))
            );
        }
        Ok((planned.is_err(), applied.is_err()))
    })();
    fs::rename(&held.root, checkout)?;
    let (planning_refused, apply_refused) = results?;
    if !planning_refused || !apply_refused {
        return Err(format!(
            "reserved checkout relocation: planning_refused={planning_refused}, apply_refused={apply_refused}"
        )
        .into());
    }
    assert!(project_links::binding::capture(root, binding)?.1 == before);
    assert_eq!(operations()?, operations_before);
    assert_eq!(fs::read(marker)?, marker_before);
    assert_eq!(fs::read(checkout.join(".env"))?, canary_before);
    assert_eq!(
        fs::metadata(checkout.join(".env"))?.permissions().mode(),
        mode_before
    );
    Ok(())
}

fn checkout_case(
    named: bool,
    retirement: Option<RetirementCase>,
) -> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let tree = tempfile::tempdir()?;
    let checkout = tree.path().join("checkout");
    fs::create_dir(&checkout)?;
    fs::write(checkout.join("main.rs"), b"fn main() {}\n")?;
    fs::write(checkout.join(".env"), b"PRIVATE=unowned-file-canary\n")?;
    git(&checkout, &["init", "--initial-branch=main"])?;
    git(&checkout, &["commit", "--allow-empty", "-m", "first"])?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let local = identity::apply(&init, &init.digest()?, &at)?;
    {
        let mut store = Store::open_at(local.root_directory(), true)?;
        let project = passports::plan(&mut store, &checkout, local.context(), &at)?;
        passports::apply(
            &mut store,
            &project,
            &project.digest()?,
            &local.context(),
            &at,
        )?;
    }
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let address = listener.local_addr()?;
    let origin = format!("http://{address}");
    let connection = connections::plan(root.path(), "Work", &origin, "github", &at)?;
    connections::apply(&connection, &connection.digest()?, &at)?;
    let account = format!("account_{}", ulid::Ulid::generate());
    let token = generated();
    super::ownership_tests::authorize(
        root.path(),
        &origin,
        named.then_some(connection.connection_id.as_str()),
        &account,
        &token,
        &at,
    )?;
    if !named {
        let journal = Journal::open(&local, false)?.ok_or("legacy journal")?;
        journal.complete(&journal.state()?.ok_or("legacy authorization")?)?;
    }
    let service_device = if named {
        connection.device_id.clone()
    } else {
        local.context().device_id
    };
    let control = Arc::new(Mutex::new(Peer::default()));
    let remote = control.clone();
    let remote_at = at.clone();
    let remote_token = token.clone();
    let worker = thread::spawn(move || -> std::io::Result<()> {
        let deadline = Instant::now() + Duration::from_secs(120);
        for request in 0..=2048 {
            let mut socket = accept_until(&listener, deadline)?;
            if remote
                .lock()
                .map_err(|_| std::io::Error::other("peer"))?
                .stop
            {
                return Ok(());
            }
            if request == 2048 {
                return Err(std::io::Error::other("fixture HTTP request bound: 2048"));
            }
            peer(
                &mut socket,
                &remote,
                &account,
                &service_device,
                &remote_token,
                &remote_at,
            )
            .map_err(|error| {
                std::io::Error::other(format!("fixture request {}: {error}", request + 1))
            })?;
        }
        Err(std::io::Error::other("request bound"))
    });
    let journey = (|| -> std::result::Result<(), Box<dyn Error>> {
        let mut contexts = Vec::new();
        for org in [FIRST, SECOND] {
            let plan = if named {
                contexts::create_plan(
                    root.path(),
                    org,
                    Some(&connection.connection_id),
                    Some(org),
                    &at,
                )?
            } else {
                contexts::create_legacy_plan(root.path(), org, Some(org), &at)?
            };
            let value = contexts::apply(&plan, &plan.digest()?, &at)?;
            contexts.push(value["context_id"].as_str().ok_or("context")?.to_owned());
        }
        let version = || -> std::result::Result<u32, Box<dyn Error>> {
            Ok(Store::planning_at(local.root_directory())?.version()?)
        };
        assert_eq!(version()?, 55);
        let remote_first = FIRST.replacen("organization_", "remote_project_", 1);
        let remote_second = SECOND.replacen("organization_", "remote_project_", 1);
        let stale = project_links::request_plan(
            root.path(),
            Some(&contexts[0]),
            &checkout,
            &remote_first,
            None,
            None,
            &at,
        )?;
        git(&checkout, &["commit", "--allow-empty", "-m", "second"])?;
        assert!(
            project_links::apply(root.path(), &stale, &stale.digest()?, None, None, &at).is_err()
        );
        assert_eq!(version()?, 55);
        assert!(control.lock().map_err(|_| "peer")?.writes.is_empty());
        let relocation = if named && retirement.is_none() {
            Some(relocation_preview(
                &local,
                &checkout,
                &tree.path().join("moved-checkout"),
                &at,
            )?)
        } else {
            None
        };
        let first = project_links::request_plan(
            root.path(),
            Some(&contexts[0]),
            &checkout,
            &remote_first,
            None,
            None,
            &at,
        )?;
        let first_value = serde_json::to_value(&first)?;
        assert!(!first_value.to_string().contains(&token));
        assert!(!first_value.to_string().contains("discard-this-canary"));
        let first_id = first_value["operation_id"]
            .as_str()
            .ok_or("operation")?
            .to_owned();
        control.lock().map_err(|_| "peer")?.lose_request = true;
        assert!(
            project_links::apply(root.path(), &first, &first.digest()?, None, None, &at).is_err()
        );
        assert_eq!(version()?, CHECKOUT_LINK_SCHEMA);
        assert_eq!(
            project_links::status(root.path(), &first_id)?["state"],
            "applying"
        );
        if matches!(retirement, Some(RetirementCase::UnknownRequest)) {
            let planned = project_links::retirement::plan(root.path(), &first_id, None, &at)?;
            let mut wrong = serde_json::to_value(&planned)?;
            wrong["source"]["progress_digest"] =
                crate::digest::sha256(b"changed source checkpoint").into();
            let wrong: project_links::retirement::Plan = serde_json::from_value(wrong)?;
            assert!(
                project_links::retirement::apply(root.path(), &wrong, &wrong.digest()?, &at)
                    .is_err()
            );
            assert_eq!(version()?, CHECKOUT_LINK_SCHEMA);
            let result =
                project_links::retirement::apply(root.path(), &planned, &planned.digest()?, &at)?;
            assert_eq!(result["remote_outcome"], "unknown");
            assert_eq!(result["reservation_released"], false);
            assert_eq!(version()?, crate::store::CHECKOUT_RETIREMENT_SCHEMA);
            let reads = control.lock().map_err(|_| "peer")?.reads.len();
            assert_eq!(
                project_links::retirement::apply(
                    root.path(),
                    &planned,
                    &planned.digest()?,
                    &after(&at, 3600)?
                )?,
                result
            );
            assert_eq!(
                project_links::apply(root.path(), &first, &first.digest()?, None, None, &at)?["state"],
                "retired"
            );
            assert!(project_links::confirmation_plan(root.path(), &first_id, None, &at).is_err());
            assert_eq!(control.lock().map_err(|_| "peer")?.reads.len(), reads);
            assert_eq!(control.lock().map_err(|_| "peer")?.writes.len(), 1);
            assert_eq!(
                fs::read(checkout.join(".env"))?,
                b"PRIVATE=unowned-file-canary\n"
            );
            let next = project_links::request_plan(
                root.path(),
                Some(&contexts[0]),
                &checkout,
                &remote_first,
                None,
                None,
                &at,
            )?;
            assert_eq!(serde_json::to_value(&next)?["schema_version"], 2);
            project_links::apply(root.path(), &next, &next.digest()?, None, None, &at)?;
            assert_eq!(version()?, crate::store::CHECKOUT_RETIREMENT_SCHEMA);
            return Ok(());
        }
        let select = contexts::select_plan(root.path(), &contexts[1], &at)?;
        contexts::apply(&select, &select.digest()?, &at)?;
        control.lock().map_err(|_| "peer")?.hide_outcome = true;
        assert!(
            project_links::apply(root.path(), &first, &first.digest()?, None, None, &at).is_err()
        );
        assert_eq!(
            project_links::status(root.path(), &first_id)?["state"],
            "applying"
        );
        control.lock().map_err(|_| "peer")?.hide_outcome = false;
        project_links::apply(root.path(), &first, &first.digest()?, None, None, &at)?;
        assert_eq!(control.lock().map_err(|_| "peer")?.writes.len(), 1);
        let confirmation = project_links::confirmation_plan(root.path(), &first_id, None, &at)?;
        let confirmation_id = serde_json::to_value(&confirmation)?["operation_id"]
            .as_str()
            .ok_or("confirmation")?
            .to_owned();
        control.lock().map_err(|_| "peer")?.lose_confirmation = true;
        control.lock().map_err(|_| "peer")?.reject_confirmation =
            matches!(retirement, Some(RetirementCase::ExpiredConfirmation));
        assert!(
            project_links::apply(
                root.path(),
                &confirmation,
                &confirmation.digest()?,
                None,
                None,
                &at
            )
            .is_err()
        );
        if matches!(retirement, Some(RetirementCase::ExpiredConfirmation)) {
            assert!(
                project_links::retirement::plan(
                    root.path(),
                    &confirmation_id,
                    Some(&contexts[0]),
                    &at
                )
                .is_err()
            );
            control.lock().map_err(|_| "peer")?.settlement = Some("unsupported".into());
            assert!(
                project_links::retirement::plan(
                    root.path(),
                    &confirmation_id,
                    Some(&contexts[0]),
                    &at
                )
                .is_err()
            );
            control.lock().map_err(|_| "peer")?.settlement = Some("expired".into());
            let planned = project_links::retirement::plan(
                root.path(),
                &confirmation_id,
                Some(&contexts[0]),
                &at,
            )?;
            control.lock().map_err(|_| "peer")?.settlement = None;
            assert!(
                project_links::retirement::apply(root.path(), &planned, &planned.digest()?, &at)
                    .is_err()
            );
            assert_eq!(version()?, CHECKOUT_LINK_SCHEMA);
            control.lock().map_err(|_| "peer")?.settlement = Some("expired".into());
            let result =
                project_links::retirement::apply(root.path(), &planned, &planned.digest()?, &at)?;
            assert_eq!(result["remote_outcome"], "expired_without_link");
            assert_eq!(result["reservation_released"], true);
            assert_eq!(version()?, crate::store::CHECKOUT_RETIREMENT_SCHEMA);
            let store = Store::planning_at(local.root_directory())?;
            assert_eq!(
                store.connection.query_row(
                    "SELECT count(*) FROM native_checkout_reservation",
                    [],
                    |r| r.get::<_, i64>(0)
                )?,
                0
            );
            drop(store);
            let reads = control.lock().map_err(|_| "peer")?.reads.len();
            assert_eq!(
                project_links::retirement::apply(
                    root.path(),
                    &planned,
                    &planned.digest()?,
                    &after(&at, 3600)?
                )?,
                result
            );
            assert_eq!(control.lock().map_err(|_| "peer")?.reads.len(), reads);
            assert_eq!(
                project_links::apply(
                    root.path(),
                    &confirmation,
                    &confirmation.digest()?,
                    None,
                    None,
                    &at
                )?["state"],
                "retired"
            );
            // Even if a stale/upstream observation says ready again, retirement
            // fences the original request before another confirmation review.
            control.lock().map_err(|_| "peer")?.settlement = None;
            assert!(project_links::confirmation_plan(root.path(), &first_id, None, &at).is_err());
            assert_eq!(control.lock().map_err(|_| "peer")?.reads.len(), reads);
            assert_eq!(control.lock().map_err(|_| "peer")?.writes.len(), 2);
            assert_eq!(
                fs::read(checkout.join(".env"))?,
                b"PRIVATE=unowned-file-canary\n"
            );
            return Ok(());
        }
        if !named {
            let later = format!("{:.3}", jiff::Timestamp::now());
            let refresh = plan(root.path(), Action::Refresh, None, None, &later)?;
            assert_eq!(
                apply(&refresh, &refresh.digest()?, &later)?["outcome"],
                "revoked"
            );
            let later = format!("{:.3}", jiff::Timestamp::now());
            let recovery = plan(root.path(), Action::Recover, None, None, &later)?;
            let intent = recovery.recovery.as_ref().ok_or("root recovery intent")?;
            assert_eq!(intent.interrupted_checkout_links.len(), 1);
            assert_eq!(
                intent.interrupted_checkout_links[0].operation_id,
                confirmation_id
            );
            assert_eq!(
                intent.interrupted_checkout_links[0].plan_digest,
                confirmation.digest()?
            );
            let mut incomplete = recovery.clone();
            incomplete
                .recovery
                .as_mut()
                .ok_or("intent")?
                .interrupted_checkout_links
                .clear();
            assert!(apply(&incomplete, &incomplete.digest()?, &later).is_err());
            assert_eq!(identity_at(root.path())?.context(), local.context());
            assert_eq!(
                project_links::status(root.path(), &confirmation_id)?["state"],
                "applying"
            );
            let store = Store::planning_at(local.root_directory())?;
            let reservations: i64 = store.connection.query_row(
                "SELECT count(*) FROM native_checkout_reservation",
                [],
                |r| r.get(0),
            )?;
            assert_eq!(reservations, 1);
            assert_eq!(control.lock().map_err(|_| "peer")?.writes.len(), 2);
            return Ok(());
        }
        let second = project_links::request_plan(
            root.path(),
            Some(&contexts[1]),
            &checkout,
            &remote_second,
            None,
            None,
            &at,
        )?;
        let second_id = serde_json::to_value(&second)?["operation_id"]
            .as_str()
            .ok_or("operation")?
            .to_owned();
        project_links::apply(root.path(), &second, &second.digest()?, None, None, &at)?;
        let other = project_links::confirmation_plan(root.path(), &second_id, None, &at)?;
        assert!(
            project_links::apply(root.path(), &other, &other.digest()?, None, None, &at).is_err()
        );
        assert_eq!(control.lock().map_err(|_| "peer")?.writes.len(), 3);
        let displaced = tree.path().join("displaced");
        fs::rename(&checkout, &displaced)?;
        let settled = project_links::apply(
            root.path(),
            &confirmation,
            &confirmation.digest()?,
            None,
            None,
            &at,
        )?;
        assert_eq!(settled["state"], "completed");
        let read_count = control.lock().map_err(|_| "peer")?.reads.len();
        assert_eq!(
            project_links::apply(
                root.path(),
                &confirmation,
                &confirmation.digest()?,
                None,
                None,
                &at
            )?,
            settled
        );
        assert_eq!(control.lock().map_err(|_| "peer")?.reads.len(), read_count);
        fs::rename(&displaced, &checkout)?;
        let adoption = project_links::adoption_plan(
            root.path(),
            &first_id,
            Some(&contexts[0]),
            &checkout,
            None,
            &at,
        )?;
        let bound =
            project_links::apply(root.path(), &adoption, &adoption.digest()?, None, None, &at)?;
        assert_eq!(bound["state"], "completed");
        assert_eq!(bound["installation_authority"], false);
        if let Some(relocation) = &relocation {
            reserved_relocation_refuses(
                &local,
                root.path(),
                &checkout,
                relocation,
                &adoption,
                &at,
            )?;
        }
        let store = Store::planning_at(local.root_directory())?;
        let (organization,context):(String,String)=store.connection.query_row(
            "SELECT p.organization_id,r.context_id FROM project_link p JOIN native_checkout_reservation r ON r.local_project_id=p.local_project_id",[],|r|Ok((r.get(0)?,r.get(1)?)))?;
        assert_eq!(organization, FIRST);
        assert_eq!(context, contexts[0]);
        drop(store);
        assert_eq!(
            contexts::list(root.path())?["selected"]["context_id"],
            contexts[1]
        );
        assert_eq!(
            fs::read(checkout.join(".env"))?,
            b"PRIVATE=unowned-file-canary\n"
        );
        assert_eq!(
            control
                .lock()
                .map_err(|_| "peer")?
                .writes
                .iter()
                .filter(|(_, path, _)| path == "/v1/projects/links")
                .count(),
            1
        );
        assert!(
            control.lock().map_err(|_| "peer")?.writes.iter().all(
                |(org, _, body)| body["authorization_revision"] == format!("corporate:{org}:1")
            )
        );
        assert_eq!(
            project_links::status(root.path(), &confirmation_id)?["state"],
            "completed"
        );
        Ok(())
    })();
    control.lock().map_err(|_| "peer")?.stop = true;
    let _wake = TcpStream::connect(address);
    let served = worker.join().map_err(|_| "peer thread")?;
    journey.map_err(|error| format!("named={named}: {error}; fixture server: {served:?}"))?;
    served?;
    Ok(())
}
