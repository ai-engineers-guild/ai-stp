//! One explicit transfer, committed with its immutable access inventory. Device
//! initialization and credentials remain separate, unchanged records.

use std::collections::{BTreeMap, BTreeSet};

use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    Action, Plan, Session,
    journal::Journal,
    transport::{Api, Reply},
};
use crate::{
    authoring::Identity,
    canonical, digest,
    error::{Failure, Result},
    identity,
    objects::Objects,
    passport,
    store::{
        Store, database,
        revisions::{self, Write},
    },
};

const KIND: &str = "account.attach";
const MAX_BYTES: usize = 4 * 1024 * 1024;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Version {
    pub stable_id: String,
    pub version: String,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Selection {
    pub account_id: String,
    pub heads: BTreeMap<String, String>,
    /// Exact passport digests, never an alias for an owner's future objects.
    pub versions: BTreeMap<String, Version>,
}

fn invalid() -> Failure {
    Failure::precondition(
        "attachment requires one verified account, the original device and unchanged local ownership",
    )
}

fn hash(value: &str, prefix: &str) -> bool {
    value.strip_prefix(prefix).is_some_and(|v| {
        v.len() == 64
            && v.bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    })
}

impl Selection {
    pub(super) fn validate(&self, identity: &Identity) -> Result<()> {
        if !passport::stable_id(&self.account_id, "account")
            || self.account_id == identity.account_id
            || self.heads.len() > 4096
            || self.versions.len() > 8192
        {
            return Err(invalid());
        }
        for (id, revision) in &self.heads {
            if !["component", "setup", "project", "developer", "device"]
                .iter()
                .any(|k| passport::stable_id(id, k))
                || !hash(revision, "revision_")
            {
                return Err(invalid());
            }
        }
        for (address, version) in &self.versions {
            if !hash(address, "sha256:")
                || !self.heads.contains_key(&version.stable_id)
                || !passport::version_number(&version.version)
            {
                return Err(invalid());
            }
        }
        Ok(())
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    plan: Plan,
    completed_at: String,
}

impl Receipt {
    fn public(&self) -> Result<Value> {
        let selection = self.plan.attachment.as_ref().ok_or_else(invalid)?;
        Ok(
            json!({"schema_version":1,"operation_id":self.plan.operation_id,
            "action":"attach","outcome":"attached","plan_digest":self.plan.digest()?,
            "account_id":selection.account_id,"device_id":self.plan.identity.device_id,
            "owner_attached":true,"completed_at":self.completed_at,
            "transferred_heads":selection.heads.len(),"retained_versions":selection.versions.len()}),
        )
    }
}

fn receipt(connection: &Connection) -> Result<Option<Receipt>> {
    let mut query = connection.prepare(
        "SELECT o.operation_id,o.state,o.detail,o.finished_at,CASE WHEN length(CAST(e.evidence AS BLOB))<=4194304 THEN e.evidence ELSE NULL END FROM operation o LEFT JOIN operation_event e ON e.operation_id=o.operation_id AND e.sequence=1 WHERE o.kind='account.attach' LIMIT 2"
    ).map_err(database)?;
    let mut rows = query.query([]).map_err(database)?;
    let Some(row) = rows.next().map_err(database)? else {
        return Ok(None);
    };
    let (id, state, hash, at, body): (String, String, String, String, String) = (
        row.get(0).map_err(database)?,
        row.get(1).map_err(database)?,
        row.get(2).map_err(database)?,
        row.get(3).map_err(database)?,
        row.get(4).map_err(database)?,
    );
    if body.len() > MAX_BYTES || rows.next().map_err(database)?.is_some() {
        return Err(invalid());
    }
    let held: Receipt =
        serde_json::from_value(canonical::parse(body.as_bytes())?).map_err(|_| invalid())?;
    held.plan.validate()?;
    if held.plan.action != Action::Attach
        || held.plan.operation_id != id
        || held.plan.digest()? != hash
        || state != "verified"
        || held.completed_at != at
        || !passport::timestamp(&at)
    {
        return Err(invalid());
    }
    Ok(Some(held))
}

pub(crate) fn effective(connection: &Connection, device: &identity::Identity) -> Result<Identity> {
    let original = device.context();
    let Some(held) = receipt(connection)? else {
        return Ok(original);
    };
    if !device.knows_original(&held.plan.identity) {
        return Err(invalid());
    }
    Ok(Identity {
        account_id: held.plan.attachment.ok_or_else(invalid)?.account_id,
        device_id: original.device_id,
    })
}

pub(super) fn owner_binding(connection: &Connection) -> Result<Option<(Identity, String)>> {
    receipt(connection)?
        .map(|held| {
            Ok((
                held.plan.identity,
                held.plan.attachment.ok_or_else(invalid)?.account_id,
            ))
        })
        .transpose()
}

/// The transfer's server is part of ownership, including after native recovery.
pub(crate) fn owner_origin(
    connection: &Connection,
    device: &identity::Identity,
) -> Result<Option<String>> {
    receipt(connection)?
        .map(|held| {
            if !device.knows_original(&held.plan.identity) {
                return Err(invalid());
            }
            Ok(held.plan.origin)
        })
        .transpose()
}

pub(crate) fn retained(connection: &Connection, owner: &str, document: &Value) -> Result<bool> {
    if document["owner_id"] == owner {
        return Ok(true);
    }
    let Some(held) = receipt(connection)? else {
        return Ok(false);
    };
    let selection = held.plan.attachment.ok_or_else(invalid)?;
    if selection.account_id != owner || document["owner_id"] != held.plan.identity.account_id {
        return Ok(false);
    }
    let hash = digest::canonical("ai-stp:passport:v1", document)?;
    Ok(selection.versions.get(&hash).is_some_and(|version| {
        document["stable_id"] == version.stable_id && document["version"] == version.version
    }))
}

/// Load once for a whole selection graph; each passport is still matched by
/// its content digest, including its original owner and immutable coordinate.
pub(crate) fn inherited(connection: &Connection, owner: &str) -> Result<BTreeSet<String>> {
    let Some(held) = receipt(connection)? else {
        return Ok(BTreeSet::new());
    };
    let selection = held.plan.attachment.ok_or_else(invalid)?;
    Ok(if selection.account_id == owner {
        selection.versions.into_keys().collect()
    } else {
        BTreeSet::new()
    })
}

pub(super) fn selection(
    connection: &Connection,
    original: &Identity,
    account: &str,
    at: &str,
) -> Result<Selection> {
    if receipt(connection)?.is_some() {
        return Err(Failure::precondition(
            "this registry already has an attached owner",
        ));
    }
    let unfinished: bool = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM operation WHERE finished_at IS NULL) OR EXISTS(SELECT 1 FROM proposal WHERE cancelled_at IS NULL AND confirmed_stable_id IS NULL AND expires_at>?) OR EXISTS(SELECT 1 FROM agent_task WHERE state IN ('planned','blocked','running'))",
        [at], |row| row.get(0)).map_err(database)?;
    if unfinished {
        return Err(Failure::precondition(
            "finish or cancel outstanding local operations, proposals and tasks before attachment",
        ));
    }
    let mut query = connection.prepare("SELECT h.stable_id,h.revision_id FROM head h ORDER BY h.stable_id,h.revision_id LIMIT 4097").map_err(database)?;
    let heads: Vec<(String, String)> = query
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))
        .map_err(database)?
        .collect::<std::result::Result<_, _>>()
        .map_err(database)?;
    if heads.len() > 4096 {
        return Err(invalid());
    }
    if heads.windows(2).any(|pair| pair[0].0 == pair[1].0) {
        return Err(Failure::precondition(
            "resolve revision head conflicts before attachment",
        ));
    }
    let objects = Objects { connection };
    let mut selection = Selection {
        account_id: account.into(),
        heads: BTreeMap::new(),
        versions: BTreeMap::new(),
    };
    for (id, revision) in &heads {
        let document = objects.revision(revision)?;
        if document["owner_id"] == account {
            return Err(Failure::precondition(
                "the destination account already owns objects in this registry",
            ));
        }
        if document["owner_id"] == original.account_id {
            selection.heads.insert(id.clone(), revision.clone());
        }
    }
    let mut query = connection.prepare("SELECT stable_id,version,passport_digest FROM object_version ORDER BY stable_id,major,minor LIMIT 8193").map_err(database)?;
    let rows: Vec<(String, String, String)> = query
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))
        .map_err(database)?
        .collect::<std::result::Result<_, _>>()
        .map_err(database)?;
    if rows.len() > 8192 {
        return Err(invalid());
    }
    for (id, version, hash) in rows {
        let document = objects.exact_version(&id, &version, Some(&hash))?;
        if document["owner_id"] == account {
            return Err(invalid());
        }
        if document["owner_id"] == original.account_id {
            selection.versions.insert(
                hash,
                Version {
                    stable_id: id,
                    version,
                },
            );
        }
    }
    selection.validate(original)?;
    Ok(selection)
}

