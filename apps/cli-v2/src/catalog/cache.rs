//! Discardable public cache, isolated below an explicitly supplied directory.

use crate::{
    canonical, digest,
    error::{Failure, Result},
    files,
    http::MAX_BODY,
    passport, wire,
};
use cap_fs_ext::{DirExt, FollowSymlinks, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::{Dir, DirBuilder, OpenOptions};
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    path::Path,
    thread,
    time::{Duration, Instant, SystemTime},
};

const OWNER: &[u8] = b"ai-stp-cli-v2 public catalog cache v1\n";
const MAX_CACHE: u64 = 64 * 1024 * 1024;
const MAX_ENTRIES: usize = 64;
pub struct Cache {
    directory: Dir,
    _lock: std::fs::File,
}
pub struct Entry {
    pub document: Value,
    pub checked_at: String,
}
fn invalid() -> Failure {
    Failure::precondition("explicit catalog cache is invalid, busy or inaccessible")
}

fn options() -> OpenOptions {
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

impl Cache {
    pub fn open(root: &Path, create: bool) -> Result<Option<Self>> {
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
            match parent.create_dir_with("ai-stp-v2-catalog", &builder) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(_) => return Err(invalid()),
            }
        }
        let directory = match parent.open_dir_nofollow("ai-stp-v2-catalog") {
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
        let mut lock_options = options();
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
        let cache = Self {
            directory,
            _lock: lock,
        };
        match cache.read_file("owner", 256)? {
            Some(owner) if owner == OWNER => {}
            None if create => {
                if cache
                    .directory
                    .entries()
                    .map_err(|_| invalid())?
                    .any(|entry| entry.map_or(true, |entry| entry.file_name() != "lock"))
                {
                    return Err(invalid());
                }
                cache.atomic("owner", OWNER)?;
            }
            _ => return Err(invalid()),
        }
        Ok(Some(cache))
    }

    fn read_file(&self, name: &str, max: u64) -> Result<Option<Vec<u8>>> {
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

    fn atomic(&self, name: &str, bytes: &[u8]) -> Result<()> {
        let temporary = format!(".tmp-{}", ulid::Ulid::generate());
        let result = (|| {
            let mut file = self
                .directory
                .open_with(&temporary, options().create_new(true))
                .map_err(|_| invalid())?;
            file.write_all(bytes)
                .and_then(|_| file.sync_all())
                .map_err(|_| invalid())?;
            drop(file);
            self.directory
                .rename(&temporary, &self.directory, name)
                .map_err(|_| invalid())
        })();
        if result.is_err() {
            let _ = self.directory.remove_file(&temporary);
        }
        result
    }

    pub fn load(&self, url: &str) -> Result<Option<Entry>> {
        let key = digest::sha256(url.as_bytes());
        let filename = format!("{}.json", &key[7..]);
        let Some(bytes) = self.read_file(&filename, MAX_BODY + 4096)? else {
            return Ok(None);
        };
        let entry = wire::parse(&bytes)?;
        let checked_at = entry["checked_at"]
            .as_str()
            .filter(|v| passport::timestamp(v))
            .ok_or_else(invalid)?;
        if entry["schema_version"] != 1
            || entry["url"] != url
            || entry["key"] != key
            || entry["document_digest"] != digest::sha256(&canonical::bytes(&entry["document"])?)
        {
            return Err(invalid());
        }
        Ok(Some(Entry {
            document: entry["document"].clone(),
            checked_at: checked_at.into(),
        }))
    }

    pub fn store(&self, url: &str, document: &Value, checked_at: &str) -> Result<()> {
        let key = digest::sha256(url.as_bytes());
        let name = format!("{}.json", &key[7..]);
        let bytes = serde_json::to_vec(&json!({"schema_version": 1, "url": url, "key": key,
            "checked_at": checked_at, "document": document, "document_digest": digest::sha256(&canonical::bytes(document)?)})).map_err(|_| invalid())?;
        if bytes.len() as u64 > MAX_BODY + 4096 {
            return Err(invalid());
        }
        let held = self
            .directory
            .entries()
            .map_err(|_| invalid())?
            .take(MAX_ENTRIES + 17)
            .collect::<std::io::Result<Vec<_>>>()
            .map_err(|_| invalid())?;
        if held.len() > MAX_ENTRIES + 16 {
            return Err(invalid());
        }
        let mut entries = Vec::new();
        for entry in held {
            let filename = entry.file_name().into_string().map_err(|_| invalid())?;
            if ["lock", "owner"].contains(&filename.as_str()) {
                continue;
            }
            if filename.starts_with(".tmp-") {
                self.directory
                    .remove_file(&filename)
                    .map_err(|_| invalid())?;
                continue;
            }
            if !filename.is_ascii()
                || filename.len() != 69
                || !filename.ends_with(".json")
                || !filename[..64]
                    .bytes()
                    .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
            {
                return Err(invalid());
            }
            let metadata = entry.metadata().map_err(|_| invalid())?;
            if !metadata.is_file() {
                return Err(invalid());
            }
            entries.push((
                metadata
                    .modified()
                    .map(|t| t.into_std())
                    .unwrap_or(SystemTime::UNIX_EPOCH),
                filename,
                metadata.len(),
            ));
        }
        if entries.len() > MAX_ENTRIES {
            return Err(invalid());
        }
        entries.retain(|(_, held, _)| held != &name);
        entries.sort();
        let mut total = bytes.len() as u64 + entries.iter().map(|(_, _, size)| size).sum::<u64>();
        while total > MAX_CACHE || entries.len() >= MAX_ENTRIES {
            let (_, oldest, size) = entries.remove(0);
            self.directory.remove_file(oldest).map_err(|_| invalid())?;
            total -= size;
        }
        self.atomic(&name, &bytes)
    }
}
