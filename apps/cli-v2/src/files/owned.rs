//! Private, owned directories with bounded locking and durable file replacement.

use crate::{
    error::{Failure, Result},
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

fn invalid() -> Failure {
    Failure::precondition("explicit private directory is invalid, busy or inaccessible")
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
        let parent =
            Dir::open_ambient_dir(root, cap_std::ambient_authority()).map_err(|_| invalid())?;
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
                Err(_) => return Err(invalid()),
            }
        }
        let directory = match parent.open_dir_nofollow(name) {
            Ok(directory) => directory,
            Err(error) if !create && error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(None);
            }
            Err(_) => return Err(invalid()),
        };
        #[cfg(unix)]
        {
            use cap_std::fs::PermissionsExt;
            if directory
                .dir_metadata()
                .map_err(|_| invalid())?
                .permissions()
                .mode()
                & 0o077
                != 0
            {
                return Err(invalid());
            }
        }
        let mut lock_options = private_options();
        lock_options.read(true).create(create);
        let lock = match directory.open_with("lock", &lock_options) {
            Ok(lock) => lock.into_std(),
            Err(error) if !create && error.kind() == std::io::ErrorKind::NotFound => {
                if directory.entries().map_err(|_| invalid())?.next().is_none() {
                    return Ok(None);
                }
                return Err(invalid());
            }
            Err(_) => return Err(invalid()),
        };
        if !lock.metadata().map_err(|_| invalid())?.is_file() {
            return Err(invalid());
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
                Err(_) => return Err(invalid()),
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
                    .map_err(|_| invalid())?
                    .any(|entry| {
                        entry.map_or(true, |entry| {
                            !matches!(entry.file_name().to_str(), Some("lock" | "owner"))
                        })
                    })
                {
                    return Err(invalid());
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
                    .map_err(|_| invalid())?;
                let metadata = file.metadata().map_err(|_| invalid())?;
                if !metadata.is_file() || metadata.nlink() != 1 {
                    return Err(invalid());
                }
                let mut prefix = Vec::new();
                Read::by_ref(&mut file)
                    .take(257)
                    .read_to_end(&mut prefix)
                    .map_err(|_| invalid())?;
                if !expected_owner.starts_with(&prefix) {
                    return Err(invalid());
                }
                file.write_all(&expected_owner[prefix.len()..])
                    .and_then(|_| file.sync_all())
                    .map_err(|_| invalid())?;
            }
            _ => return Err(invalid()),
        }
        if create {
            // Reflush on retry as well: a previous call may have written all
            // owner bytes but failed before acknowledging durable ownership.
            let file = owned
                .directory
                .open_with("owner", &private_options())
                .map_err(|_| invalid())?;
            if file.metadata().map_err(|_| invalid())?.nlink() != 1 {
                return Err(invalid());
            }
            file.sync_all().map_err(|_| invalid())?;
            owned.sync()?;
            #[cfg(unix)]
            parent
                .open(".")
                .and_then(|file| file.sync_all())
                .map_err(|_| invalid())?;
        }
        Ok(Some(owned))
    }

    pub fn read_file(&self, name: &str, max: u64) -> Result<Option<Vec<u8>>> {
        let file = match files::open_regular(&self.directory, Path::new(name)) {
            Ok(file) => file,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(_) => return Err(invalid()),
        };
        let mut bytes = Vec::new();
        file.take(max + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| invalid())?;
        if bytes.len() as u64 > max {
            return Err(invalid());
        }
        Ok(Some(bytes))
    }

    pub fn atomic(&self, name: &str, bytes: &[u8]) -> Result<()> {
        let temporary = format!(".tmp-{}", ulid::Ulid::generate());
        let result = (|| {
            let mut file = self
                .directory
                .open_with(&temporary, private_options().create_new(true))
                .map_err(|_| invalid())?;
            file.write_all(bytes)
                .and_then(|_| file.sync_all())
                .map_err(|_| invalid())?;
            drop(file);
            self.directory
                .rename(&temporary, &self.directory, name)
                .map_err(|_| invalid())?;
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
            .map_err(|_| invalid())?
            .sync_all()
            .map_err(|_| invalid())?;
        Ok(())
    }
}
