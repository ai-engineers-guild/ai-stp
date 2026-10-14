use super::*;
use ai_stp_cli_v2::{
    authoring::runtime,
    digest, passport,
    store::versions::{self, Increment},
    sync::{
        event::Event,
        ledger::{self, Scope},
        pages, versions as bindings,
    },
};
use std::collections::BTreeSet;

const ACCOUNT: &str = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV";

fn page(items: Vec<Value>, next: Option<&str>) -> Value {
    json!({"schema_version":1,"items":items,
        "page":{"schema_version":1,"page_size":100,"next_cursor":next}})
}

fn reseal(event: &mut Value) -> Result<(), Box<dyn Error>> {
    event["content_digest"] = digest::canonical("ai-stp:revision:v1", &event["payload"])?.into();
    event["revision_id"] =
        passport::revision_id(&serde_json::from_value::<Event>(event.clone())?.sealed())?.into();
    Ok(())
}

fn child(event: &Value, sequence: u64) -> Value {
    let mut next = event.clone();
    next["event_id"] = format!("event_page_{sequence}").into();
    next["sequence"] = sequence.into();
    next["parent_revision_ids"] = json!([event["revision_id"]]);
    next["created_at"] = AT.into();
    next
}

fn binding(document: &Value, version: &str) -> Result<Value, Box<dyn Error>> {
    Ok(
        json!({"version":version,"passport_digest":digest::canonical("ai-stp:passport:v1",document)?,
        "revision_id":document["revision_id"],"created_at":AT,"snapshot":document}),
    )
}

