use std::error::Error;

use ai_stp_cli_v2::{
    authoring::Identity,
    error::Failure,
    store::{
        Store,
        revisions::{self, Write},
    },
    sync::merge,
};
use serde_json::{Value, json};

const AT: &str = "2026-10-14T00:00:00.000Z";
const EXPIRED: &str = "2026-10-15T00:00:00.000Z";

#[test]
fn python_sealed_events_keep_account_content_and_payload_boundaries() -> Result<(), Box<dyn Error>>
{
    use ai_stp_cli_v2::{digest, passport, sync::event::Event};
    // Sealed by Python's production contracts and accepted by the API validator.
    let events: Vec<Value> = serde_json::from_str(include_str!("fixtures/sync-events.json"))?;
    let account = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV";
    for (i, request) in events.iter().enumerate() {
        let parsed = Event::push(request, account)?;
        assert_eq!(parsed.revision_id, request["revision_id"]);
        let mut streamed = serde_json::to_value(parsed)?;
        streamed["sequence"] = json!(i + 1);
        assert_eq!(
            Event::stream(&streamed, account)?.revision_id,
            request["revision_id"]
        );
        assert!(Event::push(request, "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z").is_err());
        streamed["payload"]["schema_version"] = json!(2);
        assert!(Event::stream(&streamed, account).is_err());
    }
    // Re-sealing the outer event must not legitimize forbidden content or a
    // mismatched inner passport. Error output never contains excluded values.
    let reseal = |event: &mut Value| -> Result<(), Box<dyn Error>> {
        let parsed: Event = serde_json::from_value(event.clone())?;
        event["revision_id"] = passport::revision_id(&parsed.sealed())?.into();
        event["content_digest"] =
            digest::canonical("ai-stp:revision:v1", &event["payload"])?.into();
        Ok(())
    };
    for patch in [
        json!({"api_key":"never-export-this-value"}),
        json!({"notes":["/home/proof/private"]}),
        json!({"required_env":[{"name":"T","purpose":"p","value":"never-export-this-value"}]}),
        json!({"requires_authorization":"never-export-this-value"}),
        json!({"nested":{"kind":"ProjectPassport"}}),
    ] {
        let mut request = events[0].clone();
        request["payload"]
            .as_object_mut()
            .ok_or("payload")?
            .extend(patch.as_object().ok_or("patch")?.clone());
        reseal(&mut request)?;
        let error = Event::push(&request, account)
            .err()
            .ok_or("forbidden event accepted")?;
        assert!(!serde_json::to_string(&error.details)?.contains("never-export-this-value"));
    }
    let mut request = events[0].clone();
    request["payload"]["facts"]["description"]["value"] = "changed after sealing".into();
    reseal(&mut request)?;
    assert!(Event::push(&request, account).is_err());
    for snapshot in [Value::Null, json!({"kind":"component"})] {
        let mut request = events[1].clone();
        request["payload"]["sync_released_versions"][0]["snapshot"] = snapshot;
        reseal(&mut request)?;
        assert!(Event::push(&request, account).is_err());
    }
    let mut request = events[1].clone();
    let mut collision = request["payload"]["sync_released_versions"][0].clone();
    collision["passport_digest"] = format!("sha256:{}", "0".repeat(64)).into();
    collision
        .as_object_mut()
        .ok_or("version")?
        .remove("snapshot");
    request["payload"]["sync_released_versions"]
        .as_array_mut()
        .ok_or("versions")?
        .push(collision);
    reseal(&mut request)?;
    assert!(Event::push(&request, account).is_err());
    let mut request = events[4].clone();
    request["payload"]["target"] = "everything".into();
    reseal(&mut request)?;
    assert!(Event::push(&request, account).is_err());
    Ok(())
}

fn id(document: &Value) -> Result<&str, Failure> {
    document["revision_id"]
        .as_str()
        .ok_or_else(|| Failure::input("proof revision absent"))
}

fn counts(store: &mut Store) -> Result<[i64; 2], Failure> {
    store.transaction(|t| {
        t.query_row(
            "SELECT (SELECT count(*) FROM revision),(SELECT count(*) FROM operation)",
            [],
            |r| Ok([r.get(0)?, r.get(1)?]),
        )
        .map_err(|_| Failure::input("proof counts failed"))
    })
}

