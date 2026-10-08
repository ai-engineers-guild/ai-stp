//! Planned local adoption: exact source bytes, current heads and one atomic effect.

use std::path::PathBuf;

use rusqlite::{Connection, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    Identity,
    bindings::{self, Address},
    contribution::{self, Format},
    discovery::{self, Candidate},
    expiry, native_identity, source,
};
use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    files,
    harnesses::{Root, Scope},
    objects::Objects,
    passport, projection,
    store::{
        Store, database, journal,
        revisions::{self, Write},
    },
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub root: PathBuf,
    pub harness_id: String,
    pub scope: Scope,
    pub root_kind: Root,
    pub candidate_id: String,
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
    pub source: Source,
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

pub use super::bindings::Binding;

fn invalid() -> Failure {
    Failure::precondition("the adoption plan or its source evidence is invalid")
}

fn stale() -> Failure {
    Failure::new(
        ErrorKind::Conflict,
        "source content, binding or revision heads changed after planning",
    )
}

pub(super) struct Prepared {
    candidate: Candidate,
    pub(super) content: source::Captured,
    address: Address,
    native_ids: Vec<String>,
}

pub(super) fn prepare(request: &Source) -> Result<Prepared> {
    let report = discovery::at(
        &request.root,
        &request.harness_id,
        request.scope,
        request.root_kind,
    )?;
    let candidate = report
        .components
        .into_iter()
        .find(|item| item.candidate_id == request.candidate_id)
        .ok_or_else(|| {
            if report.complete {
                Failure::new(
                    ErrorKind::NotFound,
                    "the selected discovery candidate is absent",
                )
            } else {
                invalid()
            }
        })?;
    if candidate.holds_secret {
        return Err(Failure::precondition(
            "credential-named sources cannot be adopted",
        ));
    }
    let mut content = source::capture_scoped(&request.root, &candidate.native_path)?;
    let native_ids = native_identity::read(&candidate, &content)?;
    if !candidate.declared_key.is_empty() {
        content.bytes = contribution::extract(
            Format::for_path(&candidate.native_path)?,
            &content.bytes,
            &candidate.declared_key,
        )?;
    }
    let content_digest = digest::bytes("ai-stp:artifact:v1", &content.bytes)?;
    let address = Address::new(
        &candidate.harness_id,
        &candidate.component_type,
        &candidate.absolute,
        content_digest,
    )?;
    Ok(Prepared {
        candidate,
        content,
        address,
        native_ids,
    })
}

pub(super) fn source_values(source: &Prepared) -> Result<Value> {
    let candidate = &source.candidate;
    let scope = match candidate.scope {
        Scope::Global => projection::Scope::Global,
        Scope::Project => projection::Scope::Project,
    };
    let name = candidate
        .absolute
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(invalid)?;
    let route = projection::route(&candidate.component_type, &candidate.harness_id, scope)?;
    let locator = if candidate.declared_key.is_empty() {
        String::new()
    } else {
        format!(
            "{}#{}",
            route.map_or(candidate.native_path.as_str(), |route| route
                .relative
                .as_str()),
            candidate.declared_key
        )
    };
    let mut values = json!({
        "component_type":candidate.component_type, "projection_kind":candidate.projection_kind,
        "native_role":candidate.native_role,"harness_id":candidate.harness_id,"scope":candidate.scope,
        "source_path":candidate.native_path,"source_name":name,"native_ids":source.native_ids,
        "entry_points":candidate.entry_points,"transport_capabilities":candidate.transport_capabilities,
        "evidence_refs":candidate.evidence_refs,"content_format":source.content.format,
        "source_mode":source.content.file_mode,
        "content_digest":source.address.content_digest,"byte_length":source.content.bytes.len(),
        "managed_paths":projection::covers(&candidate.component_type,&candidate.harness_id,name,scope)?,
        "declared_key":candidate.declared_key,"source_locator":locator,
    });
    for field in [
        "repository",
        "revision",
        "subpath",
        "package_name",
        "package_version",
        "digest",
    ] {
        values[format!("source_{field}")] = candidate.provenance[field].clone();
    }
    Ok(values)
}

