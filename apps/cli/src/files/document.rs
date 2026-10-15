//! Publish one complete private document without replacing an existing path.

#[cfg(windows)]
mod windows;

use crate::{
    error::{Failure, Result},
    files::{self, OwnedDirectory, tree},
};
use cap_fs_ext::MetadataExt;
use cap_std::fs::Dir;
use std::{io::Read, path::Path};

fn invalid() -> Failure {
    Failure::precondition("the exact document destination changed or contains conflicting bytes")
}

fn parent(output: &str, expected: &[String; 2]) -> Result<Dir> {
    let path = Path::new(output);
    if tree::destination(path)? != (output.to_owned(), expected.clone()) {
        return Err(invalid());
    }
    let parent = Dir::open_ambient_dir(
        path.parent().ok_or_else(invalid)?,
        cap_std::ambient_authority(),
    )
    .map_err(|_| invalid())?;
    if crate::identity::physical_root(&parent)? != *expected {
        return Err(invalid());
    }
    #[cfg(windows)]
    windows::private(&parent, true)?;
    Ok(parent)
}

pub(crate) fn unused(output: &str, expected: &[String; 2]) -> Result<()> {
    let parent = parent(output, expected)?;
    match parent.symlink_metadata(Path::new(output).file_name().ok_or_else(invalid)?) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        _ => Err(invalid()),
    }
}

fn matches(parent: &Dir, leaf: &Path, bytes: &[u8]) -> Result<bool> {
    match parent.symlink_metadata(leaf) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(_) => return Err(invalid()),
        Ok(meta) if !meta.is_file() || meta.is_symlink() => return Err(invalid()),
        _ => {}
    }
    let file = files::open_regular(parent, leaf).map_err(|_| invalid())?;
    let held = file.metadata().map_err(|_| invalid())?;
    let named = parent.symlink_metadata(leaf).map_err(|_| invalid())?;
    if held.nlink() != 1
        || held.len() != bytes.len() as u64
        || held.dev() != named.dev()
        || held.ino() != named.ino()
        || named.is_symlink()
    {
        return Err(invalid());
    }
    #[cfg(unix)]
    {
        use cap_std::fs::PermissionsExt;
        if held.permissions().mode() & 0o777 != 0o600 {
            return Err(invalid());
        }
    }
    #[cfg(windows)]
    {
        use cap_std::fs::MetadataExt as _;
        if held.file_attributes() & 0x400 != 0 {
            return Err(invalid());
        }
        windows::private(&file, false)?;
    }
    let mut observed = Vec::new();
    file.take(bytes.len() as u64 + 1)
        .read_to_end(&mut observed)
        .map_err(|_| invalid())?;
    if observed != bytes {
        return Err(invalid());
    }
    Ok(true)
}

/// Call only with a previously retained exact signed record. Interrupted private
/// staging can be replaced; the final path is always published with NOREPLACE.
pub(crate) fn publish(
    output: &str,
    expected: &[String; 2],
    bytes: &[u8],
    digest: &str,
) -> Result<bool> {
    if bytes.len() > 256 * 1024
        || !(digest.len() == 71
            && digest.starts_with("sha256:")
            && digest[7..]
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
    {
        return Err(invalid());
    }
    let parent = parent(output, expected)?;
    let leaf = Path::new(Path::new(output).file_name().ok_or_else(invalid)?);
    let name = format!(".ai-stp-attestation-{}", &digest[7..]);
    let owner = format!("ai-stp-attestation/1\n{digest}\n");
    if matches(&parent, leaf, bytes)? {
        if let Some(stage) = OwnedDirectory::open_at(&parent, &name, owner.as_bytes(), false)? {
            tree::clean(&parent, &name, stage);
        }
        let _ = parent.remove_dir(&name);
        tree::sync(&parent)?;
        return Ok(parent.symlink_metadata(&name).is_ok());
    }
    let stage =
        OwnedDirectory::open_at(&parent, &name, owner.as_bytes(), true)?.ok_or_else(invalid)?;
    #[cfg(windows)]
    windows::private(&stage.directory, true)?;
    for entry in stage.directory.entries().map_err(|_| invalid())? {
        if !matches!(
            entry.map_err(|_| invalid())?.file_name().to_str(),
            Some("owner" | "lock" | "record")
        ) {
            return Err(invalid());
        }
    }
    stage.atomic_checked("record", bytes, |file| {
        #[cfg(windows)]
        windows::private(file, false)?;
        #[cfg(not(windows))]
        let _ = file;
        Ok(())
    })?;
    if !matches(&stage.directory, Path::new("record"), bytes)? {
        return Err(invalid());
    }
    tree::sync(&parent)?;
    if tree::destination(Path::new(output))? != (output.to_owned(), expected.clone()) {
        return Err(invalid());
    }
    tree::rename_new(&stage.directory, "record", &parent, leaf)?;
    stage.sync()?;
    tree::sync(&parent)?;
    if !matches(&parent, leaf, bytes)? {
        return Err(invalid());
    }
    if tree::destination(Path::new(output))? != (output.to_owned(), expected.clone()) {
        return Err(invalid());
    }
    tree::clean(&parent, &name, stage);
    Ok(parent.symlink_metadata(&name).is_ok())
}
