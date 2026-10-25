//! A bounded parent-first walk over retained local content, never caller payloads.

use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

use super::{
    event::Event,
    ledger::{self, Pending, Scope},
    versions,
};
use crate::{
    authoring::Identity,
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
    store::database,
};

const MAX_REVISIONS: usize = 16384;
const MAX_CAPTURE: usize = 16 * 1024 * 1024;

fn invalid() -> Failure {
    Failure::precondition(
        "the private push does not match its retained local graph and account history",
    )
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Step {
    pub(super) local_revision: Option<String>,
    pub(super) local_parents: Vec<String>,
    pub(super) operation: String,
    pub(super) payload: Value,
    pub(super) created_at: String,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Capture {
    pub(super) entity_id: String,
    pub(super) entity_kind: String,
    pub(super) local_revision: String,
    pub(super) steps: Vec<Step>,
    pub(super) tombstone: Option<String>,
}

impl Capture {
    /// The native passport remains local; its permitted remote summary names
    /// the authenticated enrollment device, as required by the server contract.
    fn for_sender(mut self, sender: &Identity) -> Result<Self> {
        sender.validate()?;
        if self.entity_kind == "device_summary" {
            self.entity_id = sender.device_id.clone();
        }
        self.digest()?;
        Ok(self)
    }

    pub fn digest(&self) -> Result<String> {
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        if canonical::bytes(&value)?.len() > MAX_CAPTURE {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }
}

pub(super) fn capture_for_sender(
    connection: &Connection,
    native: &Identity,
    sender: &Identity,
    id: &str,
) -> Result<Capture> {
    let local_id = if id == sender.device_id {
        native.device_id.as_str()
    } else {
        id
    };
    capture(connection, native, local_id)?.for_sender(sender)
}

/// Query-only capture. Every outgoing payload is checked before the first POST.
pub fn capture(connection: &Connection, identity: &Identity, id: &str) -> Result<Capture> {
    identity.validate()?;
    let kind = if passport::stable_id(id, "developer") {
        "developer"
    } else if passport::stable_id(id, "component") {
        "component"
    } else if passport::stable_id(id, "setup") {
        "setup"
    } else if passport::stable_id(id, "device") {
        "device"
    } else {
        return super::summaries::consent(connection, identity, id);
    };
    let objects = Objects { connection };
    let head = objects.head(kind, id)?;
    if kind == "device" {
        return super::summaries::device(&head, identity);
    }
    let head_id = head["revision_id"].as_str().ok_or_else(invalid)?.to_owned();
    let tombstone: Option<String> = connection
        .query_row(
            "SELECT created_at FROM tombstone WHERE stable_id=?",
            [id],
            |r| r.get(0),
        )
        .optional()
        .map_err(database)?;
    if tombstone
        .as_deref()
        .is_some_and(|at| !passport::timestamp(at))
    {
        return Err(invalid());
    }
    let mut held = BTreeMap::new();
    let mut visiting = BTreeSet::new();
    let mut visited = BTreeSet::new();
    let mut stack = vec![(head_id.clone(), false)];
    let mut steps = Vec::new();
    let mut size = 0usize;
    while let Some((revision, expanded)) = stack.pop() {
        if visited.contains(&revision) {
            continue;
        }
        if !expanded {
            if !visiting.insert(revision.clone()) || visiting.len() + visited.len() > MAX_REVISIONS
            {
                return Err(invalid());
            }
            let document = objects.revision(&revision)?;
            if document["stable_id"] != id
                || document["kind"] != kind
                || document["visibility"] != "private"
            {
                return Err(invalid());
            }
            // Bound a deep chain while its ancestors are still held, before
            // post-order expansion can release any of those documents.
            size = size
                .checked_add(canonical::bytes(&document)?.len())
                .ok_or_else(invalid)?;
            if size > MAX_CAPTURE {
                return Err(invalid());
            }
            let parents = document["parent_revision_ids"]
                .as_array()
                .ok_or_else(invalid)?;
            stack.push((revision.clone(), true));
            for parent in parents.iter().rev() {
                stack.push((parent.as_str().ok_or_else(invalid)?.to_owned(), false));
            }
            held.insert(revision, document);
            continue;
        }
        let mut document = held.remove(&revision).ok_or_else(invalid)?;
        let parents = serde_json::from_value(document["parent_revision_ids"].clone())
            .map_err(|_| invalid())?;
        if matches!(kind, "component" | "setup") {
            document["sync_released_versions"] = if revision == head_id {
                serde_json::to_value(versions::outgoing(connection, id, kind)?)
                    .map_err(|_| invalid())?
            } else {
                json!([])
            };
            size = size
                .checked_add(canonical::bytes(&document["sync_released_versions"])?.len())
                .ok_or_else(invalid)?;
        }
        super::payload::check(&document)?;
        versions::bindings(&document, id, kind)?;
        if size > MAX_CAPTURE {
            return Err(invalid());
        }
        steps.push(Step {
            local_revision: Some(revision.clone()),
            local_parents: parents,
            operation: "upsert".into(),
            created_at: document["created_at"].as_str().ok_or_else(invalid)?.into(),
            payload: document,
        });
        visiting.remove(&revision);
        visited.insert(revision);
    }
    let result = Capture {
        entity_id: id.into(),
        entity_kind: match kind {
            "developer" => "developer_passport",
            "component" => "component_private",
            _ => "setup_private",
        }
        .into(),
        local_revision: head_id,
        steps,
        tombstone,
    };
    result.digest()?;
    Ok(result)
}

pub(super) struct Entry {
    pub event: Event,
    pub stored: Pending,
}

pub(super) struct History {
    entries: Vec<Entry>,
    local: BTreeMap<String, Vec<usize>>,
    pub head: Option<String>,
}

impl History {
    pub fn load(connection: &Connection, scope: &Scope, id: &str) -> Result<Self> {
        let rows = ledger::history(connection, scope, id)?;
        let head=connection.query_row("SELECT remote_revision_id FROM sync_remote_head WHERE account_id=? AND entity_id=?",
            params![scope.account(),id],|r|r.get(0)).optional().map_err(database)?;
        let mut result = Self {
            entries: Vec::new(),
            local: BTreeMap::new(),
            head,
        };
        for stored in rows {
            result.append(stored)?;
        }
        if result.head.as_ref().is_some_and(|head| {
            !result
                .entries
                .iter()
                .any(|r| &r.event.revision_id == head && r.stored.state == "accepted")
        }) {
            return Err(invalid());
        }
        if result
            .entries
            .iter()
            .filter(|r| r.stored.state == "pending")
            .count()
            > 1
        {
            return Err(invalid());
        }
        Ok(result)
    }

    fn append(&mut self, stored: Pending) -> Result<()> {
        let event: Event = serde_json::from_value(stored.request.clone()).map_err(|_| invalid())?;
        if let Some(id) = &stored.local_revision_id {
            self.local
                .entry(id.clone())
                .or_default()
                .push(self.entries.len());
        }
        self.entries.push(Entry { event, stored });
        Ok(())
    }

    pub fn update(&mut self, stored: Pending, head: Option<String>) -> Result<()> {
        self.head = head;
        let id = stored.request["event_id"].as_str().ok_or_else(invalid)?;
        if let Some(entry) = self.entries.iter_mut().find(|e| e.event.event_id == id) {
            entry.stored = stored;
        } else {
            self.append(stored)?;
        }
        Ok(())
    }

    pub fn pending(&self) -> Option<&Entry> {
        self.entries.iter().find(|e| e.stored.state == "pending")
    }

    fn usable(entry: &Entry) -> bool {
        entry.stored.state == "accepted"
            || (matches!(entry.stored.state.as_str(), "conflict" | "superseded")
                && entry
                    .stored
                    .receipt
                    .as_ref()
                    .is_some_and(|r| r["revision_id"] == entry.event.revision_id))
    }

    fn mapping(&self, local: &str, payload: Option<&Value>) -> Option<&Entry> {
        let indices = self.local.get(local)?;
        let choose = |only_head: bool| {
            indices.iter().rev().map(|i| &self.entries[*i]).find(|e| {
                Self::usable(e)
                    && payload.is_none_or(|v| *v == e.event.payload)
                    && (!only_head || self.head.as_deref() == Some(&e.event.revision_id))
            })
        };
        choose(true).or_else(|| choose(false))
    }

    pub fn known(&self, step: &Step, exact: bool) -> Option<&Entry> {
        if let Some(local) = &step.local_revision {
            self.mapping(local, exact.then_some(&step.payload))
        } else {
            self.entries.iter().rev().find(|e| {
                e.event.operation == step.operation
                    && e.event.payload == step.payload
                    && e.event.created_at == step.created_at
                    && Self::usable(e)
            })
        }
    }

    pub fn request(&self, capture: &Capture, step: &Step, identity: &Identity) -> Result<Value> {
        if let Some(pending) = self.pending() {
            return Ok(pending.stored.request.clone());
        }
        let parents = if let Some(local) = &step.local_revision {
            if let Some(previous) = self
                .mapping(local, None)
                .filter(|e| e.stored.state == "accepted")
            {
                vec![previous.event.revision_id.clone()]
            } else {
                step.local_parents
                    .iter()
                    .map(|p| {
                        self.mapping(p,None)
                    .map(|entry|entry.event.revision_id.clone()).ok_or_else(||Failure::precondition(
                        "a private revision parent must reach the remote ledger before its child"))
                    })
                    .collect::<Result<Vec<_>>>()?
            }
        } else {
            self.head.iter().cloned().collect()
        };
        if step.operation == "tombstone" && parents.is_empty() {
            return Err(invalid());
        }
        let sealed = json!({"schema_version":1,"entity_id":capture.entity_id,"entity_kind":capture.entity_kind,
            "parent_revision_ids":parents,"operation":step.operation,"payload":step.payload,
            "device_id":identity.device_id,"actor_id":identity.account_id,"created_at":step.created_at});
        let mut request = sealed.clone();
        request["revision_id"] = passport::revision_id(&sealed)?.into();
        request["content_digest"] = digest::canonical("ai-stp:revision:v1", &step.payload)?.into();
        request["event_id"] = format!("event_{}", ulid::Ulid::generate()).into();
        request["idempotency_key"] = format!("sync-{}", ulid::Ulid::generate()).into();
        request["expected_head_revision_id"] = json!(self.head);
        Event::push(&request, &identity.account_id)?;
        Ok(request)
    }
}

pub(super) fn receipt(entry: &Entry) -> Value {
    entry.stored.receipt.clone().unwrap_or_else(||json!({"schema_version":1,"event_id":entry.event.event_id,
        "state":"accepted","revision_id":entry.event.revision_id,"server_head_revision_id":entry.event.revision_id,
        "cursor":null,"conflict":null,"conflicting_entity_id":null,"error_code":null}))
}

pub(super) fn tombstone(capture: &Capture) -> Option<Step> {
    capture.tombstone.as_ref().map(|at| Step {
        local_revision: None,
        local_parents: vec![],
        operation: "tombstone".into(),
        payload: json!({}),
        created_at: at.clone(),
    })
}

pub(super) fn outcome(capture: &Capture, receipt: &Value, processed: usize) -> Value {
    json!({"schema_version":1,"stable_id":capture.entity_id,"local_revision_id":capture.local_revision,
        "processed_events":processed,"event_id":receipt["event_id"],"remote_revision_id":receipt["revision_id"],
        "state":receipt["state"],"server_head_revision_id":receipt["server_head_revision_id"],
        "conflict_fields":receipt["conflict"]["affected_fields"].as_array().cloned().unwrap_or_default(),
        "conflicting_entity_id":receipt["conflicting_entity_id"]})
}

pub(super) fn absent() -> Failure {
    Failure::new(
        ErrorKind::NotFound,
        "the private push target has no local record",
    )
}