pub(super) fn apply(plan: &Plan, identity: &identity::Identity, at: &str) -> Result<Value> {
    // Lock order is account, then registry. Authoring never acquires an account
    // lock. No credential replacement is part of this transaction.
    let journal = Journal::open(identity, false)?.ok_or_else(invalid)?;
    let mut store = Store::planning_at(identity.root_directory())?;
    if let Some(held) = receipt(&store.connection)? {
        if held.plan != *plan {
            return Err(invalid());
        }
        return held.public();
    }
    if journal.pending()?.is_some() {
        return Err(invalid());
    }
    let state = journal.state()?.ok_or_else(invalid)?;
    super::precondition(plan, Some(&state), at)?;
    if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        return Err(invalid());
    }
    let selected = plan.attachment.as_ref().ok_or_else(invalid)?;
    store.transaction(|t| {
        if selection(t, &plan.identity, &selected.account_id, at)? != *selected {
            return Err(invalid());
        }
        Ok(())
    })?;
    drop(store);
    let Session::Authorized { access_token, .. } = &state.session else {
        return Err(invalid());
    };
    let Reply::Resource(account) = Api::new(&plan.origin)?.me(access_token)? else {
        return Err(invalid());
    };
    if account.schema_version != 1
        || account.account_id != selected.account_id
        || account.device_id.as_deref() != Some(&plan.identity.device_id)
        || account.account_status != "active"
    {
        return Err(invalid());
    }
    super::check_binding(&super::bind(plan)?, plan)?;
    let completed_at = super::now_after(at);
    super::precondition(plan, Some(&state), &completed_at)?;
    if completed_at > plan.expires_at {
        return Err(invalid());
    }
    let mut store = Store::open_at(identity.root_directory(), true)?;
    store.transaction(|t| {
        if selection(t, &plan.identity, &selected.account_id, &completed_at)? != *selected {
            return Err(invalid());
        }
        Ok(())
    })?;
    // Old binaries cannot honor the new effective owner. Refuse them even if
    // the following SQLite transaction rolls back or the process is killed.
    store.fence_legacy_writers()?;
    commit(&mut store, plan, at, &completed_at)
}

