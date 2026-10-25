//! Actual journal/HTTP reads across view switches and authorization changes.

use super::*;
use crate::{
    account::corporate::{self, Request},
    store::Store,
};
use std::sync::{Arc, Mutex, mpsc};

const FIRST: &str = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const SECOND: &str = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAW";

struct Control {
    revision: u32,
    bump: bool,
    wrong_organization: bool,
    revoked: bool,
    stop: bool,
    gate: Option<(mpsc::SyncSender<()>, mpsc::Receiver<()>)>,
    previews: Vec<Value>,
    reads: Vec<String>,
}

fn serve(
    socket: &mut TcpStream,
    control: &Arc<Mutex<Control>>,
    account: &str,
    device: &str,
    token: &str,
    at: &str,
) -> std::io::Result<()> {
    let (header, body) = receive(socket)?;
    let route = header
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .ok_or_else(|| std::io::Error::other("route"))?;
    let headers = header
        .lines()
        .filter_map(|line| line.split_once(':'))
        .map(|(key, value)| (key.to_ascii_lowercase(), value.trim().to_owned()))
        .collect::<std::collections::BTreeMap<_, _>>();
    assert_eq!(
        headers.get("authorization").map(String::as_str),
        Some(format!("Bearer {token}").as_str())
    );
    assert!(!headers.contains_key("x-ai-stp-product-mode"));
    let organization = headers.get("x-ai-stp-organization-id").map(String::as_str);
    if route == "/v1/auth/me" {
        assert!(organization.is_none());
        return respond(
            socket,
            200,
            json!({"schema_version":1,"account_id":account,"device_id":device,"account_status":"active"}),
        );
    }
    if route == "/v1/organizations" {
        assert!(organization.is_none());
        let revision = control
            .lock()
            .map_err(|_| std::io::Error::other("fixture"))?
            .revision;
        return respond(
            socket,
            200,
            json!({"schema_version":1,"items":[
            {"schema_version":1,"organization_id":FIRST,"kind":"corporate","display_name":"First","membership_revision":revision},
            {"schema_version":1,"organization_id":SECOND,"kind":"corporate","display_name":"Second","membership_revision":revision}]}),
        );
    }
    let organization = organization.ok_or_else(|| std::io::Error::other("organization"))?;
    assert!([FIRST, SECOND].contains(&organization));
    if route == "/v1/context" {
        let control = control
            .lock()
            .map_err(|_| std::io::Error::other("fixture"))?;
        if control.revoked {
            return respond(
                socket,
                403,
                json!({"schema_version":1,"ok":false,"error":{"code":"AI_STP_PERMISSION_DENIED"}}),
            );
        }
        return respond(
            socket,
            200,
            json!({"schema_version":1,"mode":"corporate","organization_id":organization,
            "capabilities":{"schema_version":1,"registry_version":2,"mode":"corporate","context_kind":"corporate",
            "organization_id":organization,"authorization_revision":format!("corporate:{organization}:1:{}",control.revision),
            "issued_at":at,"generated_at":at,"expires_at":after(at,300).map_err(std::io::Error::other)?,
            "capabilities":["organization.read"],"unavailable":{}}}),
        );
    }
    assert!(route.starts_with(&format!("/v1/corporate/organizations/{organization}/")));
    let gate = {
        let mut control = control
            .lock()
            .map_err(|_| std::io::Error::other("fixture"))?;
        control.reads.push(format!("{organization}:{route}"));
        control.gate.take()
    };
    if let Some((started, resume)) = gate {
        started.send(()).map_err(std::io::Error::other)?;
        resume
            .recv_timeout(Duration::from_secs(10))
            .map_err(std::io::Error::other)?;
    }
    let mut control = control
        .lock()
        .map_err(|_| std::io::Error::other("fixture"))?;
    if control.bump {
        control.revision += 1;
        control.bump = false;
    }
    if route.ends_with("/catalog-assignments/plan") {
        assert!(header.starts_with("POST "));
        let body: Value = serde_json::from_slice(&body)?;
        assert_eq!(body["account_id"], account);
        assert_eq!(body["materialized"], json!([]));
        control.previews.push(body.clone());
        return respond(
            socket,
            200,
            json!({"schema_version":1,"organization_id":organization,"account_id":account,
            "harness":body["harness"],"project_id":body["project_id"],"technology_id":body["technology_id"],
            "items":[],"total":0,"future_token":"canary"}),
        );
    }
    assert!(header.starts_with("GET "));
    assert!(route.ends_with("/projects"));
    if route.contains("/members/") {
        assert!(route.contains(&format!("/members/{account}/")));
    }
    let observed = if control.wrong_organization {
        control.wrong_organization = false;
        if organization == FIRST { SECOND } else { FIRST }
    } else {
        organization
    };
    let project = observed.replacen("organization_", "remote_project_", 1);
    respond(
        socket,
        200,
        json!({"schema_version":1,"items":[{"schema_version":1,"project_id":project,
        "organization_id":observed,"name":observed,"state":"active","revision":1,"available_actions":[],
        "future_token":"canary","future_private":{"credential":"canary"}}],"future_token":"canary"}),
    )
}

