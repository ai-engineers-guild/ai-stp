use std::{
    error::Error,
    sync::{Arc, Barrier},
    thread,
};

use ai_stp_cli_v2::{
    authoring::Identity,
    error::{ErrorKind, Failure},
    passport::developer::{self, Patch},
    store::{
        Store,
        revisions::{self, Write},
    },
};
use serde_json::{Value, json};

const AT: &str = "2026-10-09T00:00:00.000Z";
const LATER: &str = "2026-10-09T00:00:01.000Z";
const NEXT: &str = "2026-10-09T00:00:02.000Z";
const EXPIRED: &str = "2026-10-10T00:00:00.000Z";

fn revision(document: &Value) -> Result<&str, Box<dyn Error>> {
    document["revision_id"]
        .as_str()
        .ok_or_else(|| "missing revision".into())
}

fn counts(store: &mut Store) -> Result<[i64; 3], Failure> {
    store.transaction(|t| t.query_row("SELECT (SELECT count(*) FROM entity),(SELECT count(*) FROM revision),(SELECT count(*) FROM operation)",[],|r|Ok([r.get(0)?,r.get(1)?,r.get(2)?])).map_err(|_|Failure::precondition("proof query failed")))
}

#[test]
fn developer_context_is_private_causal_singleton_and_replayable() -> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let mut read = Store::planning(root.path())?;
    assert!(developer::show(&mut read).is_err());
    let first = developer::plan(&mut read, None, None, identity.clone(), AT)?;
    let mut competitors = vec![first.clone()];
    for _ in 1..8 {
        competitors.push(developer::plan(
            &mut read,
            None,
            None,
            identity.clone(),
            AT,
        )?);
    }
    assert_eq!(counts(&mut read)?, [0, 0, 0]);
    assert_eq!(std::fs::read_dir(root.path())?.count(), 0);
    drop(read);
    // Independent handles start together with plans from the same absence.
    // Exactly one profile and one receipt may survive; the loser must reconcile.
    let barrier = Arc::new(Barrier::new(competitors.len()));
    let handles: Vec<_> = competitors
        .into_iter()
        .map(|plan| {
            let barrier = barrier.clone();
            let root = root.path().to_path_buf();
            let identity = identity.clone();
            thread::spawn(move || {
                barrier.wait();
                let result = (|| {
                    let mut store = Store::open(&root, true)?;
                    developer::apply(&mut store, &plan, &plan.digest()?, &identity, LATER)
                })();
                (plan, result)
            })
        })
        .collect();
    let results = handles
        .into_iter()
        .map(|h| h.join().map_err(|_| "writer panicked"))
        .collect::<Result<Vec<_>, _>>()?;
    assert_eq!(
        results.iter().filter(|(_, result)| result.is_ok()).count(),
        1
    );
    for (plan, result) in &results {
        if let Err(error) = result {
            // Opening eight durable stores can exceed the bounded lock wait.
            // Every refused contender must reconcile to the one winning profile.
            assert!(
                matches!(error.kind, ErrorKind::Conflict)
                    || matches!(error.kind, ErrorKind::Precondition)
                        && error.details.get("stage").and_then(Value::as_str)
                            == Some("lock_timeout"),
                "{error:?}"
            );
            let mut store = Store::open(root.path(), false)?;
            let before = counts(&mut store)?;
            let retried = developer::apply(&mut store, plan, &plan.digest()?, &identity, LATER)
                .err()
                .ok_or("a losing initialization created a second profile")?;
            assert!(matches!(retried.kind, ErrorKind::Conflict), "{retried:?}");
            assert_eq!(counts(&mut store)?, before);
        }
    }
    let (initialize, initial) = results
        .into_iter()
        .find_map(|(plan, result)| result.ok().map(|document| (plan, document)))
        .ok_or("no initialization won")?;
    let mut store = Store::open(root.path(), false)?;
    assert_eq!(counts(&mut store)?, [1, 1, 1]);
    // Force the real busy path even when a fast runner did not exhaust it above.
    let locked_root = root.path().to_path_buf();
    let blocked = thread::spawn(move || Store::open(&locked_root, false).err())
        .join()
        .map_err(|_| "blocked opener panicked")?
        .ok_or("a second opener bypassed the exclusive directory lock")?;
    assert!(matches!(blocked.kind, ErrorKind::Precondition));
    assert_eq!(
        blocked.details.get("stage").and_then(Value::as_str),
        Some("lock_timeout")
    );
    assert_eq!(counts(&mut store)?, [1, 1, 1]);
    assert_eq!(initial["visibility"], "private");
    assert_eq!(initial["facts"], json!({}));
    let declarations = br#"{"role":"Engineer","typical_tasks":["Review"],"priorities":["Correctness"],"preferred_languages":["Rust"],"preferred_harnesses":["codex"],"autonomy":"Review changes before delivery"}"#;
    let plan = developer::plan(
        &mut store,
        Some(revision(&initial)?),
        Some(Patch::parse(declarations)?),
        identity.clone(),
        LATER,
    )?;
    let stale = developer::plan(&mut store, None, None, identity.clone(), LATER)?;
    let before = counts(&mut store)?;
    assert!(developer::apply(&mut store, &plan, "sha256:wrong", &identity, LATER).is_err());
    assert!(developer::apply(&mut store, &plan, &plan.digest()?, &identity, EXPIRED).is_err());
    let mut forged = plan.clone();
    forged.passport["visibility"] = "public".into();
    assert!(developer::apply(&mut store, &forged, &forged.digest()?, &identity, LATER).is_err());
    let mut other = identity.clone();
    other.account_id = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into();
    assert!(developer::plan(&mut store, None, None, other.clone(), LATER).is_err());
    assert!(developer::apply(&mut store, &plan, &plan.digest()?, &other, LATER).is_err());
    store.transaction(|t|t.execute_batch("CREATE TEMP TRIGGER fail_developer BEFORE INSERT ON revision BEGIN SELECT RAISE(ABORT,'interrupted'); END;").map_err(|_|Failure::precondition("proof injection failed")))?;
    assert!(developer::apply(&mut store, &plan, &plan.digest()?, &identity, LATER).is_err());
    assert_eq!(counts(&mut store)?, before);
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER fail_developer")
            .map_err(|_| Failure::precondition("proof cleanup failed"))
    })?;
    let updated = developer::apply(&mut store, &plan, &plan.digest()?, &identity, LATER)?;
    assert_eq!(updated["created_at"], initial["created_at"]);
    assert_eq!(updated["parent_revision_ids"], json!([revision(&initial)?]));
    assert_eq!(updated["facts"]["role"]["confirmation"], "user_confirmed");
    assert!(developer::apply(&mut store, &stale, &stale.digest()?, &identity, LATER).is_err());
    let noop = developer::plan(
        &mut store,
        Some(revision(&updated)?),
        Some(Patch::parse(declarations)?),
        identity.clone(),
        NEXT,
    )?;
    assert_eq!(noop.passport, updated);
    assert_eq!(
        developer::apply(&mut store, &noop, &noop.digest()?, &identity, NEXT)?,
        updated
    );
    let edit = developer::plan(
        &mut store,
        Some(revision(&updated)?),
        Some(Patch::parse(
            br#"{"role":"Reviewer","preferred_languages":[]}"#,
        )?),
        identity.clone(),
        LATER,
    )?;
    let newest = developer::apply(&mut store, &edit, &edit.digest()?, &identity, LATER)?;
    assert_eq!(newest["facts"]["preferred_languages"]["value"], json!([]));
    assert_eq!(
        newest["facts"]["priorities"],
        updated["facts"]["priorities"]
    );
    drop(store);
    let mut store = Store::open(root.path(), false)?;
    let before = counts(&mut store)?;
    assert_eq!(
        developer::apply(
            &mut store,
            &initialize,
            &initialize.digest()?,
            &identity,
            EXPIRED
        )?,
        initial
    );
    assert_eq!(
        developer::apply(&mut store, &plan, &plan.digest()?, &identity, EXPIRED)?,
        updated
    );
    assert_eq!(
        developer::show(&mut store)?["revision_id"],
        newest["revision_id"]
    );
    assert_eq!(counts(&mut store)?, before);
    for invalid in [
        br#"{}"#.as_slice(),
        br#"{"operating_system":"linux"}"#,
        br#"{"role":null}"#,
        br#"{"role":{"token":"must-never-appear"}}"#,
        br#"{"role":"one","role":"two"}"#,
        br#"{"preferred_languages":"Rust"}"#,
        br#"{"preferred_languages":["Rust","Rust"]}"#,
        br#"{"autonomy":true}"#,
        br#"{"priorities":[""]}"#,
    ] {
        let error = Patch::parse(invalid)
            .err()
            .ok_or("invalid preference accepted")?;
        assert!(!error.to_string().contains("must-never-appear"));
    }
    assert!(Patch::parse(&vec![b' '; 16385]).is_err());
    // The retained schema also forbids a second profile through lower-level writes.
    assert!(store.transaction(|t| revisions::commit(t,&json!({"kind":"developer","stable_id":format!("developer_{}",ulid::Ulid::generate()),"owner_id":identity.account_id,"created_at":AT}),&identity.device_id,None,Write::Advance{expected_heads:&[]})).is_err());
    assert_eq!(counts(&mut store)?, before);
    assert_eq!(
        developer::show(&mut store)?["revision_id"],
        newest["revision_id"]
    );
    Ok(())
}