fn document(
    source: &Prepared,
    identity: &Identity,
    stable_id: &str,
    head: Option<&Value>,
    at: &str,
) -> Result<Value> {
    let values = source_values(source)?;
    let mut facts = head
        .map(|head| head["facts"].clone())
        .unwrap_or_else(|| json!({}));
    let mut changed = head.is_none();
    for (key, value) in values.as_object().ok_or_else(invalid)? {
        if facts.get(key).is_none_or(|fact| fact["value"] != *value) {
            facts[key] =
                json!({"value":value,"origin":"observed","confirmation":"none","observed_at":at});
            changed = true;
        }
    }
    if !changed {
        return head.cloned().ok_or_else(invalid);
    }
    revisions::seal(
        &json!({"kind":"component","stable_id":stable_id,"owner_id":identity.account_id,
        "created_at":at,"visibility":head.map_or(json!("private"),|head|head["visibility"].clone()),
        "parent_revision_ids":head.map(|head|vec![head["revision_id"].clone()]).unwrap_or_default(),"facts":facts}),
    )
}

fn build(
    transaction: &Transaction<'_>,
    prepared: &Prepared,
    source: &Source,
    identity: &Identity,
    at: &str,
    operation_id: &str,
    new_id: &str,
) -> Result<Plan> {
    let previous_binding = bindings::previous(transaction, &prepared.address)?;
    let id = previous_binding
        .as_ref()
        .map_or(new_id, |binding| binding.stable_id.as_str());
    let expected_heads = revisions::heads(transaction, id)?;
    if expected_heads.len() > 1 {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "the source component has unresolved revision heads",
        ));
    }
    let head = expected_heads
        .first()
        .map(|revision| {
            Objects {
                connection: transaction,
            }
            .revision(revision)
        })
        .transpose()?;
    if let Some(head) = &head {
        if previous_binding.is_none()
            || head["kind"] != "component"
            || head["stable_id"] != id
            || head["owner_id"] != identity.account_id
        {
            return Err(Failure::precondition(
                "the source binding or component owner is inconsistent",
            ));
        }
    } else if previous_binding.is_some() {
        return Err(invalid());
    }
    let passport = document(prepared, identity, id, head.as_ref(), at)?;
    Ok(Plan {
        binding: Binding {
            source_key: prepared.address.source_key.clone(),
            stable_id: id.into(),
            harness_id: prepared.candidate.harness_id.clone(),
            component_type: prepared.candidate.component_type.clone(),
            absolute_path: prepared.address.location.clone(),
            created_at: previous_binding
                .as_ref()
                .map_or(at.to_owned(), |binding| binding.created_at.clone()),
        },
        previous_binding,
        expected_heads,
        passport,
        schema_version: 1,
        action: "component.adopt".into(),
        operation_id: operation_id.into(),
        created_at: at.into(),
        expires_at: expiry(at)?,
        identity: identity.clone(),
        source: source.clone(),
    })
}

/// Identity comes from the owning runtime; these local IDs do not assert cloud authentication.
pub fn plan(store: &mut Store, mut source: Source, identity: Identity, at: &str) -> Result<Plan> {
    identity.validate()?;
    if !passport::timestamp(at) {
        return Err(invalid());
    }
    source.root = PathBuf::from(files::location(&source.root)?);
    let prepared = prepare(&source)?;
    let operation_id = format!("operation_{}", ulid::Ulid::generate());
    let stable_id = format!("component_{}", ulid::Ulid::generate());
    store.transaction(|transaction| {
        build(
            transaction,
            &prepared,
            &source,
            &identity,
            at,
            &operation_id,
            &stable_id,
        )
    })
}

fn journal_state(connection: &Connection, plan: &Plan, expected: &str) -> Result<Option<String>> {
    journal::state(connection, &plan.operation_id, &plan.action, expected)
}

