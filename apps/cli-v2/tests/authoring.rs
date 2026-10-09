use std::{error::Error, fs};

use ai_stp_cli_v2::{
    authoring::{
        Identity, lifecycle,
        passports::{self, Patch},
    },
    canonical, digest,
    error::Failure,
    store::{
        Store,
        revisions::{self, Write},
    },
};
use serde_json::json;

#[test]
fn confirmed_edit_is_closed_causal_atomic_and_replayable() -> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let mut store = Store::open(root.path(), true)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let id = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV";
    let at = "2026-10-08T00:00:00.000Z";
    let later = "2026-10-08T00:00:01.000Z";
    let first = store.transaction(|transaction| revisions::commit(transaction,
        &json!({"kind":"component","stable_id":id,"owner_id":identity.account_id,
            "created_at":at,"visibility":"public","extension":{"retained":true},
            "facts":{"source_path":{"value":"SKILL.md","origin":"observed","confirmation":"none","observed_at":at}}}),
        &identity.device_id,None,Write::Advance {expected_heads:&[]}))?;
    let original = first["revision_id"].as_str().ok_or("revision missing")?;
    let mut other = identity.clone();
    other.account_id = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into();
    let patch_bytes = br##"{"name":"Confirmed name","description":"Kill child processes after a timeout.","tags":["rust"],"permissions":{},"source":{"repository":"https://example.com/owner/repo","commit":"1111111111111111111111111111111111111111","path":"skill"},"required_env":[{"name":"EXAMPLE_TOKEN","purpose":"Authentication"}]}"##;
    let path = root.path().join("patch.json");
    fs::write(&path, patch_bytes)?;
    assert!(passports::plan(&mut store, id, original, Patch::read(&path)?, other, at).is_err());
    let plan = passports::plan(
        &mut store,
        id,
        original,
        Patch::read(&path)?,
        identity.clone(),
        at,
    )?;
    let encoded = canonical::bytes(&serde_json::to_value(&plan)?)?;
    let plan: passports::Plan = serde_json::from_slice(&encoded)?;
    let stale = passports::plan(
        &mut store,
        id,
        original,
        Patch::parse(br#"{"name":"A concurrent edit"}"#)?,
        identity.clone(),
        at,
    )?;
    assert!(
        passports::apply(
            &mut store,
            &plan,
            &digest::sha256(b"wrong"),
            &identity,
            later
        )
        .is_err()
    );
    let mut tampered = plan.clone();
    tampered.passport["extension"]["retained"] = false.into();
    assert!(
        passports::apply(&mut store, &tampered, &tampered.digest()?, &identity, later).is_err()
    );
    store.transaction(|transaction| {
        assert_eq!(revisions::heads(transaction,id)?,[original]);
        transaction.execute_batch("CREATE TEMP TRIGGER fail_edit BEFORE INSERT ON revision BEGIN SELECT RAISE(ABORT,'interrupted'); END;").map_err(|_| Failure::precondition("proof injection failed"))?;
        Ok(())
    })?;
    assert!(passports::apply(&mut store, &plan, &plan.digest()?, &identity, later).is_err());
    store.transaction(|transaction| {
        let receipts: i64 = transaction
            .query_row("SELECT count(*) FROM operation", [], |row| row.get(0))
            .map_err(|_| Failure::precondition("proof query failed"))?;
        assert_eq!(receipts, 0);
        assert_eq!(revisions::heads(transaction, id)?, [original]);
        transaction
            .execute_batch("DROP TRIGGER fail_edit")
            .map_err(|_| Failure::precondition("proof cleanup failed"))?;
        Ok(())
    })?;
    let edited = passports::apply(&mut store, &plan, &plan.digest()?, &identity, later)?;
    assert_eq!(edited["visibility"], "public");
    assert_eq!(edited["extension"], first["extension"]);
    assert_eq!(
        edited["facts"]["source_path"],
        first["facts"]["source_path"]
    );
    assert_eq!(edited["facts"]["name"]["confirmation"], "user_confirmed");
    assert_eq!(edited["facts"]["permissions"]["value"], json!({}));
    assert_eq!(edited["parent_revision_ids"], json!([original]));
    assert!(passports::apply(&mut store, &stale, &stale.digest()?, &identity, later).is_err());
    let revision = edited["revision_id"]
        .as_str()
        .ok_or("edited revision missing")?;
    let unchanged = passports::plan(
        &mut store,
        id,
        revision,
        Patch::parse(patch_bytes)?,
        identity.clone(),
        later,
    )?;
    assert_eq!(unchanged.passport, edited);
    assert_eq!(
        passports::apply(
            &mut store,
            &unchanged,
            &unchanged.digest()?,
            &identity,
            later
        )?,
        edited
    );
    let next = passports::plan(
        &mut store,
        id,
        revision,
        Patch::parse(br#"{"name":"Next edit"}"#)?,
        identity.clone(),
        later,
    )?;
    let outdated_forget = lifecycle::plan(&mut store, id, revision, identity.clone(), later)?;
    let newest = passports::apply(&mut store, &next, &next.digest()?, &identity, later)?;
    assert!(
        lifecycle::apply(
            &mut store,
            &outdated_forget,
            &outdated_forget.digest()?,
            &identity,
            later
        )
        .is_err()
    );
    drop(store);
    let mut store = Store::open(root.path(), false)?;
    assert_eq!(
        passports::apply(
            &mut store,
            &plan,
            &plan.digest()?,
            &identity,
            "2026-10-09T00:00:00.000Z"
        )?,
        edited
    );
    store.transaction(|transaction| {
        assert_eq!(
            revisions::heads(transaction, id)?,
            [newest["revision_id"]
                .as_str()
                .ok_or_else(|| Failure::precondition("proof revision missing"))?]
        );
        Ok(())
    })?;
    for invalid in [
        br#"{}"#.as_slice(),br#"{"name":null}"#,br#"{"name":"one","name":"two"}"#,
        br#"{"description":"<script>unsafe</script>"}"#,br#"{"managed_paths":["../escape"]}"#,
        br#"{"permissions":{"network":["https","https"]}}"#,
        br#"{"source":{"repository":"https://user:must-never-appear@example.com/repo","commit":"1111111111111111111111111111111111111111","path":"skill"}}"#,
        br#"{"requires_components":[{"stable_id":"component_01ARZ3NDEKTSV4RRFFQ69G5FAV","version":"latest","passport_digest":"sha256:1111111111111111111111111111111111111111111111111111111111111111"}]}"#,
        br#"{"required_env":[{"name":"TOKEN","purpose":"Authentication","access_token":"must-never-appear"}]}"#,
    ] {
        let error = Patch::parse(invalid).err().ok_or("unsafe patch accepted")?;
        assert!(!error.to_string().contains("must-never-appear"));
    }
    assert!(Patch::parse(&vec![b' '; 256 * 1024 + 1]).is_err());
    #[cfg(unix)]
    {
        let link = root.path().join("linked.json");
        std::os::unix::fs::symlink(&path, &link)?;
        assert!(Patch::read(&link).is_err());
    }
    let revision = newest["revision_id"].as_str().ok_or("revision missing")?;
    let forget = lifecycle::plan(&mut store, id, revision, identity.clone(), later)?;
    let stale_edit = passports::plan(
        &mut store,
        id,
        revision,
        Patch::parse(br#"{"name":"Edit after forgetting"}"#)?,
        identity.clone(),
        later,
    )?;
    assert!(
        lifecycle::apply(
            &mut store,
            &forget,
            &digest::sha256(b"wrong"),
            &identity,
            later
        )
        .is_err()
    );
    assert!(
        lifecycle::apply(
            &mut store,
            &forget,
            &forget.digest()?,
            &identity,
            "2026-10-09T00:00:00.000Z"
        )
        .is_err()
    );
    let before = forget_counts(&mut store)?;
    store.transaction(|t| t.execute_batch("CREATE TEMP TRIGGER fail_forget AFTER INSERT ON tombstone BEGIN SELECT RAISE(ABORT,'interrupted'); END;")
        .map_err(|_| Failure::precondition("proof injection failed")))?;
    assert!(lifecycle::apply(&mut store, &forget, &forget.digest()?, &identity, later).is_err());
    assert_eq!(forget_counts(&mut store)?, before);
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER fail_forget")
            .map_err(|_| Failure::precondition("proof cleanup failed"))
    })?;
    let forgotten = lifecycle::apply(&mut store, &forget, &forget.digest()?, &identity, later)?;
    assert_eq!(forgotten["state"], "forgotten");
    assert_eq!(forgotten["revision_id"], revision);
    assert!(
        passports::apply(
            &mut store,
            &stale_edit,
            &stale_edit.digest()?,
            &identity,
            later
        )
        .is_err()
    );
    assert!(
        passports::plan(
            &mut store,
            id,
            revision,
            Patch::parse(br#"{"name":"New edit"}"#)?,
            identity.clone(),
            later
        )
        .is_err()
    );
    assert!(lifecycle::plan(&mut store, id, revision, identity.clone(), later).is_err());
    assert!(
        store
            .transaction(|t| revisions::commit(
                t,
                &stale_edit.passport,
                &identity.device_id,
                None,
                Write::Advance {
                    expected_heads: &[revision.into()]
                }
            ))
            .is_err()
    );
    let after = forget_counts(&mut store)?;
    assert_eq!(
        after,
        (before.0, before.1, before.2, before.3 + 1, before.4 + 1)
    );
    drop(store);
    let mut store = Store::open(root.path(), false)?;
    assert_eq!(
        lifecycle::apply(
            &mut store,
            &forget,
            &forget.digest()?,
            &identity,
            "2026-10-09T00:00:00.000Z"
        )?,
        forgotten
    );
    assert_eq!(forget_counts(&mut store)?, after);
    assert_eq!(
        passports::apply(&mut store, &next, &next.digest()?, &identity, later)?,
        newest
    );
    store.transaction(|t| {
        assert_eq!(revisions::heads(t, id)?, [revision]);
        t.execute(
            "UPDATE tombstone SET reason='substituted' WHERE stable_id=?",
            [id],
        )
        .map_err(|_| Failure::precondition("proof substitution failed"))?;
        Ok(())
    })?;
    assert!(lifecycle::apply(&mut store, &forget, &forget.digest()?, &identity, later).is_err());
    Ok(())
}

fn forget_counts(store: &mut Store) -> Result<(i64, i64, i64, i64, i64), Failure> {
    store.transaction(|t| t.query_row(
        "SELECT (SELECT count(*) FROM revision),(SELECT count(*) FROM content),(SELECT count(*) FROM object_version),(SELECT count(*) FROM operation),(SELECT count(*) FROM tombstone)",
        [], |row| Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?,row.get(4)?)),
    ).map_err(|_| Failure::precondition("proof counts failed")))
}
