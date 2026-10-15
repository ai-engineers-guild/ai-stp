//! Exact immutable publication inputs, durable per-object delivery and catalog
//! readback, including exact interruption and observation after device replacement.

pub mod client;
pub mod contract;
pub mod interruption;
pub mod journal;
pub mod readback;
pub mod runtime;
mod set;

use std::{collections::BTreeMap, path::Path};

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{
    artifacts::{self, Member},
    authoring::{freezing, setups, source},
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
    projection::artifact,
    selection::graph,
    store::{Store, database, revisions},
};

const MAX_METADATA: usize = 8 * 1024 * 1024;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Artifact {
    pub digest: String,
    pub size_bytes: usize,
}

/// Metadata only. Payloads are re-read and verified individually at delivery.
/// This is local evidence, not authentication or permission to publish.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    pub passport: Value,
    pub passport_digest: String,
    pub artifact_inventory: Vec<String>,
    pub artifact: Artifact,
    pub projections: Vec<Artifact>,
}

fn invalid() -> Failure {
    Failure::precondition(
        "publication requires complete, unchanged immutable versions and artifacts",
    )
}

fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str> {
    value[field].as_str().ok_or_else(invalid)
}

impl Artifact {
    fn from_value(value: &Value) -> Result<Self> {
        Ok(Self {
            digest: text(value, "digest")?.into(),
            size_bytes: value["size_bytes"]
                .as_u64()
                .and_then(|v| usize::try_from(v).ok())
                .ok_or_else(invalid)?,
        })
    }

    fn read(&self, connection: &Connection) -> Result<Vec<u8>> {
        let bytes = revisions::read_content(connection, &self.digest)?;
        if bytes.len() != self.size_bytes {
            return Err(invalid());
        }
        Ok(bytes)
    }
}

impl Snapshot {
    /// Local attachment history does not change the sealed version's owner.
    pub fn require_owner(&self, account: &str) -> Result<()> {
        if !passport::stable_id(account, "account") || self.passport["owner_id"] != account {
            return Err(Failure::precondition(
                "only the immutable passport owner can create its publication plan",
            ));
        }
        Ok(())
    }

    /// Recheck exact addressed bytes at use; never retain a graph of payloads.
    pub fn payload(&self, connection: &Connection, address: &str) -> Result<Vec<u8>> {
        std::iter::once(&self.artifact)
            .chain(&self.projections)
            .find(|item| item.digest == address)
            .ok_or_else(|| Failure::input("the publication does not declare that artifact"))?
            .read(connection)
    }
}

fn exact(
    connection: &Connection,
    id: &str,
    version: &str,
    expected_digest: Option<&str>,
) -> Result<Value> {
    let objects = Objects { connection };
    objects.require_active(id)?;
    let document = objects.exact_version(id, version, expected_digest)?;
    let overlay: bool = connection
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM overlay_origin WHERE revision_id=?)",
            [text(&document, "revision_id")?],
            |row| row.get(0),
        )
        .map_err(database)?;
    if overlay {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "a local overlay cannot be published; materialize an owner version",
        ));
    }
    Ok(document)
}

fn component_files(document: &Value, payload: &[u8]) -> Result<Vec<Member>> {
    match text(document, "artifact_format")? {
        artifacts::FILE_FORMAT => Ok(vec![Member {
            path: String::new(),
            bytes: payload.into(),
            mode: 0o644,
        }]),
        artifacts::TREE_FORMAT => artifacts::decode_tree(payload),
        artifact::FORMAT => {
            let scope = document["adaptations"]
                .as_array()
                .ok_or_else(invalid)?
                .iter()
                .flat_map(|a| a["scope_adaptations"].as_array().into_iter().flatten())
                .find(|s| s["projection_artifact"] == document["artifact"])
                .ok_or_else(invalid)?;
            artifact::verify(scope, payload)
        }
        _ => Err(invalid()),
    }
}