fn replay(connection: &Connection, plan: &Plan) -> Result<Value> {
    let revision = plan.passport["revision_id"].as_str().ok_or_else(invalid)?;
    let held = Objects { connection }.revision(revision)?;
    if held != plan.passport {
        return Err(stale());
    }
    let address = held["facts"]["content_digest"]["value"]
        .as_str()
        .ok_or_else(invalid)?;
    let bytes = revisions::read_content(connection, address)?;
    if held["facts"]["byte_length"]["value"].as_u64() != Some(bytes.len() as u64) {
        return Err(invalid());
    }
    Ok(held)
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
        || plan.action != "component.adopt"
        || plan.identity != *identity
        || plan.digest()? != expected_digest
        || !plan.source.root.is_absolute()
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::stable_id(&plan.binding.stable_id, "component")
        || !passport::timestamp(at)
        || !passport::timestamp(&plan.created_at)
        || plan.expires_at != expiry(&plan.created_at)?
    {
        return Err(invalid());
    }
    let known = journal_state(&store.connection, plan, expected_digest)?;
    if known.as_deref() == Some("verified") {
        return replay(&store.connection, plan);
    }
    if known.as_deref().is_some_and(|state| state != "applying") {
        return Err(Failure::precondition(
            "the adoption operation is terminal; create a new plan",
        ));
    }
    if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        if known.is_some() {
            store.transaction(|transaction| {
                if journal_state(transaction,plan,expected_digest)?.as_deref() == Some("applying") {
                    transaction.execute("UPDATE operation SET state='stale',finished_at=? WHERE operation_id=? AND state='applying'",params![at,plan.operation_id]).map_err(database)?;
                }
                Ok(())
            })?;
        }
        return Err(Failure::precondition(
            "the adoption plan is not within its validity interval",
        ));
    }
    let completed = store.transaction(|transaction| {
        match journal_state(transaction,plan,expected_digest)?.as_deref() {
            Some("verified") => return Ok(true),
            Some("applying") => {},
            None => {
                transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?,?,'applying',?,?)",params![plan.operation_id,plan.action,at,expected_digest]).map_err(database)?;
            }
            Some(_) => return Err(stale()),
        }
        Ok(false)
    })?;
    if completed {
        return replay(&store.connection, plan);
    }
    let result = (|| {
        let prepared = prepare(&plan.source)?;
        store.transaction(|transaction| {
            match journal_state(transaction,plan,expected_digest)?.as_deref() {
                Some("verified") => return replay(transaction,plan),
                Some("applying") => {},
                _ => return Err(stale()),
            }
            let current = build(transaction,&prepared,&plan.source,&plan.identity,&plan.created_at,&plan.operation_id,&plan.binding.stable_id)?;
            if current.digest()? != expected_digest { return Err(stale()); }
            revisions::content(transaction,&prepared.content.bytes,at)?;
            let held = revisions::commit(transaction,&plan.passport,&identity.device_id,Some(&plan.operation_id),Write::Advance { expected_heads:&plan.expected_heads })?;
            bindings::replace(transaction,plan.previous_binding.as_ref(),&plan.binding)?;
            let settled = transaction.execute("UPDATE operation SET state='verified',finished_at=? WHERE operation_id=? AND state='applying'",params![at,plan.operation_id]).map_err(database)?;
            if settled != 1 { return Err(stale()); }
            Ok(held)
        })
    })();
    if let Err(error) = &result {
        let state = if matches!(error.kind, ErrorKind::Conflict | ErrorKind::NotFound) {
            "stale"
        } else {
            "failed"
        };
        store.transaction(|transaction| {
            if journal_state(transaction,plan,expected_digest)?.as_deref() == Some("applying") {
                transaction.execute("UPDATE operation SET state=?,finished_at=? WHERE operation_id=? AND state='applying'",params![state,at,plan.operation_id]).map_err(database)?;
            }
            Ok(())
        })?;
    }
    result
}