#[test]
fn received_pages_commit_together_and_preserve_history_and_local_boundaries()
-> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let mut store = Store::open(root.path(), true)?;
    let scope = Scope::new(ACCOUNT, "https://sync.example.test")?;
    store.transaction(|t| scope.bind(t, AT))?;
    let fixtures: Vec<Value> = serde_json::from_str(include_str!("../fixtures/sync-events.json"))?;
    let mut events = Vec::new();
    for (index, fixture) in fixtures.iter().enumerate() {
        let mut value = serde_json::to_value(Event::push(fixture, ACCOUNT)?)?;
        value["sequence"] = json!(index + 1);
        events.push(value);
    }
    let empty = BTreeSet::new();
    let mut invalid = events.clone();
    invalid[4]["payload"]["origin"] = "tampered after sealing".into();
    let failure = pages::apply(
        &mut store,
        &scope,
        &page(invalid.clone(), Some("p1")),
        None,
        100,
        &empty,
        AT,
    )
    .err()
    .ok_or("tampered page accepted")?;
    assert_eq!(failure.details["event_id"], events[4]["event_id"]);
    assert_eq!(counts(&mut store)?, [0, 1]);
    store.transaction(|t| {
        assert!(pages::cursor(t, &scope)?.is_none());
        Ok(())
    })?;
    // Named abandonment also rolls back when a later event fails.
    invalid[4]["sequence"] = 6.into();
    let skip: BTreeSet<_> = [events[1]["event_id"].as_str().ok_or("id")?.to_owned()].into();
    assert!(
        pages::apply(
            &mut store,
            &scope,
            &page(invalid, None),
            None,
            100,
            &skip,
            AT
        )
        .is_err()
    );
    store.transaction(|t| {
        let count: i64 = t
            .query_row("SELECT count(*) FROM sync_abandoned_event", [], |r| {
                r.get(0)
            })
            .map_err(|_| Failure::input("proof skip count"))?;
        assert_eq!(count, 0);
        Ok(())
    })?;
    let initial = page(events.clone(), Some("p1"));
    let result = pages::apply(&mut store, &scope, &initial, None, 100, &empty, AT)?;
    assert_eq!(result["applied"], 5);
    assert_eq!(result["pending_version_count"], 0);
    assert_eq!(counts(&mut store)?, [4, 1]); // Three drafts and one immutable snapshot.
    let id = events[1]["entity_id"].as_str().ok_or("component")?;
    let draft = events[1]["payload"]["revision_id"]
        .as_str()
        .ok_or("draft")?;
    store.transaction(|t| {
        let entities: i64 = t
            .query_row("SELECT count(*) FROM entity", [], |r| r.get(0))
            .map_err(|_| Failure::input("proof entities"))?;
        assert_eq!(entities, 3); // A foreign device is never a local passport.
        assert_eq!(revisions::heads(t, id)?, [draft]);
        assert_eq!(versions::next(t, id, Increment::Minor)?, "1.1");
        assert_eq!(bindings::outgoing(t, id, "component")?.len(), 1);
        Ok(())
    })?;
    drop(store);
    assert_eq!(runtime::versions(root.path(), id)?["next_minor"], "1.1");
    assert!(runtime::inspect(root.path(), "component", id, Some("1.0")).is_err());
    let mut store = Store::open(root.path(), false)?;
    assert!(pages::apply(&mut store, &scope, &initial, None, 100, &empty, AT).is_err());
    let foreign = Scope::new(ACCOUNT, "https://foreign.example.test")?;
    assert!(pages::apply(&mut store, &foreign, &initial, Some("p1"), 100, &empty, AT).is_err());
    let result = pages::apply(
        &mut store,
        &scope,
        &page(events.clone(), None),
        Some("p1"),
        100,
        &empty,
        AT,
    )?;
    assert_eq!(result["replayed"], 5);
    assert_eq!(result["cursor"], "p1");
    let mut wrong_sequence = events[0].clone();
    wrong_sequence["sequence"] = 100.into();
    assert!(
        pages::apply(
            &mut store,
            &scope,
            &page(vec![wrong_sequence], Some("bad")),
            Some("p1"),
            100,
            &empty,
            AT
        )
        .is_err()
    );

    // Missing historical snapshots reserve their exact coordinates until the
    // content arrives. Neither generic legacy envelope is an installable version.
    let mut legacy = Event::stream(&events[1], ACCOUNT)?.passport()?;
    legacy["facts"]["description"]["value"] = "retained historical snapshot".into();
    legacy = revisions::seal(&legacy)?;
    let metadata = binding(&legacy, "1.1")?;
    let mut reference = metadata.clone();
    reference
        .as_object_mut()
        .ok_or("binding")?
        .remove("snapshot");
    let mut missing = child(&events[1], 6);
    missing["payload"]["sync_released_versions"] = json!([reference]);
    reseal(&mut missing)?;
    let result = pages::apply(
        &mut store,
        &scope,
        &page(vec![missing.clone()], Some("p2")),
        Some("p1"),
        100,
        &empty,
        AT,
    )?;
    assert_eq!(result["pending_version_count"], 1);
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../../tests/golden/passports/component-version.json"
    ))?;
    let mut replacement = fixture["value"].clone();
    replacement["stable_id"] = id.into();
    replacement["version"] = "1.1".into();
    replacement = revisions::seal(&replacement)?;
    passport::versions::validate_document(&replacement)?;
    let refused = store
        .transaction(|t| {
            versions::record(
                t,
                &replacement,
                events[1]["device_id"].as_str().unwrap_or(""),
                None,
                AT,
            )
        })
        .err()
        .ok_or("pending number reassigned")?;
    assert!(matches!(
        refused.kind,
        ai_stp_cli_v2::error::ErrorKind::Conflict
    ));
    store.transaction(|t| {
        assert!(versions::next(t, id, Increment::Minor).is_err());
        Ok(())
    })?;
    let mut collision = child(&missing, 7);
    collision["payload"]["sync_released_versions"] = json!([binding(&legacy, "1.0")?]);
    reseal(&mut collision)?;
    assert!(
        pages::apply(
            &mut store,
            &scope,
            &page(vec![collision], Some("bad")),
            Some("p2"),
            100,
            &empty,
            AT
        )
        .is_err()
    );
    let mut complete = child(&missing, 7);
    complete["payload"]["sync_released_versions"] = json!([metadata]);
    reseal(&mut complete)?;
    let result = pages::apply(
        &mut store,
        &scope,
        &page(vec![complete.clone()], Some("p3")),
        Some("p2"),
        100,
        &empty,
        AT,
    )?;
    assert_eq!(result["pending_version_count"], 0);

    // Native snapshots remain fully usable as metadata; no artifact is fetched.
    let mut native = fixture["value"].clone();
    native["stable_id"] = id.into();
    native["version"] = "2.0".into();
    native = revisions::seal(&native)?;
    passport::versions::validate_document(&native)?;
    let mut release = child(&complete, 8);
    release["payload"]["sync_released_versions"] = json!([binding(&native, "2.0")?]);
    reseal(&mut release)?;
    pages::apply(
        &mut store,
        &scope,
        &page(vec![release.clone()], Some("p4")),
        Some("p3"),
        100,
        &empty,
        AT,
    )?;
    store.transaction(|t| {
        assert_eq!(revisions::heads(t, id)?, [draft]);
        assert_eq!(versions::next(t, id, Increment::Minor)?, "2.1");
        let outgoing = bindings::outgoing(t, id, "component")?;
        assert_eq!(outgoing.len(), 3);
        assert_eq!(outgoing[1].snapshot, Some(legacy.clone()));
        Ok(())
    })?;
    drop(store);
    assert!(runtime::inspect(root.path(), "component", id, Some("1.1")).is_err());
    assert!(runtime::inspect(root.path(), "component", id, Some("2.0")).is_ok());
    let mut store = Store::open(root.path(), false)?;

    let mut revoke = child(&events[4], 9);
    revoke["operation"] = "tombstone".into();
    revoke["payload"] =
        json!({"schema_version":1,"scope":"task","target":"full-auto","revoked_at":AT});
    reseal(&mut revoke)?;
    pages::apply(
        &mut store,
        &scope,
        &page(vec![revoke], Some("p5")),
        Some("p4"),
        100,
        &empty,
        AT,
    )?;
    // Replaying an older upsert cannot restore a revoked consent.
    pages::apply(
        &mut store,
        &scope,
        &page(vec![events[4].clone()], None),
        Some("p5"),
        100,
        &empty,
        AT,
    )?;
    store.transaction(|t| {
        let revoked: String = t
            .query_row(
                "SELECT revoked_at FROM consent WHERE account_id=?",
                [ACCOUNT],
                |r| r.get(0),
            )
            .map_err(|_| Failure::input("proof consent"))?;
        assert_eq!(revoked, AT);
        t.execute(
            "INSERT INTO tombstone(stable_id,reason,created_at) VALUES (?,'local_forget',?)",
            rusqlite::params![id, AT],
        )
        .map_err(|_| Failure::input("proof tombstone"))?;
        Ok(())
    })?;
    let mut later = child(&release, 10);
    let mut document = Event::stream(&events[1], ACCOUNT)?.passport()?;
    document["parent_revision_ids"] = json!([draft]);
    document["facts"]["description"]["value"] = "later received history".into();
    later["payload"] = revisions::seal(&document)?;
    reseal(&mut later)?;
    pages::apply(
        &mut store,
        &scope,
        &page(vec![later], Some("p6")),
        Some("p5"),
        100,
        &empty,
        AT,
    )?;
    store.transaction(|t| {
        let reason: String = t
            .query_row(
                "SELECT reason FROM tombstone WHERE stable_id=?",
                [id],
                |r| r.get(0),
            )
            .map_err(|_| Failure::input("proof tombstone retained"))?;
        assert_eq!(reason, "local_forget");
        Ok(())
    })?;
    let mut forbidden = child(&events[3], 11);
    forbidden["payload"]["api_key"] = "generated-forbidden-value".into();
    reseal(&mut forbidden)?;
    let packet = page(vec![forbidden.clone()], Some("p7"));
    assert!(pages::apply(&mut store, &scope, &packet, Some("p6"), 100, &empty, AT).is_err());
    let skip = [forbidden["event_id"].as_str().ok_or("skip")?.to_owned()].into();
    let result = pages::apply(&mut store, &scope, &packet, Some("p6"), 100, &skip, AT)?;
    assert_eq!(result["skipped_event_ids"], json!([forbidden["event_id"]]));
    let result = pages::apply(&mut store, &scope, &packet, Some("p7"), 100, &empty, AT)?;
    assert_eq!(result["skipped_event_ids"], json!([forbidden["event_id"]]));
    // A locally accepted revocation can precede pulling its older remote
    // ancestor. That unseen ancestor must not reactivate the consent either.
    let mut older = events[4].clone();
    older["entity_id"] = "consent_arrival_order".into();
    older["event_id"] = "event_older_consent".into();
    older["sequence"] = 12.into();
    reseal(&mut older)?;
    let mut pushed = child(&older, 13);
    pushed.as_object_mut().ok_or("event")?.remove("sequence");
    pushed["idempotency_key"] = "revoke-before-pulling-parent".into();
    pushed["expected_head_revision_id"] = older["revision_id"].clone();
    pushed["operation"] = "tombstone".into();
    pushed["payload"] =
        json!({"schema_version":1,"scope":"task","target":"full-auto","revoked_at":AT});
    reseal(&mut pushed)?;
    store.transaction(|t| {
        ledger::retain(t,&scope,&pushed)?;
        ledger::record_receipt(t,&scope,&json!({"schema_version":1,"event_id":pushed["event_id"],
            "state":"accepted","revision_id":pushed["revision_id"],"server_head_revision_id":pushed["revision_id"],
            "cursor":null,"conflict":null,"conflicting_entity_id":null,"error_code":null}))
    })?;
    pages::apply(
        &mut store,
        &scope,
        &page(vec![older], Some("p8")),
        Some("p7"),
        100,
        &empty,
        AT,
    )?;
    store.transaction(|t| {
        let revoked: String = t
            .query_row(
                "SELECT revoked_at FROM consent WHERE account_id=?",
                [ACCOUNT],
                |r| r.get(0),
            )
            .map_err(|_| Failure::input("proof late ancestor"))?;
        assert_eq!(revoked, AT);
        Ok(())
    })?;
    Ok(())
}
