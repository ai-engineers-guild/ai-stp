//! The exclusive lock every mutation holds, and the durable write it protects.
//!
//! The lock is bound to the canonical target directory, not to a process, a
//! user or a setup id. Two managers pointed at the same target contend; two
//! pointed at different targets never do.
//!
//! Acquisition is non-blocking on purpose. A caller that waits silently on a
//! lock held by a crashed process looks identical to a caller doing slow work,
//! and the consumer's timeout would then be charged to the wrong cause.
//!
//! # Why the operating-system lock is not enough on its own
//!
//! Advisory file locks differ in what they are owned by. A POSIX record lock is
//! owned by the *process*, so a second acquisition from inside one process
//! succeeds and silently merges with the first: no contention is reported, and
//! two code paths both believe they hold the target exclusively. Other flavours
//! bind to the open file description and do report it.
//!
//! This kernel does not depend on which flavour a platform provides. Each setup
//! system ships one binary with two surfaces, so a wire command and a human
//! command can reach this lock in one process; [`HELD_TARGETS`] claims the path
//! in-process first, and only then is the operating-system lock taken for the
//! cross-process case. Both are released on drop, and the in-process refusal is
//! the same on every platform.

use std::collections::HashSet;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

use cap_fs_ext::{DirExt, FollowSymlinks, MetadataExt, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::{Dir, OpenOptions};

use crate::installation::error::{Error, ReasonCode, Result};

/// The file name the lock is taken on inside the control directory.
pub const LOCK_FILE_NAME: &str = "target.lock";

/// Lock paths currently claimed by this process.
static HELD_TARGETS: OnceLock<Mutex<HashSet<PathBuf>>> = OnceLock::new();

fn held_targets() -> &'static Mutex<HashSet<PathBuf>> {
    HELD_TARGETS.get_or_init(|| Mutex::new(HashSet::new()))
}

/// Claim a path in-process, or report that this process already holds it.
///
/// A poisoned mutex is recovered rather than propagated: the guarded value is a
/// set of paths, and a panic elsewhere does not make the set meaningless. Losing
/// the ability to take any lock afterwards would be the worse outcome.
fn claim_in_process(path: &Path) -> bool {
    let mut held = held_targets()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    held.insert(path.to_path_buf())
}

fn release_in_process(path: &Path) {
    let mut held = held_targets()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    held.remove(path);
}

/// An exclusive, target-bound lock released when the value is dropped.
#[derive(Debug)]
pub struct TargetLock {
    file: File,
    path: PathBuf,
    identity: crate::installation::identity::Identity,
}

impl TargetLock {
    /// Take the lock without waiting.
    ///
    /// # Errors
    ///
    /// Returns [`ReasonCode::LockUnavailable`] if another holder has it, and
    /// [`ReasonCode::StateUnavailable`] if the lock file cannot be opened.
    pub fn acquire(control_directory: &Path) -> Result<Self> {
        let path = control_directory.join(LOCK_FILE_NAME);

        if !claim_in_process(&path) {
            return Err(Error::new(
                ReasonCode::LockUnavailable,
                format!("this process already holds {}", path.display()),
            ));
        }

        let acquire_os_lock = || -> Result<(File, crate::installation::identity::Identity)> {
            let open_lock =
                || -> std::io::Result<(File, crate::installation::identity::Identity)> {
                    let parent = control_directory
                        .parent()
                        .ok_or_else(|| std::io::Error::other("control directory has no parent"))?;
                    let name = control_directory
                        .file_name()
                        .ok_or_else(|| std::io::Error::other("control directory has no name"))?;
                    let parent = Dir::open_ambient_dir(parent, cap_std::ambient_authority())?;
                    let control = parent.open_dir_nofollow(name)?;
                    let mut options = OpenOptions::new();
                    options
                        .create(true)
                        .read(true)
                        .write(true)
                        .truncate(false)
                        .follow(FollowSymlinks::No)
                        .nonblock(true);
                    let file = control.open_with(LOCK_FILE_NAME, &options)?;
                    let metadata = file.metadata()?;
                    #[cfg(windows)]
                    {
                        use cap_std::fs::MetadataExt as _;
                        if metadata.file_attributes() & 0x400 != 0 {
                            return Err(std::io::Error::other("lock is a reparse point"));
                        }
                    }
                    if !metadata.is_file() || metadata.nlink() != 1 {
                        return Err(std::io::Error::other("lock is not a regular file"));
                    }
                    let identity = crate::installation::identity::file(&file)?;
                    Ok((file.into_std(), identity))
                };
            let (file, identity) = open_lock().map_err(|source| {
                Error::new(
                    ReasonCode::StateUnavailable,
                    format!("cannot open lock file {}", path.display()),
                )
                .with_source(source)
            })?;
            file.try_lock().map_err(|source| {
                Error::new(
                    ReasonCode::LockUnavailable,
                    format!("another process holds {}", path.display()),
                )
                .with_source(source)
            })?;
            Ok((file, identity))
        };

        match acquire_os_lock() {
            Ok((file, identity)) => Ok(Self {
                file,
                path,
                identity,
            }),
            Err(error) => {
                // The in-process claim must not outlive a failed acquisition, or
                // the next attempt would be refused by this process forever.
                release_in_process(&path);
                Err(error)
            }
        }
    }

