//! Bounded target-relative observations; no directory scanning or before-images.

use std::{ffi::OsString, io::Read, path::Path};

use cap_fs_ext::{DirExt, MetadataExt};
use cap_std::fs::{Dir, Metadata, PermissionsExt};

use super::{Target, invalid};
use crate::{error::Result, files};

pub(crate) struct Content {
    pub bytes: Vec<u8>,
    pub mode: u32,
}

pub(crate) struct Observation {
    pub parents: Vec<[String; 2]>,
    pub identity: Option<[String; 2]>,
    pub content: Option<Content>,
}

fn identity(metadata: &Metadata) -> [String; 2] {
    [metadata.dev().to_string(), metadata.ino().to_string()]
}

fn complete(
    ancestors: Vec<(Dir, OsString, Metadata)>,
    observed: Observation,
) -> Result<Observation> {
    for (directory, name, expected) in ancestors {
        if !same(
            &expected,
            &directory.symlink_metadata(name).map_err(|_| invalid())?,
        ) {
            return Err(invalid());
        }
    }
    Ok(observed)
}

fn same(left: &Metadata, right: &Metadata) -> bool {
    left.dev() == right.dev() && left.ino() == right.ino()
}

/// Resolve each parent without aliases and revalidate the named chain after I/O.
/// Only the requested file can enter memory; host bytes are never persisted here.
fn observe(root: &Dir, path: &str) -> Result<Observation> {
    if !crate::artifacts::safe_path(path) {
        return Err(invalid());
    }
    let path = Path::new(path);
    let mut directory = root.try_clone().map_err(|_| invalid())?;
    let mut ancestors = Vec::new();
    let mut observed = Observation {
        parents: vec![identity(&root.dir_metadata().map_err(|_| invalid())?)],
        identity: None,
        content: None,
    };
    for part in path.parent().ok_or_else(invalid)?.components() {
        let metadata = match directory.symlink_metadata(part.as_os_str()) {
            Ok(value) if value.is_dir() => value,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return complete(ancestors, observed);
            }
            _ => return Err(invalid()),
        };
        let child = directory
            .open_dir_nofollow(part.as_os_str())
            .map_err(|_| invalid())?;
        if !same(&metadata, &child.dir_metadata().map_err(|_| invalid())?) {
            return Err(invalid());
        }
        observed.parents.push(identity(&metadata));
        ancestors.push((directory, part.as_os_str().to_owned(), metadata));
        directory = child;
    }
    let name = path.file_name().ok_or_else(invalid)?;
    let named = match directory.symlink_metadata(name) {
        Ok(value) if value.is_file() => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return complete(ancestors, observed);
        }
        _ => return Err(invalid()),
    };
    let mut file = files::open_regular(&directory, Path::new(name)).map_err(|_| invalid())?;
    let before = file.metadata().map_err(|_| invalid())?;
    if !same(&named, &before) || before.len() > 4 * 1024 * 1024 || before.nlink() != 1 {
        return Err(invalid());
    }
    let mode = before.permissions().mode();
    if mode & 0o7000 != 0 || mode & 0o400 == 0 {
        return Err(invalid());
    }
    let mut bytes = Vec::new();
    file.by_ref()
        .take(4 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| invalid())?;
    let after = file.metadata().map_err(|_| invalid())?;
    if bytes.len() as u64 != before.len()
        || after.len() != before.len()
        || after.nlink() != 1
        || after.permissions().mode() != mode
        || after.modified().map_err(|_| invalid())? != before.modified().map_err(|_| invalid())?
        || !same(
            &after,
            &directory.symlink_metadata(name).map_err(|_| invalid())?,
        )
    {
        return Err(invalid());
    }
    observed.identity = Some(identity(&before));
    observed.content = Some(Content {
        bytes,
        mode: mode & 0o777,
    });
    complete(ancestors, observed)
}

impl Target {
    pub(crate) fn read(&self, path: &str) -> Result<Option<Content>> {
        Ok(self.observe(path)?.content)
    }

    pub(crate) fn observe(&self, path: &str) -> Result<Observation> {
        let result = observe(&self.directory()?, path)?;
        self.revalidate()?;
        Ok(result)
    }
}
