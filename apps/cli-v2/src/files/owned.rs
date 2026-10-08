//! Private, owned directories with bounded locking and durable file replacement.

use crate::{
    error::{Failure, Result},
    files,
};
use cap_fs_ext::{DirExt, FollowSymlinks, OpenOptionsFollowExt, OpenOptionsSyncExt};
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
        let lock = directory
            .open_with("lock", &lock_options)
            .map_err(|_| invalid())?
            .into_std();
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
            None if create => {
                if owned
                    .directory
                    .entries()
                    .map_err(|_| invalid())?
                    .any(|entry| entry.map_or(true, |entry| entry.file_name() != "lock"))
                {
                    return Err(invalid());
                }
                owned.atomic("owner", expected_owner)?;
            }
            _ => return Err(invalid()),
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
