//! Real SQLite/lock failure boundaries; synthetic receipts grant no component authority.

use super::*;
use std::{error::Error, fs};

pub(in crate::provider::runtime::configuration) fn prove(
    template: &single::Plan,
) -> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir_in("/tmp")?;
    let parent = temporary.path().join("state");
    fs::create_dir(&parent)?;
    let mut children = Vec::new();
    for scope in [Scope::Global, Scope::UserRoot] {
        let root = temporary.path().join(scope.as_str());
        fs::create_dir(&root)?;
        let mut value = template.value()?;
        let id = format!("operation_{}", ulid::Ulid::generate());
        value["operation_id"] = id.clone().into();
        value["state_parent"] = json!(parent);
        value["state_identity"] = json!(identity(&Target::open(&parent)?)?);
        value["target_path"] = json!(root);
        value["target_scope"] = json!(scope);
        value["target_identity"] = json!(identity(&Target::open(&root)?)?);
        value["provider_version"] = "0.0.94".into();
        value["status_before"]["canonical_target"] = json!(root);
        value["provider_plan"]["plan"]["canonical_target"] = json!(root);
        value["provider_plan"]["plan"]["operation_id"] = id.into();
        value["provider_plan"]["plan"]["provider_version"] = "0.0.94".into();
        children.push(Child {
            plan_digest: single::fingerprint(&value)?,
            plan: value,
            bundle_source: None,
        });
    }
    let plan = Plan {
        schema_version: 1,
        action: model::KIND.into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: template.created_at.clone(),
        expires_at: template.expires_at.clone(),
        children,
        project: None,
        program: model::Program {
            executable: None,
            observation_digest: format!("sha256:{}", "a".repeat(64)),
        },
    };
    let value = plan.value()?;
    let bytes = serde_json::to_vec(&value)?;
    let digest = model::fingerprint(&value)?;
    let plan = Plan::parse(&bytes, &digest)?;
    let mut group = journal::Journal::open(&parent, plan, &digest)?;
    let namespace = group.namespace.as_ref().ok_or("namespace")?;
    let mut locks = Vec::new();
    for child in &group.plan.children {
        locks.push(super::super::journal::Journal::open_shared(
            &parent,
            &child.parsed()?,
            &child.plan_digest,
            namespace,
        )?);
    }
    let mut record = Record {
        handoff: None,
        schema_version: 1,
        plan_digest: digest.clone(),
        plan: value,
        phase: "preparing".into(),
        prepared: vec![None; 2],
        results: vec![None; 2],
    };
    {
        let mut store = group.store()?;
        let interrupted = store.transaction(|t| {
            let child = &group.plan.children[0];
            locks[0].admit_at(t, namespace, &child.parsed()?, &child.plan_digest)?;
            Err::<(), _>(invalid())
        });
        assert!(interrupted.is_err());
        assert_eq!(
            store
                .connection
                .query_row("SELECT count(*) FROM operation", [], |r| r.get::<_, i64>(0))?,
            0
        );
        store.transaction(|t| {
            for (child, lock) in group.plan.children.iter().zip(&locks) {
                lock.admit_at(t, namespace, &child.parsed()?, &child.plan_digest)?;
            }
            journal::write(t, &group.plan, &digest, &record)
        })?;
        assert_eq!(
            store
                .connection
                .query_row("SELECT count(*) FROM operation", [], |r| r.get::<_, i64>(0))?,
            3
        );
    }
    drop(locks);
    group.namespace.take();
    for (index, child) in group.plan.children.iter().enumerate() {
        assert!(
            authorize(
                &parent,
                &child.parsed()?,
                &child.plan_digest,
                Mode::Apply,
                None
            )
            .is_err()
        );
        assert!(
            authorize(
                &parent,
                &child.parsed()?,
                &child.plan_digest,
                Mode::Cancel,
                None
            )
            .is_err()
        );
        authorize(
            &parent,
            &child.parsed()?,
            &child.plan_digest,
            Mode::Prepare,
            Some(&group),
        )?;
        record.prepared[index] = Some(outcome::preparation(&child.parsed()?)?);
        group.save(&record)?;
    }
    record.phase = "applying".into();
    group.save(&record)?;
    for (index, child) in group.plan.children.iter().enumerate() {
        let plan = child.parsed()?;
        authorize(
            &parent,
            &plan,
            &child.plan_digest,
            Mode::Apply,
            Some(&group),
        )?;
        let lock = super::super::journal::Journal::open(&parent, &plan, &child.plan_digest)?;
        let hash = &plan.executable_digest;
        let provider = json!({"state":"verified","operation":"remove","plan_digest":plan.provider_plan["plan_digest"],
            "expected_target_digest":plan.provider_plan["plan"]["expected_target_digest"],"target_identity_digest":hash,"backup_ref":null,"setup_id":null});
        let result = outcome::build(&plan, &child.plan_digest, &provider, hash)?;
        lock.complete(&plan, &child.plan_digest, &result)?;
        drop(lock);
        // A crash here leaves the child complete but its parent checkpoint pending.
        assert_eq!(
            apply::apply(
                &parent,
                &serde_json::to_vec(&child.plan)?,
                &child.plan_digest,
                None
            )?,
            result
        );
        let mut competing = child.plan.clone();
        let id = format!("operation_{}", ulid::Ulid::generate());
        competing["operation_id"] = id.clone().into();
        competing["provider_plan"]["plan"]["operation_id"] = id.into();
        let competing_digest = single::fingerprint(&competing)?;
        let competing = single::Plan::parse(&serde_json::to_vec(&competing)?, &competing_digest)?;
        let lock = super::super::journal::Journal::open(&parent, &competing, &competing_digest)?;
        assert!(
            lock.admit(&competing, &competing_digest).is_err(),
            "completed child lost its parent's root reservation"
        );
        drop(lock);
        record.results[index] = Some(result);
        group.save(&record)?;
    }
    let mut cancelled = record.plan.clone();
    cancelled["children"][0]["plan_digest"] = "sha256:invalid".into();
    assert!(
        Plan::parse(
            &serde_json::to_vec(&cancelled)?,
            &model::fingerprint(&cancelled)?
        )
        .is_err()
    );
    record.phase = "verified".into();
    group.save(&record)?;
    let expected = record.result(&group.plan)?;
    attribution(&parent, &group.plan)?;
    drop(group);
    for scope in ["global", "user_root"] {
        fs::remove_dir(temporary.path().join(scope))?;
    }
    for action in ["status", "apply", "cancel"] {
        assert_eq!(execute(&parent, &bytes, &digest, action)?, expected);
    }
    Ok(())
}

