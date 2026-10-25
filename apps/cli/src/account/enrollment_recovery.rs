//! Reviewed replacement of one revoked enrollment without rotating local identity.

use std::{collections::BTreeSet, path::Path};

use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    Session, State, connections,
    journal::Journal,
    model::{Outcome, Receipt},
};
use crate::{
    canonical, digest,
    error::{Failure, Result},
    files::{self, OwnedDirectory},
    identity::{self, credentials::Vault},
    passport,
    store::{ENROLLMENT_RECOVERY_SCHEMA, PROFILE_SCHEMA, Store, database},
};

const KIND: &str = "account.connection.recover";
const LIMIT: usize = 131072;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct MissingKeyEvidence {
    pub session_receipt_digest: String,
    pub observed_at: String,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub previous: connections::Enrollment,
    pub account_id: String,
    pub session_revision: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub revoked_receipt_digest: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub missing_key: Option<MissingKeyEvidence>,
    pub authorized_receipt_digest: String,
    pub registry_schema_before: u32,
    pub replacement: connections::Plan,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Record {
    plan: Plan,
    plan_digest: String,
}

struct Held {
    record: Record,
    confirmation: Option<Receipt>,
}

fn invalid() -> Failure {
    Failure::precondition(
        "the reviewed enrollment recovery or its original account evidence changed",
    )
}

fn hash(value: &str) -> bool {
    value.strip_prefix("sha256:").is_some_and(|v| {
        v.len() == 64
            && v.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}

fn receipt_digest(receipt: &Receipt) -> Result<String> {
    receipt.validate()?;
    digest::canonical(
        "ai-stp:plan:v1",
        &serde_json::to_value(receipt).map_err(|_| invalid())?,
    )
}

impl Plan {
    fn validate(&self) -> Result<()> {
        self.previous.validate()?;
        self.replacement.validate()?;
        let proof_matches = match (
            self.schema_version,
            &self.revoked_receipt_digest,
            &self.missing_key,
        ) {
            (1, Some(receipt), None) => hash(receipt),
            (2, None, Some(missing)) => {
                hash(&missing.session_receipt_digest) && missing.observed_at == self.created_at
            }
            _ => false,
        };
        if !proof_matches
            || self.action != KIND
            || !passport::stable_id(&self.operation_id, "operation")
            || self.operation_id == self.replacement.operation_id
            || self.replacement.recovery_operation_id.as_deref() != Some(self.operation_id.as_str())
            || !passport::stable_id(&self.account_id, "account")
            || !passport::stable_id(&self.session_revision, "operation")
            || self.expires_at != crate::authoring::expiry(&self.created_at)?
            || self.created_at != self.replacement.created_at
            || self.expires_at != self.replacement.expires_at
            || !hash(&self.authorized_receipt_digest)
            || ![PROFILE_SCHEMA, ENROLLMENT_RECOVERY_SCHEMA].contains(&self.registry_schema_before)
            || self.replacement.registry_schema_before != ENROLLMENT_RECOVERY_SCHEMA
            || self.replacement.registry_schema_after != ENROLLMENT_RECOVERY_SCHEMA
            || self.previous.connection_id == self.replacement.connection_id
            || self.previous.device_id == self.replacement.device_id
            || self.previous.origin != self.replacement.origin
            || self.previous.provider != self.replacement.provider
            || self.previous.credential_store != self.replacement.credential_store
        {
            return Err(invalid());
        }
        Ok(())
    }

    pub fn digest(&self) -> Result<String> {
        self.validate()?;
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

fn evidence(
    journal: &Journal,
    state: &State,
    missing_key: bool,
) -> Result<(String, String, String)> {
    let admissible = if missing_key {
        matches!(&state.session, Session::Authorized { .. })
    } else {
        matches!(&state.session,Session::Closed{reason} if reason=="device_revoked")
            && state.outcome == Outcome::Revoked
    };
    if !admissible || state.plan.connection.is_none() {
        return Err(Failure::precondition(
            "recovery requires retained revocation evidence or an authorized session with a missing enrollment key",
        ));
    }
    let current = state.receipt()?;
    let observed = receipt_digest(&current)?;
    if missing_key && state.outcome == Outcome::Authorized {
        return Ok((
            current.account_id.ok_or_else(invalid)?,
            observed.clone(),
            observed,
        ));
    }
    let mut next = state.plan.expected_revision.clone();
    let mut seen = BTreeSet::new();
    let mut before = state.plan.created_at.clone();
    while let Some(id) = next {
        if seen.len() >= 4096 || !seen.insert(id.clone()) {
            return Err(invalid());
        }
        let receipt = journal.receipt_id(&id)?.ok_or_else(invalid)?;
        if receipt.plan.connection != state.plan.connection
            || receipt.plan.root != state.plan.root
            || receipt.plan.root_identity != state.plan.root_identity
            || receipt.plan.credential_store != state.plan.credential_store
            || receipt.plan.origin != state.plan.origin
            || receipt.completed_at > before
        {
            return Err(invalid());
        }
        if receipt.outcome == Outcome::Authorized {
            let account = receipt.account_id.clone().ok_or_else(invalid)?;
            if matches!(&state.session,Session::Authorized{account_id,..} if account_id!=&account) {
                return Err(invalid());
            }
            return Ok((account, observed, receipt_digest(&receipt)?));
        }
        next = receipt.plan.expected_revision;
        before = receipt.plan.created_at;
    }
    Err(invalid())
}

fn find(connection: &Connection, id: &str, previous: bool) -> Result<Option<String>> {
    connection.query_row(if previous {
        "SELECT operation_id FROM native_enrollment_recovery WHERE previous_connection_id=?"
    } else {
        "SELECT operation_id FROM native_enrollment_recovery WHERE replacement_connection_id=?"
    },[id],|row|row.get(0)).optional().map_err(database)
}

fn check_confirmation(plan: &Plan, child: &connections::Record, receipt: &Receipt) -> Result<()> {
    receipt.validate()?;
    let connection = receipt.plan.connection.as_ref().ok_or_else(invalid)?;
    if receipt.outcome != Outcome::Authorized
        || !matches!(
            receipt.plan.action,
            super::Action::Poll | super::Action::Refresh
        )
        || receipt.account_id.as_deref() != Some(plan.account_id.as_str())
        || receipt.completed_at < plan.created_at
        || receipt.plan.root != plan.replacement.root
        || receipt.plan.root_identity != plan.replacement.root_identity
        || receipt.plan.identity.account_id != plan.replacement.local_identity.account_id
        || connection.connection_id != plan.replacement.connection_id
        || connection.device_id != plan.replacement.device_id
        || child.public_key.as_deref() != Some(connection.public_key.as_str())
        || connection.origin != plan.previous.origin
        || connection.provider != plan.previous.provider
        || connection.credential_namespace != plan.previous.credential_namespace
        || connection.credential_store != plan.previous.credential_store
        || receipt.plan.expected_account_id.as_deref() != Some(plan.account_id.as_str())
        || receipt.plan.revoked_public_key.as_deref() != Some(plan.previous.public_key.as_str())
    {
        return Err(invalid());
    }
    Ok(())
}

fn load(connection: &Connection, id: &str) -> Result<Held> {
    let (previous,replacement,detail,confirmation):(String,String,String,Option<String>)=connection.query_row(
        "SELECT previous_connection_id,replacement_connection_id,detail,confirmation FROM native_enrollment_recovery WHERE operation_id=?",
        [id],|row|Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?))).map_err(database)?;
    if detail.len() > LIMIT
        || confirmation
            .as_ref()
            .is_some_and(|value| value.len() > 65536)
    {
        return Err(invalid());
    }
    let record: Record =
        serde_json::from_value(canonical::parse(detail.as_bytes())?).map_err(|_| invalid())?;
    let plan = &record.plan;
    if plan.digest()? != record.plan_digest
        || plan.operation_id != id
        || plan.previous.connection_id != previous
        || plan.replacement.connection_id != replacement
    {
        return Err(invalid());
    }
    let old = connections::record(connection, &previous)?.ok_or_else(invalid)?;
    let child = connections::record(connection, &replacement)?.ok_or_else(invalid)?;
    if child.plan != plan.replacement
        || child.credential_namespace != plan.previous.credential_namespace
        || old.public_key.as_deref() != Some(plan.previous.public_key.as_str())
        || old.plan.device_id != plan.previous.device_id
        || old.plan.origin != plan.previous.origin
        || old.plan.provider != plan.previous.provider
        || old.plan.credential_store != plan.previous.credential_store
        || old.credential_namespace != plan.previous.credential_namespace
        || old.plan.root != child.plan.root
        || old.plan.root_identity != child.plan.root_identity
        || old.plan.local_identity.account_id != child.plan.local_identity.account_id
    {
        return Err(invalid());
    }
    let confirmation: Option<Receipt> = confirmation
        .map(|value| {
            serde_json::from_value(canonical::parse(value.as_bytes())?).map_err(|_| invalid())
        })
        .transpose()?;
    if let Some(receipt) = &confirmation {
        check_confirmation(plan, &child, receipt)?;
    }
    let (kind,state,started,finished,admitted):(String,String,String,Option<String>,String)=connection.query_row(
        "SELECT kind,state,started_at,finished_at,coalesce(detail,'') FROM operation WHERE operation_id=?",
        [id],|row|Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?,row.get(4)?))).map_err(database)?;
    if kind != KIND
        || admitted != detail
        || !passport::timestamp(&started)
        || started < plan.created_at
        || state
            != if confirmation.is_some() {
                "verified"
            } else {
                "applying"
            }
        || finished.as_deref() != confirmation.as_ref().map(|r| r.completed_at.as_str())
    {
        return Err(invalid());
    }
    Ok(Held {
        record,
        confirmation,
    })
}

fn pending_delivery(connection: &Connection, enrollment: &connections::Enrollment) -> Result<()> {
    if crate::publication::interruption::pending_enrollment(connection, &enrollment.connection_id)?
        || crate::sync::interruption::pending_enrollment(connection, &enrollment.connection_id)?
    {
        return Err(Failure::precondition(
            "the original enrollment has an unfinished publication or sync; its exact remote outcome must be reconciled before this recovery",
        ));
    }
    Ok(())
}

pub fn plan(root: &Path, connection: &str, label: &str, at: &str) -> Result<Plan> {
    let id = super::identity_at(root)?;
    let previous = connections::enrollment(&id, connection)?;
    let journal = Journal::for_connection(&id, Some(&previous), false)?.ok_or_else(invalid)?;
    if journal.pending()?.is_some() {
        return Err(Failure::precondition(
            "resume the original account operation before planning enrollment recovery",
        ));
    }
    let state = journal.state()?.ok_or_else(invalid)?;
    super::check_binding(&id, &state.plan)?;
    super::check_enrollment_constraints(&id, &state.plan)?;
    if at < state.completed_at.as_str() {
        return Err(invalid());
    }
    let missing_key = if matches!(&state.session, Session::Authorized { .. }) {
        if previous.key_present(&id)? {
            return Err(Failure::precondition(
                "the enrollment key is present; retain positive server revocation evidence before replacing it",
            ));
        }
        true
    } else {
        false
    };
    let (account_id, observed_receipt_digest, authorized_receipt_digest) =
        evidence(&journal, &state, missing_key)?;
    let mut replacement = connections::plan(root, label, &previous.origin, &previous.provider, at)?;
    let store = Store::planning_at(id.root_directory())?;
    if store.version()? == ENROLLMENT_RECOVERY_SCHEMA
        && find(&store.connection, connection, true)?.is_some()
    {
        return Err(Failure::precondition(
            "resume the retained enrollment recovery instead of planning another replacement",
        ));
    }
    pending_delivery(&store.connection, &previous)?;
    let registry_schema_before = store.version()?;
    let operation_id = format!("operation_{}", ulid::Ulid::generate());
    replacement.registry_schema_before = ENROLLMENT_RECOVERY_SCHEMA;
    replacement.registry_schema_after = ENROLLMENT_RECOVERY_SCHEMA;
    replacement.recovery_operation_id = Some(operation_id.clone());
    let plan = Plan {
        schema_version: if missing_key { 2 } else { 1 },
        action: KIND.into(),
        operation_id,
        created_at: at.into(),
        expires_at: crate::authoring::expiry(at)?,
        previous,
        account_id,
        session_revision: state.revision,
        revoked_receipt_digest: if missing_key {
            None
        } else {
            Some(observed_receipt_digest.clone())
        },
        missing_key: if missing_key {
            Some(MissingKeyEvidence {
                session_receipt_digest: observed_receipt_digest,
                observed_at: at.into(),
            })
        } else {
            None
        },
        authorized_receipt_digest,
        registry_schema_before,
        replacement,
    };
    plan.validate()?;
    id.revalidate()?;
    Ok(plan)
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let value = canonical::parse(&files::read(path, LIMIT as u64)?)?;
    let plan: Plan = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    if plan.digest()? != digest::canonical("ai-stp:plan:v1", &value)? {
        return Err(invalid());
    }
    Ok(plan)
}

fn public(connection: &Connection, held: &Held) -> Result<Value> {
    let plan = &held.record.plan;
    let child =
        connections::record(connection, &plan.replacement.connection_id)?.ok_or_else(invalid)?;
    let mut value = json!({"schema_version":1,"plan":plan,"plan_digest":held.record.plan_digest,
        "state":if held.confirmation.is_some(){"authorized"}else if child.public_key.is_some(){"sign_in_required"}else{"creating_key"},
        "previous_connection_id":plan.previous.connection_id,"replacement_connection_id":plan.replacement.connection_id,
        "account_id":plan.account_id,"confirmation":held.confirmation.as_ref().map(Receipt::public),
        "local_identity_changed":false,"contexts_retargeted":false,"online_verified":false});
    if plan.missing_key.is_some() {
        value["preparation_reason"] = "missing_enrollment_key".into();
        value["server_preconditions"] =
            json!(["same_account", "revoked_previous_key", "distinct_new_key"]);
    }
    Ok(value)
}

pub fn apply(plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    plan.validate()?;
    if plan.digest()? != expected || !passport::timestamp(at) || at < plan.created_at.as_str() {
        return Err(invalid());
    }
    let id = plan.replacement.bind()?;
    plan.previous.check_record(&id)?;
    // Drain original account users before the credential/registry locks. Keep
    // that journal, its key and all public receipts for exact historical replay.
    let journal = Journal::for_connection(&id, Some(&plan.previous), false)?.ok_or_else(invalid)?;
    if journal.pending()?.is_some() {
        return Err(invalid());
    }
    let state = journal.state()?.ok_or_else(invalid)?;
    let proof = evidence(&journal, &state, plan.missing_key.is_some())?;
    let observed = plan
        .revoked_receipt_digest
        .as_ref()
        .or_else(|| plan.missing_key.as_ref().map(|e| &e.session_receipt_digest))
        .ok_or_else(invalid)?;
    if state.revision != plan.session_revision
        || plan.created_at < state.completed_at
        || proof
            != (
                plan.account_id.clone(),
                observed.clone(),
                plan.authorized_receipt_digest.clone(),
            )
    {
        return Err(invalid());
    }
    {
        let directory = OwnedDirectory::open_at(
            id.root_directory(),
            connections::NAMESPACE,
            connections::OWNER,
            false,
        )?
        .ok_or_else(invalid)?;
        if identity::physical_root(&directory.directory)? != plan.previous.credential_namespace {
            return Err(invalid());
        }
        let vault = Vault::new(&directory, plan.previous.credential_store)?;
        let mut store = Store::open_at(id.root_directory(), false)?;
        let held = if store.version()? == ENROLLMENT_RECOVERY_SCHEMA {
            find(&store.connection, &plan.previous.connection_id, true)?
                .map(|id| load(&store.connection, &id))
                .transpose()?
        } else {
            None
        };
        if let Some(held) = held {
            if held.record.plan != *plan || held.record.plan_digest != expected {
                return Err(invalid());
            }
        } else {
            if at >= plan.expires_at.as_str() {
                return Err(Failure::precondition(
                    "the enrollment recovery plan expired before admission",
                ));
            }
            if store.version()? != plan.registry_schema_before {
                return Err(invalid());
            }
            if plan.missing_key.is_some() && vault.read_key(&plan.previous.device_id)?.is_some() {
                return Err(Failure::precondition(
                    "the original enrollment key is present again; review a new recovery plan",
                ));
            }
            if vault.read_key(&plan.replacement.device_id)?.is_some() {
                return Err(Failure::precondition(
                    "the replacement credential slot is already owned",
                ));
            }
            pending_delivery(&store.connection, &plan.previous)?;
            let record = Record {
                plan: plan.clone(),
                plan_digest: expected.into(),
            };
            let detail = String::from_utf8(canonical::bytes(
                &serde_json::to_value(record).map_err(|_| invalid())?,
            )?)
            .map_err(|_| invalid())?;
            if detail.len() > LIMIT {
                return Err(invalid());
            }
            // Older clients waiting for this journal must refuse its new owner
            // marker, even if they loaded the old schema before taking its lock.
            journal.fence_enrollment()?;
            store.enrollment_recovery_transaction(|tx| {
                connections::admit(tx,&plan.replacement,&plan.replacement.digest()?,&plan.previous.credential_namespace,at)?;
                tx.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?1,?2,'applying',?3,?4)",params![plan.operation_id,KIND,at,detail]).map_err(database)?;
                tx.execute("INSERT INTO native_enrollment_recovery(operation_id,previous_connection_id,replacement_connection_id,detail) VALUES (?1,?2,?3,?4)",params![plan.operation_id,plan.previous.connection_id,plan.replacement.connection_id,detail]).map_err(database)?;
                Ok(())
            })?;
        }
    }
    // The child apply owns its credential lock and resumes an admitted create
    // after expiry. Never hold that lock across this call.
    connections::apply(&plan.replacement, &plan.replacement.digest()?, at)?;
    let store = Store::planning_at(id.root_directory())?;
    let result = public(
        &store.connection,
        &load(&store.connection, &plan.operation_id)?,
    )?;
    id.revalidate()?;
    Ok(result)
}

