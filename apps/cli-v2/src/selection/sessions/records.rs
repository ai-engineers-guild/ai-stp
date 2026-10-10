//! Bounded proposal records and independently verified confirmation history.

use super::{
    Confirmation, Context, MAX_BYTES, Member, Plan, Proposal, context::context_history, hash,
    invalid, value,
};
use crate::{
    authoring::{Identity, setups},
    canonical,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
    store::database,
};
use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Trace {
    policy_version: String,
    developer_revision: String,
    device_revision: String,
    project_revision: String,
    candidates: Vec<Member>,
}

pub(super) fn replay(
    connection: &Connection,
    held: &Proposal,
    id: &str,
    version: &str,
    identity: &Identity,
) -> Result<Confirmation> {
    let passport = Objects { connection }.exact_version(id, version, None)?;
    let mut expected_members = value(
        &held
            .members
            .iter()
            .map(Member::reference)
            .collect::<Vec<_>>(),
    )?;
    passport::versions::normalize_component_refs(&mut expected_members)?;
    if passport["owner_id"] != identity.account_id
        || passport["harness_id"] != held.harness_id
        || passport["facts"]["snapshot"]["value"] != held.snapshot
        || passport["facts"]["project_id"]["value"] != held.project_id
        || passport["components"] != expected_members
    {
        return Err(invalid());
    }
    setups::verify(connection, &passport)?;
    let (snapshot, body, created): (String, String, String) = connection.query_row(
        "SELECT snapshot,body,created_at FROM recommendation_trace WHERE stable_id=? AND version=? AND proposal_id=?",
        params![id,version,held.proposal_id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?))).map_err(database)?;
    if snapshot != held.snapshot || body.len() > MAX_BYTES || passport["created_at"] != created {
        return Err(invalid());
    }
    let trace: Trace =
        serde_json::from_value(canonical::parse(body.as_bytes())?).map_err(|_| invalid())?;
    let context = Context {
        project_id: held.project_id.clone(),
        harness_id: held.harness_id.clone(),
        policy_version: trace.policy_version,
        developer_revision: trace.developer_revision,
        device_revision: trace.device_revision,
        project_revision: trace.project_revision,
    };
    if trace.candidates != held.members || context.snapshot(&trace.candidates)? != held.snapshot {
        return Err(invalid());
    }
    context_history(connection, &context, identity)?;
    let receipt: (String, String, String) = connection.query_row(
        "SELECT o.kind,o.state,coalesce(o.detail,'') FROM revision r JOIN operation o ON o.operation_id=r.operation_id WHERE r.revision_id=?",
        [passport["revision_id"].as_str().ok_or_else(invalid)?],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?))).map_err(database)?;
    if receipt.0 != "selection.confirm" || receipt.1 != "verified" || !hash(&receipt.2) {
        return Err(invalid());
    }
    Ok(Confirmation {
        passport,
        created: false,
        state: "pending_install",
    })
}

pub(super) fn load(connection: &Connection, id: &str) -> Result<Option<Proposal>> {
    if !passport::stable_id(id, "proposal") {
        return Err(invalid());
    }
    let row = connection.query_row(
        "SELECT project_id,harness_id,snapshot,CASE WHEN length(CAST(graph AS BLOB))<=1048576 THEN graph ELSE NULL END,created_at,expires_at,cancelled_at,confirmed_stable_id,confirmed_version FROM proposal WHERE proposal_id=?",
        [id],|r| Ok((r.get::<_,String>(0)?,r.get::<_,String>(1)?,r.get::<_,String>(2)?,r.get::<_,Option<String>>(3)?,r.get::<_,String>(4)?,r.get::<_,String>(5)?,r.get::<_,Option<String>>(6)?,r.get::<_,Option<String>>(7)?,r.get::<_,Option<String>>(8)?))
    ).optional().map_err(database)?;
    let Some((
        project_id,
        harness_id,
        snapshot,
        graph,
        created_at,
        expires_at,
        cancelled_at,
        confirmed_stable_id,
        confirmed_version,
    )) = row
    else {
        return Ok(None);
    };
    let graph = graph.ok_or_else(invalid)?;
    let members: Vec<Member> =
        serde_json::from_value(canonical::parse(graph.as_bytes())?).map_err(|_| invalid())?;
    if members.len() > 512
        || !passport::stable_id(&project_id, "project")
        || !hash(&snapshot)
        || !passport::timestamp(&created_at)
        || !passport::timestamp(&expires_at)
        || created_at >= expires_at
        || cancelled_at
            .as_ref()
            .is_some_and(|s| !passport::timestamp(s) || s < &created_at)
        || confirmed_stable_id.is_some() != confirmed_version.is_some()
        || confirmed_stable_id
            .as_ref()
            .is_some_and(|s| !passport::stable_id(s, "setup"))
        || confirmed_version
            .as_ref()
            .is_some_and(|s| !passport::version_number(s))
        || (cancelled_at.is_some() && confirmed_stable_id.is_some())
        || members.windows(2).any(|m| m[0].stable_id >= m[1].stable_id)
        || members.iter().any(|m| {
            !passport::stable_id(&m.stable_id, "component")
                || !passport::version_number(&m.version)
                || !hash(&m.passport_digest)
                || !matches!(
                    m.lane.as_str(),
                    "authoritative" | "experimental" | "local_owner_or_pinned"
                )
                || m.lane_reason.len() > 4096
                || !matches!(m.consent_source.as_str(), "" | "runtime_explicit")
                || !m.overlay_revision_id.is_empty()
        })
    {
        return Err(invalid());
    }
    crate::harnesses::definition(&harness_id)?;
    Ok(Some(Proposal {
        proposal_id: id.into(),
        project_id,
        harness_id,
        snapshot,
        members,
        created_at,
        expires_at,
        cancelled_at,
        confirmed_stable_id,
        confirmed_version,
    }))
}