    /// The lock file path.
    #[must_use]
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Verify that the named lock still refers to this held regular file.
    ///
    /// # Errors
    /// Refuses an inaccessible, replaced, linked or aliased lock entry.
    pub fn revalidate(&self) -> Result<()> {
        let check = || -> std::io::Result<()> {
            let parent = self
                .path
                .parent()
                .ok_or_else(|| std::io::Error::other("lock has no parent"))?;
            let directory = Dir::open_ambient_dir(parent, cap_std::ambient_authority())?;
            let named = directory.symlink_metadata(LOCK_FILE_NAME)?;
            if !named.is_file()
                || named.is_symlink()
                || named.nlink() != 1
                || crate::installation::identity::file(&directory.open_with(LOCK_FILE_NAME, &{
                    let mut options = cap_std::fs::OpenOptions::new();
                    options
                        .read(true)
                        .follow(cap_fs_ext::FollowSymlinks::No)
                        .nonblock(true);
                    options
                })?)?
                    != self.identity
            {
                return Err(std::io::Error::other("the held lock entry changed"));
            }
            #[cfg(windows)]
            {
                use cap_std::fs::MetadataExt as _;
                if named.file_attributes() & 0x400 != 0 {
                    return Err(std::io::Error::other("the lock is a reparse point"));
                }
            }
            Ok(())
        };
        check().map_err(|source| {
            Error::new(
                ReasonCode::StateUnavailable,
                "the prefix writer lock was replaced",
            )
            .with_source(source)
        })
    }

    /// Record a non-secret owner note inside the lock file.
    ///
    /// The note is diagnostic only. Nothing reads it to make a decision, because
    /// a decision taken from an unverified note inside a contended file is a
    /// decision taken from whatever the previous holder left behind.
    ///
    /// # Errors
    ///
    /// Returns [`ReasonCode::StateUnavailable`] if the note cannot be written.
    pub fn annotate(&mut self, note: &str) -> Result<()> {
        self.file
            .set_len(0)
            .and_then(|()| self.file.write_all(note.as_bytes()))
            .map_err(|source| {
                Error::new(
                    ReasonCode::StateUnavailable,
                    format!("cannot annotate {}", self.path.display()),
                )
                .with_source(source)
            })
    }
}

impl Drop for TargetLock {
    fn drop(&mut self) {
        // A failed unlock is not actionable here: the value is going away and
        // the operating system releases the lock when the descriptor closes.
        let _ = self.file.unlock();
        release_in_process(&self.path);
    }
}

/// Replace a file's contents durably, or leave the previous contents intact.
///
/// The bytes land in a sibling temporary file that is flushed to disk before the
/// rename, so an interruption leaves either the old file or the new one — never
/// a half-written file that parses as valid state.
///
/// Missing parent directories are created. A namespace can be nested — Codex
/// routes skills to `.agents/skills`, Antigravity keeps everything under
/// subdirectories of a home it shares — so writing one is routinely the act
/// that first creates its directory. Doing it here rather than at each call
/// site is what keeps two write paths from disagreeing, which they did: the
/// bundle path created parents and the catalog path did not, so a setup with a
/// nested file installed over the wire and failed from disk.
///
/// # Errors
///
/// Returns [`ReasonCode::StateUnavailable`] if any step fails.
pub fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let Some(parent) = path.parent() else {
        return Err(Error::new(
            ReasonCode::StateUnavailable,
            format!("{} has no parent directory", path.display()),
        ));
    };
    let Some(file_name) = path.file_name().and_then(|name| name.to_str()) else {
        return Err(Error::new(
            ReasonCode::StateUnavailable,
            format!("{} has no usable file name", path.display()),
        ));
    };
    fs::create_dir_all(parent).map_err(|source| {
        Error::new(
            ReasonCode::StateUnavailable,
            format!("cannot create {}", parent.display()),
        )
        .with_source(source)
    })?;
    let temporary = parent.join(format!(".{file_name}.staging"));

    let write = || -> std::io::Result<()> {
        let mut file = File::create(&temporary)?;
        file.write_all(bytes)?;
        file.sync_all()
    };
    write().map_err(|source| {
        let _ = fs::remove_file(&temporary);
        Error::new(
            ReasonCode::StateUnavailable,
            format!("cannot stage {}", temporary.display()),
        )
        .with_source(source)
    })?;

    // The rename swaps in a fresh inode, so a file restricted to 0o600 would be
    // widened to `File::create`'s default 0o644 without anyone being told.
    // Carry the destination's mode onto the staging file first.
    if let Ok(metadata) = fs::metadata(path) {
        fs::set_permissions(&temporary, metadata.permissions()).map_err(|source| {
            let _ = fs::remove_file(&temporary);
            Error::new(
                ReasonCode::StateUnavailable,
                format!("cannot preserve the mode of {}", path.display()),
            )
            .with_source(source)
        })?;
    }

    fs::rename(&temporary, path).map_err(|source| {
        let _ = fs::remove_file(&temporary);
        Error::new(
            ReasonCode::StateUnavailable,
            format!(
                "cannot promote {} to {}",
                temporary.display(),
                path.display()
            ),
        )
        .with_source(source)
    })?;

    sync_directory(parent);
    Ok(())
}