pub(super) fn constraints(
    id: &identity::Identity,
    connection: &connections::Enrollment,
) -> Result<Option<(String, String)>> {
    let store = Store::planning_at(id.root_directory())?;
    if store.version()? != ENROLLMENT_RECOVERY_SCHEMA {
        return Ok(None);
    }
    find(&store.connection, &connection.connection_id, false)?
        .map(|operation| {
            let held = load(&store.connection, &operation)?;
            Ok((
                held.record.plan.account_id,
                held.record.plan.previous.public_key,
            ))
        })
        .transpose()
}

pub(super) fn check_child(id: &identity::Identity, child: &connections::Plan) -> Result<()> {
    let Some(operation) = &child.recovery_operation_id else {
        return Ok(());
    };
    let store = Store::planning_at(id.root_directory())?;
    if store.version()? != ENROLLMENT_RECOVERY_SCHEMA {
        return Err(Failure::precondition(
            "apply the reviewed parent enrollment recovery before its child key operation",
        ));
    }
    if load(&store.connection, operation)?.record.plan.replacement != *child {
        return Err(invalid());
    }
    Ok(())
}

pub(super) fn fresh(id: &identity::Identity, connection: &connections::Enrollment) -> Result<()> {
    let store = Store::planning_at(id.root_directory())?;
    if store.version()? == ENROLLMENT_RECOVERY_SCHEMA
        && find(&store.connection, &connection.connection_id, true)?.is_some()
    {
        return Err(Failure::precondition(
            "this enrollment is retired by an admitted recovery; use its explicit replacement connection for new requests",
        ));
    }
    Ok(())
}