#[test]
fn named_corporate_reads_freeze_views_and_refuse_changed_authority()
-> std::result::Result<(), Box<dyn Error>> {
    exercise(true)
}

#[test]
fn legacy_corporate_reads_preserve_the_original_session_and_offline_registry()
-> std::result::Result<(), Box<dyn Error>> {
    exercise(false)
}

fn exercise(named: bool) -> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let local = identity::apply(&init, &init.digest()?, &at)?;
    let original = local.report();
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let address = listener.local_addr()?;
    let origin = format!("http://{address}");
    let connection = if named {
        let plan = connections::plan(root.path(), "Company", &origin, "github", &at)?;
        connections::apply(&plan, &plan.digest()?, &at)?;
        Some(plan)
    } else {
        None
    };
    let connection_id = connection.as_ref().map(|plan| plan.connection_id.as_str());
    let device = connection
        .as_ref()
        .map_or_else(|| local.context().device_id, |plan| plan.device_id.clone());
    let account = format!("account_{}", ulid::Ulid::generate());
    let token = generated();
    super::ownership_tests::authorize(root.path(), &origin, connection_id, &account, &token, &at)?;
    let control = Arc::new(Mutex::new(Control {
        revision: 1,
        bump: false,
        wrong_organization: false,
        revoked: false,
        stop: false,
        gate: None,
        previews: vec![],
        reads: vec![],
    }));
    let server_control = control.clone();
    let (server_account, server_token, server_at) = (account.clone(), token.clone(), at.clone());
    let worker = thread::spawn(move || -> std::io::Result<()> {
        let deadline = Instant::now() + Duration::from_secs(90);
        for _ in 0..256 {
            let mut socket = accept_until(&listener, deadline)?;
            if server_control
                .lock()
                .map_err(|_| std::io::Error::other("fixture"))?
                .stop
            {
                return Ok(());
            }
            serve(
                &mut socket,
                &server_control,
                &server_account,
                &device,
                &server_token,
                &server_at,
            )?;
        }
        Err(std::io::Error::other("request bound"))
    });
    let journey = (|| -> std::result::Result<(), Box<dyn Error>> {
        let mut contexts = Vec::new();
        for organization in [FIRST, SECOND] {
            let plan = if named {
                contexts::create_plan(
                    root.path(),
                    "Company",
                    connection_id,
                    Some(organization),
                    &at,
                )?
            } else {
                contexts::create_legacy_plan(root.path(), "Company", Some(organization), &at)?
            };
            let result = contexts::apply(&plan, &plan.digest()?, &at)?;
            contexts.push(result["context_id"].as_str().ok_or("context")?.to_owned());
        }
        let select = |id: &str| -> std::result::Result<(), Box<dyn Error>> {
            let plan = contexts::select_plan(root.path(), id, &at)?;
            contexts::apply(&plan, &plan.digest()?, &at)?;
            Ok(())
        };
        select(&contexts[0])?;
        let (started, read_started) = mpsc::sync_channel(1);
        let (resume, continue_read) = mpsc::sync_channel(1);
        control.lock().map_err(|_| "fixture")?.gate = Some((started, continue_read));
        let read_root = root.path().to_owned();
        let reading = thread::spawn(move || {
            corporate::observe(
                &read_root,
                None,
                Request::Projects {
                    membership_only: false,
                },
            )
        });
        read_started.recv_timeout(Duration::from_secs(10))?;
        select(&contexts[1])?;
        resume.send(())?;
        let first = reading.join().map_err(|_| "read thread")??;
        assert_eq!(first["observation"]["context"]["context_id"], contexts[0]);
        assert_eq!(
            first["observation"]["data"]["items"][0]["organization_id"],
            FIRST
        );
        let second = corporate::observe(
            root.path(),
            None,
            Request::Projects {
                membership_only: true,
            },
        )?;
        assert_eq!(second["observation"]["context"]["context_id"], contexts[1]);
        assert_eq!(
            second["observation"]["data"]["items"][0]["organization_id"],
            SECOND
        );
        assert!(!first.to_string().contains("canary"));
        assert!(!first.to_string().contains(&token));
        let operation_count = || -> std::result::Result<i64, Box<dyn Error>> {
            let store = Store::planning_at(local.root_directory())?;
            Ok(store
                .connection
                .query_row("SELECT count(*) FROM operation", [], |row| row.get(0))?)
        };
        let before = operation_count()?;
        for target in [
            "codex",
            "claude-code",
            "antigravity",
            "grok-build",
            "cursor",
            "opencode",
            "pi",
        ] {
            let observation = corporate::observe(
                root.path(),
                Some(&contexts[0]),
                Request::AssignmentPreview {
                    harness: target.into(),
                    project_id: None,
                    technology_id: None,
                },
            )?;
            assert_eq!(observation["observation"]["data"]["harness"], target);
            assert_eq!(
                observation["observation"]["organization"]["organization_id"],
                FIRST
            );
            assert_eq!(observation["observation"]["installation_authority"], false);
        }
        assert_eq!(control.lock().map_err(|_| "fixture")?.previews.len(), 7);
        control.lock().map_err(|_| "fixture")?.bump = true;
        assert!(
            corporate::observe(
                root.path(),
                None,
                Request::Projects {
                    membership_only: false
                }
            )
            .is_err()
        );
        control.lock().map_err(|_| "fixture")?.wrong_organization = true;
        assert!(
            corporate::observe(
                root.path(),
                None,
                Request::Projects {
                    membership_only: false
                }
            )
            .is_err()
        );
        let cached = contexts::show(root.path(), &contexts[1], false)?;
        let reads = control.lock().map_err(|_| "fixture")?.reads.len();
        control.lock().map_err(|_| "fixture")?.revoked = true;
        assert!(
            corporate::observe(
                root.path(),
                None,
                Request::Projects {
                    membership_only: false
                }
            )
            .is_err()
        );
        assert_eq!(control.lock().map_err(|_| "fixture")?.reads.len(), reads);
        assert_eq!(contexts::show(root.path(), &contexts[1], false)?, cached);
        assert_eq!(
            operation_count()?,
            before,
            "read/preview wrote native operation state"
        );
        assert_eq!(local.report(), original);
        assert_eq!(
            status(root.path(), &at)?["session"]["state"],
            if named { "absent" } else { "authorized" }
        );
        Ok(())
    })();
    control.lock().map_err(|_| "fixture")?.stop = true;
    let _wake = TcpStream::connect(address)?;
    let served = worker.join().map_err(|_| "server thread")?;
    journey?;
    served?;
    Ok(())
}