pub(super) fn require(connection: &Connection, id: &str) -> Result<Proposal> {
    load(connection, id)?
        .ok_or_else(|| Failure::new(ErrorKind::NotFound, "the selection proposal does not exist"))
}

fn text(input: &Value) -> Result<String> {
    String::from_utf8(canonical::bytes(input)?).map_err(|_| invalid())
}

pub(super) fn insert(connection: &Connection, plan: &Plan, snapshot: &str) -> Result<Proposal> {
    // The ephemeral row is the entire effect: no entity, version or journal.
    connection.execute(
        "INSERT INTO proposal(proposal_id,project_id,harness_id,snapshot,graph,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
        params![plan.proposal_id, plan.context.project_id, plan.context.harness_id, snapshot,
            text(&value(&plan.members)?)?, plan.created_at, plan.expires_at],
    ).map_err(database)?;
    require(connection, &plan.proposal_id)
}

pub(super) fn cancel(connection: &Connection, held: &Proposal, at: &str) -> Result<Proposal> {
    connection
        .execute(
            "UPDATE proposal SET cancelled_at=? WHERE proposal_id=?",
            params![at, held.proposal_id],
        )
        .map_err(database)?;
    require(connection, &held.proposal_id)
}

pub(super) fn freeze(
    transaction: &Transaction<'_>,
    held: &Proposal,
    context: Context,
    identity: &Identity,
    expected_digest: &str,
    at: &str,
) -> Result<Confirmation> {
    let request = setups::Request {
        harness_id: held.harness_id.clone(),
        name: format!("{} local setup", held.harness_id),
        description: "Private setup frozen from an exact local selection.".into(),
        purpose: "Apply the confirmed component composition to the selected harness.".into(),
        members: held.members.iter().map(Member::reference).collect(),
        requirements: None,
    };
    let id = format!("setup_{}", ulid::Ulid::generate());
    let (mut passport, _) = setups::compile(transaction, &request, &id, identity, at)?;
    passport["facts"]["project_id"] =
        json!({"value":held.project_id,"origin":"derived","confirmation":"none","observed_at":at});
    passport["facts"]["snapshot"]["value"] = held.snapshot.clone().into();
    passport["target_role"] = "local-project".into();
    let (passport, payload) = setups::finish(passport)?;
    let operation = format!("operation_{}", ulid::Ulid::generate());
    transaction.execute(
        "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,'selection.confirm','verified',?,?,?)",
        params![operation, at, at, expected_digest],
    ).map_err(database)?;
    let passport = setups::persist(transaction, &passport, &payload, identity, &operation, at)?;
    let trace = value(&Trace {
        policy_version: context.policy_version,
        developer_revision: context.developer_revision,
        device_revision: context.device_revision,
        project_revision: context.project_revision,
        candidates: held.members.clone(),
    })?;
    transaction.execute(
        "INSERT INTO recommendation_trace(stable_id,version,proposal_id,snapshot,body,created_at) VALUES (?,'1.0',?,?,?,?)",
        params![id, held.proposal_id, held.snapshot, text(&trace)?, at],
    ).map_err(database)?;
    transaction.execute(
        "INSERT INTO selected_version(project_id,harness_id,stable_id,version,state,selected_at) VALUES (?,?,?,'1.0','pending_install',?) ON CONFLICT(project_id,harness_id) DO UPDATE SET stable_id=excluded.stable_id,version=excluded.version,state=excluded.state,selected_at=excluded.selected_at",
        params![held.project_id, held.harness_id, id, at],
    ).map_err(database)?;
    transaction
        .execute(
            "UPDATE proposal SET confirmed_stable_id=?,confirmed_version='1.0' WHERE proposal_id=?",
            params![id, held.proposal_id],
        )
        .map_err(database)?;
    Ok(Confirmation {
        passport,
        created: true,
        state: "pending_install",
    })
}
