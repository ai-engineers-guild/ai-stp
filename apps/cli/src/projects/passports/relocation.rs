//! Internal metadata-only move; the corporate owner supplies reviewed authority.

use super::*;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Relocation {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub root: PathBuf,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub previous_root: PathBuf,
    pub root_identity: [String; 2],
    pub previous: Value,
    pub passport: Value,
}

pub(crate) fn observe_relocation(
    connection: &Connection,
    path: &Path,
    previous_root: &Path,
    project: &Value,
    identity: &Identity,
    at: &str,
) -> Result<Relocation> {
    let id = project["stable_id"].as_str().ok_or_else(invalid)?;
    if registered_document(connection, previous_root, id, identity)? != *project
        || !absent(previous_root)?
    {
        return Err(invalid());
    }
    let (path, directory) = root(path)?;
    let marker = marker::open(&directory, false)?;
    if path.starts_with(previous_root)
        || previous_root.starts_with(&path)
        || marker::read(marker.as_ref())?.as_deref() != Some(id)
        || bound(connection, &path)?.is_some()
        || pending(connection, &path, Some(id))?.is_some()
    {
        return Err(invalid());
    }
    let values = observation(&path, &directory)?;
    Ok(Relocation {
        root: path,
        previous_root: previous_root.to_owned(),
        root_identity: marker::identity(&directory)?,
        previous: project.clone(),
        passport: document(&values, id, Some(project), identity, at)?,
    })
}

/// The caller commits the terminal parent receipt and current-location CAS in
/// this same transaction. Public ordinary observation cannot call this route.
pub(crate) fn commit_relocation(
    transaction: &Transaction<'_>,
    held: &Relocation,
    operation: &str,
    identity: &Identity,
    at: &str,
) -> Result<()> {
    let fresh = observe_relocation(
        transaction,
        &held.root,
        &held.previous_root,
        &held.previous,
        identity,
        at,
    )?;
    if fresh != *held || held.root_identity != marker::identity(&root(&held.root)?.1)? {
        return Err(invalid());
    }
    let id = held.previous["stable_id"].as_str().ok_or_else(invalid)?;
    let head = held.previous["revision_id"]
        .as_str()
        .ok_or_else(invalid)?
        .to_owned();
    revisions::commit(
        transaction,
        &held.passport,
        &identity.device_id,
        Some(operation),
        Write::Advance {
            expected_heads: &[head],
        },
    )?;
    let changed = transaction
        .execute(
            "UPDATE project_root SET root=? WHERE stable_id=? AND root=?",
            params![
                held.root.to_str().ok_or_else(invalid)?,
                id,
                held.previous_root.to_str().ok_or_else(invalid)?
            ],
        )
        .map_err(database)?;
    if changed != 1 {
        return Err(invalid());
    }
    Ok(())
}
