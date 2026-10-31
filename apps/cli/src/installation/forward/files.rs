//! Bounded file observations and descriptor-relative publication.

use std::{
    collections::BTreeMap,
    io::{Read, Write},
    path::Path,
};

use cap_fs_ext::{FollowSymlinks, MetadataExt, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::{Dir, Metadata, OpenOptions};
use serde::{Deserialize, Serialize};

use super::{Change, Content, Result, invalid};

pub(super) const FILE_LIMIT: usize = 32 * 1024 * 1024;
pub(super) use crate::installation::identity::Identity;

pub(super) fn io<T>(value: std::io::Result<T>) -> Result<T> {
    value.map_err(|error| invalid().with_source(error))
}

pub(super) fn dir_id(directory: &Dir) -> Result<Identity> {
    io(crate::installation::identity::directory(directory))
}

pub(super) fn open_root(path: &Path) -> Result<Dir> {
    let root = crate::installation::target::open(path)?;
    dir_id(&root)?;
    Ok(root)
}

#[cfg_attr(
    not(unix),
    allow(
        clippy::unnecessary_wraps,
        reason = "Directory flushing is available on Unix only."
    )
)]
pub(super) fn sync(directory: &Dir) -> Result<()> {
    #[cfg(unix)]
    io(io(directory.open("."))?.sync_all())?;
    #[cfg(not(unix))]
    let _ = directory;
    Ok(())
}

pub(super) fn mode(metadata: &Metadata) -> u32 {
    #[cfg(unix)]
    {
        use cap_std::fs::MetadataExt as _;
        metadata.mode() & 0o777
    }
    #[cfg(not(unix))]
    {
        let _ = metadata;
        0o600
    }
}

pub(super) fn valid_path(path: &str) -> bool {
    crate::archive::safe_path(path) && path.split('/').count() <= 64
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Stamp {
    pub(super) identity: Identity,
    pub(super) digest: String,
    pub(super) length: usize,
    pub(super) mode: u32,
}

/// One held observation, including the directory chain that led to the file.
#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Observation {
    pub(super) parents: BTreeMap<String, Identity>,
    pub(super) file: Option<Stamp>,
}

pub(super) fn parent(
    root: &Dir,
    path: &str,
    create: bool,
) -> Result<(Option<Dir>, BTreeMap<String, Identity>)> {
    if !valid_path(path) {
        return Err(invalid());
    }
    let mut current = io(root.try_clone())?;
    let mut parents = BTreeMap::new();
    let mut relative = String::new();
    let mut parts = path.split('/').peekable();
    while let Some(name) = parts.next() {
        if parts.peek().is_none() {
            break;
        }
        if !relative.is_empty() {
            relative.push('/');
        }
        relative.push_str(name);
        let next = match crate::installation::target::child(&current, std::ffi::OsStr::new(name)) {
            Ok(directory) => directory,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound && create => {
                io(current.create_dir(name))?;
                sync(&current)?;
                io(crate::installation::target::child(
                    &current,
                    std::ffi::OsStr::new(name),
                ))?
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok((None, parents));
            }
            Err(error) => return Err(invalid().with_source(error)),
        };
        parents.insert(relative.clone(), dir_id(&next)?);
        current = next;
    }
    Ok((Some(current), parents))
}

fn read_file(directory: &Dir, name: &str) -> Result<Option<(Stamp, Vec<u8>)>> {
    let mut options = OpenOptions::new();
    options.read(true).follow(FollowSymlinks::No).nonblock(true);
    let mut file = match directory.open_with(name, &options) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(invalid().with_source(error)),
    };
    let before = io(file.metadata())?;
    let id = io(crate::installation::identity::file(&file))?;
    if !before.is_file() || before.nlink() != 1 || before.len() > FILE_LIMIT as u64 {
        return Err(invalid());
    }
    let mut bytes = Vec::new();
    io(Read::by_ref(&mut file)
        .take(FILE_LIMIT as u64 + 1)
        .read_to_end(&mut bytes))?;
    let after = io(file.metadata())?;
    let named = io(directory.symlink_metadata(name))?;
    if bytes.len() as u64 != before.len()
        || after.len() != before.len()
        || after.modified().ok() != before.modified().ok()
        || after.nlink() != 1
        || mode(&after) != mode(&before)
        || io(crate::installation::identity::file(&io(
            directory.open_with(name, &options)
        )?))?
            != id
        || named.nlink() != 1
    {
        return Err(invalid());
    }
    Ok(Some((
        Stamp {
            identity: id,
            digest: crate::digest::sha256(&bytes),
            length: bytes.len(),
            mode: mode(&before),
        },
        bytes,
    )))
}