#[cfg(unix)]
fn sync_directory(path: &Path) {
    // The rename is only durable once the directory entry itself is flushed.
    // A failure here is not recoverable by retrying and does not invalidate the
    // rename, so it is observed and not escalated.
    if let Ok(directory) = File::open(path) {
        let _ = directory.sync_all();
    }
}

#[cfg(not(unix))]
fn sync_directory(_path: &Path) {
    // Windows has no directory handle to flush in the POSIX sense; the rename
    // is ordered by the file system itself.
}

/// True for the temporary name [`atomic_write`] stages beside a file:
/// `.<name>.staging`. Anywhere the name turns up it is this kernel's
/// in-flight write, interrupted before the rename — bookkeeping, not
/// content, the way the journal is bookkeeping.
#[must_use]
pub fn is_staging_name(name: &str) -> bool {
    name.strip_prefix('.')
        .and_then(|rest| rest.strip_suffix(".staging"))
        .is_some_and(|middle| !middle.is_empty())
}

/// Refuse to write `path`, which lives under `root`, when any component of
/// the way down is a symbolic link.
///
/// `fs::create_dir_all` and `fs::copy` both follow links they meet, so a
/// directory swapped for a link between one operation and the next carries
/// the write out of the tree it was aimed at. [`atomic_write`]'s rename
/// makes the *final* component safe by replacing whatever sits there; this
/// checks the components the rename cannot reach.
///
/// # Errors
///
/// Returns [`ReasonCode::IntegrityMismatch`] when a link is found, and
/// [`ReasonCode::StateUnavailable`] when `path` is not under `root` or a
/// component cannot be inspected.
pub fn refuse_linked_descent(root: &Path, path: &Path) -> Result<()> {
    let relative = path.strip_prefix(root).map_err(|source| {
        Error::new(
            ReasonCode::StateUnavailable,
            format!("{} is not inside {}", path.display(), root.display()),
        )
        .with_source(source)
    })?;
    let mut at = root.to_path_buf();
    for component in relative.components() {
        at.push(component.as_os_str());
        match fs::symlink_metadata(&at) {
            Ok(metadata) if metadata.is_symlink() => {
                return Err(Error::new(
                    ReasonCode::IntegrityMismatch,
                    format!(
                        "{} is a symbolic link and is not written through",
                        at.display()
                    ),
                ));
            }
            Ok(_) => {}
            Err(source) if source.kind() == std::io::ErrorKind::NotFound => {}
            Err(source) => {
                return Err(Error::new(
                    ReasonCode::StateUnavailable,
                    format!("cannot read {}", at.display()),
                )
                .with_source(source));
            }
        }
    }
    Ok(())
}

/// Remove one file and flush the directory that held it.
///
/// An unlink without a directory flush is as provisional as a rename without
/// one: a crash can resurrect the entry. Durable deletes go through here for
/// the same reason durable writes go through [`atomic_write`].
///
/// # Errors
///
/// Propagates the `remove_file` failure. The directory flush is
/// best-effort, as it is for the write side.
pub fn remove_file(path: &Path) -> std::io::Result<()> {
    fs::remove_file(path)?;
    if let Some(parent) = path.parent() {
        sync_directory(parent);
    }
    Ok(())
}

