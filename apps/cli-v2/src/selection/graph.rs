//! Bounded exact dependency closure; any refusal removes the entire install order.

use std::collections::{BTreeMap, BTreeSet, VecDeque};

use rusqlite::{Connection, OptionalExtension};
use serde_json::{Value, json};

use crate::{
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
    snapshot::Snapshot,
    wire,
};

const MAX_DEPTH: usize = 32;
const MAX_NODES: usize = 512;
const MAX_EDGES: usize = 8192;

#[derive(Clone, Eq, Ord, PartialEq, PartialOrd)]
struct Reference {
    stable_id: String,
    version: String,
    passport_digest: String,
    required_by: String,
}

impl Reference {
    fn from_value(value: &Value, parent: &str) -> Self {
        Self {
            stable_id: value["stable_id"].as_str().unwrap_or("").into(),
            version: value["version"].as_str().unwrap_or("").into(),
            passport_digest: value["passport_digest"].as_str().unwrap_or("").into(),
            required_by: parent.into(),
        }
    }

    fn exact(&self) -> bool {
        (passport::stable_id(&self.stable_id, "component")
            || passport::stable_id(&self.stable_id, "setup"))
            && passport::version_number(&self.version)
            && self
                .passport_digest
                .strip_prefix("sha256:")
                .is_some_and(|hex| {
                    hex.len() == 64
                        && hex
                            .bytes()
                            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
                })
    }

    fn view(&self) -> Value {
        json!({"schema_version": 1, "stable_id": self.stable_id, "version": self.version,
            "passport_digest": self.passport_digest, "required_by": self.required_by})
    }

    fn refusal(&self, code: &str, summary: &str, details: Value) -> Value {
        let mut details = details.as_object().cloned().unwrap_or_default();
        details.insert(
            "stable_id".into(),
            if self.stable_id.is_empty() {
                "unnamed"
            } else {
                &self.stable_id
            }
            .into(),
        );
        if !self.required_by.is_empty() {
            details.insert("required_by".into(), self.required_by.clone().into());
        }
        json!({"schema_version": 1, "code": code, "summary": summary, "details": details})
    }
}

struct Node {
    reference: Reference,
    revision: String,
    requires: Vec<Reference>,
    depth: usize,
}

impl Node {
    fn view(&self) -> Value {
        json!({"schema_version": 1, "stable_id": self.reference.stable_id,
            "version": self.reference.version, "passport_digest": self.reference.passport_digest,
            "revision_id": self.revision, "depth": self.depth,
            "requires": self.requires.iter().map(Reference::view).collect::<Vec<_>>()})
    }
}

fn database(_: rusqlite::Error) -> Failure {
    Failure::precondition("dependency graph records are not readable")
}

pub fn read(snapshot: &Snapshot, members: &[String], proposal: Option<&str>) -> Result<Value> {
    if members.is_empty() == proposal.is_none() {
        return Err(Failure::input(
            "name either a proposal or one or more exact members",
        ));
    }
    let mut roots = Vec::new();
    if let Some(id) = proposal {
        if !passport::stable_id(id, "proposal") {
            return Err(Failure::input("proposal identifier is invalid"));
        }
        let graph: Option<String> = snapshot
            .connection
            .query_row(
                "SELECT graph FROM proposal WHERE proposal_id = ?",
                [id],
                |row| row.get(0),
            )
            .optional()
            .map_err(database)?;
        let graph = wire::parse(
            graph
                .ok_or_else(|| {
                    Failure::new(
                        ErrorKind::NotFound,
                        "the proposal does not exist in this snapshot",
                    )
                })?
                .as_bytes(),
        )?;
        let graph = graph
            .as_array()
            .ok_or_else(|| Failure::precondition("proposal members are invalid"))?;
        if graph.len() > MAX_NODES {
            return Err(Failure::precondition(
                "proposal exceeds the dependency root bound",
            ));
        }
        roots.extend(graph.iter().map(|value| Reference::from_value(value, "")));
    } else {
        if members.len() > MAX_NODES {
            return Err(Failure::input("too many dependency roots"));
        }
        for member in members {
            let (id, version) = member
                .split_once('@')
                .ok_or_else(|| Failure::input("a member must name id@X.Y"))?;
            if (!passport::stable_id(id, "component") && !passport::stable_id(id, "setup"))
                || !passport::version_number(version)
            {
                return Err(Failure::input(
                    "a member must name an exact component or setup version",
                ));
            }
            let held: Option<String> = snapshot.connection.query_row(
                "SELECT passport_digest FROM object_version WHERE stable_id = ? AND version = ?",
                [id, version], |row| row.get(0),
            ).optional().map_err(database)?;
            roots.push(Reference {
                stable_id: id.into(),
                version: version.into(),
                passport_digest: held.ok_or_else(|| {
                    Failure::new(
                        ErrorKind::NotFound,
                        "an exact root version does not exist in this snapshot",
                    )
                })?,
                required_by: String::new(),
            });
        }
    }
    resolve(&snapshot.connection, roots)
}