// Import the same independently authored branch shape as an authenticated pull.
// The transport proof separately establishes the account and event binding.
fn branch(
    store: &mut Store,
    base: &Value,
    field: &str,
    value: Value,
    identity: &Identity,
) -> Result<Value, Failure> {
    store.transaction(|t| {
        let mut document = base.clone();
        document["parent_revision_ids"] = json!([id(base)?]);
        document["facts"][field] =
            json!({"value":value,"origin":"declared","confirmation":"user_confirmed"});
        revisions::commit(
            t,
            &revisions::seal(&document)?,
            &identity.device_id,
            None,
            Write::Received {
                account_id: &identity.account_id,
            },
        )
    })
}

#[test]
fn private_graph_merge_preserves_conflicts_and_atomic_replay() -> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let stable = "developer_01ARZ3NDEKTSV4RRFFQ69G5FAV";
    let mut empty = Store::planning(root.path())?;
    assert!(merge::preview(&mut empty, stable, &identity.account_id).is_err());
    drop(empty);
    assert_eq!(std::fs::read_dir(root.path())?.count(), 0);
    let mut store = Store::open(root.path(), true)?;
    let base = store.transaction(|t| revisions::commit(t,
        &json!({"kind":"developer","stable_id":stable,"owner_id":identity.account_id,"created_at":AT}),
        &identity.device_id, None, Write::Advance { expected_heads:&[] }))?;
    assert_eq!(
        merge::preview(&mut store, stable, &identity.account_id)?["state"],
        "up_to_date"
    );
    let left = branch(&mut store, &base, "role", json!("Engineer"), &identity)?;
    let right = branch(
        &mut store,
        &base,
        "preferred_languages",
        json!(["Rust"]),
        &identity,
    )?;
    let before = counts(&mut store)?;
    let report = merge::preview(&mut store, stable, &identity.account_id)?;
    assert_eq!(report["state"], "merge_ready");
    assert_eq!(report["common_ancestor_revision_id"], base["revision_id"]);
    assert!(!serde_json::to_string(&report)?.contains("Engineer"));
    let plan = merge::plan(&mut store, stable, identity.clone(), AT)?;
    assert_eq!(
        report["candidate_revision_id"],
        plan.passport["revision_id"]
    );
    let mut expected = vec![id(&left)?.to_owned(), id(&right)?.to_owned()];
    expected.sort();
    assert_eq!(plan.expected_heads, expected);
    assert_eq!(plan.passport["parent_revision_ids"], json!(expected));
    assert_eq!(counts(&mut store)?, before);
    assert!(merge::apply(&mut store, &plan, "sha256:wrong", &identity, AT).is_err());
    assert!(merge::apply(&mut store, &plan, &plan.digest()?, &identity, EXPIRED).is_err());
    let mut forged = plan.clone();
    forged.passport["facts"]["role"]["value"] = "forged".into();
    assert!(merge::apply(&mut store, &forged, &forged.digest()?, &identity, AT).is_err());
    let other = Identity {
        account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into(),
        ..identity.clone()
    };
    assert!(merge::plan(&mut store, stable, other.clone(), AT).is_err());
    assert!(merge::apply(&mut store, &plan, &plan.digest()?, &other, AT).is_err());
    store.transaction(|t| t.execute_batch("CREATE TEMP TRIGGER fail_merge BEFORE INSERT ON revision BEGIN SELECT RAISE(ABORT,'interrupted'); END;").map_err(|_| Failure::input("proof trigger failed")))?;
    assert!(merge::apply(&mut store, &plan, &plan.digest()?, &identity, AT).is_err());
    assert_eq!(counts(&mut store)?, before);
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER fail_merge")
            .map_err(|_| Failure::input("proof cleanup failed"))
    })?;
    let merged = merge::apply(&mut store, &plan, &plan.digest()?, &identity, AT)?;
    assert_eq!(merged["facts"]["role"]["value"], "Engineer");
    assert_eq!(
        merged["facts"]["preferred_languages"]["value"],
        json!(["Rust"])
    );
    assert_eq!(counts(&mut store)?, [before[0] + 1, before[1] + 1]);
    let a = branch(
        &mut store,
        &merged,
        "role",
        json!("private-local-value"),
        &identity,
    )?;
    branch(
        &mut store,
        &merged,
        "role",
        json!("private-remote-value"),
        &identity,
    )?;
    let report = merge::preview(&mut store, stable, &identity.account_id)?;
    assert_eq!(report["state"], "conflict");
    assert_eq!(report["affected_fields"], json!(["/facts/role/value"]));
    assert!(!serde_json::to_string(&report)?.contains("private-local-value"));
    assert!(!serde_json::to_string(&report)?.contains("private-remote-value"));
    assert!(merge::plan(&mut store, stable, identity.clone(), AT).is_err());
    let before = counts(&mut store)?;
    assert_eq!(
        merge::apply(&mut store, &plan, &plan.digest()?, &identity, EXPIRED)?,
        merged
    );
    assert_eq!(counts(&mut store)?, before);
    assert_eq!(
        merge::preview(&mut store, stable, &identity.account_id)?["state"],
        "conflict"
    );
    let mut reused = plan.clone();
    reused.passport = a;
    assert!(merge::apply(&mut store, &reused, &reused.digest()?, &identity, AT).is_err());
    branch(&mut store, &merged, "role", json!("third-value"), &identity)?;
    assert_eq!(
        merge::preview(&mut store, stable, &identity.account_id)?["state"],
        "manual_resolution"
    );
    assert!(merge::plan(&mut store, stable, identity.clone(), AT).is_err());
    let component = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV";
    let base = store.transaction(|t| revisions::commit(t,
        &json!({"kind":"component","stable_id":component,"owner_id":identity.account_id,"created_at":AT}),
        &identity.device_id, None, Write::Advance { expected_heads:&[] }))?;
    branch(&mut store, &base, "name", json!("one"), &identity)?;
    branch(&mut store, &base, "description", json!("two"), &identity)?;
    assert_eq!(
        merge::preview(&mut store, component, &identity.account_id)?["state"],
        "manual_resolution"
    );
    assert!(merge::plan(&mut store, component, identity.clone(), AT).is_err());
    let transferred = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
    let old = revisions::seal(&json!({"kind":"component","stable_id":transferred,
        "owner_id":other.account_id,"created_at":AT}))?;
    let mut attached = old.clone();
    attached["parent_revision_ids"] = json!([id(&old)?]);
    attached["owner_id"] = identity.account_id.clone().into();
    let attached = revisions::seal(&attached)?;
    store.transaction(|t| {
        for document in [&old, &attached, &old] {
            revisions::commit(t, document, &identity.device_id, None,
                Write::Received { account_id:&identity.account_id })?;
        }
        assert_eq!(revisions::heads(t, transferred)?, [id(&attached)?]);
        let mut forged = attached.clone();
        forged["parent_revision_ids"] = json!([id(&attached)?]);
        forged["owner_id"] = other.account_id.clone().into();
        assert!(revisions::commit(t, &revisions::seal(&forged)?, &identity.device_id, None,
            Write::Received { account_id:&identity.account_id }).is_err());
        let unknown = format!("revision_{}", "e".repeat(64));
        let receipt = json!({"schema_version":1,"event_id":"event_exact_unknown","state":"conflict",
            "revision_id":id(&attached)?,"server_head_revision_id":unknown,"cursor":null,
            "conflict":null,"error_code":null,"conflicting_entity_id":null});
        t.execute("INSERT INTO sync_event(account_id,event_id,sync_key,local_revision_id,remote_revision_id,entity_id,direction,request_json,state,receipt_json,created_at) VALUES (?,'event_exact_unknown','exact',?,?,?,'push','{}','conflict',?,?)",
            rusqlite::params![identity.account_id,id(&attached)?,id(&attached)?,transferred,receipt.to_string(),AT])
            .map_err(|_| Failure::input("proof receipt failed"))?;
        Ok(())
    })?;
    let report = merge::preview(&mut store, transferred, &identity.account_id)?;
    assert_eq!(report["state"], "conflict");
    assert!(report["common_ancestor_revision_id"].is_null());
    assert_eq!(
        merge::preview(&mut store, transferred, &other.account_id)?["state"],
        "up_to_date"
    );
    Ok(())
}