pub(super) fn commit(
    store: &mut Store,
    plan: &Plan,
    at: &str,
    completed_at: &str,
) -> Result<Value> {
    let selected = plan.attachment.as_ref().ok_or_else(invalid)?;
    store.transaction(|t| {
        if selection(t, &plan.identity, &selected.account_id, completed_at)? != *selected { return Err(invalid()); }
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,KIND,at,completed_at,plan.digest()?]).map_err(database)?;
        for (id, revision) in &selected.heads {
            let mut document = Objects { connection:t }.revision(revision)?;
            if document["stable_id"] != *id || document["owner_id"] != plan.identity.account_id { return Err(invalid()); }
            document["owner_id"] = selected.account_id.clone().into();
            document["parent_revision_ids"] = json!([revision]);
            document["created_at"] = completed_at.into();
            revisions::commit(t, &document, &plan.identity.device_id, Some(&plan.operation_id),
                Write::Transfer { expected_heads:std::slice::from_ref(revision), previous_owner:&plan.identity.account_id })?;
        }
        let held = Receipt { plan:plan.clone(), completed_at:completed_at.into() };
        let body = canonical::bytes(&serde_json::to_value(&held).map_err(|_| invalid())?)?;
        if body.len() > MAX_BYTES { return Err(invalid()); }
        t.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,1,?,'planned','verified','attached',?)",
            params![plan.operation_id,completed_at,String::from_utf8(body).map_err(|_| invalid())?]).map_err(database)?;
        held.public()
    })
}
