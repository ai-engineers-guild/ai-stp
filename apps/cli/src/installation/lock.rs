//! An exclusive lock on an already held configuration metadata directory.
//!
//! Claims use complete physical identity rather than a pathname. Creation and
//! validation stay relative to the held directory; no writer reopens an ambient
//! parent after target admission.

use super::{
    Error, ReasonCode, Result,
    identity::{self, Identity},
};
use cap_fs_ext::{FollowSymlinks, MetadataExt, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::{Dir, OpenOptions};
use std::{
    collections::HashSet,
    fs::File,
    path::{Path, PathBuf},
    sync::{Mutex, OnceLock},
};

pub const LOCK_FILE_NAME: &str = "target.lock";
static HELD: OnceLock<Mutex<HashSet<Identity>>> = OnceLock::new();

fn claims() -> &'static Mutex<HashSet<Identity>> {
    HELD.get_or_init(Mutex::default)
}
fn release(identity: &Identity) {
    claims()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .remove(identity);
}
fn invalid() -> Error {
    Error::new(
        ReasonCode::StateUnavailable,
        "the installation writer lock or its directory changed",
    )
}

fn options(create: bool) -> OpenOptions {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .write(create)
        .create(create)
        .truncate(false)
        .follow(FollowSymlinks::No)
        .nonblock(true);
    #[cfg(unix)]
    {
        use cap_std::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options
}

fn open_lock(directory: &Dir, create: bool) -> std::io::Result<(File, Identity)> {
    let file = directory.open_with(LOCK_FILE_NAME, &options(create))?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.nlink() != 1 {
        return Err(std::io::Error::other(
            "installation lock is not a plain file",
        ));
    }
    #[cfg(windows)]
    {
        use cap_std::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return Err(std::io::Error::other(
                "installation lock is a reparse point",
            ));
        }
    }
    let identity = identity::file(&file)?;
    Ok((file.into_std(), identity))
}

#[derive(Debug)]
pub struct TargetLock {
    file: File,
    control: Dir,
    control_identity: Identity,
    file_identity: Identity,
    path: PathBuf,
}

impl TargetLock {
    pub fn acquire(path: &Path) -> Result<Self> {
        let directory = super::target::open(path)?;
        Self::acquire_at(&directory, path)
    }

    pub(crate) fn acquire_at(directory: &Dir, path: &Path) -> Result<Self> {
        let control = directory
            .try_clone()
            .map_err(|source| invalid().with_source(source))?;
        let control_identity =
            identity::directory(&control).map_err(|source| invalid().with_source(source))?;
        if !claims()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .insert(control_identity)
        {
            return Err(Error::new(
                ReasonCode::LockUnavailable,
                "this process already holds the physical installation directory",
            ));
        }
        let acquire = || -> Result<Self> {
            let (file, file_identity) =
                open_lock(&control, true).map_err(|source| invalid().with_source(source))?;
            file.try_lock().map_err(|source| {
                Error::new(
                    ReasonCode::LockUnavailable,
                    "another writer holds the installation directory",
                )
                .with_source(source)
            })?;
            Ok(Self {
                file,
                control,
                control_identity,
                file_identity,
                path: path.to_owned(),
            })
        };
        match acquire() {
            Ok(lock) => Ok(lock),
            Err(error) => {
                release(&control_identity);
                Err(error)
            }
        }
    }

    pub fn path(&self) -> PathBuf {
        self.path.join(LOCK_FILE_NAME)
    }

    pub fn revalidate(&self) -> Result<()> {
        let named = super::target::open(&self.path)?;
        if identity::directory(&named).map_err(|source| invalid().with_source(source))?
            != self.control_identity
        {
            return Err(invalid());
        }
        let (_, named_identity) =
            open_lock(&self.control, false).map_err(|source| invalid().with_source(source))?;
        if named_identity != self.file_identity
            || identity::standard_file(&self.file)
                .map_err(|source| invalid().with_source(source))?
                != self.file_identity
        {
            return Err(invalid());
        }
        Ok(())
    }
}
impl Drop for TargetLock {
    fn drop(&mut self) {
        let _ = self.file.unlock();
        release(&self.control_identity);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_physical_directory_contends_and_release_allows_the_next_writer()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let path = root.path().canonicalize()?;
        let directory = super::super::target::open(&path)?;
        let first = TargetLock::acquire_at(&directory, &path)?;
        assert!(TargetLock::acquire_at(&directory, &path).is_err());
        assert!(TargetLock::acquire(&path).is_err());
        drop(first);
        let next = TargetLock::acquire(&path)?;
        next.revalidate()?;
        drop(next);
        drop(directory);
        Ok(())
    }

    #[test]
    fn failed_alias_acquisition_releases_claim_without_touching_unowned_content()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let path = root.path().canonicalize()?;
        let other = path.join("keep");
        std::fs::write(&other, b"unowned")?;
        let lock = path.join(LOCK_FILE_NAME);
        std::fs::hard_link(&other, &lock)?;
        assert!(TargetLock::acquire(&path).is_err());
        std::fs::remove_file(&lock)?;
        let held = TargetLock::acquire(&path)?;
        held.revalidate()?;
        assert_eq!(std::fs::read(&other)?, b"unowned");
        drop(held);
        Ok(())
    }

    #[test]
    fn separate_physical_directories_do_not_contend()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let first_root = tempfile::tempdir()?;
        let second_root = tempfile::tempdir()?;
        let first = TargetLock::acquire(&first_root.path().canonicalize()?)?;
        let second = TargetLock::acquire(&second_root.path().canonicalize()?)?;
        first.revalidate()?;
        second.revalidate()?;
        drop(second);
        drop(first);
        Ok(())
    }
}
