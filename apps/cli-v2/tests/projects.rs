use std::{error::Error, fs};

use ai_stp_cli_v2::{
    authoring::Identity,
    canonical, digest,
    error::Failure,
    projects::{self, passports},
    store::{Store, revisions},
};
use serde_json::json;

#[test]
fn project_identity_observation_and_interrupted_registration() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let state = temporary.path().join("state");
    let root = temporary.path().join("project-cafe\u{301}");
    fs::create_dir(&state)?;
    fs::create_dir(&root)?;
    fs::write(root.join("main.rs"), b"fn main() {}\n")?;
    fs::write(root.join(".env"), b"TOKEN=synthetic-private-value")?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let at = "2026-10-09T00:00:00.000Z";
    let later = "2026-10-09T00:00:01.000Z";
    let expired = "2026-10-10T00:00:00.000Z";
    let mut store = Store::open(&state, true)?;
    let plan = passports::plan(&mut store, &root, identity.clone(), at)?;
    let plan: passports::Plan =
        serde_json::from_slice(&canonical::bytes(&serde_json::to_value(&plan)?)?)?;
    let id = plan.passport["stable_id"]
        .as_str()
        .ok_or("project missing")?;
    assert!(!root.join(".ai-stp-v2-project").exists());
    assert_eq!(counts(&mut store)?, [0, 0, 0]);
    assert!(!serde_json::to_string(&plan)?.contains("synthetic-private-value"));
    assert_eq!(plan.passport["facts"]["file_count"]["value"], 1);
    assert_eq!(
        plan.passport["facts"]["languages"]["value"],
        json!(["rust"])
    );
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
    assert!(passports::apply(&mut store, &plan, &plan.digest()?, &identity, expired).is_err());
    let mut forged = plan.clone();
    forged.passport["facts"]["file_count"]["value"] = 2000.into();
    forged.passport = revisions::seal(&forged.passport)?;
    assert!(passports::apply(&mut store, &forged, &forged.digest()?, &identity, later).is_err());
    fs::write(root.join("main.rs"), b"fn changed() {}\n")?;
    assert!(passports::apply(&mut store, &plan, &plan.digest()?, &identity, later).is_err());
    assert_eq!(counts(&mut store)?, [0, 0, 0]);
    fs::write(root.join("main.rs"), b"fn main() {}\n")?;
    let stale = passports::plan(&mut store, &root, identity.clone(), at)?;
    store.transaction(|t| {
        t.execute_batch("CREATE TEMP TRIGGER interrupt_registration BEFORE INSERT ON revision BEGIN SELECT RAISE(ABORT,'interrupted'); END;")
            .map_err(|_| Failure::precondition("proof injection failed"))?;
        Ok(())
    })?;
    assert!(passports::apply(&mut store, &plan, &plan.digest()?, &identity, later).is_err());
    assert_eq!(counts(&mut store)?, [0, 0, 1]);
    assert_eq!(
        fs::read_to_string(root.join(".ai-stp-v2-project/project-id"))?,
        format!("{id}\n")
    );
    assert!(passports::apply(&mut store, &stale, &stale.digest()?, &identity, later).is_err());
    drop(store);
    // A restarted process resumes the accepted observation even after source
    // changes and expiry. It must not claim that later bytes were scanned then.
    fs::write(root.join("main.rs"), b"fn after_interruption() {}\n")?;
    let mut store = Store::open(&state, false)?;
    let recovered = passports::plan(&mut store, &root, identity.clone(), expired)?;
    assert_eq!(recovered.digest()?, plan.digest()?);
    let result = passports::apply(
        &mut store,
        &recovered,
        &recovered.digest()?,
        &identity,
        expired,
    )?;
    assert_eq!(result["revision_id"], plan.passport["revision_id"]);
    assert_eq!(counts(&mut store)?, [1, 1, 1]);
    assert_eq!(
        passports::apply(&mut store, &plan, &plan.digest()?, &identity, expired)?,
        result
    );
    assert_eq!(counts(&mut store)?, [1, 1, 1]);
    let next = passports::plan(&mut store, &root, identity.clone(), expired)?;
    assert_eq!(next.passport["stable_id"], id);
    assert_eq!(next.passport["created_at"], at);
    assert_eq!(
        next.passport["parent_revision_ids"],
        json!([result["revision_id"]])
    );
    assert_ne!(
        next.passport["facts"]["index_digest"],
        result["facts"]["index_digest"]
    );
    let newest = passports::apply(&mut store, &next, &next.digest()?, &identity, expired)?;
    let unchanged = passports::plan(&mut store, &root, identity.clone(), expired)?;
    assert_eq!(unchanged.passport, next.passport);
    passports::apply(
        &mut store,
        &unchanged,
        &unchanged.digest()?,
        &identity,
        expired,
    )?;
    assert_eq!(counts(&mut store)?, [1, 2, 3]);
    assert_eq!(
        passports::apply(&mut store, &plan, &plan.digest()?, &identity, expired)?,
        result
    );
    store.transaction(|t| {
        assert_eq!(
            json!(revisions::heads(t, id)?),
            json!([newest["revision_id"]])
        );
        Ok(())
    })?;

    let copied = temporary.path().join("copied");
    fs::create_dir(&copied)?;
    let marker = copied.join(".ai-stp-v2-project");
    fs::create_dir(&marker)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&marker, fs::Permissions::from_mode(0o700))?;
    }
    for name in ["owner", "lock", "project-id"] {
        fs::write(
            marker.join(name),
            fs::read(root.join(".ai-stp-v2-project").join(name))?,
        )?;
    }
    fs::write(copied.join("main.rs"), b"fn copy() {}\n")?;
    fs::write(
        marker.join("project-id"),
        b"project_01JQZK7B8N4M6P2R9T5V0X3Y7Z\n",
    )?;
    assert!(passports::plan(&mut store, &copied, identity.clone(), expired).is_err());
    fs::write(marker.join("project-id"), format!("{id}\n"))?;
    let copy = passports::plan(&mut store, &copied, identity.clone(), expired)?;
    assert_ne!(copy.passport["stable_id"], id);
    passports::apply(&mut store, &copy, &copy.digest()?, &identity, expired)?;
    assert_eq!(
        fs::read_to_string(root.join(".ai-stp-v2-project/project-id"))?,
        format!("{id}\n")
    );
    assert_eq!(
        fs::read_to_string(marker.join("project-id"))?,
        format!(
            "{}\n",
            copy.passport["stable_id"].as_str().ok_or("copy missing")?
        )
    );

    let moved = temporary.path().join("renamed");
    fs::rename(&root, &moved)?;
    let relocation = passports::plan(&mut store, &moved, identity.clone(), expired)?;
    assert_eq!(relocation.passport["stable_id"], id);
    // A restored old root makes the exact move stale; it must not be guessed.
    fs::create_dir(&root)?;
    assert!(
        passports::apply(
            &mut store,
            &relocation,
            &relocation.digest()?,
            &identity,
            expired
        )
        .is_err()
    );
    fs::remove_dir(&root)?;
    passports::apply(
        &mut store,
        &relocation,
        &relocation.digest()?,
        &identity,
        expired,
    )?;
    store.transaction(|t| {
        let stored: String = t
            .query_row(
                "SELECT root FROM project_root WHERE stable_id=?",
                [id],
                |r| r.get(0),
            )
            .map_err(|_| Failure::precondition("proof root missing"))?;
        assert_eq!(
            fs::canonicalize(stored).map_err(|_| Failure::precondition("proof root absent"))?,
            fs::canonicalize(&moved)
                .map_err(|_| Failure::precondition("proof moved root absent"))?
        );
        Ok(())
    })?;
    let mut wrong_owner = identity.clone();
    wrong_owner.account_id = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into();
    assert!(passports::plan(&mut store, &moved, wrong_owner, expired).is_err());
    assert!(
        !projects::index(&moved)?["files"]
            .as_array()
            .ok_or("index missing")?
            .iter()
            .any(|p| p["path"].as_str().is_some_and(|p| p.contains("ai-stp")))
    );
    let held = fs::read(moved.join(".ai-stp-v2-project/project-id"))?;
    fs::hard_link(
        moved.join(".ai-stp-v2-project/project-id"),
        temporary.path().join("marker-alias"),
    )?;
    assert!(passports::plan(&mut store, &moved, identity, expired).is_err());
    assert_eq!(fs::read(moved.join(".ai-stp-v2-project/project-id"))?, held);
    Ok(())
}

fn counts(store: &mut Store) -> ai_stp_cli_v2::error::Result<[i64; 3]> {
    store.transaction(|t| t.query_row("SELECT (SELECT count(*) FROM project_root),(SELECT count(*) FROM revision),(SELECT count(*) FROM operation)",[],|r|Ok([r.get(0)?,r.get(1)?,r.get(2)?]))
        .map_err(|_| Failure::precondition("proof counts missing")))
}
