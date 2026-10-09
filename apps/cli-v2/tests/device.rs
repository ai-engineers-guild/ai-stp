use std::{
    error::Error,
    sync::{Arc, Barrier},
    thread,
};

use ai_stp_cli_v2::{
    authoring::Identity,
    error::{ErrorKind, Failure},
    passport::device,
    store::{
        Store,
        revisions::{self, Write},
    },
};
use serde_json::json;

const AT: &str = "2026-10-09T00:00:00.000Z";
const NEXT: &str = "2026-10-09T00:00:01.000Z";
const LATER: &str = "2026-10-09T00:00:02.000Z";
const EXPIRED: &str = "2026-10-10T00:00:00.000Z";

fn counts(store: &mut Store) -> Result<[i64; 3], Failure> {
    store.transaction(|t| t.query_row("SELECT (SELECT count(*) FROM entity),(SELECT count(*) FROM revision),(SELECT count(*) FROM operation)",[],|r|Ok([r.get(0)?,r.get(1)?,r.get(2)?])).map_err(|_|Failure::precondition("proof query failed")))
}

#[test]
fn device_observations_are_owned_revalidated_and_do_not_manufacture_history()
-> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let mut read = Store::planning(root.path())?;
    let first = device::plan(&mut read, identity.clone(), AT)?;
    let second = device::plan(&mut read, identity.clone(), AT)?;
    assert_eq!(counts(&mut read)?, [0, 0, 0]);
    assert_eq!(std::fs::read_dir(root.path())?.count(), 0);
    drop(read);
    let barrier = Arc::new(Barrier::new(2));
    let writers: Vec<_> = [first, second]
        .into_iter()
        .map(|plan| {
            let barrier = barrier.clone();
            let root = root.path().to_owned();
            let identity = identity.clone();
            thread::spawn(move || {
                barrier.wait();
                let result = (|| {
                    let mut store = Store::open(&root, true)?;
                    device::apply(&mut store, &plan, &plan.digest()?, &identity, AT)
                })();
                (plan, result)
            })
        })
        .collect();
    let results = writers
        .into_iter()
        .map(|h| h.join().map_err(|_| "writer panicked"))
        .collect::<Result<Vec<_>, _>>()?;
    assert_eq!(results.iter().filter(|(_, r)| r.is_ok()).count(), 1);
    assert!(
        results
            .iter()
            .filter_map(|(_, r)| r.as_ref().err())
            .all(|e| matches!(e.kind, ErrorKind::Conflict))
    );
    let (initial, document) = results
        .into_iter()
        .find_map(|(p, r)| r.ok().map(|d| (p, d)))
        .ok_or("no winner")?;
    let mut store = Store::open(root.path(), false)?;
    assert_eq!(counts(&mut store)?, [1, 1, 1]);
    assert_eq!(document["stable_id"], identity.device_id);
    assert_eq!(document["visibility"], "private");
    assert_eq!(document["facts"].as_object().ok_or("facts")?.len(), 3);
    assert!(document["facts"].get("installed_harnesses").is_none());
    assert_eq!(
        document["facts"]["operating_system"]["value"],
        std::env::consts::OS
    );
    assert_eq!(
        document["facts"]["architecture"]["value"],
        if cfg!(target_arch = "aarch64") {
            "arm64"
        } else {
            "x86_64"
        }
    );
    assert_eq!(
        document["facts"]["tool_versions"]["value"],
        json!([format!("ai-stp-cli-v2={}", env!("CARGO_PKG_VERSION"))])
    );
    let unchanged = device::plan(&mut store, identity.clone(), NEXT)?;
    assert_eq!(unchanged.passport, document);
    let before = counts(&mut store)?;
    assert!(device::apply(&mut store, &unchanged, "sha256:wrong", &identity, NEXT).is_err());
    assert!(device::apply(&mut store, &unchanged, &unchanged.digest()?, &identity, AT).is_err());
    assert!(
        device::apply(
            &mut store,
            &unchanged,
            &unchanged.digest()?,
            &identity,
            EXPIRED
        )
        .is_err()
    );
    for field in [
        "operating_system",
        "architecture",
        "tool_versions",
        "installed_harnesses",
    ] {
        let mut forged = unchanged.clone();
        forged.passport["facts"][field] = json!({"value":"caller-claim","origin":"observed","confirmation":"none","observed_at":NEXT});
        forged.passport = revisions::seal(&forged.passport)?;
        assert!(device::apply(&mut store, &forged, &forged.digest()?, &identity, NEXT).is_err());
    }
    let mut forged = unchanged.clone();
    forged.passport["visibility"] = "public".into();
    forged.passport = revisions::seal(&forged.passport)?;
    assert!(device::apply(&mut store, &forged, &forged.digest()?, &identity, NEXT).is_err());
    let mut other = identity.clone();
    other.account_id = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into();
    assert!(device::plan(&mut store, other.clone(), NEXT).is_err());
    assert!(device::apply(&mut store, &unchanged, &unchanged.digest()?, &other, NEXT).is_err());
    other = identity.clone();
    other.device_id = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into();
    assert!(device::plan(&mut store, other, NEXT).is_err());
    assert_eq!(counts(&mut store)?, before);
    assert_eq!(
        device::apply(
            &mut store,
            &unchanged,
            &unchanged.digest()?,
            &identity,
            NEXT
        )?,
        document
    );
    assert_eq!(counts(&mut store)?, [1, 1, 2]);
    assert_eq!(
        device::apply(&mut store, &initial, &initial.digest()?, &identity, EXPIRED)?,
        document
    );
    assert_eq!(counts(&mut store)?, [1, 1, 2]);

    // Model a prior CLI release through the real revision writer. The new
    // refresh changes only its observed version and retains old platform times.
    let mut old = document.clone();
    old["facts"]["tool_versions"]["value"] = json!(["ai-stp-cli-v2=0.0.0"]);
    old["parent_revision_ids"] = json!([document["revision_id"]]);
    let heads = vec![
        document["revision_id"]
            .as_str()
            .ok_or("revision")?
            .to_owned(),
    ];
    let old = store.transaction(|t| {
        revisions::commit(
            t,
            &old,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: &heads,
            },
        )
    })?;
    let refreshed = device::plan(&mut store, identity.clone(), LATER)?;
    assert_eq!(
        refreshed.passport["parent_revision_ids"],
        json!([old["revision_id"]])
    );
    assert_eq!(
        refreshed.passport["facts"]["operating_system"],
        document["facts"]["operating_system"]
    );
    assert_eq!(
        refreshed.passport["facts"]["tool_versions"]["observed_at"],
        LATER
    );
    let after = device::apply(
        &mut store,
        &refreshed,
        &refreshed.digest()?,
        &identity,
        LATER,
    )?;
    assert_eq!(counts(&mut store)?, [1, 3, 3]);
    assert_eq!(
        device::apply(&mut store, &initial, &initial.digest()?, &identity, EXPIRED)?,
        document
    );
    assert_eq!(
        store.transaction(|t| revisions::heads(t, &identity.device_id))?,
        vec![after["revision_id"].as_str().ok_or("revision")?.to_owned()]
    );
    assert_eq!(
        device::plan(&mut store, identity.clone(), EXPIRED)?.passport,
        after
    );

    // Empty existing contexts still have a real causal parent. Newer/unknown
    // observation fields must refuse instead of being silently discarded.
    let mut empty = after.clone();
    empty["facts"] = json!({});
    empty["parent_revision_ids"] = json!([after["revision_id"]]);
    let heads = vec![after["revision_id"].as_str().ok_or("revision")?.to_owned()];
    let empty = store.transaction(|t| {
        revisions::commit(
            t,
            &empty,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: &heads,
            },
        )
    })?;
    let plan = device::plan(&mut store, identity.clone(), EXPIRED)?;
    assert_eq!(
        plan.passport["parent_revision_ids"],
        json!([empty["revision_id"]])
    );
    let mut advanced = empty.clone();
    advanced["facts"]["future_observation"] =
        json!({"value":"unowned","origin":"observed","confirmation":"none","observed_at":EXPIRED});
    advanced["parent_revision_ids"] = json!([empty["revision_id"]]);
    let heads = vec![empty["revision_id"].as_str().ok_or("revision")?.to_owned()];
    store.transaction(|t| {
        revisions::commit(
            t,
            &advanced,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: &heads,
            },
        )
    })?;
    let before = counts(&mut store)?;
    assert!(device::plan(&mut store, identity.clone(), EXPIRED).is_err());
    assert!(device::apply(&mut store, &plan, &plan.digest()?, &identity, EXPIRED).is_err());
    assert_eq!(counts(&mut store)?, before);
    Ok(())
}
