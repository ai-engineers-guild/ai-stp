use std::{error::Error, fs};

use ai_stp_cli_v2::{
    authoring::Identity,
    canonical,
    error::Failure,
    projects::{passports, technology::retained},
    store::Store,
};
use serde_json::{Value, json};

fn sql(store: &mut Store, sql: &str) -> Result<(), Box<dyn Error>> {
    store.transaction(|t| {
        t.execute_batch(sql)
            .map_err(|_| Failure::precondition("proof SQL failed"))
    })?;
    Ok(())
}

fn counts(store: &mut Store) -> Result<[i64; 3], Box<dyn Error>> {
    Ok(store.transaction(|t| t.query_row(
        "SELECT (SELECT count(*) FROM tech_scan),(SELECT count(*) FROM tech_finding),(SELECT count(*) FROM operation WHERE kind='project.technology.record')",
        [], |r| Ok([r.get(0)?,r.get(1)?,r.get(2)?]),
    ).map_err(|_| Failure::precondition("proof counts failed")))?)
}

fn row(store: &mut Store) -> Result<Value, Box<dyn Error>> {
    Ok(store.transaction(|t| t.query_row(
        "SELECT review,freshness,first_seen_scan,last_seen_scan,override_technology_id,override_version,reviewed_at,claims FROM tech_finding WHERE kind='package' AND coordinate='react'",
        [], |r| Ok(json!({"review":r.get::<_,String>(0)?,"freshness":r.get::<_,String>(1)?,
            "first":r.get::<_,String>(2)?,"last":r.get::<_,String>(3)?,
            "override":r.get::<_,Option<String>>(4)?,"version":r.get::<_,Option<String>>(5)?,
            "reviewed_at":r.get::<_,Option<String>>(6)?,"claims":r.get::<_,String>(7)?})),
    ).map_err(|_| Failure::precondition("proof row failed")))?)
}

