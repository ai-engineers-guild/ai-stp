use super::*;
use crate::{account::access::Access, http::Endpoint};

#[test]
fn private_access_binds_account_device_origin_expiry_and_physical_root()
-> std::result::Result<(), Box<dyn Error>> {
    let sandbox = tempfile::tempdir()?;
    let root = sandbox.path().join("state");
    fs::create_dir(&root)?;
    let at = format!(
        "{:.3}",
        jiff::Timestamp::now().checked_sub(Duration::from_secs(7200))?
    );
    let init = identity::plan(&root, identity::Storage::File, &at)?;
    let device = identity::apply(&init, &init.digest()?, &at)?;
    let account = format!("account_{}", ulid::Ulid::generate());
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let start = plan(&root, Action::Start, Some(&origin), None, &at)?;
    let mut state = State {
        plan: start.clone(),
        revision: start.operation_id.clone(),
        session: Session::Authorized {
            account_id: account.clone(),
            access_token: model::Secret(Zeroizing::new("generated-private-access".into())),
            refresh_token: model::Secret(Zeroizing::new("generated-private-refresh".into())),
            expires_at: after(&at, 10800)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.clone(),
    };
    let journal = Journal::open(&device, true)?.ok_or("journal")?;
    journal.write(&state)?;
    drop(journal);
    assert!(Access::load(&root, "http://127.0.0.1:1", false).is_err());
    let mut access = Access::load(&root, &origin, false)?;
    let binding = access.binding().clone();
    binding.validate()?;
    assert_eq!(binding.account_id, account);
    let endpoint = Endpoint::new(&origin)?;
    let url = endpoint.route(&["fixture"], &[])?;
    assert!(
        access
            .read(
                &endpoint,
                &url,
                "application/json",
                1024,
                Duration::from_secs(5)
            )
            .is_err()
    );
    let observed = json!({"schema_version":1,"account_id":account,
        "device_id":device.context().device_id,"account_status":"active"});
    let server = thread::spawn(move || -> std::io::Result<()> {
        let mut wrong_account = observed.clone();
        wrong_account["account_id"] = format!("account_{}", ulid::Ulid::generate()).into();
        let mut wrong_device = observed.clone();
        wrong_device["device_id"] = format!("device_{}", ulid::Ulid::generate()).into();
        for value in [wrong_account, wrong_device, observed] {
            let mut socket = accept(&listener)?;
            let (headers, body) = receive(&mut socket)?;
            assert!(headers.starts_with("GET /v1/auth/me "));
            assert!(
                headers
                    .to_ascii_lowercase()
                    .contains("authorization: bearer generated-private-access\r\n")
            );
            assert!(body.is_empty());
            respond(&mut socket, 200, value)?;
        }
        let mut socket = accept(&listener)?;
        let (headers, body) = receive(&mut socket)?;
        assert!(headers.starts_with("GET /v1/catalog/fixture "));
        assert!(
            headers
                .to_ascii_lowercase()
                .contains("authorization: bearer generated-private-access\r\n")
        );
        assert!(body.is_empty());
        respond(&mut socket, 200, json!({"fixture":true}))?;
        Ok(())
    });
    assert!(access.verify().is_err());
    assert!(access.verify().is_err());
    access.verify()?;
    let other = Endpoint::new("http://127.0.0.1:1")?;
    assert!(
        access
            .read(
                &other,
                &other.route(&["fixture"], &[])?,
                "application/json",
                1024,
                Duration::from_secs(5)
            )
            .is_err()
    );
    let bytes = access.read(
        &endpoint,
        &url,
        "application/json",
        1024,
        Duration::from_secs(5),
    )?;
    assert_eq!(crate::wire::parse(&bytes)?, json!({"fixture":true}));
    server.join().map_err(|_| "fixture server panicked")??;

    let displaced = sandbox.path().join("displaced");
    fs::rename(&root, &displaced)?;
    fs::create_dir(&root)?;
    assert!(access.revalidate().is_err());
    assert!(access.cache(true).is_err());
    assert!(fs::read_dir(&root)?.next().is_none());
    drop(access);
    fs::remove_dir(&root)?;
    fs::rename(&displaced, &root)?;

    let Session::Authorized { expires_at, .. } = &mut state.session else {
        return Err("authorized session expected".into());
    };
    *expires_at = after(&at, 3600)?;
    let journal = Journal::open(&device, false)?.ok_or("journal")?;
    journal.write(&state)?;
    drop(journal);
    assert!(Access::load(&root, &origin, false).is_err());
    let mut offline = Access::load(&root, &origin, true)?;
    assert!(offline.binding() == &binding);
    assert!(offline.verify().is_err());
    assert!(
        offline
            .read(
                &endpoint,
                &url,
                "application/json",
                1024,
                Duration::from_secs(5)
            )
            .is_err()
    );
    Ok(())
}