/// Remove one empty directory and flush the directory that held it. See
/// [`remove_file`].
///
/// # Errors
///
/// Propagates the `remove_dir` failure.
pub fn remove_dir(path: &Path) -> std::io::Result<()> {
    fs::remove_dir(path)?;
    if let Some(parent) = path.parent() {
        sync_directory(parent);
    }
    Ok(())
}

/// Remove a directory tree and flush the directory that held it. See
/// [`remove_file`].
///
/// # Errors
///
/// Propagates the `remove_dir_all` failure.
pub fn remove_dir_all(path: &Path) -> std::io::Result<()> {
    fs::remove_dir_all(path)?;
    if let Some(parent) = path.parent() {
        sync_directory(parent);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::panic)]

    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let base =
            std::env::temp_dir().join(format!("setup-core-lock-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(&base).unwrap();
        base
    }

    #[test]
    fn a_second_holder_in_this_process_is_refused_rather_than_silently_merged() {
        // The operating-system lock underneath is process-owned, so this second
        // acquisition would succeed on its own. The in-process claim is what
        // makes it a refusal, and this test fails if that claim is removed.
        let control = scratch("contended");
        let first = TargetLock::acquire(&control).unwrap();
        let error = TargetLock::acquire(&control).unwrap_err();
        assert_eq!(error.reason(), ReasonCode::LockUnavailable);
        drop(first);
    }

    #[test]
    fn a_refused_acquisition_does_not_strand_the_claim_it_failed_to_complete() {
        let control = scratch("no-leak");
        let first = TargetLock::acquire(&control).unwrap();
        assert!(TargetLock::acquire(&control).is_err());
        assert!(TargetLock::acquire(&control).is_err());
        drop(first);
        // If the refused attempts had leaked their claim, this would fail.
        assert!(TargetLock::acquire(&control).is_ok());
        let lock = control.join(LOCK_FILE_NAME);
        let other = control.join("unrelated");
        fs::write(&other, b"leave unchanged").unwrap();
        fs::remove_file(&lock).unwrap();
        fs::hard_link(&other, &lock).unwrap();
        assert!(TargetLock::acquire(&control).is_err());
        fs::remove_file(&lock).unwrap();
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(&other, &lock).unwrap();
            assert!(TargetLock::acquire(&control).is_err());
            fs::remove_file(&lock).unwrap();
        }
        assert!(TargetLock::acquire(&control).is_ok());
        assert_eq!(fs::read(other).unwrap(), b"leave unchanged");
    }

    #[test]
    fn the_lock_is_released_when_the_holder_is_dropped() {
        let control = scratch("released");
        drop(TargetLock::acquire(&control).unwrap());
        let second = TargetLock::acquire(&control);
        assert!(second.is_ok());
    }

    #[test]
    fn two_targets_do_not_contend() {
        let one = scratch("target-one");
        let two = scratch("target-two");
        let first = TargetLock::acquire(&one).unwrap();
        let second = TargetLock::acquire(&two);
        assert!(second.is_ok());
        drop(first);
    }

    #[test]
    fn an_atomic_write_creates_the_directories_its_path_names() {
        // A nested namespace is written before its directory exists: Codex's
        // `.agents/skills` and every Antigravity namespace are the first thing
        // to create their own parent. This failed with "cannot stage" until the
        // creation moved in here, where both write paths reach it.
        let base = scratch("atomic-nested");
        let file = base.join("antigravity-cli").join("settings.json");
        atomic_write(&file, b"{}").unwrap();
        assert_eq!(fs::read(&file).unwrap(), b"{}");

        let deeper = base.join("a").join("b").join("c").join("leaf");
        atomic_write(&deeper, b"deep").unwrap();
        assert_eq!(fs::read(&deeper).unwrap(), b"deep");
    }

    #[test]
    fn an_atomic_write_replaces_contents_and_leaves_no_staging_file() {
        let base = scratch("atomic");
        let file = base.join("state.json");
        atomic_write(&file, b"first").unwrap();
        atomic_write(&file, b"second").unwrap();
        assert_eq!(fs::read(&file).unwrap(), b"second");
        assert!(!base.join(".state.json.staging").exists());
    }

    #[cfg(unix)]
    #[test]
    fn an_atomic_write_keeps_the_permissions_the_file_had() {
        use std::os::unix::fs::PermissionsExt;

        let base = scratch("atomic-mode");
        let file = base.join("secrets.json");
        atomic_write(&file, b"first").unwrap();
        let mut mode = fs::metadata(&file).unwrap().permissions();
        mode.set_mode(0o600);
        fs::set_permissions(&file, mode).unwrap();

        atomic_write(&file, b"second").unwrap();

        assert_eq!(
            fs::metadata(&file).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(fs::read(&file).unwrap(), b"second");
    }
}
