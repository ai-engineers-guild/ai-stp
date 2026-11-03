//! Coordinate publication with the unchanged locks used by released writers.
use super::{CONTROLS, Custody, Target, adoption::Adoption, forward, invalid, marker, native};
use crate::{error::Result, installation::lock::TargetLock};
use cap_fs_ext::DirExt;
use cap_std::fs::Dir;
use std::ffi::OsStr;

fn state_file(control: &str) -> String {
    format!(
        "NDDEV-{}-PROVIDER.json",
        control
            .trim_start_matches('.')
            .trim_end_matches("-setup-system")
            .to_ascii_uppercase()
    )
}
/// An empty coordination lock is not an external ownership receipt. It may
/// remain after a refused/cancelled native attempt; every other entry refuses.
pub(super) fn lock_only(target: &Target, directory: &Dir, control: &str) -> Result<bool> {
    if native(forward::observe(target, &state_file(control)))?
        .1
        .is_some()
    {
        return Ok(false);
    }
    let mut lock = false;
    for entry in directory.entries().map_err(|_| invalid())? {
        let entry = entry.map_err(|_| invalid())?;
        if entry.file_name() != OsStr::new("target.lock") {
            return Ok(false);
        }
        lock = true;
    }
    if !lock {
        return Ok(false);
    }
    let content = native(forward::observe(target, &format!("{control}/target.lock")))?
        .1
        .ok_or_else(invalid)?;
    Ok(content.bytes.is_empty())
}
pub(crate) struct Locks {
    held: Vec<TargetLock>,
}
impl Locks {
    pub(crate) fn acquire(
        target: &Target,
        custody: &Custody,
        adoption: Option<&Adoption>,
    ) -> Result<Self> {
        let root = native(target.directory())?;
        let expected = marker(target, custody)?;
        let mut held = Vec::new();
        for name in CONTROLS {
            if adoption.is_some_and(|proof| proof.control() == name) {
                continue;
            }
            let mut builder = cap_std::fs::DirBuilder::new();
            builder.recursive(false);
            #[cfg(unix)]
            {
                use cap_std::fs::DirBuilderExt;
                builder.mode(0o700);
            }
            match root.create_dir_with(name, &builder) {
                Ok(()) => (),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => (),
                Err(_) => return Err(invalid()),
            }
            let control = root.open_dir_nofollow(name).map_err(|_| invalid())?;
            let lock = native(TargetLock::acquire_at(&control, &target.root().join(name)))?;
            if let Some(journal) =
                native(forward::observe(target, &format!("{name}/journal.json")))?.1
            {
                if journal.bytes != expected || journal.mode != 0o600 {
                    return Err(invalid());
                }
            } else if !lock_only(target, &control, name)? {
                return Err(invalid());
            }
            held.push(lock);
        }
        let locks = Self { held };
        locks.revalidate()?;
        Ok(locks)
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        for lock in &self.held {
            native(lock.revalidate())?;
        }
        Ok(())
    }
}