pub(super) fn read(root: &Dir, path: &str) -> Result<(Observation, Option<Content>)> {
    let (directory, parents) = parent(root, path, false)?;
    let Some(directory) = directory else {
        if parent(root, path, false)?.1 != parents {
            return Err(invalid());
        }
        return Ok((
            Observation {
                parents,
                file: None,
            },
            None,
        ));
    };
    let name = path.rsplit('/').next().ok_or_else(invalid)?;
    let (file, content) = match read_file(&directory, name)? {
        Some((stamp, bytes)) => {
            let content = Content {
                bytes,
                mode: stamp.mode,
            };
            (Some(stamp), Some(content))
        }
        None => (None, None),
    };
    // A replaced ancestor never lends its new identity to an old file read.
    if parent(root, path, false)?.1 != parents {
        return Err(invalid());
    }
    Ok((Observation { parents, file }, content))
}

pub(super) fn same_content(stamp: Option<&Stamp>, desired: Option<&Content>) -> bool {
    match (stamp, desired) {
        (None, None) => true,
        (Some(stamp), Some(content)) => {
            stamp.digest == crate::digest::sha256(&content.bytes)
                && stamp.length == content.bytes.len()
                && stamp.mode == content.mode
        }
        _ => false,
    }
}

pub(super) fn check_parents(before: &Observation, now: &Observation) -> Result<()> {
    if before
        .parents
        .iter()
        .any(|(path, id)| now.parents.get(path) != Some(id))
    {
        return Err(invalid());
    }
    Ok(())
}

pub(super) fn stage(directory: &Dir, name: &str, content: &Content) -> Result<()> {
    // The directory is exclusively owned by this admitted transaction. A
    // partial stage is ordinary activation state, never the previous contents.
    let previous = read_file(directory, name)?;
    if let Some((_, existing)) = &previous
        && !content.bytes.starts_with(existing)
    {
        return Err(invalid());
    }
    let mut options = OpenOptions::new();
    options
        .write(true)
        .create_new(previous.is_none())
        .follow(FollowSymlinks::No)
        .nonblock(true);
    #[cfg(unix)]
    {
        use cap_std::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = io(directory.open_with(name, &options))?;
    let metadata = io(file.metadata())?;
    let id = io(crate::installation::identity::file(&file))?;
    if !metadata.is_file()
        || metadata.nlink() != 1
        || previous
            .as_ref()
            .is_some_and(|(stamp, _)| stamp.identity != id)
    {
        return Err(invalid());
    }
    io(file.set_len(0))?;
    io(file.write_all(&content.bytes))?;
    #[cfg(unix)]
    {
        use cap_std::fs::PermissionsExt;
        io(file.set_permissions(cap_std::fs::Permissions::from_mode(content.mode)))?;
    }
    io(file.sync_all())?;
    sync(directory)
}

pub(super) fn publish(root: &Dir, staging: &Dir, name: &str, change: &Change) -> Result<()> {
    let (now, _) = read(root, &change.path)?;
    check_parents(&change.before, &now)?;
    if same_content(now.file.as_ref(), change.after.as_ref()) {
        return Ok(());
    }
    if now.file != change.before.file {
        return Err(invalid());
    }
    let (destination, parents) = parent(root, &change.path, change.after.is_some())?;
    let destination = destination.ok_or_else(invalid)?;
    let leaf = change.path.rsplit('/').next().ok_or_else(invalid)?;
    if let Some(content) = &change.after {
        stage(staging, name, content)?;
    }
    let (checked, _) = read(root, &change.path)?;
    if checked.file != now.file || checked.parents != parents {
        return Err(invalid());
    }
    if change.after.is_some() {
        io(staging.rename(name, &destination, leaf))?;
    } else {
        io(destination.remove_file(leaf))?;
    }
    sync(&destination)?;
    sync(staging)?;
    let (after, _) = read(root, &change.path)?;
    if after.parents != parents || !same_content(after.file.as_ref(), change.after.as_ref()) {
        return Err(invalid());
    }
    Ok(())
}
