//! Planned project observations with durable recovery across SQLite and a marker.

mod marker;

use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

use cap_std::fs::Dir;
use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{
    authoring::{Identity, expiry},
    canonical, digest,
    error::{Failure, Result},
    files,
    objects::Objects,
    passport,
    store::{
        Store, database, journal,
        revisions::{self, Write},
    },
};

const ACTION: &str = "project.passport.record";

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub identity: Identity,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub root: PathBuf,
    pub root_identity: [String; 2],
    pub previous_marker: Option<String>,
    #[serde(
        serialize_with = "serialize_previous",
        deserialize_with = "deserialize_previous"
    )]
    pub previous_root: Option<PathBuf>,
    pub expected_heads: Vec<String>,
    pub passport: Value,
}

// Optional paths still need the byte-preserving representation used by every
// native filesystem plan; NFC display strings cannot reopen decomposed names.
#[derive(Deserialize, Serialize)]
struct Previous(
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    PathBuf,
);
fn serialize_previous<S: serde::Serializer>(
    value: &Option<PathBuf>,
    serializer: S,
) -> std::result::Result<S::Ok, S::Error> {
    value
        .as_ref()
        .map(|p| Previous(p.clone()))
        .serialize(serializer)
}
fn deserialize_previous<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<Option<PathBuf>, D::Error> {
    Ok(Option::<Previous>::deserialize(deserializer)?.map(|p| p.0))
}

fn invalid() -> Failure {
    Failure::precondition("the project observation, identity or registration precondition changed")
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
    fn encoded(&self) -> Result<String> {
        let bytes = canonical::bytes(&serde_json::to_value(self).map_err(|_| invalid())?)?;
        if bytes.len() > 256 * 1024 {
            return Err(invalid());
        }
        String::from_utf8(bytes).map_err(|_| invalid())
    }
    fn id(&self) -> Result<&str> {
        self.passport["stable_id"].as_str().ok_or_else(invalid)
    }
    fn validate(&self, identity: &Identity) -> Result<()> {
        identity.validate()?;
        if self.schema_version != 1
            || self.action != ACTION
            || self.identity != *identity
            || !passport::stable_id(&self.operation_id, "operation")
            || !passport::stable_id(self.id()?, "project")
            || self.passport["kind"] != "project"
            || self.passport["owner_id"] != identity.account_id
            || self.expires_at != expiry(&self.created_at)?
            || !self.root.is_absolute()
            || self.expected_heads.len() > 1
        {
            return Err(invalid());
        }
        passport::validate(&self.passport)?;
        self.encoded()?;
        Ok(())
    }
}

fn root(path: &Path) -> Result<(PathBuf, Dir)> {
    let (path, directory) = super::open_root(path)?;
    Ok((PathBuf::from(files::location(&path)?), directory))
}

fn absent(path: &Path) -> Result<bool> {
    match path.symlink_metadata() {
        Ok(_) => Ok(false),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(true),
        Err(_) => Err(invalid()),
    }
}

