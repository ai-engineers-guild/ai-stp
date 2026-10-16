//! Bounded graph inspection and deterministic, owner-confirmed developer merges.

use std::collections::{BTreeMap, BTreeSet, VecDeque};

use rusqlite::{OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::{
    authoring::{Identity, expiry},
    digest,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
    store::{Store, database, journal, revisions},
};

const MAX_GRAPH: usize = 16_384;
const ACTION: &str = "sync.merge";

fn invalid() -> Failure {
    Failure::input("the private revision merge plan or graph is invalid")
}

struct Graph {
    heads: Vec<String>,
    documents: Vec<Value>,
    base: Option<Value>,
    forward: Option<usize>,
}

fn distances(t: &Transaction<'_>, id: &str, start: &str) -> Result<BTreeMap<String, usize>> {
    let mut seen = BTreeMap::new();
    let mut pending = VecDeque::from([(start.to_owned(), 0)]);
    while let Some((revision, distance)) = pending.pop_front() {
        if seen.contains_key(&revision) {
            continue;
        }
        if seen.len() >= MAX_GRAPH {
            return Err(Failure::precondition(
                "the revision graph exceeds the bounded merge walk",
            ));
        }
        let document = Objects { connection: t }.revision(&revision)?;
        if document["stable_id"] != id {
            return Err(invalid());
        }
        for parent in document["parent_revision_ids"]
            .as_array()
            .ok_or_else(invalid)?
        {
            pending.push_back((parent.as_str().ok_or_else(invalid)?.into(), distance + 1));
        }
        seen.insert(revision, distance);
    }
    Ok(seen)
}

fn graph(t: &Transaction<'_>, id: &str) -> Result<Graph> {
    if !["developer", "component", "setup"]
        .iter()
        .any(|kind| passport::stable_id(id, kind))
    {
        return Err(invalid());
    }
    let objects = Objects { connection: t };
    objects.require_active(id)?;
    let heads = revisions::heads(t, id)?;
    if heads.is_empty() {
        return Err(Failure::new(
            ErrorKind::NotFound,
            "the object has no local revision heads",
        ));
    }
    if heads.len() > MAX_GRAPH {
        return Err(invalid());
    }
    // More than two heads need manual resolution. Validate them one at a time
    // without retaining every passport merely to return that decision.
    let mut documents = Vec::with_capacity(heads.len().min(2));
    for revision in &heads {
        let document = objects.revision(revision)?;
        if document["stable_id"] != id || document["visibility"] != "private" {
            return Err(Failure::precondition(
                "private synchronization requires private revision heads",
            ));
        }
        if heads.len() <= 2 {
            documents.push(document);
        }
    }
    let mut result = Graph {
        heads,
        documents,
        base: None,
        forward: None,
    };
    if result.heads.len() == 2 {
        let left = distances(t, id, &result.heads[0])?;
        let right = distances(t, id, &result.heads[1])?;
        result.forward = if left.contains_key(&result.heads[1]) {
            Some(0)
        } else if right.contains_key(&result.heads[0]) {
            Some(1)
        } else {
            None
        };
        let base = left
            .iter()
            .filter_map(|(revision, a)| {
                right.get(revision).map(|b| ((*a).max(*b), a + b, revision))
            })
            .min();
        result.base = base
            .map(|(_, _, revision)| objects.revision(revision))
            .transpose()?;
    }
    Ok(result)
}

fn body(mut document: Value) -> Result<Map<String, Value>> {
    let fields = document.as_object_mut().ok_or_else(invalid)?;
    fields.remove("revision_id");
    fields.remove("parent_revision_ids");
    Ok(std::mem::take(fields))
}

fn fields(
    base: &Map<String, Value>,
    left: &Map<String, Value>,
    right: &Map<String, Value>,
    path: &str,
    depth: usize,
    conflicts: &mut Vec<String>,
) -> Result<Map<String, Value>> {
    if depth > 64 {
        return Err(invalid());
    }
    let keys: BTreeSet<_> = base.keys().chain(left.keys()).chain(right.keys()).collect();
    let mut result = Map::new();
    for key in keys {
        let (before, a, b) = (base.get(key), left.get(key), right.get(key));
        let at = format!("{path}/{}", key.replace('~', "~0").replace('/', "~1"));
        let value = if a == b || b == before {
            a.cloned()
        } else if a == before {
            b.cloned()
        } else if let (Some(Value::Object(a)), Some(Value::Object(b))) = (a, b) {
            match before {
                None => Some(Value::Object(fields(
                    &Map::new(),
                    a,
                    b,
                    &at,
                    depth + 1,
                    conflicts,
                )?)),
                Some(Value::Object(before)) => Some(Value::Object(fields(
                    before,
                    a,
                    b,
                    &at,
                    depth + 1,
                    conflicts,
                )?)),
                _ => {
                    conflicts.push(at);
                    None
                }
            }
        } else {
            conflicts.push(at);
            None
        };
        if let Some(value) = value {
            result.insert(key.clone(), value);
        }
    }
    Ok(result)
}

fn candidate(graph: &Graph) -> Result<(Option<Value>, Vec<String>)> {
    let Some(base) = &graph.base else {
        return Ok((None, vec!["/".into()]));
    };
    if graph.documents.len() != 2 || graph.documents.iter().any(|v| v["kind"] != "developer") {
        return Ok((None, vec!["/".into()]));
    }
    let mut conflicts = Vec::new();
    let mut merged = fields(
        &body(base.clone())?,
        &body(graph.documents[0].clone())?,
        &body(graph.documents[1].clone())?,
        "",
        0,
        &mut conflicts,
    )?;
    if !conflicts.is_empty() {
        return Ok((None, conflicts));
    }
    merged.insert("parent_revision_ids".into(), json!(graph.heads));
    Ok((Some(revisions::seal(&Value::Object(merged))?), conflicts))
}

fn missing_remote(t: &Transaction<'_>, account: &str, id: &str) -> Result<Option<String>> {
    // Failed outbox attempts hold local retirement evidence, not server receipts.
    let receipt: Option<String> = t.query_row(
        "SELECT receipt_json FROM sync_event WHERE account_id=? AND entity_id=? AND direction='push' AND state IN ('accepted','conflict','rejected','superseded') AND receipt_json IS NOT NULL ORDER BY created_at DESC,rowid DESC LIMIT 1",
        [account, id], |row| row.get(0)).optional().map_err(database)?;
    let Some(receipt) = receipt else {
        return Ok(None);
    };
    let receipt = crate::wire::parse(receipt.as_bytes())?;
    static SCHEMA: crate::wire::Schema = crate::wire::Schema::new(include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/resources/schemas/v1/sync-event-receipt.schema.json"
    )));
    SCHEMA.validate(&receipt)?;
    let Some(remote) = receipt["server_head_revision_id"].as_str() else {
        return Ok(None);
    };
    let known: bool = t
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM sync_event WHERE account_id=? AND remote_revision_id=?)",
            [account, remote],
            |row| row.get(0),
        )
        .map_err(database)?;
    Ok((!known).then(|| remote.to_owned()))
}