/// Project state follows the latest complete installation, including shared roots.
fn attribution(parent: &Path, template: &Plan) -> std::result::Result<(), Box<dyn Error>> {
    use crate::{
        authoring::Identity,
        digest,
        store::revisions::{self, Write},
    };
    let project_root = parent
        .parent()
        .ok_or("fixture parent")?
        .join("registered-project");
    fs::create_dir(&project_root)?;
    let unrelated_root = project_root.with_file_name("unrelated-location-checkout");
    fs::create_dir(&unrelated_root)?;
    let owner = Identity {
        account_id: format!("account_{}", ulid::Ulid::generate()),
        device_id: format!("device_{}", ulid::Ulid::generate()),
    };
    let project_id = format!("project_{}", ulid::Ulid::generate());
    let setup = format!("setup_{}", ulid::Ulid::generate());
    let at = "2026-10-14T00:00:00.000Z";
    let passport = Store::open(parent, false)?.transaction(|t| {
        let project = revisions::commit(t, &json!({"kind":"project","stable_id":project_id,"owner_id":owner.account_id,"created_at":at}),
            &owner.device_id, None, Write::Advance {expected_heads:&[]})?;
        t.execute("INSERT INTO entity(stable_id,kind,created_at) VALUES (?,'setup',?)",rusqlite::params![setup,at]).map_err(database)?;
        t.execute("INSERT INTO project_root(root,stable_id) VALUES (?,?)",rusqlite::params![project_root.to_str(),project_id]).map_err(database)?;
        t.execute("INSERT INTO selected_version VALUES (?,'codex',?,'1.0','pending_install',?)",rusqlite::params![project_id,setup,at]).map_err(database)?;
        Ok(project)
    })?;
    let selected = || -> std::result::Result<String, Box<dyn Error>> {
        Ok(Store::open(parent, false)?.connection.query_row(
            "SELECT state FROM selected_version WHERE project_id=?",
            [&project_id],
            |r| r.get(0),
        )?)
    };
    let mut original_root = None;
    let mut last = None;
    for round in 0..2 {
        let hash = digest::sha256(b"fixture receipts, not authenticated execution evidence");
        let mut value = template.value()?;
        value["operation_id"] = format!("operation_{}", ulid::Ulid::generate()).into();
        value["project"] = json!({"root":project_root,"root_identity":identity(&Target::open(&project_root)?)?,
            "binding":{"project_id":project_id,"identity":owner,"passport_digest":digest::canonical("ai-stp:passport:v1",&passport)?,
            "selection":{"stable_id":setup,"version":"1.0","selected_at":at}}});
        for child in value["children"].as_array_mut().ok_or("children")? {
            let plan = &mut child["plan"];
            let id = format!("operation_{}", ulid::Ulid::generate());
            let target = parent.parent().ok_or("parent")?.join(format!(
                "installed-{round}-{}",
                plan["target_scope"].as_str().ok_or("scope")?
            ));
            fs::create_dir(&target)?;
            plan["operation_id"] = id.clone().into();
            plan["action"] = "configuration.install".into();
            plan["target_path"] = json!(target);
            plan["target_identity"] = json!(identity(&Target::open(&target)?)?);
            plan["status_before"]["canonical_target"] = json!(target);
            plan["setup"] = json!({"stable_id":setup,"version":"1.0","passport_digest":hash});
            plan["provider_plan"]["plan"]["operation_id"] = id.into();
            plan["provider_plan"]["plan"]["canonical_target"] = json!(target);
            plan["provider_plan"]["plan"]["operation"] = "install".into();
            plan["provider_plan"]["plan"]["bundle"] = json!({"bundle_format":"ai-stp-bundle/2","bundle_digest":hash,"artifact_digest":hash,"bundle_size":1024});
            child["plan_digest"] = single::fingerprint(plan)?.into();
            child["bundle_source"] = "/unused/fixture.zip".into();
        }
        let digest = model::fingerprint(&value)?;
        let plan = Plan::parse(&serde_json::to_vec(&value)?, &digest)?;
        let group = journal::Journal::open(parent, plan, &digest)?;
        let mut record = Record {
            handoff: None,
            schema_version: 1,
            plan_digest: digest.clone(),
            plan: value,
            phase: "preparing".into(),
            prepared: vec![None; 2],
            results: vec![None; 2],
        };
        group.save(&record)?;
        {
            let store = Store::planning(parent)?;
            let before = store.connection.serialize("main")?.to_vec();
            let physical = identity(&Target::open(&project_root)?)?;
            assert!(
                crate::provider::configuration::location_unreserved(
                    &store.connection,
                    &project_root,
                    &project_root,
                    &physical,
                )
                .is_err(),
                "an unfinished configuration set lost its separate project-root reservation"
            );
            let moved = project_root.with_file_name("moved-configuration-project");
            fs::rename(&project_root, &moved)?;
            let refused = crate::provider::configuration::location_unreserved(
                &store.connection,
                &project_root,
                &moved,
                &physical,
            );
            fs::rename(&moved, &project_root)?;
            assert!(
                refused.is_err(),
                "a moved aggregate project was declared unrelated to its retained installation"
            );
            crate::provider::configuration::location_unreserved(
                &store.connection,
                &unrelated_root,
                &unrelated_root,
                &identity(&Target::open(&unrelated_root)?)?,
            )?;
            assert_eq!(store.connection.serialize("main")?.to_vec(), before);
        }
        record.phase = "verified".into();
        assert!(
            group.save(&record).is_err(),
            "partial set claimed installed project state"
        );
        for (index, child) in group.plan.children.iter().enumerate() {
            let plan = child.parsed()?;
            record.prepared[index] = Some(outcome::preparation(&plan)?);
        }
        record.phase = "applying".into();
        group.save(&record)?;
        Store::open(parent, false)?.transaction(|t| project::publishing(t, &group.plan))?;
        assert_eq!(selected()?, "pending_install");
        for (index, child) in group.plan.children.iter().enumerate() {
            let plan = child.parsed()?;
            let provider = json!({"state":"verified","operation":"install","plan_digest":plan.provider_plan["plan_digest"],
                "expected_target_digest":plan.provider_plan["plan"]["expected_target_digest"],"target_identity_digest":hash,"backup_ref":null,"setup_id":setup});
            record.results[index] =
                Some(outcome::build(&plan, &child.plan_digest, &provider, &hash)?);
        }
        record.phase = "verified".into();
        group.save(&record)?;
        assert_eq!(selected()?, "installed");
        if round == 0 {
            let mut external = group.plan.children[0].parsed()?;
            external.operation_id = format!("operation_{}", ulid::Ulid::generate());
            external.provider_plan["plan"]["operation_id"] = external.operation_id.clone().into();
            original_root = Some(external);
            Store::open(parent, false)?.transaction(|t| {
                crate::provider::runtime::configuration::project::invalidate_related(
                    t,
                    original_root.as_ref().ok_or_else(invalid)?,
                )
            })?;
            assert_eq!(selected()?, "pending_install");
        } else {
            Store::open(parent, false)?.transaction(|t| {
                crate::provider::runtime::configuration::project::invalidate_related(
                    t,
                    original_root.as_ref().ok_or_else(invalid)?,
                )
            })?;
            assert_eq!(
                selected()?,
                "installed",
                "old-root write invalidated a newer installation at different roots"
            );
        }
        last = Some(group.plan.value()?);
    }
    let value = last.ok_or("last installation")?;
    let digest = model::fingerprint(&value)?;
    let bytes = serde_json::to_vec(&value)?;
    Store::open(parent,false)?.connection.execute("UPDATE selected_version SET state='pending_install',selected_at='2026-10-14T01:00:00.000Z' WHERE project_id=?",[&project_id])?;
    execute(parent, &bytes, &digest, "apply")?;
    assert_eq!(
        selected()?,
        "pending_install",
        "history rewrote a later selection"
    );
    Ok(())
}
