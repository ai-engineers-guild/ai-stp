//! Local source addresses and relocation; source bytes do not confer ownership.

use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    files,
    objects::Objects,
    passport,
    store::{database, revisions},
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::{
    path::Path,
    time::{Duration, Instant},
};

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

pub(super) struct Address {
    pub harness_id: String,
    pub component_type: String,
    pub location: String,
    pub content_digest: String,
    pub source_key: String,
}

impl Address {
    pub fn new(
        harness_id: &str,
        component_type: &str,
        path: &Path,
        content_digest: String,
    ) -> Result<Self> {
        let location = files::location(path)?;
        let source_key = digest::canonical(
            "ai-stp:component-source-binding:v1",
            &json!({
                "harness_id":harness_id, "component_type":component_type, "absolute_path":location
            }),
        )?;
        Ok(Self {
            harness_id: harness_id.into(),
            component_type: component_type.into(),
            location,
            content_digest,
            source_key,
        })
    }
}

fn invalid() -> Failure {
    Failure::precondition("the local source binding cannot be safely inspected")
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

fn bindings(transaction: &Transaction<'_>, source: &Address) -> Result<Vec<Binding>> {
    let mut query = transaction.prepare("SELECT source_key,stable_id,harness_id,component_type,absolute_path,created_at FROM component_source_binding WHERE harness_id=? AND component_type=? ORDER BY source_key LIMIT 4097").map_err(database)?;
    let rows = query
        .query_map(
            params![source.harness_id, source.component_type],
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

pub(super) fn previous(
    transaction: &Transaction<'_>,
    prepared: &Address,
) -> Result<Option<Binding>> {
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

pub(super) fn replace(
    transaction: &Transaction<'_>,
    previous: Option<&Binding>,
    binding: &Binding,
) -> Result<()> {
    validate_binding(binding)?;
    if let Some(previous) = previous {
        let changed = transaction
            .execute(
                "DELETE FROM component_source_binding WHERE source_key=? AND stable_id=?",
                params![previous.source_key, previous.stable_id],
            )
            .map_err(database)?;
        if changed != 1 {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "the previous source binding changed",
            ));
        }
    }
    transaction.execute("INSERT INTO component_source_binding(source_key,stable_id,harness_id,component_type,absolute_path,created_at) VALUES (?,?,?,?,?,?)",params![binding.source_key,binding.stable_id,binding.harness_id,binding.component_type,binding.absolute_path,binding.created_at]).map_err(database)?;
    Ok(())
}
