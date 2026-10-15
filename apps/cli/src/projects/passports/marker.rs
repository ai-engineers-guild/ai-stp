//! The preview owns its marker separately from the production project marker.

use std::{io::Read, path::Path};

use cap_fs_ext::MetadataExt;
use cap_std::fs::Dir;

use crate::{
    error::{Failure, Result},
    files::{self, OwnedDirectory},
    passport,
};

const NAME: &str = ".ai-stp-v2-project";
const OWNER: &[u8] = b"ai-stp-cli-v2 project identity v1\n";

fn invalid() -> Failure {
    Failure::precondition("the private project marker is invalid or changed")
}

pub(super) fn open(root: &Dir, create: bool) -> Result<Option<OwnedDirectory>> {
    OwnedDirectory::open_at(root, NAME, OWNER, create)
}

pub(super) fn identity(root: &Dir) -> Result<[String; 2]> {
    let meta = root.dir_metadata().map_err(|_| invalid())?;
    Ok([meta.dev().to_string(), meta.ino().to_string()])
}

pub(super) fn sync_root(root: &Dir) -> Result<()> {
    let _ = root;
    #[cfg(unix)]
    root.open(".")
        .and_then(|file| file.sync_all())
        .map_err(|_| invalid())?;
    Ok(())
}

pub(super) fn read(directory: Option<&OwnedDirectory>) -> Result<Option<String>> {
    let Some(directory) = directory else {
        return Ok(None);
    };
    inventory(directory, None)?;
    let Some(bytes) = directory.read_file("project-id", 128)? else {
        return Ok(None);
    };
    let value = std::str::from_utf8(&bytes).map_err(|_| invalid())?;
    let id = value.strip_suffix('\n').ok_or_else(invalid)?;
    if !passport::stable_id(id, "project") {
        return Err(invalid());
    }
    Ok(Some(id.to_owned()))
}

/// Interrupted atomic replacements are recognized only while resuming the
/// exact prepared operation. Unknown files are never removed or overwritten.
pub(super) fn inventory(directory: &OwnedDirectory, expected: Option<&str>) -> Result<Vec<String>> {
    let mut temporary = Vec::new();
    for (count, entry) in directory
        .directory
        .entries()
        .map_err(|_| invalid())?
        .enumerate()
    {
        if count >= 32 {
            return Err(invalid());
        }
        let entry = entry.map_err(|_| invalid())?;
        let name = entry.file_name().into_string().map_err(|_| invalid())?;
        let metadata = directory
            .directory
            .symlink_metadata(&name)
            .map_err(|_| invalid())?;
        if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.nlink() != 1 {
            return Err(invalid());
        }
        if matches!(name.as_str(), "owner" | "lock" | "project-id") {
            continue;
        }
        let id = name.strip_prefix(".tmp-").ok_or_else(invalid)?;
        let expected = expected.ok_or_else(invalid)?;
        if !passport::stable_id(&format!("operation_{id}"), "operation") {
            return Err(invalid());
        }
        let mut bytes = Vec::new();
        files::open_regular(&directory.directory, Path::new(&name))
            .map_err(|_| invalid())?
            .take(129)
            .read_to_end(&mut bytes)
            .map_err(|_| invalid())?;
        if !format!("{expected}\n").as_bytes().starts_with(&bytes) {
            return Err(invalid());
        }
        temporary.push(name);
    }
    Ok(temporary)
}

pub(super) fn finish(directory: &OwnedDirectory, previous: Option<&str>, id: &str) -> Result<()> {
    let temporary = inventory(directory, Some(id))?;
    let held = directory.read_file("project-id", 128)?;
    let expected = format!("{id}\n").into_bytes();
    if held.as_deref() != Some(&expected) {
        let before = previous.map(|value| format!("{value}\n").into_bytes());
        if held != before {
            return Err(invalid());
        }
        directory.atomic("project-id", &expected)?;
    }
    for name in temporary {
        directory
            .directory
            .remove_file(name)
            .map_err(|_| invalid())?;
    }
    directory.sync()
}