pub(super) fn confirm(id: &identity::Identity, receipt: &Receipt) -> Result<()> {
    let Some(connection) = &receipt.plan.connection else {
        return Ok(());
    };
    if receipt.outcome != Outcome::Authorized {
        return Ok(());
    }
    let mut store = Store::open_at(id.root_directory(), false)?;
    if store.version()? != ENROLLMENT_RECOVERY_SCHEMA {
        return Ok(());
    }
    let Some(operation) = find(&store.connection, &connection.connection_id, false)? else {
        return Ok(());
    };
    let held = load(&store.connection, &operation)?;
    let child =
        connections::record(&store.connection, &connection.connection_id)?.ok_or_else(invalid)?;
    check_confirmation(&held.record.plan, &child, receipt)?;
    if held.confirmation.is_some() {
        return Ok(());
    }
    let detail = String::from_utf8(canonical::bytes(
        &serde_json::to_value(receipt).map_err(|_| invalid())?,
    )?)
    .map_err(|_| invalid())?;
    if detail.len() > 65536 {
        return Err(invalid());
    }
    store.transaction(|tx| {
        tx.execute("UPDATE native_enrollment_recovery SET confirmation=?1 WHERE operation_id=?2 AND confirmation IS NULL",params![detail,operation]).map_err(database)?;
        tx.execute("UPDATE operation SET state='verified',finished_at=?1 WHERE operation_id=?2 AND kind=?3",params![receipt.completed_at,operation,KIND]).map_err(database)?;
        Ok(())
    })
}

pub fn list(root: &Path) -> Result<Value> {
    let id = super::identity_at(root)?;
    let store = Store::planning_at(id.root_directory())?;
    let mut recoveries = Vec::new();
    if store.version()? == ENROLLMENT_RECOVERY_SCHEMA {
        let mut statement=store.connection.prepare("SELECT operation_id FROM native_enrollment_recovery ORDER BY operation_id LIMIT 65").map_err(database)?;
        let ids = statement
            .query_map([], |row| row.get::<_, String>(0))
            .map_err(database)?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(database)?;
        if ids.len() > 64 {
            return Err(invalid());
        }
        for operation in ids {
            let held = load(&store.connection, &operation)?;
            held.record.plan.replacement.belongs(&id)?;
            recoveries.push(public(&store.connection, &held)?);
        }
    }
    id.revalidate()?;
    Ok(json!({"schema_version":1,"recoveries":recoveries,"online_verified":false}))
}