pub fn prove() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let state = temporary.path().join("state");
    let root = temporary.path().join("project-cafe\u{301}");
    fs::create_dir(&state)?;
    fs::create_dir(&root)?;
    let nested = root.join("cafe\u{301}");
    fs::create_dir(&nested)?;
    let manifest = nested.join("package.json");
    let source = r#"{"dependencies":{"react":"^19"}}"#;
    fs::write(&manifest, source)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let at = "2026-10-09T00:00:00.000Z";
    let later = "2026-10-09T00:00:01.000Z";
    let expired = "2026-10-10T00:00:00.000Z";
    let mut store = Store::open(&state, true)?;
    assert!(retained::plan(&mut store, &root, identity.clone(), at).is_err());
    let project = passports::plan(&mut store, &root, identity.clone(), at)?;
    passports::apply(&mut store, &project, &project.digest()?, &identity, at)?;
    drop(store);
    let mut planning = Store::planning(&state)?;
    let plan = retained::plan(&mut planning, &root, identity.clone(), at)?;
    let plan: retained::Plan =
        serde_json::from_slice(&canonical::bytes(&serde_json::to_value(plan)?)?)?;
    assert_eq!(counts(&mut planning)?, [0, 0, 0]);
    drop(planning);
    let mut store = Store::open(&state, false)?;
    let competing = retained::plan(&mut store, &root, identity.clone(), at)?;
    assert!(retained::apply(&mut store, &plan, "sha256:wrong", &identity, later).is_err());
    assert!(retained::apply(&mut store, &plan, &plan.digest()?, &identity, expired).is_err());
    fs::write(&manifest, r#"{"dependencies":{"react":"^20"}}"#)?;
    assert!(retained::apply(&mut store, &plan, &plan.digest()?, &identity, later).is_err());
    fs::write(&manifest, source)?;
    let mut changed = plan.clone();
    changed.root_identity[0] = "changed".into();
    assert!(retained::apply(&mut store, &changed, &changed.digest()?, &identity, later).is_err());
    changed = plan.clone();
    changed.expected_revision = format!("revision_{}", "a".repeat(64));
    assert!(retained::apply(&mut store, &changed, &changed.digest()?, &identity, later).is_err());
    let marker = root.join(".ai-stp-v2-project/project-id");
    let marker_bytes = fs::read(&marker)?;
    fs::write(&marker, "project_01JQZK7B8N4M6P2R9T5V0X3Y7Z\n")?;
    assert!(retained::apply(&mut store, &plan, &plan.digest()?, &identity, later).is_err());
    fs::write(&marker, marker_bytes)?;
    sql(
        &mut store,
        "CREATE TEMP TRIGGER interrupt_scan BEFORE INSERT ON operation WHEN NEW.kind='project.technology.record' BEGIN SELECT RAISE(ABORT,'interrupted'); END;",
    )?;
    assert!(retained::apply(&mut store, &plan, &plan.digest()?, &identity, later).is_err());
    assert_eq!(counts(&mut store)?, [0, 0, 0]);
    sql(&mut store, "DROP TRIGGER interrupt_scan;")?;
    let receipt = retained::apply(&mut store, &plan, &plan.digest()?, &identity, later)?;
    assert_eq!(counts(&mut store)?[0], 1);
    assert_eq!(counts(&mut store)?[2], 1);
    let first = row(&mut store)?;
    assert!(
        first["claims"]
            .as_str()
            .ok_or("claims")?
            .contains("cafe\u{301}/package.json")
    );
    assert!(
        retained::apply(
            &mut store,
            &competing,
            &competing.digest()?,
            &identity,
            later
        )
        .is_err()
    );
    let before_review = retained::plan(&mut store, &root, identity.clone(), at)?;
    sql(
        &mut store,
        "UPDATE tech_finding SET review='overridden',override_technology_id='technology_00000000000000000000000001',override_version='20',reviewed_at='2026-10-09T00:00:01.000Z' WHERE coordinate='react';",
    )?;
    assert!(
        retained::apply(
            &mut store,
            &before_review,
            &before_review.digest()?,
            &identity,
            later
        )
        .is_err()
    );
    let reviewed = row(&mut store)?;
    for (bytes, freshness) in [
        ("{", "stale"),
        ("{}", "absent"),
        ("{", "absent"),
        (source, "current"),
    ] {
        fs::write(&manifest, bytes)?;
        let next = retained::plan(&mut store, &root, identity.clone(), at)?;
        retained::apply(&mut store, &next, &next.digest()?, &identity, later)?;
        let current = row(&mut store)?;
        assert_eq!(current["freshness"], freshness);
        for key in ["review", "first", "override", "version", "reviewed_at"] {
            assert_eq!(current[key], reviewed[key], "{key}");
        }
    }
    let newest = row(&mut store)?;
    let before_replay = counts(&mut store)?;
    let renamed = temporary.path().join("unavailable-project");
    fs::rename(&root, &renamed)?;
    assert_eq!(
        retained::apply(&mut store, &plan, &plan.digest()?, &identity, expired)?,
        receipt
    );
    assert_eq!(counts(&mut store)?, before_replay);
    assert_eq!(row(&mut store)?, newest);
    fs::rename(&renamed, &root)?;
    sql(
        &mut store,
        "UPDATE tech_scan SET detector_version='unknown-profile';",
    )?;
    assert!(retained::plan(&mut store, &root, identity.clone(), at).is_err());
    sql(
        &mut store,
        "UPDATE tech_scan SET detector_version='native-technology/1';",
    )?;
    sql(
        &mut store,
        "UPDATE operation SET detail='{}' WHERE kind='project.technology.record';",
    )?;
    assert!(retained::apply(&mut store, &plan, &plan.digest()?, &identity, expired).is_err());

    // Empty observations still conflict through their durable scan identity.
    let empty_root = temporary.path().join("empty");
    fs::create_dir(&empty_root)?;
    let project = passports::plan(&mut store, &empty_root, identity.clone(), at)?;
    passports::apply(&mut store, &project, &project.digest()?, &identity, at)?;
    let first = retained::plan(&mut store, &empty_root, identity.clone(), at)?;
    let stale = retained::plan(&mut store, &empty_root, identity.clone(), at)?;
    retained::apply(&mut store, &first, &first.digest()?, &identity, later)?;
    assert!(retained::apply(&mut store, &stale, &stale.digest()?, &identity, later).is_err());
    Ok(())
}
