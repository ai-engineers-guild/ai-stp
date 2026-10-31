use super::*;

const ACCOUNT: &str = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const DEVICE: &str = "device_01ARZ3NDEKTSV4RRFFQ69G5FAW";
const ORGANIZATION: &str = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAX";
const NOW: &str = "2030-01-02T03:04:05.000Z";

fn pending() -> Result<Pending> {
    let mut body = contract::unsigned(ACCOUNT, DEVICE, 7, NOW);
    body["signature"] = "A".repeat(86).into();
    let body = String::from_utf8(canonical::bytes(&body)?).map_err(|_| invalid())?;
    Ok(Pending {
        sha256: digest::sha256(body.as_bytes()),
        body,
        session_revision: "original-session".into(),
        authority_digest: digest::sha256(b"original-authority"),
        checked_at: NOW.into(),
        expires_at: at(time(NOW)? + 240)?,
        next_attempt_at: NOW.into(),
        attempts: 0,
    })
}
fn response(pending: &Pending) -> Result<Value> {
    let body = pending.request()?;
    Ok(
        json!({"schema_version":1,"organization_id":ORGANIZATION,"account_id":ACCOUNT,"device_id":DEVICE,
        "cli_version":body["cli_version"],"capabilities":body["capabilities"],"last_sync_at":null,
        "reported_state":"active","health_state":"active","checked_at":body["checked_at"],
        "received_at":NOW,"revision":1,"stale_after_seconds":86400}),
    )
}

#[test]
fn foreground_signature_has_the_exact_server_ascii_preimage() -> Result<()> {
    let mut body = contract::unsigned(ACCOUNT, DEVICE, 7, NOW);
    body["cli_version"] = "1.0.0".into();
    let expected = concat!(
        "ai-stp:installation-heartbeat:v1\norganization_01ARZ3NDEKTSV4RRFFQ69G5FAX\n",
        "{\"account_id\":\"account_01ARZ3NDEKTSV4RRFFQ69G5FAV\",\"capabilities\":[\"cli.foreground-liveness\"],",
        "\"checked_at\":\"2030-01-02T03:04:05.000Z\",\"cli_version\":\"1.0.0\",",
        "\"device_id\":\"device_01ARZ3NDEKTSV4RRFFQ69G5FAW\",\"health_state\":\"active\",",
        "\"last_sync_at\":null,\"policy_version\":7,\"schema_version\":1}"
    );
    assert_eq!(contract::message(ORGANIZATION, &body)?, expected.as_bytes());
    body["unreviewed"] = true.into();
    assert!(contract::message(ORGANIZATION, &body).is_err());
    Ok(())
}

#[test]
fn backoff_keeps_original_bytes_and_stops_before_signature_expiry() -> Result<()> {
    let mut pending = pending()?;
    let original = pending.body.clone();
    pending.attempted(NOW, 60, 3600)?;
    assert!(!pending.ready(&at(time(NOW)? + 59)?)?);
    pending.attempted(&at(time(NOW)? + 60)?, 60, 3600)?;
    assert_eq!(pending.next_attempt_at, at(time(NOW)? + 180)?);
    pending.attempted(&at(time(NOW)? + 180)?, 60, 3600)?;
    assert_eq!(pending.next_attempt_at, pending.expires_at);
    assert!(!pending.ready(&pending.expires_at)?);
    assert!(!pending.ready(&at(time(NOW)? - 1)?)?);
    assert_eq!(pending.body, original);
    Ok(())
}

#[test]
fn later_server_view_is_superseded_not_an_original_acknowledgement() -> Result<()> {
    let pending = pending()?;
    let mut value = response(&pending)?;
    assert_eq!(pending.acknowledge(ORGANIZATION, &value)?, "acknowledged");
    value["checked_at"] = "2030-01-02T03:04:05.001Z".into();
    assert_eq!(pending.acknowledge(ORGANIZATION, &value)?, "superseded");
    value["organization_id"] = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAY".into();
    assert!(pending.acknowledge(ORGANIZATION, &value).is_err());
    value = response(&pending)?;
    value["capabilities"] = json!(["a.different-observation"]);
    assert!(pending.acknowledge(ORGANIZATION, &value).is_err());
    value = response(&pending)?;
    value["checked_at"] = "2030-01-02T03:04:04.000Z".into();
    assert!(pending.acknowledge(ORGANIZATION, &value).is_err());
    Ok(())
}

#[test]
fn retained_observation_survives_a_client_upgrade_and_refuses_changed_bytes() -> Result<()> {
    let mut pending = pending()?;
    let mut body = pending.request()?;
    body["cli_version"] = "0.1.0".into();
    pending.body = String::from_utf8(canonical::bytes(&body)?).map_err(|_| invalid())?;
    pending.sha256 = digest::sha256(pending.body.as_bytes());
    pending.request()?;
    pending.body.push(' ');
    assert!(pending.request().is_err());
    Ok(())
}
