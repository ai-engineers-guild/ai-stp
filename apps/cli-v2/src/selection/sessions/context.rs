//! Exact context and graph evaluation; observations come from the owning runtime.

use super::{invalid, value};
use crate::{
    authoring::{Identity, setups},
    digest,
    error::{Failure, Result},
    objects::Objects,
    passport::{self, developer},
    provider::Info,
    selection::eligibility::{self, Evidence, Target},
};
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// The owning runtime supplies these observations and rights in process. This
/// type deliberately has no deserializer or command-line representation.
pub struct Runtime<'a> {
    pub identity: &'a Identity,
    pub target: &'a Target,
    pub evidence: &'a BTreeMap<String, Evidence>,
    pub provider: Option<&'a Info>,
    pub policy_version: &'a str,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Member {
    pub stable_id: String,
    pub version: String,
    pub passport_digest: String,
    pub lane: String,
    pub lane_reason: String,
    pub consent_source: String,
    pub overlay_revision_id: String,
}

impl Member {
    pub(crate) fn reference(&self) -> setups::Member {
        setups::Member {
            stable_id: self.stable_id.clone(),
            version: self.version.clone(),
            passport_digest: self.passport_digest.clone(),
        }
    }
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Context {
    pub project_id: String,
    pub harness_id: String,
    pub developer_revision: String,
    pub device_revision: String,
    pub project_revision: String,
    pub policy_version: String,
}

impl Context {
    pub(super) fn snapshot(&self, members: &[Member]) -> Result<String> {
        digest::canonical(
            "ai-stp:selection-snapshot:v1",
            &json!({
                "project_id":self.project_id,"harness_id":self.harness_id,
                "developer_revision":self.developer_revision,"device_revision":self.device_revision,
                "project_revision":self.project_revision,"policy_version":self.policy_version,
                "members":members.iter().map(|m| json!({"stable_id":m.stable_id,"version":m.version,
                    "passport_digest":m.passport_digest,"overlay_revision_id":m.overlay_revision_id})).collect::<Vec<_>>()
            }),
        )
    }
}

pub(super) fn owned_head(
    connection: &Connection,
    kind: &str,
    id: &str,
    identity: &Identity,
) -> Result<Value> {
    let objects = Objects { connection };
    objects.require_active(id)?;
    let document = objects.head(kind, id)?;
    if document["owner_id"] != identity.account_id {
        return Err(Failure::precondition(
            "the context passport belongs to another identity",
        ));
    }
    Ok(document)
}

pub(super) fn context_history(
    connection: &Connection,
    context: &Context,
    identity: &Identity,
) -> Result<()> {
    let objects = Objects { connection };
    for (kind, revision, expected_id) in [
        ("developer", &context.developer_revision, None),
        ("device", &context.device_revision, None),
        (
            "project",
            &context.project_revision,
            Some(context.project_id.as_str()),
        ),
    ] {
        let document = objects.revision(revision)?;
        if document["kind"] != kind
            || document["owner_id"] != identity.account_id
            || expected_id.is_some_and(|id| document["stable_id"] != id)
        {
            return Err(invalid());
        }
    }
    Ok(())
}

pub(super) fn evaluate(
    connection: &Connection,
    project: &str,
    roots: &[setups::Member],
    runtime: &Runtime<'_>,
) -> Result<(Context, Vec<Member>)> {
    runtime.identity.validate()?;
    runtime.target.validate()?;
    if runtime.target.owner_id != runtime.identity.account_id
        || runtime.target.for_redistribution
        || runtime.policy_version.is_empty()
        || runtime.policy_version.len() > 1024
        || runtime.policy_version.chars().any(char::is_control)
        || roots.len() > 512
        || roots
            .iter()
            .any(|m| !passport::stable_id(&m.stable_id, "component"))
    {
        return Err(invalid());
    }
    let project = owned_head(connection, "project", project, runtime.identity)?;
    let device = owned_head(
        connection,
        "device",
        &runtime.identity.device_id,
        runtime.identity,
    )?;
    let developer = developer::current(connection)?
        .ok_or_else(|| Failure::precondition("the developer context is missing"))?;
    if developer["owner_id"] != runtime.identity.account_id {
        return Err(invalid());
    }
    let mut members = Vec::new();
    let mut relevant = BTreeMap::new();
    if roots.is_empty()
        && !runtime.provider.is_some_and(|provider| {
            provider.document()["harness_id"] == runtime.target.harness_id
                && provider.supports_platform(&runtime.target.os, &runtime.target.arch)
                && provider.supports_target(runtime.target.scope)
        })
    {
        return Err(Failure::precondition(
            "the empty setup requires a supported provider target",
        ));
    }
    if !roots.is_empty() {
        let roots = value(&roots)?.as_array().ok_or_else(invalid)?.clone();
        let report = eligibility::assess_connection(
            connection,
            &roots,
            runtime.target,
            runtime.evidence,
            runtime.provider,
        )?;
        if report["admissible"] != true {
            return Err(
                Failure::precondition("the proposal graph is not mechanically admissible")
                    .with_details([("assessment".into(), report)]),
            );
        }
        let assessments = report["assessments"].as_array().ok_or_else(invalid)?;
        for node in report["graph"]["nodes"].as_array().ok_or_else(invalid)? {
            let id = node["stable_id"].as_str().ok_or_else(invalid)?;
            if !passport::stable_id(id, "component") {
                return Err(invalid());
            }
            let report = assessments
                .iter()
                .find(|r| r["stable_id"] == id)
                .ok_or_else(invalid)?;
            let evidence = runtime.evidence.get(id).ok_or_else(invalid)?;
            relevant.insert(id.to_owned(), evidence);
            members.push(Member {
                stable_id: id.into(),
                version: node["version"].as_str().ok_or_else(invalid)?.into(),
                passport_digest: node["passport_digest"].as_str().ok_or_else(invalid)?.into(),
                lane: report["lane"].as_str().ok_or_else(invalid)?.into(),
                lane_reason: report["lane_reason"].as_str().ok_or_else(invalid)?.into(),
                consent_source: if evidence.consented {
                    "runtime_explicit".into()
                } else {
                    String::new()
                },
                overlay_revision_id: String::new(),
            });
        }
    }
    members.sort_by(|a, b| (&a.stable_id, &a.version).cmp(&(&b.stable_id, &b.version)));
    // Changes in established rights, consent or provider surface cannot hide
    // behind unchanged context passports. Only this graph's evidence is bound.
    let policy = json!({"policy_version":runtime.policy_version,"target":runtime.target,
        "provider":runtime.provider.map(Info::document),"evidence":relevant});
    let context = Context {
        project_id: project["stable_id"].as_str().ok_or_else(invalid)?.into(),
        harness_id: runtime.target.harness_id.clone(),
        developer_revision: developer["revision_id"]
            .as_str()
            .ok_or_else(invalid)?
            .into(),
        device_revision: device["revision_id"].as_str().ok_or_else(invalid)?.into(),
        project_revision: project["revision_id"].as_str().ok_or_else(invalid)?.into(),
        policy_version: digest::canonical("ai-stp:plan:v1", &value(&policy)?)?,
    };
    value(&members)?;
    Ok((context, members))
}
