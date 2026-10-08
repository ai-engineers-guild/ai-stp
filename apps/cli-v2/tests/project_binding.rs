use std::{error::Error, fs};

use ai_stp_cli_v2::{
    authoring::{
        Identity,
        passports::{self, Patch},
        project_binding::{self, Request, Target},
        releases, scaffold,
    },
    canonical,
    error::Failure,
    projection::Scope,
    provider::Info,
    store::{Store, versions::Increment},
};
use serde_json::{Value, json};

fn counts(store: &mut Store) -> Result<(i64, i64, i64, i64, i64), Failure> {
    store.transaction(|t| t.query_row("SELECT (SELECT count(*) FROM entity),(SELECT count(*) FROM revision),(SELECT count(*) FROM content),(SELECT count(*) FROM component_source_binding),(SELECT count(*) FROM operation)",[],|r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?))).map_err(|_| Failure::precondition("proof query failed")))
}

fn head(store: &mut Store, id: &str) -> Result<Value, Failure> {
    store.transaction(|t| {
        let bytes: String = t.query_row("SELECT r.content FROM revision r JOIN head h ON h.revision_id=r.revision_id WHERE h.stable_id=?",[id],|r|r.get(0)).map_err(|_| Failure::precondition("proof head missing"))?;
        canonical::parse(bytes.as_bytes())
    })
}

