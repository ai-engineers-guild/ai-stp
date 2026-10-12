//! Bounded observations of the program entries an operation must preserve.

use super::super::plan::{Existing, invalid};
use crate::{digest, error::Result, files};
use cap_fs_ext::{DirExt, MetadataExt};
use cap_std::fs::{Dir, PermissionsExt};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::Read,
    path::Path,
    time::{Duration, Instant},
};

struct Inventory {
    entries: BTreeMap<String, Value>,
    bytes: u64,
    started: Instant,
    identities: bool,
}

impl Inventory {
    fn new() -> Self {
        Self {
            entries: BTreeMap::new(),
            bytes: 0,
            started: Instant::now(),
            identities: false,
        }
    }

    fn entry(&mut self, directory: &Dir, leaf: &str, path: &str) -> Result<Option<Value>> {
        if path.len() > 8192
            || path.split('/').count() > 64
            || self.entries.len() >= 65_536
            || self.started.elapsed() > Duration::from_secs(300)
        {
            return Err(invalid());
        }
        let metadata = match directory.symlink_metadata(leaf) {
            Ok(value) => value,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(_) => return Err(invalid()),
        };
        let mode = metadata.permissions().mode() & 0o7777;
        let value = if metadata.is_symlink() {
            let link = directory.read_link_contents(leaf).map_err(|_| invalid())?;
            let link = link
                .to_str()
                .filter(|v| v.len() <= 8192)
                .ok_or_else(invalid)?;
            json!({"kind":"link","value":link,"mode":mode})
        } else if metadata.is_dir() {
            json!({"kind":"directory","mode":mode})
        } else if metadata.is_file() && metadata.nlink() == 1 {
            self.bytes = self.bytes.checked_add(metadata.len()).ok_or_else(invalid)?;
            if self.bytes > 8 * 1024 * 1024 * 1024 {
                return Err(invalid());
            }
            let mut file =
                files::open_regular(directory, Path::new(leaf)).map_err(|_| invalid())?;
            let held = file.metadata().map_err(|_| invalid())?;
            if (held.dev(), held.ino(), held.len())
                != (metadata.dev(), metadata.ino(), metadata.len())
            {
                return Err(invalid());
            }
            let mut hash = Sha256::new();
            let mut count = 0;
            let mut buffer = [0; 64 * 1024];
            loop {
                if self.started.elapsed() > Duration::from_secs(300) {
                    return Err(invalid());
                }
                let length = file.read(&mut buffer).map_err(|_| invalid())?;
                if length == 0 {
                    break;
                }
                count += length as u64;
                if count > metadata.len() {
                    return Err(invalid());
                }
                hash.update(&buffer[..length]);
            }
            let after = file.metadata().map_err(|_| invalid())?;
            let named = directory.symlink_metadata(leaf).map_err(|_| invalid())?;
            if count != metadata.len()
                || after.len() != held.len()
                || after.modified().ok() != held.modified().ok()
                || (named.dev(), named.ino()) != (held.dev(), held.ino())
            {
                return Err(invalid());
            }
            json!({"kind":"file","mode":mode,"bytes":count,"digest":digest::representation(&hash.finalize())})
        } else {
            return Err(invalid());
        };
        Ok(Some(value))
    }

    fn walk(&mut self, directory: &Dir, prefix: &str, excluded: &BTreeSet<String>) -> Result<()> {
        for entry in directory.entries().map_err(|_| invalid())? {
            let entry = entry.map_err(|_| invalid())?;
            let leaf = entry.file_name();
            let leaf = leaf.to_str().ok_or_else(invalid)?;
            let path = if prefix.is_empty() {
                leaf.to_owned()
            } else {
                format!("{prefix}/{leaf}")
            };
            if excluded.contains(&path) {
                continue;
            }
            let before = directory.symlink_metadata(leaf).map_err(|_| invalid())?;
            let mut value = self.entry(directory, leaf, &path)?.ok_or_else(invalid)?;
            if self.identities {
                value["identity"] = json!([before.dev().to_string(), before.ino().to_string()]);
            }
            let descend = value["kind"] == "directory";
            self.entries.insert(path.clone(), value);
            if descend {
                let child = directory.open_dir_nofollow(leaf).map_err(|_| invalid())?;
                let held = child.dir_metadata().map_err(|_| invalid())?;
                if (held.dev(), held.ino()) != (before.dev(), before.ino()) {
                    return Err(invalid());
                }
                self.walk(&child, &path, excluded)?;
            }
            let after = directory.symlink_metadata(leaf).map_err(|_| invalid())?;
            if (
                before.dev(),
                before.ino(),
                before.permissions().mode(),
                before.len(),
            ) != (
                after.dev(),
                after.ino(),
                after.permissions().mode(),
                after.len(),
            ) || before.modified().map_err(|_| invalid())?
                != after.modified().map_err(|_| invalid())?
            {
                return Err(invalid());
            }
        }
        Ok(())
    }

