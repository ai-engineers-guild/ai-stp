//! SQLite atomicity proof only. Authenticated provider acceptance is a real CLI journey.

use super::{
    journal::Journal,
    outcome,
    plan::{self, Plan},
};
use crate::{
    authoring::Identity,
    digest,
    error::Failure,
    store::{
        Store, database,
        revisions::{self, Write},
    },
};
use serde_json::{Value, json};
use std::{error::Error, path::Path};

pub(super) fn prove(state: &Path, original: &Plan) -> std::result::Result<(), Box<dyn Error>> {
    let owner = Identity {
        account_id: format!("account_{}", ulid::Ulid::generate()),
        device_id: format!("device_{}", ulid::Ulid::generate()),
    };
    let project = format!("project_{}", ulid::Ulid::generate());
    let setup = format!("setup_{}", ulid::Ulid::generate());
    let at = "2026-10-12T00:00:00.000Z";
    let document = Store::open(state, false)?.transaction(|t| {
        let document = revisions::commit(t, &json!({"kind":"project","stable_id":project,"owner_id":owner.account_id,"created_at":at}), &owner.device_id, None, Write::Advance {expected_heads:&[]})?;
        t.execute("INSERT INTO entity(stable_id,kind,created_at) VALUES (?,'setup',?)",rusqlite::params![setup,at]).map_err(database)?;
        t.execute("INSERT INTO project_root(root,stable_id) VALUES (?,?)",rusqlite::params![original.target_path,project]).map_err(database)?;
        t.execute("INSERT INTO selected_version VALUES (?,'codex',?,'1.0','pending_install',?)",rusqlite::params![project,setup,at]).map_err(database)?;
        Ok(document)
    })?;
    let mut value = original.value()?;
    let operation = format!("operation_{}", ulid::Ulid::generate());
    let hash = digest::sha256(b"fixture-only component; no execution authority");
    value["operation_id"] = operation.clone().into();
    value["action"] = "configuration.install".into();
    value["target_scope"] = "project".into();
    value["setup"] = json!({"stable_id":setup,"version":"1.0","passport_digest":hash});
    value["project"] = json!({"project_id":project,"identity":owner,
        "passport_digest":digest::canonical("ai-stp:passport:v1", &document)?,
        "selection":{"stable_id":setup,"version":"1.0","selected_at":at}});
    value["provider_plan"]["plan"]["operation_id"] = operation.into();
    value["provider_plan"]["plan"]["operation"] = "install".into();
    value["provider_plan"]["plan"]["bundle"] = json!({"bundle_format":"ai-stp-bundle/2","bundle_digest":hash,"artifact_digest":hash,"bundle_size":1024});
    let digest = plan::fingerprint(&value)?;
    let plan = Plan::parse(&serde_json::to_vec(&value)?, &digest)?;
    let recorded = || {
        Store::open(state, false)?.transaction(|t| {
            t.query_row(
                "SELECT state FROM selected_version WHERE project_id=?",
                [&project],
                |r| r.get::<_, String>(0),
            )
            .map_err(database)
        })
    };
    let journal = Journal::open(state, &plan, &digest)?;
    journal.admit(&plan, &digest)?;
    let provider = json!({"state":"verified","operation":"install","plan_digest":plan.provider_plan["plan_digest"],
        "expected_target_digest":plan.provider_plan["plan"]["expected_target_digest"],"target_identity_digest":hash,"backup_ref":null,"setup_id":setup});
    let result = outcome::build(&plan, &digest, &provider, &hash)?;
    let interrupted = Store::open(state, false)?.transaction(|t| {
        super::project::completed(t, &plan)?;
        Err::<(), _>(Failure::precondition(
            "fixture interruption before receipt commit",
        ))
    });
    assert!(interrupted.is_err());
    assert_eq!(recorded()?, "pending_install");
    assert_eq!(
        journal.read(&plan, &digest)?.ok_or("missing intent")?.state,
        "applying"
    );
    journal.complete(&plan, &digest, &result)?;
    assert_eq!(recorded()?, "installed");
    drop(journal);
    Store::open(state, false)?.transaction(|t| {
        t.execute("UPDATE selected_version SET state='pending_install',selected_at='2026-10-12T01:00:00.000Z' WHERE project_id=?",[&project]).map_err(database)?;
        assert!(super::project::admitting(t,&plan).is_err());
        super::project::completed(t,&plan)?;
        Ok(())
    })?;
    assert_eq!(
        recorded()?,
        "pending_install",
        "older completion overwrote a later selection"
    );
    assert_eq!(
        super::apply::apply(state, &serde_json::to_vec(&value)?, &digest, None)?,
        result
    );
    assert_eq!(
        recorded()?,
        "pending_install",
        "historical replay changed selection"
    );
    let mut unbound = value;
    unbound.as_object_mut().ok_or("plan")?.remove("project");
    let mut unbound: Plan = serde_json::from_value(unbound)?;
    unbound.setup = Value::Null;
    unbound.action = "configuration.remove".into();
    Store::open(state, false)?.transaction(|t| super::project::completed(t, &unbound))?;
    assert_eq!(recorded()?, "pending_install");
    Ok(())
}
