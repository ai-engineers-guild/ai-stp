//! Pure preparation of owned replacements for the complete source dependency graph.

use std::collections::{BTreeMap, BTreeSet};

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::Member;
use crate::{
    authoring::{Identity, derivation, freezing},
    canonical, digest,
    error::{Failure, Result},
    objects::Objects,
    passport,
    provider::Info,
    selection::graph,
    store::revisions,
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DerivedMember {
    pub source: Member,
    pub passport: Value,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Derivation {
    pub provider: Value,
    pub members: Vec<DerivedMember>,
}

pub(super) struct Built {
    pub documents: Vec<Value>,
    pub derivation: Derivation,
    pub artifacts: BTreeMap<String, Vec<u8>>,
}

fn invalid() -> Failure {
    Failure::precondition(
        "the recast cannot preserve its complete exact graph and owned derivations",
    )
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key].as_str().ok_or_else(invalid)
}

fn reference(document: &Value) -> Result<Member> {
    Ok(Member {
        stable_id: text(document, "stable_id")?.into(),
        version: text(document, "version")?.into(),
        passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
    })
}

fn target(document: &Value, harness: &str) -> bool {
    document["adaptations"]
        .as_array()
        .is_some_and(|items| items.iter().any(|item| item["harness_id"] == harness))
}

pub(super) fn build(
    connection: &Connection,
    original: &Value,
    provider: &Info,
    identity: &Identity,
    at: &str,
    expected: Option<&[DerivedMember]>,
) -> Result<Built> {
    let harness = text(provider.document(), "harness_id")?;
    let source_harness = text(original, "harness_id")?;
    if source_harness == harness {
        return Err(invalid());
    }
    let closure = graph::exact(
        connection,
        original["components"].as_array().ok_or_else(invalid)?,
    )?;
    if closure["resolved"] != true {
        return Err(invalid());
    }
    let documents = closure["nodes"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(|node| {
            Objects { connection }.exact_version(
                text(node, "stable_id")?,
                text(node, "version")?,
                Some(text(node, "passport_digest")?),
            )
        })
        .collect::<Result<Vec<_>>>()?;
    // The verified closure is topological: a dependent follows all its children.
    let mut changed = BTreeSet::new();
    for document in &documents {
        if !target(document, harness)
            || document["requires_components"]
                .as_array()
                .into_iter()
                .flatten()
                .any(|reference| {
                    reference["stable_id"]
                        .as_str()
                        .is_some_and(|id| changed.contains(id))
                })
        {
            changed.insert(text(document, "stable_id")?.to_owned());
        }
    }
    let mut identities = BTreeMap::new();
    let mut unique = BTreeSet::new();
    if let Some(expected) = expected {
        for member in expected {
            let id = text(&member.passport, "stable_id")?;
            if !passport::stable_id(id, "component")
                || !unique.insert(id.to_owned())
                || identities
                    .insert(member.source.stable_id.clone(), id.to_owned())
                    .is_some()
            {
                return Err(invalid());
            }
        }
        if identities.keys().cloned().collect::<BTreeSet<_>>() != changed {
            return Err(invalid());
        }
    } else {
        for id in changed {
            identities.insert(id, format!("component_{}", ulid::Ulid::generate()));
        }
    }
    let source_ids: BTreeSet<_> = documents
        .iter()
        .map(|document| text(document, "stable_id"))
        .collect::<Result<_>>()?;
    if identities
        .values()
        .any(|id| source_ids.contains(id.as_str()))
    {
        return Err(invalid());
    }
    let mut built = Built {
        documents: Vec::new(),
        derivation: Derivation {
            provider: provider.document().clone(),
            members: Vec::new(),
        },
        artifacts: BTreeMap::new(),
    };
    let mut references = BTreeMap::new();
    let mut size = 0usize;
    let mut metadata = 0usize;
    for before in documents {
        if target(&before, harness) {
            freezing::verify(connection, &before)?;
        }
        let source = reference(&before)?;
        let mut document = before.clone();
        if let Some(id) = identities.get(&source.stable_id) {
            if !target(&before, harness) {
                let derived =
                    derivation::build(connection, before.clone(), source_harness, provider, at)?;
                document = derived.document;
                for (address, bytes) in derived.artifacts {
                    if let Some(held) = built.artifacts.get(&address) {
                        if held != &bytes {
                            return Err(invalid());
                        }
                    } else {
                        size = size
                            .checked_add(bytes.len())
                            .filter(|size| *size <= 128 * 1024 * 1024)
                            .ok_or_else(invalid)?;
                        built.artifacts.insert(address, bytes);
                    }
                }
            }
            document["stable_id"] = id.clone().into();
            document["owner_id"] = identity.account_id.clone().into();
            document["version"] = "1.0".into();
            document["visibility"] = "private".into();
            document["created_at"] = at.into();
            document["parent_revision_ids"] = json!([]);
            document["compatibility_evidence_refs"] = json!([]);
            if document.get("requires_components").is_none() {
                document["requires_components"] = json!([]);
            }
            let dependencies = document["requires_components"]
                .as_array_mut()
                .ok_or_else(invalid)?;
            for dependency in dependencies {
                *dependency = references
                    .get(text(dependency, "stable_id")?)
                    .cloned()
                    .ok_or_else(invalid)?;
            }
            document["facts"]["source_component"] =
                json!({"value":source,"origin":"derived","confirmation":"none","observed_at":at});
            if document["facts"].get("requires_components").is_some() {
                document["facts"]["requires_components"] = json!({"value":document["requires_components"],"origin":"derived","confirmation":"none","observed_at":at});
            }
            passport::versions::normalize_component_refs(&mut document["requires_components"])?;
            document = revisions::seal(&document)?;
            passport::versions::validate_document(&document)?;
            built.derivation.members.push(DerivedMember {
                source: source.clone(),
                passport: document.clone(),
            });
        }
        metadata = metadata
            .checked_add(canonical::bytes(&document)?.len())
            .filter(|size| *size <= 8 * 1024 * 1024)
            .ok_or_else(invalid)?;
        references.insert(
            source.stable_id,
            serde_json::to_value(reference(&document)?).map_err(|_| invalid())?,
        );
        built.documents.push(document);
    }
    if let Some(expected) = expected
        && serde_json::to_value(expected).map_err(|_| invalid())?
            != serde_json::to_value(&built.derivation.members).map_err(|_| invalid())?
    {
        return Err(invalid());
    }
    Ok(built)
}
