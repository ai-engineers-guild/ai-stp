//! Private, owned directories with bounded locking and durable file replacement.

use crate::{
    error::{ErrorKind, Failure, Result},
    files,
};
use cap_fs_ext::{DirExt, FollowSymlinks, MetadataExt, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::{Dir, DirBuilder, OpenOptions};
use std::{
    io::{Read, Write},
    path::Path,
    thread,
    time::{Duration, Instant},
};

pub(crate) struct OwnedDirectory {
    pub directory: Dir,
    _lock: std::fs::File,
}

fn invalid(stage: &'static str) -> Failure {
    Failure::precondition("explicit private directory is invalid or inaccessible")
        .with_details([("stage".into(), stage.into())])
}

fn io_failure(stage: &'static str, error: std::io::Error) -> Failure {
    // OS error numbers are diagnostic; never include paths or error strings.
    invalid(stage).with_details([("os_error".into(), error.raw_os_error().into())])
}

pub(crate) fn private_options() -> OpenOptions {
    let mut options = OpenOptions::new();
    options
        .write(true)
        .follow(FollowSymlinks::No)
        .nonblock(true);
    #[cfg(unix)]
    {
        use cap_std::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options
}

impl OwnedDirectory {
    pub fn open(root: &Path, name: &str, owner: &[u8], create: bool) -> Result<Option<Self>> {
        let parent = Dir::open_ambient_dir(root, cap_std::ambient_authority())
            .map_err(|error| io_failure("parent_open", error))?;
        Self::open_at(&parent, name, owner, create)
    }

    pub fn open_at(parent: &Dir, name: &str, owner: &[u8], create: bool) -> Result<Option<Self>> {
        if create {
            let mut builder = DirBuilder::new();
            builder.recursive(false);
            #[cfg(unix)]
            {
                use cap_std::fs::DirBuilderExt;
                builder.mode(0o700);
            }
            match parent.create_dir_with(name, &builder) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => return Err(io_failure("directory_create", error)),
            }
        }
        let directory = match parent.open_dir_nofollow(name) {
            Ok(directory) => directory,
            Err(error) if !create && error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(None);
            }
            Err(error) => return Err(io_failure("directory_open", error)),
        };
        #[cfg(unix)]
        {
            use cap_std::fs::PermissionsExt;
            if directory
                .dir_metadata()
                .map_err(|error| io_failure("directory_metadata", error))?
                .permissions()
                .mode()
                & 0o077
                != 0
            {
                return Err(invalid("directory_permissions"));
            }
        }
        let mut lock_options = private_options();
        lock_options.read(true);
        // Elect the creator atomically, then join the existing inode. Concurrent
        // O_CREAT opens can fail with ENOENT on Darwin even for this bare leaf.
        // Neither path replaces the lock or follows a substituted symlink.
        let opened = if create {
            match directory.open_with("lock", lock_options.clone().create_new(true)) {
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                    directory.open_with("lock", &lock_options)
                }
                result => result,
            }
        } else {
            directory.open_with("lock", &lock_options)
        };
        let lock = match opened {
            Ok(lock) => lock.into_std(),
            Err(error) if !create && error.kind() == std::io::ErrorKind::NotFound => {
                if directory
                    .entries()
                    .map_err(|error| io_failure("directory_inventory", error))?
                    .next()
                    .is_none()
                {
                    return Ok(None);
                }
                return Err(invalid("lock_missing"));
            }
            Err(error) => return Err(io_failure("lock_open", error)),
        };
        if !lock
            .metadata()
            .map_err(|error| io_failure("lock_metadata", error))?
            .is_file()
        {
            return Err(invalid("lock_type"));
        }
        let started = Instant::now();
        loop {
            match lock.try_lock() {
                Ok(()) => break,
                Err(std::fs::TryLockError::WouldBlock)
                    if started.elapsed() < Duration::from_secs(2) =>
                {
                    thread::sleep(Duration::from_millis(20))
                }
                Err(std::fs::TryLockError::Error(error)) => {
                    return Err(io_failure("lock_acquire", error));
                }
                Err(std::fs::TryLockError::WouldBlock) => {
                    return Err(Failure::new(
                        ErrorKind::Unavailable,
                        "explicit private directory is temporarily locked by another operation",
                    )
                    .with_details([("stage".into(), "lock_timeout".into())]));
                }
            }
        }
        let owned = Self {
            directory,
            _lock: lock,
        };
        let expected_owner = owner;
        match owned.read_file("owner", 256)? {
            Some(owner) if owner == expected_owner => {}
            held if expected_owner.starts_with(held.as_deref().unwrap_or_default()) => {
                if owned
                    .directory
                    .entries()
                    .map_err(|error| io_failure("owner_inventory", error))?
                    .any(|entry| {
                        entry.map_or(true, |entry| {
                            !matches!(entry.file_name().to_str(), Some("lock" | "owner"))
                        })
                    })
                {
                    return Err(invalid("owner_unclaimed_content"));
                }
                if !create {
                    return Ok(None);
                }
                // The initial owner is immutable. Complete only its exact
                // prefix under the lock, while no application data exists.
                // A temporary-file rename here could strand an unowned stage
                // after interruption before the first owner was published.
                let mut file = owned
                    .directory
                    .open_with("owner", private_options().read(true).create(true))
                    .map_err(|error| io_failure("owner_open", error))?;
                let metadata = file
                    .metadata()
                    .map_err(|error| io_failure("owner_metadata", error))?;
                if !metadata.is_file() || metadata.nlink() != 1 {
                    return Err(invalid("owner_type"));
                }
                let mut prefix = Vec::new();
                Read::by_ref(&mut file)
                    .take(257)
                    .read_to_end(&mut prefix)
                    .map_err(|error| io_failure("owner_read", error))?;
                if !expected_owner.starts_with(&prefix) {
                    return Err(invalid("owner_prefix"));
                }
                file.write_all(&expected_owner[prefix.len()..])
                    .and_then(|_| file.sync_all())
                    .map_err(|error| io_failure("owner_write", error))?;
            }
            _ => return Err(invalid("owner_mismatch")),
        }
        if create {
            // Reflush on retry as well: a previous call may have written all
            // owner bytes but failed before acknowledging durable ownership.
            let file = owned
                .directory
                .open_with("owner", &private_options())
                .map_err(|error| io_failure("owner_flush_open", error))?;
            if file
                .metadata()
                .map_err(|error| io_failure("owner_flush_metadata", error))?
                .nlink()
                != 1
            {
                return Err(invalid("owner_links"));
            }
            file.sync_all()
                .map_err(|error| io_failure("owner_flush", error))?;
            owned.sync()?;
            #[cfg(unix)]
            parent
                .open(".")
                .and_then(|file| file.sync_all())
                .map_err(|error| io_failure("parent_flush", error))?;
        }
        Ok(Some(owned))
    }

    pub fn read_file(&self, name: &str, max: u64) -> Result<Option<Vec<u8>>> {
        let file = match files::open_regular(&self.directory, Path::new(name)) {
            Ok(file) => file,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(io_failure("file_open", error)),
        };
        let mut bytes = Vec::new();
        file.take(max + 1)
            .read_to_end(&mut bytes)
            .map_err(|error| io_failure("file_read", error))?;
        if bytes.len() as u64 > max {
            return Err(invalid("file_size"));
        }
        Ok(Some(bytes))
    }

    pub fn atomic(&self, name: &str, bytes: &[u8]) -> Result<()> {
        let temporary = format!(".tmp-{}", ulid::Ulid::generate());
        let result = (|| {
            let mut file = self
                .directory
                .open_with(&temporary, private_options().create_new(true))
                .map_err(|error| io_failure("temporary_create", error))?;
            file.write_all(bytes)
                .and_then(|_| file.sync_all())
                .map_err(|error| io_failure("temporary_write", error))?;
            drop(file);
            self.directory
                .rename(&temporary, &self.directory, name)
                .map_err(|error| io_failure("temporary_publish", error))?;
            self.sync()
        })();
        if result.is_err() {
            let _ = self.directory.remove_file(&temporary);
        }
        result
    }

    pub fn sync(&self) -> Result<()> {
        #[cfg(unix)]
        self.directory
            .open(".")
            .map_err(|error| io_failure("directory_flush_open", error))?
            .sync_all()
            .map_err(|error| io_failure("directory_flush", error))?;
        Ok(())
    }
}
