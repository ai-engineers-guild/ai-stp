//! One portable project identity, with an exact, atomically retained adaptation graph.

use std::{
    collections::{BTreeMap, BTreeSet},
    path::PathBuf,
};

use rusqlite::{Connection, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    Identity, adaptations,
    bindings::{self, Address, Binding},
    expiry, freezing, source_project,
};
use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files,
    objects::Objects,
    passport,
    projection::Scope,
    provider::Info,
    store::{
        Store, database, journal,
        revisions::{self, Write},
    },
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Target {
    pub harness_id: String,
    pub scope: Scope,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub root: PathBuf,
    pub targets: Vec<Target>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub identity: Identity,
    pub request: Request,
    pub providers: Vec<Value>,
    pub snapshot_digest: String,
    pub binding: Binding,
    pub previous_binding: Option<Binding>,
    pub expected_heads: Vec<String>,
    pub passport: Value,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

fn invalid() -> Failure {
    Failure::precondition("the portable project binding violates its source or adaptation contract")
}
fn stale() -> Failure {
    Failure::new(
        ErrorKind::Conflict,
        "the project source, binding or revision heads changed after planning",
    )
}

struct Prepared {
    address: Address,
    values: Value,
    snapshot_digest: String,
    adaptations: Vec<Value>,
    artifacts: BTreeMap<String, Vec<u8>>,
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(invalid)
}

fn prepare(request: &Request, providers: &[Value]) -> Result<Prepared> {
    if request.targets.is_empty() || request.targets.len() > 21 || providers.len() > 7 {
        return Err(invalid());
    }
    let mut declarations = BTreeMap::new();
    for document in providers {
        let info = Info::parse(&canonical::bytes(document)?)?;
        if declarations
            .insert(text(document, "harness_id")?.to_owned(), info)
            .is_some()
        {
            return Err(invalid());
        }
    }
    let project = source_project::capture(&request.root)?;
    let values: Value = project.patch.clone().into();
    if values["tags"].as_array().is_none_or(Vec::is_empty) {
        return Err(Failure::precondition(
            "project binding requires at least one explicit tag in component-passport.json",
        ));
    }
    if values.get("harness_id").is_some_and(|v| v != "undefined") {
        return Err(invalid());
    }

    let address = Address::new(
        "undefined",
        text(&values, "component_type")?,
        &request.root,
        text(&project.report, "source_digest")?.into(),
    )?;
    let snapshot_digest = text(&project.report, "snapshot_digest")?.to_owned();
    let mut targets = BTreeSet::new();
    let mut grouped: BTreeMap<String, Value> = BTreeMap::new();
    let mut artifacts = BTreeMap::new();
    let mut total = 0usize;
    for target in &request.targets {
        if !targets.insert((target.harness_id.as_str(), target.scope.as_str())) {
            return Err(invalid());
        }
        let provider = declarations.get(&target.harness_id).ok_or_else(invalid)?;
        let prepared = adaptations::from_snapshot(&project, target.scope, provider)?;
        for bytes in [prepared.source_bytes, prepared.projection_bytes] {
            let address = digest::bytes("ai-stp:artifact:v1", &bytes)?;
            if let std::collections::btree_map::Entry::Vacant(entry) = artifacts.entry(address) {
                total = total.checked_add(bytes.len()).ok_or_else(invalid)?;
                if total > 128 * 1024 * 1024 {
                    return Err(Failure::precondition(
                        "the complete project adaptation payload exceeds 128 MiB",
                    ));
                }
                entry.insert(bytes);
            }
        }
        if let Some(held) = grouped.get_mut(&target.harness_id) {
            held["scope_adaptations"]
                .as_array_mut()
                .ok_or_else(invalid)?
                .push(prepared.adaptation["scope_adaptations"][0].clone());
        } else {
            grouped.insert(target.harness_id.clone(), prepared.adaptation);
        }
    }
    if declarations
        .keys()
        .any(|harness| !grouped.contains_key(harness))
    {
        return Err(invalid());
    }
    let adaptations = grouped
        .into_values()
        .map(adaptations::seal_derived)
        .collect::<Result<Vec<_>>>()?;
    Ok(Prepared {
        address,
        values,
        snapshot_digest,
        adaptations,
        artifacts,
    })
}

fn document(
    prepared: &Prepared,
    id: &str,
    identity: &Identity,
    head: Option<&Value>,
    at: &str,
) -> Result<Value> {
    if let Some(head) = head {
        // Refresh cannot silently discard an old scope or an independently authored adaptation.
        for old in head["adaptations"].as_array().ok_or_else(invalid)? {
            if old["implementation_mode"] != "derived"
                || old["transform"]["transform_id"] != "portable-source"
            {
                return Err(invalid());
            }
            let new = prepared
                .adaptations
                .iter()
                .find(|a| a["harness_id"] == old["harness_id"])
                .ok_or_else(|| {
                    Failure::precondition(
                        "project refresh must include every existing harness scope",
                    )
                })?;
            for scope in old["scope_adaptations"].as_array().ok_or_else(invalid)? {
                if !new["scope_adaptations"]
                    .as_array()
                    .ok_or_else(invalid)?
                    .iter()
                    .any(|s| s["scope"] == scope["scope"])
                {
                    return Err(Failure::precondition(
                        "project refresh must include every existing harness scope",
                    ));
                }
            }
        }
    }
    let mut document = head.cloned().unwrap_or_else(|| {
        json!({"kind":"component","stable_id":id,
        "owner_id":identity.account_id,"version":"1.0","visibility":"private","facts":{}})
    });
    let mut facts = prepared.values.clone();
    facts["content_digest"] = prepared.address.content_digest.clone().into();
    facts["content_format"] = crate::artifacts::TREE_FORMAT.into();
    facts["byte_length"] = prepared
        .artifacts
        .get(&prepared.address.content_digest)
        .ok_or_else(invalid)?
        .len()
        .into();
    for (key, value) in facts.as_object().ok_or_else(invalid)? {
        if document["facts"][key]["value"] != *value {
            // Reading authored source observes a declaration; it does not assert human confirmation.
            document["facts"][key] =
                json!({"value":value,"origin":"observed","confirmation":"none","observed_at":at});
        }
    }
    document["created_at"] = at.into();
    document["parent_revision_ids"] = head.map_or(json!([]), |h| json!([h["revision_id"]]));
    let mut document =
        freezing::complete(document, &prepared.values, prepared.adaptations.clone())?;
    if let Some(head) = head {
        let mut comparable = document.clone();
        for key in ["created_at", "parent_revision_ids", "revision_id"] {
            comparable[key] = head[key].clone();
        }
        if comparable == *head {
            document = head.clone();
        }
    }
    Ok(document)
}

struct Built {
    binding: Binding,
    previous_binding: Option<Binding>,
    expected_heads: Vec<String>,
    passport: Value,
}

fn build(
    transaction: &Transaction<'_>,
    prepared: &Prepared,
    identity: &Identity,
    at: &str,
    new_id: &str,
) -> Result<Built> {
    let changed_kind: bool = transaction.query_row("SELECT EXISTS(SELECT 1 FROM component_source_binding WHERE harness_id='undefined' AND absolute_path=? AND component_type!=?)",params![prepared.address.location,prepared.address.component_type],|r|r.get(0)).map_err(database)?;
    if changed_kind {
        return Err(Failure::precondition(
            "an existing project binding cannot change component kind",
        ));
    }

    let previous_binding = bindings::previous(transaction, &prepared.address)?;
    let id = previous_binding
        .as_ref()
        .map_or(new_id, |b| b.stable_id.as_str());
    let expected_heads = revisions::heads(transaction, id)?;
    if expected_heads.len() > 1 {
        return Err(stale());
    }
    let head = expected_heads
        .first()
        .map(|id| {
            Objects {
                connection: transaction,
            }
            .revision(id)
        })
        .transpose()?;
    if let Some(head) = &head {
        if previous_binding.is_none()
            || head["kind"] != "component"
            || head["stable_id"] != id
            || head["owner_id"] != identity.account_id
        {
            return Err(invalid());
        }
    } else if previous_binding.is_some() {
        return Err(invalid());
    }
    let passport = document(prepared, id, identity, head.as_ref(), at)?;
    let binding = Binding {
        source_key: prepared.address.source_key.clone(),
        stable_id: id.into(),
        harness_id: prepared.address.harness_id.clone(),
        component_type: prepared.address.component_type.clone(),
        absolute_path: prepared.address.location.clone(),
        created_at: previous_binding
            .as_ref()
            .map_or(at.to_owned(), |b| b.created_at.clone()),
    };
    Ok(Built {
        binding,
        previous_binding,
        expected_heads,
        passport,
    })
}

pub fn plan(
    store: &mut Store,
    mut request: Request,
    providers: &[Info],
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    request.root = PathBuf::from(files::location(&request.root)?);
    request
        .targets
        .sort_by(|a, b| (&a.harness_id, a.scope.as_str()).cmp(&(&b.harness_id, b.scope.as_str())));
    let mut providers: Vec<_> = providers.iter().map(|p| p.document().clone()).collect();
    providers.sort_by(|a, b| a["harness_id"].as_str().cmp(&b["harness_id"].as_str()));
    let prepared = prepare(&request, &providers)?;
    let id = format!("component_{}", ulid::Ulid::generate());
    let built = store.transaction(|t| build(t, &prepared, &identity, at, &id))?;
    Ok(Plan {
        schema_version: 1,
        action: "component.source.bind".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
        request,
        providers,
        snapshot_digest: prepared.snapshot_digest,
        binding: built.binding,
        previous_binding: built.previous_binding,
        expected_heads: built.expected_heads,
        passport: built.passport,
    })
}

fn replay(connection: &Connection, plan: &Plan) -> Result<Value> {
    let document = Objects { connection }.revision(text(&plan.passport, "revision_id")?)?;
    if document != plan.passport {
        return Err(stale());
    }
    let mut released = document.clone();
    released["parent_revision_ids"] = json!([]);
    freezing::verify(connection, &revisions::seal(&released)?)?;
    Ok(document)
}

pub fn apply(
    store: &mut Store,
    plan: &Plan,
    expected_digest: &str,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    identity.validate()?;
    if plan.schema_version != 1
        || plan.action != "component.source.bind"
        || plan.identity != *identity
        || plan.digest()? != expected_digest
        || !plan.request.root.is_absolute()
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::stable_id(&plan.binding.stable_id, "component")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
    {
        return Err(invalid());
    }
    if let Some(state) = journal::state(
        &store.connection,
        &plan.operation_id,
        &plan.action,
        expected_digest,
    )? {
        if state != "verified" {
            return Err(invalid());
        }
        return replay(&store.connection, plan);
    }
    if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        return Err(Failure::precondition(
            "the project binding plan is not within its validity interval",
        ));
    }
    // Capture and compile once before opening the writer; only immutable bytes cross the transaction boundary.
    let prepared = prepare(&plan.request, &plan.providers)?;
    store.transaction(|t| {
        if let Some(state) = journal::state(t,&plan.operation_id,&plan.action,expected_digest)? {
            if state != "verified" { return Err(invalid()); }
            return replay(t,plan);
        }
        let current = build(t,&prepared,&plan.identity,&plan.created_at,&plan.binding.stable_id)?;
        if current.binding != plan.binding || current.previous_binding != plan.previous_binding
            || current.expected_heads != plan.expected_heads || current.passport != plan.passport
            || prepared.snapshot_digest != plan.snapshot_digest { return Err(stale()); }
        for bytes in prepared.artifacts.values() { revisions::content(t,bytes,at)?; }
        let document = revisions::commit(t,&plan.passport,&identity.device_id,Some(&plan.operation_id),Write::Advance {expected_heads:&plan.expected_heads})?;
        bindings::replace(t,plan.previous_binding.as_ref(),&plan.binding)?;
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        Ok(document)
    })
}
