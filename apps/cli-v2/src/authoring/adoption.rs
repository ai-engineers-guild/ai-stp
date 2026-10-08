//! Planned local adoption: exact source bytes, current heads and one atomic effect.

use std::{
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    contribution::{self, Format},
    discovery::{self, Candidate},
    source,
};
use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    files,
    harnesses::{Root, Scope},
    objects::Objects,
    passport, projection,
    store::{
        Store, database,
        revisions::{self, Write},
    },
};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Identity {
    pub account_id: String,
    pub device_id: String,
}

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

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub source_key: String,
    pub stable_id: String,
    pub harness_id: String,
    pub component_type: String,
    #[serde(
        serialize_with = "files::serialize_location",
        deserialize_with = "files::deserialize_location"
    )]
    pub absolute_path: String,
    pub created_at: String,
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

fn invalid() -> Failure {
    Failure::precondition("the adoption plan or its source evidence is invalid")
}

fn stale() -> Failure {
    Failure::new(
        ErrorKind::Conflict,
        "source content, binding or revision heads changed after planning",
    )
}

struct Prepared {
    candidate: Candidate,
    content: source::Captured,
    content_digest: String,
    location: String,
    source_key: String,
}

fn prepare(request: &Source) -> Result<Prepared> {
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
    if !candidate.declared_key.is_empty() {
        content.bytes = contribution::extract(
            Format::for_path(&candidate.native_path)?,
            &content.bytes,
            &candidate.declared_key,
        )?;
    }
    let content_digest = digest::bytes("ai-stp:artifact:v1", &content.bytes)?;
    let location = files::location(&candidate.absolute)?;
    let source_key = digest::canonical(
        "ai-stp:component-source-binding:v1",
        &json!({
            "harness_id":candidate.harness_id, "component_type":candidate.component_type, "absolute_path":location
        }),
    )?;
    Ok(Prepared {
        candidate,
        content,
        content_digest,
        location,
        source_key,
    })
}

fn binding_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<Binding> {
    Ok(Binding {
        source_key: row.get(0)?,
        stable_id: row.get(1)?,
        harness_id: row.get(2)?,
        component_type: row.get(3)?,
        absolute_path: row.get(4)?,
        created_at: row.get(5)?,
    })
}

fn validate_binding(binding: &Binding) -> Result<()> {
    if !passport::stable_id(&binding.stable_id, "component")
        || !passport::timestamp(&binding.created_at)
        || !Path::new(&binding.absolute_path).is_absolute()
        || digest::canonical(
            "ai-stp:component-source-binding:v1",
            &json!({
                "harness_id":binding.harness_id,"component_type":binding.component_type,"absolute_path":binding.absolute_path
            }),
        )? != binding.source_key
    {
        return Err(Failure::precondition(
            "the stored source binding disagrees with its identity",
        ));
    }
    Ok(())
}

fn bindings(transaction: &Transaction<'_>, source: &Prepared) -> Result<Vec<Binding>> {
    let mut query = transaction.prepare("SELECT source_key,stable_id,harness_id,component_type,absolute_path,created_at FROM component_source_binding WHERE harness_id=? AND component_type=? ORDER BY source_key LIMIT 4097").map_err(database)?;
    let rows = query
        .query_map(
            params![source.candidate.harness_id, source.candidate.component_type],
            binding_row,
        )
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if rows.len() > 4096 {
        return Err(Failure::precondition(
            "source binding discovery exceeds its bounded scope",
        ));
    }
    Ok(rows)
}