#[test]
fn portable_project_retains_one_identity_and_an_atomic_exact_graph() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().join("review");
    let scaffold = scaffold::plan(
        &root,
        scaffold::Request {
            component_type: "skill".into(),
            name: "review".into(),
            language: "none".into(),
        },
    )?;
    scaffold::apply(&scaffold, &scaffold.digest()?)?;
    let mut patch = canonical::parse(&fs::read(root.join("component-passport.json"))?)?;
    patch["description"] = "Review changed files and explain findings.".into();
    patch["tags"] = json!(["code-review"]);
    patch["license"] = json!({"spdx_id":"MIT","redistribution_allowed":true});
    fs::write(
        root.join("component-passport.json"),
        canonical::bytes(&patch)?,
    )?;
    let body = "---\nname: review\ndescription: Review code.\n---\nReview changed files and report findings.\n";
    fs::write(root.join("source/SKILL.md"), body)?;
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let providers = declarations
        .iter()
        .filter(|v| ["cursor", "codex"].contains(&v["harness_id"].as_str().unwrap_or("")))
        .map(|v| Info::parse(&canonical::bytes(v)?))
        .collect::<Result<Vec<_>, _>>()?;
    let request = Request {
        root: root.clone(),
        targets: vec![
            Target {
                harness_id: "cursor".into(),
                scope: Scope::Project,
            },
            Target {
                harness_id: "codex".into(),
                scope: Scope::UserRoot,
            },
            Target {
                harness_id: "cursor".into(),
                scope: Scope::Global,
            },
        ],
    };
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let at = "2026-10-08T00:00:00.000Z";
    let later = "2026-10-08T00:00:01.000Z";
    let mut store = Store::open(temporary.path(), true)?;
    patch.as_object_mut().ok_or("patch missing")?.remove("tags");
    fs::write(
        root.join("component-passport.json"),
        canonical::bytes(&patch)?,
    )?;
    assert!(
        project_binding::plan(
            &mut store,
            request.clone(),
            &providers,
            identity.clone(),
            at
        )
        .is_err()
    );
    patch["tags"] = json!(["code-review"]);
    fs::write(
        root.join("component-passport.json"),
        canonical::bytes(&patch)?,
    )?;
    let plan = project_binding::plan(
        &mut store,
        request.clone(),
        &providers,
        identity.clone(),
        at,
    )?;
    assert_eq!(counts(&mut store)?, (0, 0, 0, 0, 0));
    assert_eq!(plan.binding.harness_id, "undefined");
    assert!(plan.passport["origin_harness_id"].is_null());
    assert!(!serde_json::to_string(&plan.passport)?.contains(&root.to_string_lossy().to_string()));
    assert_eq!(
        plan.passport["adaptations"]
            .as_array()
            .ok_or("adaptations missing")?
            .len(),
        2
    );
    assert_eq!(
        plan.passport["adaptations"][1]["scope_adaptations"]
            .as_array()
            .ok_or("scopes missing")?
            .len(),
        2
    );
    fs::write(root.join("notes.md"), "A changed project snapshot.")?;
    assert!(project_binding::apply(&mut store, &plan, &plan.digest()?, &identity, later).is_err());
    assert_eq!(counts(&mut store)?, (0, 0, 0, 0, 0));
    fs::remove_file(root.join("notes.md"))?;
    fs::write(
        root.join("source/SKILL.md"),
        format!("{body}Changed instructions.\n"),
    )?;
    assert!(project_binding::apply(&mut store, &plan, &plan.digest()?, &identity, later).is_err());
    fs::write(root.join("source/SKILL.md"), body)?;
    let mut forged = plan.clone();
    forged.passport["description"] = "Forged result".into();
    assert!(
        project_binding::apply(&mut store, &forged, &forged.digest()?, &identity, later).is_err()
    );
    assert!(project_binding::apply(&mut store, &plan, "wrong-digest", &identity, later).is_err());
    let other = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAW".into(),
        ..identity.clone()
    };
    assert!(project_binding::apply(&mut store, &plan, &plan.digest()?, &other, later).is_err());
    // The receipt is last: failure here proves CAS, revision, head and binding rollback together.
    store.transaction(|t| t.execute_batch("CREATE TEMP TRIGGER fail_receipt BEFORE INSERT ON operation BEGIN SELECT RAISE(ABORT,'proof failure'); END;").map_err(|_| Failure::precondition("proof trigger failed")))?;
    assert!(project_binding::apply(&mut store, &plan, &plan.digest()?, &identity, later).is_err());
    assert_eq!(counts(&mut store)?, (0, 0, 0, 0, 0));
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER fail_receipt;")
            .map_err(|_| Failure::precondition("proof trigger failed"))
    })?;
    let plan: project_binding::Plan =
        serde_json::from_slice(&canonical::bytes(&serde_json::to_value(&plan)?)?)?;
    let first = project_binding::apply(&mut store, &plan, &plan.digest()?, &identity, later)?;
    assert_eq!(counts(&mut store)?, (1, 1, 3, 1, 1));
    assert_eq!(
        project_binding::apply(&mut store, &plan, &plan.digest()?, &identity, later)?,
        first
    );
    let mut reversed = request.clone();
    reversed.targets.reverse();
    let unchanged =
        project_binding::plan(&mut store, reversed, &providers, identity.clone(), later)?;
    assert_eq!(unchanged.passport, first);
    project_binding::apply(
        &mut store,
        &unchanged,
        &unchanged.digest()?,
        &identity,
        later,
    )?;
    assert_eq!(counts(&mut store)?.1, 1);
    let id = first["stable_id"].as_str().ok_or("identity missing")?;
    let revision = first["revision_id"].as_str().ok_or("revision missing")?;
    assert!(project_binding::plan(&mut store, request.clone(), &providers, other, at).is_err());
    let mut missing = request.clone();
    missing.targets.remove(0);
    assert!(project_binding::plan(&mut store, missing, &providers, identity.clone(), at).is_err());
    let stale = project_binding::plan(
        &mut store,
        request.clone(),
        &providers,
        identity.clone(),
        at,
    )?;
    let edit = passports::plan(
        &mut store,
        id,
        revision,
        Patch::try_from(json!({"description":"A later authored description."}))?,
        identity.clone(),
        later,
    )?;
    let edited = passports::apply(&mut store, &edit, &edit.digest()?, &identity, later)?;
    assert!(
        project_binding::apply(&mut store, &stale, &stale.digest()?, &identity, later).is_err()
    );
    assert_eq!(
        project_binding::apply(&mut store, &plan, &plan.digest()?, &identity, later)?,
        first
    );
    assert_eq!(head(&mut store, id)?, edited);
    let mut request = request;
    request.targets.push(Target {
        harness_id: "cursor".into(),
        scope: Scope::UserRoot,
    });
    let update = project_binding::plan(
        &mut store,
        request.clone(),
        &providers,
        identity.clone(),
        later,
    )?;
    let updated = project_binding::apply(&mut store, &update, &update.digest()?, &identity, later)?;
    assert_eq!(
        updated["parent_revision_ids"],
        json!([edited["revision_id"]])
    );
    assert_eq!(updated["stable_id"], first["stable_id"]);
    assert_eq!(
        updated["adaptations"][1]["scope_adaptations"]
            .as_array()
            .ok_or("scopes missing")?
            .len(),
        3
    );
    let release = releases::plan(
        &mut store,
        id,
        updated["revision_id"].as_str().ok_or("revision missing")?,
        Increment::Minor,
        &providers,
        identity.clone(),
        later,
    )?;
    let version = releases::apply(&mut store, &release, &release.digest()?, &identity, later)?;
    assert_eq!(version["version"], "1.0");
    assert_eq!(version["adaptations"], updated["adaptations"]);
    if let Some(destination) = std::env::var_os("AI_STP_PROJECT_BINDING_PROOF_DIR") {
        let destination = std::path::PathBuf::from(destination);
        fs::create_dir_all(&destination)?;
        fs::write(
            destination.join("component.json"),
            canonical::bytes(&version)?,
        )?;
        store.transaction(|t| {
            let mut query = t
                .prepare("SELECT digest,bytes FROM content")
                .map_err(|_| Failure::precondition("proof query failed"))?;
            let rows = query
                .query_map([], |r| {
                    Ok((r.get::<_, String>(0)?, r.get::<_, Vec<u8>>(1)?))
                })
                .map_err(|_| Failure::precondition("proof query failed"))?;
            for row in rows {
                let (address, bytes) =
                    row.map_err(|_| Failure::precondition("proof query failed"))?;
                fs::write(
                    destination.join(format!("{}.zip", address.replace(':', "-"))),
                    bytes,
                )
                .map_err(|_| Failure::precondition("proof export failed"))?;
            }
            Ok(())
        })?;
    }
    let moved = temporary.path().join("moved-review");
    fs::rename(&root, &moved)?;
    let mut relocation = request.clone();
    relocation.root = moved.clone();
    let relocated =
        project_binding::plan(&mut store, relocation, &providers, identity.clone(), later)?;
    assert_eq!(relocated.binding.stable_id, id);
    assert_eq!(relocated.passport, updated);
    project_binding::apply(
        &mut store,
        &relocated,
        &relocated.digest()?,
        &identity,
        later,
    )?;
    fs::create_dir_all(root.join("source"))?;
    for file in [
        ".ai-stp-template.json",
        ".gitignore",
        "component-passport.json",
        "source/SKILL.md",
    ] {
        fs::copy(moved.join(file), root.join(file))?;
    }
    let copied = project_binding::plan(
        &mut store,
        request.clone(),
        &providers,
        identity.clone(),
        later,
    )?;
    assert_ne!(copied.binding.stable_id, id);
    drop(store);
    let mut store = Store::open(temporary.path(), false)?;
    fs::remove_file(root.join("source/SKILL.md"))?;
    assert_eq!(
        project_binding::apply(
            &mut store,
            &plan,
            &plan.digest()?,
            &identity,
            "2026-10-09T00:00:00.000Z"
        )?,
        first
    );
    assert_eq!(head(&mut store, id)?, updated);
    let digest = first["adaptations"][0]["source_artifact"]["digest"]
        .as_str()
        .ok_or("source missing")?;
    store.transaction(|t| {
        t.execute("UPDATE content SET bytes=x'00' WHERE digest=?", [digest])
            .map(|_| ())
            .map_err(|_| Failure::precondition("proof corruption failed"))
    })?;
    assert!(project_binding::apply(&mut store, &plan, &plan.digest()?, &identity, later).is_err());
    Ok(())
}
