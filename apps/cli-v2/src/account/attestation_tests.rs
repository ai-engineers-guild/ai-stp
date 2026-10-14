//! Real key, immutable source, HTTP authorization and interrupted file export.

use super::*;
use crate::{attestation, authoring::embedded, store::Store};

#[test]
fn author_evidence_is_exact_durable_and_historical_after_logout()
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
    drop(store);
    let server = thread::spawn(move || -> std::io::Result<()> {
        for _ in 0..5 {
            let mut socket = accept(&listener)?;
            let (header, _) = receive(&mut socket)?;
            assert!(header.starts_with("GET /v1/auth/me "));
            assert!(header.contains(&token));
            respond(
                &mut socket,
                200,
                json!({"schema_version":1,"account_id":context.account_id,
                "device_id":context.device_id,"account_status":"active"}),
            )?;
        }
        Ok(())
    });
    let mut request = attestation::Request {
        stable_id: authored.component["stable_id"].as_str().ok_or("id")?.into(),
        version: "1.0".into(),
        evidence: json!({
        "check_id":"credentials","policy_version":"safety-3","tool_versions":{"fixture":"1"},
        "harness_id":"codex","harness_version":"1.0","provider_version":"1.0",
        "test_case_ids":["credential-fixture"],"result":"passed","attested_at":at}),
    };
    let adaptation = &authored.component["adaptations"][0];
    let scope = &adaptation["scope_adaptations"][0];
    request.evidence["adaptation_id"] = adaptation["adaptation_id"].clone();
    request.evidence["projection_digest"] = scope["projection_artifact"]["digest"].clone();
    request.evidence["provider_profile_digest"] =
        scope["required_surface"]["profile_digest"].clone();
    request.evidence["scope"] = scope["scope"].clone();
    let output = root.path().join("evidence.json");
    let plan = attestation::plan(root.path(), None, request.clone(), &output, &at)?;
    let hash = plan.digest()?;
    let value = serde_json::to_value(&plan)?;
    let operation = value["operation_id"].as_str().ok_or("operation")?;
    assert!(!output.exists());
    assert!(attestation::apply(&plan, "sha256:bad", &at).is_err());
    let mut changed = value.clone();
    changed["account"]["revision"] = format!("operation_{}", ulid::Ulid::generate()).into();
    let changed: attestation::Plan = serde_json::from_value(changed)?;
    assert!(attestation::apply(&changed, &changed.digest()?, &at).is_err());
    let mut changed = value.clone();
    changed["record"]["object_digest"] = format!("sha256:{}", "f".repeat(64)).into();
    let changed: attestation::Plan = serde_json::from_value(changed)?;
    assert!(attestation::apply(&changed, &changed.digest()?, &at).is_err());
    let mut changed = value.clone();
    changed["record"]["projection_digest"] = format!("sha256:{}", "f".repeat(64)).into();
    let changed: attestation::Plan = serde_json::from_value(changed)?;
    assert!(attestation::apply(&changed, &changed.digest()?, &at).is_err());
    fs::write(&output, b"existing")?;
    assert!(attestation::apply(&plan, &hash, &at).is_err());
    assert_eq!(fs::read(&output)?, b"existing");
    fs::remove_file(&output)?;
    // Refuse an unowned stage after durable signing. The signed receipt, rather
    // than the caller's missing output, supplies all bytes for the retry.
    let stage = root
        .path()
        .join(format!(".ai-stp-attestation-{}", &hash[7..]));
    std::os::unix::fs::symlink(root.path().join("absent"), &stage)?;
    assert!(attestation::apply(&plan, &hash, &at).is_err());
    let signed = attestation::status(root.path(), operation)?;
    assert_eq!(signed["state"], "signed");
    let journal = Journal::open(&device, false)?.ok_or("journal")?;
    journal.retire()?;
    drop(journal);
    fs::remove_file(&stage)?;
    let completed = attestation::apply(&plan, &hash, &at)?;
    assert_eq!(completed["state"], "completed");
    assert_eq!(completed["attestation"], signed["attestation"]);
    assert_eq!(fs::metadata(&output)?.permissions().mode() & 0o777, 0o600);
    assert_eq!(
        canonical::parse(&fs::read(&output)?)?,
        completed["attestation"]
    );
    assert!(!stage.exists());
    let record = &completed["attestation"];
    assert_eq!(
        attestation::contract::verify(
            record,
            value["account"]["public_key"].as_str().ok_or("key")?
        )?,
        completed["attestation_digest"]
    );
    let mut changed = record.clone();
    changed["result"] = "failed".into();
    assert!(
        attestation::contract::verify(
            &changed,
            value["account"]["public_key"].as_str().ok_or("key")?
        )
        .is_err()
    );
    fs::remove_file(&output)?;
    assert_eq!(
        attestation::apply(&plan, &hash, &after(&at, 3600)?)?,
        completed
    );
    assert_eq!(attestation::status(root.path(), operation)?, completed);
    assert!(
        !output.exists(),
        "historical replay recreated a removed output"
    );
    assert!(attestation::plan(root.path(), None, request, &output, &at).is_err());
    server.join().map_err(|_| "server thread")??;
    Ok(())
}