fn previous(transaction: &Transaction<'_>, prepared: &Prepared) -> Result<Option<Binding>> {
    let exact = transaction.query_row("SELECT source_key,stable_id,harness_id,component_type,absolute_path,created_at FROM component_source_binding WHERE source_key=?",[&prepared.source_key],binding_row).optional().map_err(database)?;
    if let Some(row) = exact {
        validate_binding(&row)?;
        if row.absolute_path != prepared.location
            && !files::same_location(Path::new(&row.absolute_path), Path::new(&prepared.location))
                .unwrap_or(false)
        {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "different filesystem locations share a normalized source binding address",
            ));
        }
        return Ok(Some(row));
    }
    let rows = bindings(transaction, prepared)?;
    let started = Instant::now();
    let mut moved = Vec::new();
    let mut aliases = Vec::new();
    for row in rows {
        validate_binding(&row)?;
        if started.elapsed() > Duration::from_secs(10) {
            return Err(invalid());
        }
        match Path::new(&row.absolute_path).symlink_metadata() {
            Ok(_) => {
                if files::same_location(
                    Path::new(&row.absolute_path),
                    Path::new(&prepared.location),
                )
                .unwrap_or(false)
                {
                    aliases.push(row);
                }
            }
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory
                ) =>
            {
                let heads = revisions::heads(transaction, &row.stable_id)?;
                if heads.len() != 1 {
                    continue;
                }
                let head = Objects {
                    connection: transaction,
                }
                .revision(&heads[0])?;
                if head["facts"]["content_digest"]["value"] == prepared.content_digest {
                    moved.push(row);
                }
            }
            Err(_) => {
                return Err(Failure::precondition(
                    "a prior source location cannot be safely inspected",
                ));
            }
        }
    }
    if aliases.len() > 1 {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "multiple source bindings name the same location",
        ));
    }
    if let Some(row) = aliases.pop() {
        return Ok(Some(row));
    }
    // Copies remain distinct; only one vanished source with identical bytes can move.
    Ok(if moved.len() == 1 { moved.pop() } else { None })
}

fn document(
    source: &Prepared,
    identity: &Identity,
    stable_id: &str,
    head: Option<&Value>,
    at: &str,
) -> Result<Value> {
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
    let native_ids = if matches!(candidate.component_type.as_str(), "instruction" | "skill") {
        Vec::new()
    } else {
        vec![name]
    };
    let mut values = json!({
        "component_type":candidate.component_type, "projection_kind":candidate.projection_kind,
        "native_role":candidate.native_role,"harness_id":candidate.harness_id,"scope":candidate.scope,
        "source_path":candidate.native_path,"source_name":name,"native_ids":native_ids,
        "entry_points":candidate.entry_points,"transport_capabilities":candidate.transport_capabilities,
        "evidence_refs":candidate.evidence_refs,"content_format":source.content.format,
        "content_digest":source.content_digest,"byte_length":source.content.bytes.len(),
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
    let previous_binding = previous(transaction, prepared)?;
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
            source_key: prepared.source_key.clone(),
            stable_id: id.into(),
            harness_id: prepared.candidate.harness_id.clone(),
            component_type: prepared.candidate.component_type.clone(),
            absolute_path: prepared.location.clone(),
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
    if !passport::stable_id(&identity.account_id, "account")
        || !passport::stable_id(&identity.device_id, "device")
        || !passport::timestamp(at)
    {
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

fn expiry(at: &str) -> Result<String> {
    let expires = at
        .parse::<jiff::Timestamp>()
        .map_err(|_| invalid())?
        .checked_add(Duration::from_secs(900))
        .map_err(|_| invalid())?;
    Ok(format!("{expires:.3}"))
}

fn journal_state(connection: &Connection, plan: &Plan, expected: &str) -> Result<Option<String>> {
    let known: Option<(String, String, String)> = connection
        .query_row(
            "SELECT kind,state,coalesce(detail,'') FROM operation WHERE operation_id=?",
            [&plan.operation_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .map_err(database)?;
    match known {
        Some((kind, state, binding)) if kind == plan.action && binding == expected => {
            Ok(Some(state))
        }
        Some(_) => Err(stale()),
        None => Ok(None),
    }
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
    if plan.schema_version != 1
        || plan.action != "component.adopt"
        || plan.identity != *identity
        || !passport::stable_id(&identity.account_id, "account")
        || !passport::stable_id(&identity.device_id, "device")
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
            if let Some(previous) = &plan.previous_binding {
                let changed = transaction.execute("DELETE FROM component_source_binding WHERE source_key=? AND stable_id=?",params![previous.source_key,previous.stable_id]).map_err(database)?;
                if changed != 1 { return Err(stale()); }
            }
            transaction.execute("INSERT INTO component_source_binding(source_key,stable_id,harness_id,component_type,absolute_path,created_at) VALUES (?,?,?,?,?,?)",params![plan.binding.source_key,plan.binding.stable_id,plan.binding.harness_id,plan.binding.component_type,plan.binding.absolute_path,plan.binding.created_at]).map_err(database)?;
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
