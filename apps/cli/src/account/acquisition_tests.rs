//! Remote enrollment access and local immutable-byte authorship are distinct.

use super::*;
use crate::{
    account::access::Access,
    authoring::{runtime, setups},
    catalog::acquisition,
    store::Store,
};

#[test]
fn named_private_acquisition_keeps_the_local_actor_and_original_connection()
-> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let device = identity::apply(&init, &init.digest()?, &at)?;
    let original = device.report();
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let connection = connections::plan(root.path(), "Private catalog", &origin, "github", &at)?;
    connections::apply(&connection, &connection.digest()?, &at)?;
    let start = plan_for_connection(
        root.path(),
        Action::Start,
        None,
        None,
        Some(&connection.connection_id),
        &at,
    )?;
    let account = format!("account_{}", ulid::Ulid::generate());
    let token = generated();
    let state = State {
        plan: start.clone(),
        revision: start.operation_id.clone(),
        session: Session::Authorized {
            account_id: account.clone(),
            access_token: model::Secret(Zeroizing::new(token.clone())),
            refresh_token: model::Secret(Zeroizing::new(generated())),
            expires_at: after(&at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.clone(),
    };
    Journal::for_connection(&device, start.connection.as_ref(), true)?
        .ok_or("journal")?
        .write(&state)?;
    let id = format!("setup_{}", ulid::Ulid::generate());
    let (document, payload) = {
        let store = Store::planning(root.path())?;
        setups::compile(
            &store.connection,
            &setups::Request {
                harness_id: "codex".into(),
                name: "Private empty setup".into(),
                description: "An exact private acquisition fixture.".into(),
                purpose: "Verify independent enrollment access.".into(),
                members: vec![],
                requirements: None,
            },
            &id,
            &crate::authoring::Identity {
                account_id: account.clone(),
                device_id: connection.device_id.clone(),
            },
            &at,
        )?
    };
    let metadata = json!({"schema_version":1,"visibility":"private","lifecycle":"active","published_at":at,
        "passport_digest":crate::digest::canonical("ai-stp:passport:v1",&document)?,"passport":document,
        "trust":{"trust_lane":"local_owner_or_pinned","author_verified":false,"component_verified":false}});
    let route = format!("/v1/catalog/setups/{id}/versions/1.0");
    let (server_device, server_account, server_token) =
        (connection.device_id.clone(), account.clone(), token.clone());
    let worker = thread::spawn(move || -> std::io::Result<()> {
        for _ in 0..2 {
            for step in 0..4 {
                let mut socket = accept(&listener)?;
                let (header, body) = receive(&mut socket)?;
                assert!(body.is_empty());
                let authenticated = header.to_ascii_lowercase().contains(&format!(
                    "authorization: bearer {}\r\n",
                    server_token.to_ascii_lowercase()
                ));
                match step {
                    0 => {
                        assert!(header.starts_with("GET /v1/auth/me "));
                        assert!(authenticated);
                        respond(
                            &mut socket,
                            200,
                            json!({"schema_version":1,"account_id":server_account,"device_id":server_device,"account_status":"active"}),
                        )?;
                    }
                    1 => {
                        assert!(header.starts_with(&format!("GET {route} ")));
                        assert!(!authenticated);
                        respond(&mut socket, 404, json!({}))?;
                    }
                    2 => {
                        assert!(header.starts_with(&format!("GET {route}/private ")));
                        assert!(authenticated);
                        respond(&mut socket, 200, metadata.clone())?;
                    }
                    _ => {
                        assert!(header.starts_with(&format!("GET {route}/artifact ")));
                        assert!(authenticated);
                        write!(
                            socket,
                            "HTTP/1.1 200 Result\r\nContent-Type: application/octet-stream\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                            payload.len()
                        )?;
                        socket.write_all(&payload)?;
                    }
                }
            }
        }
        Ok(())
    });
    let mut access =
        Access::for_connection(root.path(), None, Some(&connection.connection_id), false)?;
    access.verify()?;
    let other = crate::authoring::Identity {
        account_id: account.clone(),
        device_id: connection.device_id.clone(),
    };
    assert!(access.check_local_actor(&other).is_err());
    let reviewed = runtime::plan(root.path(), |_, actor, at| {
        acquisition::plan_with_access(None, &id, "1.0", actor, at, Some(&access))
    })?;
    assert_eq!(
        reviewed["plan"]["operation"]["identity"]["device_id"],
        device.context().device_id
    );
    assert_eq!(
        reviewed["plan"]["operation"]["access"]["device_id"],
        connection.device_id
    );
    assert_ne!(device.context().device_id, connection.device_id);
    drop(access);
    let local = contexts::create_plan(root.path(), "Offline view", None, None, &at)?;
    let created = contexts::apply(&local, &local.digest()?, &at)?;
    let select = contexts::select_plan(
        root.path(),
        created["context_id"].as_str().ok_or("context")?,
        &at,
    )?;
    contexts::apply(&select, &select.digest()?, &at)?;
    let file = root.path().join("reviewed.json");
    fs::write(&file, canonical::bytes(&reviewed["plan"])?)?;
    let result = runtime::apply(&file, reviewed["plan_digest"].as_str().ok_or("digest")?)?;
    assert_eq!(result["stable_id"], id);
    worker.join().map_err(|_| "private acquisition fixture")??;
    assert_eq!(
        runtime::apply(&file, reviewed["plan_digest"].as_str().ok_or("digest")?)?,
        result
    );
    assert_eq!(identity_at(root.path())?.report(), original);
    assert_eq!(status(root.path(), &at)?["session"]["state"], "absent");
    Ok(())
}