pub(crate) fn exact(connection: &Connection, members: &[Value]) -> Result<Value> {
    if members.len() > MAX_NODES {
        return Err(Failure::input("too many dependency roots"));
    }
    resolve(
        connection,
        members
            .iter()
            .map(|value| Reference::from_value(value, ""))
            .collect(),
    )
}

fn resolve(connection: &Connection, mut roots: Vec<Reference>) -> Result<Value> {
    roots.sort();
    let mut edges = roots.len();
    let mut frontier: VecDeque<_> = roots.into_iter().map(|root| (root, 0)).collect();
    let mut pinned: BTreeMap<String, Reference> = BTreeMap::new();
    let mut found: BTreeMap<String, Node> = BTreeMap::new();
    let mut refusals = Vec::new();
    while let Some((reference, depth)) = frontier.pop_front() {
        let mut reject =
            |code, summary, details| refusals.push(reference.refusal(code, summary, details));
        if !reference.exact() {
            reject(
                "reference_floating",
                "a dependency does not name an exact version and digest",
                json!({"version": if reference.version.is_empty() { "none" } else { &reference.version }}),
            );
            continue;
        }
        if let Some(held) = pinned.get(&reference.stable_id) {
            if held.version != reference.version
                || held.passport_digest != reference.passport_digest
            {
                reject(
                    "version_conflict",
                    "two paths require different versions of one object",
                    json!({"already": held.version, "also": reference.version}),
                );
            }
            continue;
        }
        pinned.insert(reference.stable_id.clone(), reference.clone());
        if depth > MAX_DEPTH {
            reject(
                "closure_too_deep",
                "this dependency chain is longer than the declared bound",
                json!({"depth": depth.to_string(), "limit": MAX_DEPTH.to_string()}),
            );
            continue;
        }
        if found.len() >= MAX_NODES {
            reject(
                "closure_too_large",
                "this closure holds more objects than the declared bound",
                json!({"limit": MAX_NODES.to_string()}),
            );
            continue;
        }
        let document = match (Objects { connection }).exact_version(
            &reference.stable_id,
            &reference.version,
            Some(&reference.passport_digest),
        ) {
            Ok(document) => document,
            Err(error) => {
                match error.kind {
                    ErrorKind::NotFound => reject(
                        "dependency_missing",
                        "this machine does not hold that exact version",
                        json!({"version": reference.version}),
                    ),
                    ErrorKind::Conflict => reject(
                        "digest_mismatch",
                        "the held version stands for different content than the reference names",
                        json!({"expected": reference.passport_digest}),
                    ),
                    ErrorKind::Input | ErrorKind::Precondition => reject(
                        "dependency_unreadable",
                        "the revision behind that version cannot be read",
                        json!({"version": reference.version}),
                    ),
                    _ => return Err(error),
                }
                continue;
            }
        };
        let deleted: bool = connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM tombstone WHERE stable_id = ?)",
                [&reference.stable_id],
                |row| row.get(0),
            )
            .map_err(database)?;
        let state = match document.get("lifecycle_state") {
            None | Some(Value::Null) => "complete",
            Some(value) => value.as_str().unwrap_or("invalid"),
        };
        if !matches!(state, "complete" | "draft" | "conflict") {
            reject(
                "dependency_unreadable",
                "the revision declares an unknown lifecycle state",
                json!({}),
            );
            continue;
        }
        if deleted || state == "draft" {
            reject(
                "dependency_not_registrable",
                "a draft or deleted object is required by this composition",
                json!({"version": reference.version}),
            );
            continue;
        }
        let field = if document["kind"] == "setup" {
            "components"
        } else {
            "requires_components"
        };
        let mut requires: Vec<_> = document[field]
            .as_array()
            .into_iter()
            .flatten()
            .map(|value| Reference::from_value(value, &reference.stable_id))
            .collect();
        edges += requires.len();
        if edges > MAX_EDGES {
            reject(
                "closure_too_large",
                "this closure exceeds the dependency edge bound",
                json!({"limit": MAX_EDGES.to_string()}),
            );
            break;
        }
        requires.sort();
        frontier.extend(requires.iter().cloned().map(|item| (item, depth + 1)));
        found.insert(
            reference.stable_id.clone(),
            Node {
                reference,
                revision: document["revision_id"].as_str().unwrap_or("").into(),
                requires,
                depth,
            },
        );
    }
    let (order, cycle) = ordered(&found);
    if !cycle.is_empty() {
        refusals.push(json!({"schema_version": 1, "code": "dependency_cycle",
            "summary": "these objects require each other in a cycle", "details": {"members": cycle.join(", ")}}));
    }
    refusals.sort_by(|left, right| {
        (
            left["code"].as_str(),
            left["details"]["stable_id"].as_str(),
            left["details"]["required_by"].as_str(),
        )
            .cmp(&(
                right["code"].as_str(),
                right["details"]["stable_id"].as_str(),
                right["details"]["required_by"].as_str(),
            ))
    });
    let mut nodes = Vec::new();
    let mut references = Vec::new();
    if refusals.is_empty() {
        for id in order {
            if let Some(node) = found.get(&id) {
                nodes.push(node.view());
                references.push(format!(
                    "{}@{}",
                    node.reference.stable_id, node.reference.version
                ));
            }
        }
    }
    Ok(
        json!({"schema_version": 1, "resolved": refusals.is_empty(), "nodes": nodes,
        "order": references, "refusals": refusals, "max_depth": MAX_DEPTH,
        "max_nodes": MAX_NODES, "max_edges": MAX_EDGES}),
    )
}

fn ordered(found: &BTreeMap<String, Node>) -> (Vec<String>, Vec<String>) {
    let mut remaining: BTreeMap<_, BTreeSet<_>> = found
        .iter()
        .map(|(id, node)| {
            (
                id.clone(),
                node.requires
                    .iter()
                    .filter(|edge| found.contains_key(&edge.stable_id))
                    .map(|edge| edge.stable_id.clone())
                    .collect(),
            )
        })
        .collect();
    let mut order = Vec::new();
    while !remaining.is_empty() {
        let ready: BTreeSet<_> = remaining
            .iter()
            .filter(|(_, needs)| needs.is_empty())
            .map(|(id, _)| id.clone())
            .collect();
        if ready.is_empty() {
            return (order, remaining.into_keys().collect());
        }
        for id in &ready {
            remaining.remove(id);
            order.push(id.clone());
        }
        for needs in remaining.values_mut() {
            needs.retain(|id| !ready.contains(id));
        }
    }
    (order, Vec::new())
}