fn pending(connection: &Connection, path: &Path, id: Option<&str>) -> Result<Option<Plan>> {
    let encoded = serde_json::to_value(Previous(path.to_owned())).map_err(|_| invalid())?;
    let mut query = connection.prepare(
        "SELECT detail FROM operation WHERE kind=? AND state='prepared' AND (json_extract(detail,'$.root.utf8_base64')=? OR json_extract(detail,'$.passport.stable_id')=?) LIMIT 2"
    ).map_err(database)?;
    let rows = query
        .query_map(
            params![
                ACTION,
                encoded["utf8_base64"].as_str().ok_or_else(invalid)?,
                id
            ],
            |r| r.get::<_, String>(0),
        )
        .map_err(database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(database)?;
    if rows.len() > 1 {
        return Err(invalid());
    }
    rows.first()
        .map(|text| {
            if text.len() > 256 * 1024 {
                return Err(invalid());
            }
            serde_json::from_value(canonical::parse(text.as_bytes())?).map_err(|_| invalid())
        })
        .transpose()
}

fn bound(connection: &Connection, path: &Path) -> Result<Option<String>> {
    connection
        .query_row(
            "SELECT stable_id FROM project_root WHERE root=?",
            [path.to_str().ok_or_else(invalid)?],
            |r| r.get(0),
        )
        .optional()
        .map_err(database)
}
fn location(connection: &Connection, id: &str) -> Result<Option<PathBuf>> {
    connection
        .query_row(
            "SELECT root FROM project_root WHERE stable_id=?",
            [id],
            |r| r.get::<_, String>(0),
        )
        .optional()
        .map(|p| p.map(PathBuf::from))
        .map_err(database)
}

fn previous(connection: &Connection, id: &str, identity: &Identity) -> Result<Value> {
    let objects = Objects { connection };
    let document = objects.head("project", id)?;
    objects.require_active(id)?;
    if document["owner_id"] != identity.account_id || document["visibility"] != "private" {
        return Err(invalid());
    }
    Ok(document)
}

pub(crate) struct Registered {
    pub path: PathBuf,
    pub directory: Dir,
    pub identity: [String; 2],
    pub project: Value,
}

/// Reuse the existing private marker and binding without repairing or creating it.
pub(crate) fn registered(
    connection: &Connection,
    path: &Path,
    identity: &Identity,
) -> Result<Registered> {
    let (path, directory) = root(path)?;
    let held = marker::open(&directory, false)?;
    let id = marker::read(held.as_ref())?.ok_or_else(invalid)?;
    if bound(connection, &path)?.as_ref() != Some(&id)
        || location(connection, &id)?.as_ref() != Some(&path)
    {
        return Err(invalid());
    }
    Ok(Registered {
        path,
        identity: marker::identity(&directory)?,
        directory,
        project: previous(connection, &id, identity)?,
    })
}

fn observation(path: &Path, directory: &Dir) -> Result<Value> {
    let observed = super::index(path)?;
    if observed["state"] != "complete"
        || marker::identity(directory)? != marker::identity(&root(path)?.1)?
    {
        return Err(Failure::precondition(
            "the project index is incomplete or the root changed",
        ));
    }
    let entries = observed["files"].as_array().ok_or_else(invalid)?;
    let fingerprints: Vec<_> = entries.iter().map(|item| json!({"path":item["path"], "digest":item["digest"], "size_bytes":item["size_bytes"]})).collect();
    let configuration: Vec<_> = entries
        .iter()
        .zip(&fingerprints)
        .filter(|(item, _)| {
            matches!(
                item["kind"].as_str(),
                Some("manifest" | "lock" | "config" | "agent_surface")
            )
        })
        .map(|(_, item)| item.clone())
        .collect();
    let languages: BTreeSet<_> = entries
        .iter()
        .filter_map(|item| item["language"].as_str())
        .collect();
    Ok(json!({"root": files::display(path),
        "index_digest":digest::canonical("ai-stp:project-index:v1", &json!({"state":"complete","entries":fingerprints}))?,
        "configuration_digest":digest::canonical("ai-stp:project-configuration:v1", &json!(configuration))?,
        "file_count":entries.len(),"index_state":"complete","languages":languages,
        "metadata_only_count":entries.iter().filter(|item| item["digest"].is_null()).count()}))
}

fn document(
    values: &Value,
    id: &str,
    earlier: Option<&Value>,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    let mut facts = serde_json::Map::new();
    for (key, value) in values.as_object().ok_or_else(invalid)? {
        let held = earlier.map(|item| &item["facts"][key]);
        facts.insert(key.clone(), match held {
            Some(held) if held["value"] == *value => held.clone(),
            _ => json!({"value":value,"origin":"observed","confirmation":"none","observed_at":at}),
        });
    }
    let mut result = json!({"kind":"project","stable_id":id,"owner_id":identity.account_id,
        "created_at":earlier.map(|p| &p["created_at"]).cloned().unwrap_or_else(|| at.into()),
        "visibility":"private","facts":facts,"parent_revision_ids":earlier.map(|p| vec![p["revision_id"].clone()]).unwrap_or_default()});
    result = revisions::seal(&result)?;
    if let Some(earlier) = earlier
        && earlier["facts"] == result["facts"]
    {
        return Ok(earlier.clone());
    }
    Ok(result)
}

pub fn plan(store: &mut Store, path: &Path, identity: Identity, at: &str) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    let (root, directory) = root(path)?;
    let root_identity = marker::identity(&directory)?;
    if let Some(held) = store.transaction(|t| pending(t, &root, None))? {
        held.validate(&identity)?;
        if held.root != root || held.root_identity != root_identity {
            return Err(invalid());
        }
        return Ok(held);
    }
    let marker = marker::open(&directory, false)?;
    let previous_marker = marker::read(marker.as_ref())?;
    let values = observation(&root, &directory)?;
    store.transaction(|t| {
        let bound = bound(t, &root)?;
        let previous_root = previous_marker
            .as_deref()
            .map(|id| location(t, id))
            .transpose()?
            .flatten();
        if let Some(id) = &previous_marker {
            if previous_root.is_none() {
                return Err(Failure::precondition(
                    "the project marker has no identity in this preview registry",
                ));
            }
            previous(t, id, &identity)?;
        }
        let reuse = if let Some(id) = bound {
            if previous_marker.as_deref() != Some(&id) {
                return Err(invalid());
            }
            Some(id)
        } else if previous_root.as_ref().is_some_and(|p| p != &root)
            && absent(previous_root.as_ref().ok_or_else(invalid)?)?
        {
            previous_marker.clone()
        } else {
            None
        };
        let id = reuse
            .clone()
            .unwrap_or_else(|| format!("project_{}", ulid::Ulid::generate()));
        if pending(t, &root, Some(&id))?.is_some() {
            return Err(invalid());
        }
        let earlier = reuse
            .as_ref()
            .map(|id| previous(t, id, &identity))
            .transpose()?;
        let previous_root = if reuse.is_some() {
            location(t, &id)?
        } else {
            None
        };
        Ok(Plan {
            schema_version: 1,
            action: ACTION.into(),
            operation_id: format!("operation_{}", ulid::Ulid::generate()),
            created_at: at.into(),
            expires_at,
            identity: identity.clone(),
            root,
            root_identity,
            previous_marker,
            previous_root,
            expected_heads: earlier
                .as_ref()
                .map(|p| vec![p["revision_id"].as_str().unwrap_or("").to_owned()])
                .unwrap_or_default(),
            passport: document(&values, &id, earlier.as_ref(), &identity, at)?,
        })
    })
}