/// Values never leave the private registry in a conflict report.
pub fn preview(store: &mut Store, id: &str, account: &str) -> Result<Value> {
    if !passport::stable_id(account, "account") {
        return Err(invalid());
    }
    store.transaction(|t| {
        let graph = graph(t, id)?;
        let mut report = json!({"schema_version":1,"stable_id":id,"head_revision_ids":graph.heads,
            "state":"manual_resolution","common_ancestor_revision_id":null,
            "candidate_revision_id":null,"server_head_revision_id":null,"affected_fields":["/"]});
        if graph.heads.len() == 1 {
            let remote = missing_remote(t, account, id)?;
            report["state"] = if remote.is_some() {
                "conflict"
            } else {
                "up_to_date"
            }
            .into();
            if remote.is_none() {
                report["common_ancestor_revision_id"] = graph.heads[0].clone().into();
                report["candidate_revision_id"] = graph.heads[0].clone().into();
            }
            report["server_head_revision_id"] = json!(remote);
            report["affected_fields"] = json!([]);
        } else if graph.heads.len() == 2 {
            report["common_ancestor_revision_id"] = graph
                .base
                .as_ref()
                .map_or(Value::Null, |v| v["revision_id"].clone());
            if let Some(index) = graph.forward {
                report["state"] = "fast_forward".into();
                report["candidate_revision_id"] = graph.heads[index].clone().into();
                report["affected_fields"] = json!([]);
            } else if graph.base.is_none() {
                report["state"] = "conflict".into();
            } else if graph.documents.iter().all(|v| v["kind"] == "developer") {
                let (merged, conflicts) = candidate(&graph)?;
                report["state"] = if merged.is_some() {
                    "merge_ready"
                } else {
                    "conflict"
                }
                .into();
                report["candidate_revision_id"] =
                    merged.map_or(Value::Null, |v| v["revision_id"].clone());
                report["affected_fields"] = json!(conflicts);
            }
        }
        Ok(report)
    })
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub identity: Identity,
    pub stable_id: String,
    pub expected_heads: Vec<String>,
    pub passport: Value,
    pub created_at: String,
    pub expires_at: String,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

fn owned_candidate(graph: &Graph, identity: &Identity) -> Result<Value> {
    if graph.documents.len() != 2
        || graph
            .documents
            .iter()
            .any(|v| v["kind"] != "developer" || v["owner_id"] != identity.account_id)
    {
        return Err(Failure::precondition(
            "a mechanical merge requires two owned developer heads",
        ));
    }
    let (candidate, conflicts) = candidate(graph)?;
    candidate.ok_or_else(|| {
        Failure::new(
            ErrorKind::Conflict,
            "the developer heads need explicit field resolution",
        )
        .with_details([("fields".into(), json!(conflicts))])
    })
}

pub fn plan(store: &mut Store, id: &str, identity: Identity, at: &str) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    store.transaction(|t| {
        let graph = graph(t, id)?;
        let document = owned_candidate(&graph, &identity)?;
        Ok(Plan {
            schema_version: 1,
            action: ACTION.into(),
            operation_id: format!("operation_{}", ulid::Ulid::generate()),
            identity,
            stable_id: id.into(),
            expected_heads: graph.heads,
            passport: document,
            created_at: at.into(),
            expires_at,
        })
    })
}

pub fn apply(
    store: &mut Store,
    plan: &Plan,
    expected: &str,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    identity.validate()?;
    if plan.schema_version != 1
        || plan.action != ACTION
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected
    {
        return Err(invalid());
    }
    store.transaction(|t| {
        if let Some(state) = journal::state(t, &plan.operation_id, ACTION, expected)? {
            if state != "verified" { return Err(invalid()); }
            let held = Objects { connection:t }.revision(plan.passport["revision_id"].as_str().ok_or_else(invalid)?)?;
            if held != plan.passport { return Err(invalid()); }
            return Ok(held);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
            return Err(Failure::precondition("the merge plan expired before applying"));
        }
        let graph = graph(t, &plan.stable_id)?;
        if graph.heads != plan.expected_heads {
            return Err(Failure::new(ErrorKind::Conflict,"the revision heads changed after merge planning"));
        }
        let document = owned_candidate(&graph, identity)?;
        if document != plan.passport { return Err(invalid()); }
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,ACTION,at,at,expected]).map_err(database)?;
        revisions::commit(t, &document, &identity.device_id, Some(&plan.operation_id),
            revisions::Write::Advance { expected_heads:&plan.expected_heads })
    })
}
