use super::{
    event::Event,
    ledger::{self, Scope},
    push::{self, History},
};
use crate::{
    authoring::Identity,
    passport::device,
    store::{
        Store, database,
        revisions::{self, Write},
    },
};
use rusqlite::params;
use serde_json::{Value, json};

const AT: &str = "2026-10-14T00:00:00.000Z";

fn identity() -> Identity {
    Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    }
}

#[test]
fn capture_projects_device_and_account_scoped_consent() -> Result<(), Box<dyn std::error::Error>> {
    let root = tempfile::tempdir()?;
    let identity = identity();
    let mut store = Store::open(root.path(), true)?;
    let plan = device::plan(&mut store, identity.clone(), AT)?;
    device::apply(&mut store, &plan, &plan.digest()?, &identity, AT)?;
    let summary = push::capture(&store.connection, &identity, &identity.device_id)?;
    let payload = &summary.steps[0].payload;
    assert_eq!(payload.as_object().map(|v| v.len()), Some(7));
    assert_eq!(
        payload["operating_system"],
        plan.passport["facts"]["operating_system"]["value"]
    );
    assert_eq!(payload["detected_harnesses"], json!([]));
    assert!(summary.steps[0].local_revision.is_none());
    assert!(payload.get("facts").is_none());
    store.transaction(|t| {
        t.execute("INSERT INTO consent(consent_id,account_id,scope,target,fingerprint,observed,decided_by,origin,created_at) VALUES ('request_consent_proof',?,'task','full-auto','{}','[]','owner','user',?)", params![identity.account_id, AT]).map_err(database)?;
        Ok(())
    })?;
    let consent = push::capture(&store.connection, &identity, "request_consent_proof")?;
    assert_eq!(consent.entity_kind, "unverified_consent");
    assert_eq!(consent.steps[0].operation, "upsert");
    assert!(
        push::capture(
            &store.connection,
            &Identity {
                account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into(),
                ..identity.clone()
            },
            "request_consent_proof"
        )
        .is_err()
    );
    store.transaction(|t| {
        t.execute(
            "UPDATE consent SET revoked_at=? WHERE account_id=?",
            params![AT, identity.account_id],
        )
        .map_err(database)?;
        Ok(())
    })?;
    let revoked = push::capture(&store.connection, &identity, &consent.entity_id)?;
    assert_eq!(revoked.entity_id, consent.entity_id);
    assert_eq!(revoked.steps[0].operation, "tombstone");
    assert_eq!(
        revoked.steps[0].payload,
        json!({"schema_version":1,"scope":"task","target":"full-auto","revoked_at":AT})
    );
    assert_ne!(revoked.digest()?, consent.digest()?);
    Ok(())
}

#[test]
fn retained_conflict_is_a_remote_parent_but_never_an_accepted_head()
-> Result<(), Box<dyn std::error::Error>> {
    let root = tempfile::tempdir()?;
    let identity = identity();
    let scope = Scope::new(&identity.account_id, "https://sync.example.test")?;
    let fixture: Vec<Value> =
        serde_json::from_str(include_str!("../../tests/fixtures/sync-events.json"))?;
    let parent = Event::push(&fixture[0], &identity.account_id)?;
    let mut child = parent.passport()?;
    child["parent_revision_ids"] = json!([child["revision_id"]]);
    child["facts"]["description"]["value"] = "New local revision".into();
    child = revisions::seal(&child)?;
    let mut store = Store::open(root.path(), true)?;
    store.transaction(|t| {
        scope.bind(t, AT)?;
        revisions::commit(t, &parent.passport()?, &identity.device_id, None, Write::Advance {expected_heads:&[]})?;
        revisions::commit(t, &child, &identity.device_id, None, Write::Advance {expected_heads:&[parent.payload["revision_id"].as_str().unwrap_or("").into()]})?;
        ledger::retain(t, &scope, &fixture[0])?;
        ledger::record_receipt(t, &scope, &json!({"schema_version":1,"event_id":parent.event_id,"state":"conflict","revision_id":parent.revision_id,"server_head_revision_id":null,"cursor":null,"conflict":null,"conflicting_entity_id":null,"error_code":null}))?;
        Ok(())
    })?;
    let capture = push::capture(&store.connection, &identity, &parent.entity_id)?;
    let history = History::load(&store.connection, &scope, &parent.entity_id)?;
    assert!(history.head.is_none());
    assert_eq!(capture.steps.len(), 2);
    assert_eq!(
        history
            .known(&capture.steps[0], false)
            .map(|entry| entry.stored.state.as_str()),
        Some("conflict")
    );
    let request = history.request(&capture, &capture.steps[1], &identity)?;
    assert_eq!(request["parent_revision_ids"], json!([parent.revision_id]));
    assert!(request["expected_head_revision_id"].is_null());
    assert_eq!(
        request["payload"]["parent_revision_ids"],
        json!([parent.payload["revision_id"]])
    );
    Ok(())
}