fn snapshot(connection: &Connection, document: Value, root: Option<&Path>) -> Result<Snapshot> {
    let original = Artifact::from_value(&document["artifact"])?;
    let mut inventory = Vec::new();
    let mut projections = BTreeMap::new();
    match text(&document, "kind")? {
        "component" => {
            freezing::verify(connection, &document)?;
            let mut files = component_files(&document, &original.read(connection)?)?;
            if let Some(root) = root {
                let mut selected = source::project(root)?;
                if document["artifact_format"] == artifacts::FILE_FORMAT {
                    if selected.len() != 1 || selected[0].bytes != files[0].bytes {
                        return Err(invalid());
                    }
                    files = selected;
                } else {
                    files.sort_by(|a, b| a.path.cmp(&b.path));
                    selected.sort_by(|a, b| a.path.cmp(&b.path));
                    if files != selected {
                        return Err(invalid());
                    }
                }
            }
            inventory.extend(files.into_iter().map(|f| f.path).filter(|p| !p.is_empty()));
            for adaptation in document["adaptations"].as_array().ok_or_else(invalid)? {
                for scope in adaptation["scope_adaptations"]
                    .as_array()
                    .ok_or_else(invalid)?
                {
                    let item = Artifact::from_value(&scope["projection_artifact"])?;
                    if let Some(held) = projections.insert(item.digest.clone(), item.clone())
                        && held != item
                    {
                        return Err(invalid());
                    }
                }
            }
        }
        "setup" if root.is_none() => setups::verify(connection, &document)?,
        _ => return Err(invalid()),
    }
    inventory.sort();
    if inventory.len() > 1000
        || inventory.windows(2).any(|pair| pair[0] == pair[1])
        || inventory
            .iter()
            .any(|p| p.chars().count() > 512 || !artifacts::safe_path(p))
    {
        return Err(invalid());
    }
    Ok(Snapshot {
        passport_digest: digest::canonical("ai-stp:passport:v1", &document)?,
        passport: document,
        artifact_inventory: inventory,
        artifact: original,
        projections: projections.into_values().collect(),
    })
}

/// Read a consistent local graph. Components precede their setup; embedded
/// records remain inside the setup definition and are not separate publications.
/// The caller must separately establish fresh account and catalog authority.
pub fn prepare(
    store: &mut Store,
    id: &str,
    version: &str,
    expected_digest: Option<&str>,
    component_root: Option<&Path>,
) -> Result<Vec<Snapshot>> {
    store.transaction(|connection| {
        let document = exact(connection, id, version, expected_digest)?;
        let mut result = Vec::new();
        let mut metadata = 0;
        let mut append = |item: Snapshot| -> Result<()> {
            metadata +=
                canonical::bytes(&serde_json::to_value(&item).map_err(|_| invalid())?)?.len();
            if metadata > MAX_METADATA {
                return Err(invalid());
            }
            result.push(item);
            Ok(())
        };
        if document["kind"] == "setup" {
            if component_root.is_some() {
                return Err(Failure::input(
                    "a source comparison directory applies only to a component",
                ));
            }
            let payload = Artifact::from_value(&document["artifact"])?.read(connection)?;
            let embedded = setups::definition::verify(&document, &payload)?;
            let embedded_ids: std::collections::BTreeSet<_> = embedded.into_keys().collect();
            drop(payload);
            let references = document["components"].as_array().ok_or_else(invalid)?;
            let closure = graph::exact(connection, references)?;
            let nodes = closure["nodes"].as_array().ok_or_else(invalid)?;
            if closure["resolved"] != true || nodes.len() != references.len() {
                return Err(invalid());
            }
            for node in nodes {
                let member = exact(
                    connection,
                    text(node, "stable_id")?,
                    text(node, "version")?,
                    Some(text(node, "passport_digest")?),
                )?;
                if member["kind"] != "component" {
                    return Err(invalid());
                }
                if !embedded_ids.contains(text(&member, "stable_id")?) {
                    append(snapshot(connection, member, None)?)?;
                }
            }
        }
        append(snapshot(connection, document, component_root)?)?;
        Ok(result)
    })
}