fn preconditions(t: &Transaction<'_>, plan: &Plan) -> Result<Option<Value>> {
    let id = plan.id()?;
    if let Some(marked) = &plan.previous_marker {
        previous(t, marked, &plan.identity)?;
        if location(t, marked)?.is_none() {
            return Err(invalid());
        }
    }
    if revisions::heads(t, id)? != plan.expected_heads
        || location(t, id)? != plan.previous_root
        || bound(t, &plan.root)?
            .is_some_and(|held| held != id || plan.previous_marker.as_deref() != Some(id))
    {
        return Err(invalid());
    }
    if let Some(before) = &plan.previous_root
        && before != &plan.root
        && !absent(before)?
    {
        return Err(invalid());
    }
    if plan.expected_heads.is_empty() {
        Ok(None)
    } else {
        previous(t, id, &plan.identity).map(Some)
    }
}

fn receipt(connection: &Connection, plan: &Plan) -> Result<Value> {
    let held = Objects { connection }
        .revision(plan.passport["revision_id"].as_str().ok_or_else(invalid)?)?;
    if held != plan.passport {
        return Err(invalid());
    }
    Ok(passport::view(&held))
}

pub fn apply(
    store: &mut Store,
    plan: &Plan,
    expected_digest: &str,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    plan.validate(identity)?;
    if !passport::timestamp(at) || plan.digest()? != expected_digest {
        return Err(invalid());
    }
    let encoded = plan.encoded()?;
    let state = store.transaction(|t| journal::state(t, &plan.operation_id, ACTION, &encoded))?;
    if state.as_deref() == Some("verified") {
        return store.transaction(|t| receipt(t, plan));
    }
    if state.as_deref().is_some_and(|state| state != "prepared") {
        return Err(invalid());
    }
    let (path, directory) = root(&plan.root)?;
    if path != plan.root || marker::identity(&directory)? != plan.root_identity {
        return Err(invalid());
    }
    if state.is_none() {
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
            return Err(Failure::precondition(
                "the project plan expired before it started",
            ));
        }
        let marker = marker::open(&directory, false)?;
        if marker::read(marker.as_ref())? != plan.previous_marker {
            return Err(invalid());
        }
        let values = observation(&plan.root, &directory)?;
        store.transaction(|t| {
            if pending(t,&plan.root,Some(plan.id()?))?.is_some() { return Err(invalid()); }
            let earlier = preconditions(t,plan)?;
            if document(&values,plan.id()?,earlier.as_ref(),identity,&plan.created_at)? != plan.passport { return Err(invalid()); }
            t.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?,?,'prepared',?,?)",
                params![plan.operation_id,ACTION,at,encoded]).map_err(database)?;
            Ok(())
        })?;
    }
    // The prepared operation retains the accepted observation. Recovery does
    // not reinterpret later source bytes as the earlier scan; a new scan does.
    store.transaction(|t| preconditions(t, plan).map(|_| ()))?;
    if marker::identity(&root(&plan.root)?.1)? != plan.root_identity {
        return Err(invalid());
    }
    let marker = marker::open(&directory, true)?.ok_or_else(invalid)?;
    marker::finish(&marker, plan.previous_marker.as_deref(), plan.id()?)?;
    marker::sync_root(&directory)?;
    if marker::identity(&root(&plan.root)?.1)? != plan.root_identity {
        return Err(invalid());
    }
    store.transaction(|t| {
        preconditions(t,plan)?;
        if journal::state(t,&plan.operation_id,ACTION,&encoded)?.as_deref() != Some("prepared") { return Err(invalid()); }
        revisions::commit(t,&plan.passport,&identity.device_id,Some(&plan.operation_id),Write::Advance {expected_heads:&plan.expected_heads})?;
        t.execute("INSERT INTO project_root(root,stable_id) VALUES (?,?) ON CONFLICT(stable_id) DO UPDATE SET root=excluded.root",
            params![plan.root.to_str().ok_or_else(invalid)?,plan.id()?]).map_err(database)?;
        t.execute("UPDATE operation SET state='verified',finished_at=? WHERE operation_id=?",params![at,plan.operation_id]).map_err(database)?;
        receipt(t,plan)
    })
}