    fn digest(&self) -> Result<String> {
        Ok(digest::sha256(
            &serde_json_canonicalizer::to_vec(&self.entries).map_err(|_| invalid())?,
        ))
    }
}

pub(super) fn launch_names(entry: &str) -> Result<[String; 3]> {
    let command = entry.strip_prefix("bin/").ok_or_else(invalid)?;
    if command.is_empty() || command.contains('/') {
        return Err(invalid());
    }
    Ok([
        command.into(),
        format!(".{command}.version"),
        format!(".{command}.manifest.json"),
    ])
}

/// Cancellation may change only the component's validated shared metadata.
pub(super) fn unchanged(root: &Dir) -> Result<String> {
    let metadata = root.dir_metadata().map_err(|_| invalid())?;
    let mut inventory = Inventory::new();
    inventory.identities = true;
    inventory.entries.insert(
        String::new(),
        json!({"kind":"directory",
        "mode":metadata.permissions().mode() & 0o7777,
        "identity":[metadata.dev().to_string(), metadata.ino().to_string()]}),
    );
    inventory.walk(root, "", &BTreeSet::from([".nddev-software".into()]))?;
    inventory.digest()
}

pub(super) fn preserved(root: &Dir, version: &str, entry: &str) -> Result<String> {
    let mut excluded = BTreeSet::from([version.into(), ".nddev-software".into()]);
    excluded.extend(launch_names(entry)?.map(|v| format!("bin/{v}")));
    let mut inventory = Inventory::new();
    inventory.walk(root, "", &excluded)?;
    inventory.digest()
}

pub(super) fn launch(root: &Dir, entry: &str) -> Result<String> {
    let bin = root.open_dir_nofollow("bin").map_err(|_| invalid())?;
    let mut inventory = Inventory::new();
    for leaf in launch_names(entry)? {
        if let Some(value) = inventory.entry(&bin, &leaf, &leaf)? {
            inventory.entries.insert(leaf, value);
        }
    }
    inventory.digest()
}

pub(super) fn active(root: &Dir, version: &str, entry: &str) -> Result<bool> {
    let bin = root.open_dir_nofollow("bin").map_err(|_| invalid())?;
    let marker = launch_names(entry)?[1].clone();
    match bin.symlink_metadata(&marker) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(_) => return Err(invalid()),
        Ok(_) => (),
    }
    let file = files::open_regular(&bin, Path::new(&marker)).map_err(|_| invalid())?;
    let mut bytes = Vec::new();
    file.take(1025)
        .read_to_end(&mut bytes)
        .map_err(|_| invalid())?;
    if bytes.len() > 1024 {
        return Err(invalid());
    }
    Ok(bytes == version.as_bytes())
}

pub(super) fn removed(root: &Dir, version: &str, expected: &Existing) -> Result<Value> {
    match root.symlink_metadata(version) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        _ => return Err(invalid()),
    }
    if expected.selected_is_active {
        let bin = root.open_dir_nofollow("bin").map_err(|_| invalid())?;
        for leaf in launch_names(&expected.entry_point)? {
            match bin.symlink_metadata(leaf) {
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                _ => return Err(invalid()),
            }
        }
    } else if launch(root, &expected.entry_point)? != expected.launch_digest {
        return Err(invalid());
    }
    Ok(
        json!({"verification":"selected_version_absent","entry_point":expected.entry_point,
        "preserved_digest":expected.preserved_digest}),
    )
}
