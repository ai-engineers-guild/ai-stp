//! Independently compare a staged payload with the authenticated vendor bytes.

use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::{Read, Seek},
    path::{Component, Path, PathBuf},
    time::{Duration, Instant},
};

use cap_fs_ext::{DirExt, MetadataExt};
use cap_std::fs::{Dir, PermissionsExt};
use serde::Serialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use super::plan::invalid;
use crate::{digest, error::Result, files};

const ENTRIES: usize = 65_536;
const CONTENT: u64 = 8 * 1024 * 1024 * 1024;

#[derive(PartialEq, Eq, Serialize)]
struct Member {
    digest: String,
    bytes: u64,
    mode: u32,
}

#[derive(Default, PartialEq, Eq, Serialize)]
struct Inventory {
    files: BTreeMap<String, Member>,
    directories: BTreeSet<String>,
    bytes: u64,
}

fn relative(path: &Path) -> Result<String> {
    if path.as_os_str().len() > 8192 || path.components().count() > 64 {
        return Err(invalid());
    }
    let mut result = PathBuf::new();
    for part in path.components() {
        match part {
            Component::Normal(name) => result.push(name),
            Component::CurDir => (),
            _ => return Err(invalid()),
        }
    }
    result
        .to_str()
        .filter(|p| !p.is_empty())
        .map(str::to_owned)
        .ok_or_else(invalid)
}

fn contents(mut input: impl Read, size: u64, started: Instant) -> Result<String> {
    if size > CONTENT {
        return Err(invalid());
    }
    let mut hash = Sha256::new();
    let mut count = 0u64;
    let mut buffer = [0u8; 64 * 1024];
    loop {
        if started.elapsed() > Duration::from_secs(300) {
            return Err(invalid());
        }
        let n = input.read(&mut buffer).map_err(|_| invalid())?;
        if n == 0 {
            break;
        }
        count = count.checked_add(n as u64).ok_or_else(invalid)?;
        if count > size {
            return Err(invalid());
        }
        hash.update(&buffer[..n]);
    }
    if count != size {
        return Err(invalid());
    }
    Ok(digest::representation(&hash.finalize()))
}

impl Inventory {
    fn parents(&mut self, path: &str) -> Result<()> {
        for parent in Path::new(path).ancestors().skip(1) {
            if parent.as_os_str().is_empty() {
                break;
            }
            let parent = relative(parent)?;
            if self.files.contains_key(&parent) {
                return Err(invalid());
            }
            self.directories.insert(parent);
        }
        self.bounded()
    }

    fn bounded(&self) -> Result<()> {
        if self.files.len() + self.directories.len() > ENTRIES || self.bytes > CONTENT {
            return Err(invalid());
        }
        Ok(())
    }

    fn insert(&mut self, path: String, member: Member) -> Result<()> {
        if self.directories.contains(&path) {
            return Err(invalid());
        }
        self.bytes = self.bytes.checked_add(member.bytes).ok_or_else(invalid)?;
        self.parents(&path)?;
        if self.files.insert(path, member).is_some() {
            return Err(invalid());
        }
        self.bounded()
    }
}

fn archive(file: &mut File, command: &str, started: Instant) -> Result<(Inventory, usize)> {
    let mut magic = [0; 2];
    file.rewind()
        .and_then(|()| file.read_exact(&mut magic))
        .map_err(|_| invalid())?;
    file.rewind().map_err(|_| invalid())?;
    let mut inventory = Inventory::default();
    if magic != [0x1f, 0x8b] {
        let bytes = file.metadata().map_err(|_| invalid())?.len();
        inventory.insert(
            command.into(),
            Member {
                digest: contents(file, bytes, started)?,
                bytes,
                mode: 0o755,
            },
        )?;
        return Ok((inventory, 1));
    }
    let mut tar = tar::Archive::new(flate2::read::GzDecoder::new(file));
    let mut names = BTreeSet::new();
    for entry in tar.entries().map_err(|_| invalid())? {
        let mut entry = entry.map_err(|_| invalid())?;
        let name = relative(&entry.path().map_err(|_| invalid())?)?;
        if !names.insert(name.clone()) || names.len() > ENTRIES {
            return Err(invalid());
        }
        let kind = entry.header().entry_type();
        if kind.is_dir() {
            if inventory.files.contains_key(&name) {
                return Err(invalid());
            }
            inventory.parents(&name)?;
            inventory.directories.insert(name);
            inventory.bounded()?;
        } else if kind.is_file() {
            let bytes = entry.size();
            if inventory
                .bytes
                .checked_add(bytes)
                .is_none_or(|n| n > CONTENT)
            {
                return Err(invalid());
            }
            let mode = if entry.header().mode().map_err(|_| invalid())? & 0o111 != 0 {
                0o755
            } else {
                0o644
            };
            let digest = contents(&mut entry, bytes, started)?;
            inventory.insert(
                name,
                Member {
                    digest,
                    bytes,
                    mode,
                },
            )?;
        } else {
            return Err(invalid());
        }
    }
    if inventory.files.is_empty() {
        return Err(invalid());
    }
    Ok((inventory, names.len()))
}

fn installed(
    directory: &Dir,
    root: &Path,
    inventory: &mut Inventory,
    started: Instant,
) -> Result<()> {
    for entry in directory.entries().map_err(|_| invalid())? {
        let entry = entry.map_err(|_| invalid())?;
        let leaf = entry.file_name();
        let path = root.join(&leaf);
        let name = relative(&path)?;
        let meta = directory.symlink_metadata(&leaf).map_err(|_| invalid())?;
        if meta.is_dir() {
            if meta.permissions().mode() & 0o7777 != 0o755 {
                return Err(invalid());
            }
            inventory.directories.insert(name);
            inventory.bounded()?;
            installed(
                &directory.open_dir_nofollow(leaf).map_err(|_| invalid())?,
                &path,
                inventory,
                started,
            )?;
        } else if meta.is_file() && meta.nlink() == 1 {
            let mut file =
                files::open_regular(directory, Path::new(&leaf)).map_err(|_| invalid())?;
            let held = file.metadata().map_err(|_| invalid())?;
            if held.dev() != meta.dev() || held.ino() != meta.ino() {
                return Err(invalid());
            }
            let member = Member {
                digest: contents(&mut file, held.len(), started)?,
                bytes: held.len(),
                mode: held.permissions().mode() & 0o7777,
            };
            let after = file.metadata().map_err(|_| invalid())?;
            if after.len() != held.len() || after.modified().ok() != held.modified().ok() {
                return Err(invalid());
            }
            inventory.insert(name, member)?;
        } else {
            return Err(invalid());
        }
    }
    Ok(())
}

pub(super) fn payload(
    root: &Dir,
    source: &mut File,
    version: &str,
    entry_point: &str,
    final_prefix: &Path,
) -> Result<Value> {
    let started = Instant::now();
    let command = entry_point.strip_prefix("bin/").ok_or_else(invalid)?;
    let (expected, archive_entries) = archive(source, command, started)?;
    let version_root = root.open_dir_nofollow(version).map_err(|_| invalid())?;
    let mut actual = Inventory::default();
    installed(&version_root, Path::new(""), &mut actual, started)?;
    if actual != expected {
        return Err(invalid());
    }
    let bin = root.open_dir_nofollow("bin").map_err(|_| invalid())?;
    for directory in [&version_root, &bin] {
        if directory
            .dir_metadata()
            .map_err(|_| invalid())?
            .permissions()
            .mode()
            & 0o7777
            != 0o755
        {
            return Err(invalid());
        }
    }
    let link = bin.read_link_contents(command).map_err(|_| invalid())?;
    // The component binds its Unix launcher to the canonical final path even
    // while that path names the private mount. Never follow it on the host.
    let member = relative(
        link.strip_prefix(final_prefix.join(version))
            .map_err(|_| invalid())?,
    )?;
    if !actual.files.get(&member).is_some_and(|m| m.mode == 0o755) {
        return Err(invalid());
    }
    let marker_name = format!(".{command}.version");
    let manifest_name = format!(".{command}.manifest.json");
    if record(&bin, &marker_name)? != version.as_bytes() {
        return Err(invalid());
    }
    let manifest = crate::wire::parse(&record(&bin, &manifest_name)?)?;
    if manifest
        != json!({"schema_version":1,"version":version,
        "executable":format!("{version}/{member}"),"executable_sha256":actual.files[&member].digest})
    {
        return Err(invalid());
    }
    let bin_members = bin
        .entries()
        .map_err(|_| invalid())?
        .take(4)
        .map(|e| e.map(|e| e.file_name()))
        .collect::<std::io::Result<BTreeSet<_>>>()
        .map_err(|_| invalid())?;
    if bin_members
        != [command, marker_name.as_str(), manifest_name.as_str()]
            .map(std::ffi::OsString::from)
            .into()
    {
        return Err(invalid());
    }
    root.open_dir_nofollow(".nddev-software")
        .map_err(|_| invalid())?;
    let members = root
        .entries()
        .map_err(|_| invalid())?
        .take(4)
        .map(|e| e.map(|e| e.file_name()))
        .collect::<std::io::Result<BTreeSet<_>>>()
        .map_err(|_| invalid())?;
    if members
        != [version, "bin", ".nddev-software"]
            .map(std::ffi::OsString::from)
            .into()
    {
        return Err(invalid());
    }
    let bytes = serde_json_canonicalizer::to_vec(&actual).map_err(|_| invalid())?;
    Ok(
        json!({"verification":"exact_vendor_archive_inventory", "files":actual.files.len(), "archive_entries":archive_entries, "bytes":actual.bytes,
        "inventory_digest":digest::sha256(&bytes), "entry_point":entry_point,"member":member}),
    )
}

fn record(parent: &Dir, name: &str) -> Result<Vec<u8>> {
    let file = files::open_regular(parent, Path::new(name)).map_err(|_| invalid())?;
    let metadata = file.metadata().map_err(|_| invalid())?;
    if metadata.nlink() != 1
        || metadata.len() > 16 * 1024
        || metadata.permissions().mode() & 0o7777 != 0o600
    {
        return Err(invalid());
    }
    let mut bytes = Vec::new();
    file.take(16 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| invalid())?;
    if bytes.len() as u64 != metadata.len() {
        return Err(invalid());
    }
    Ok(bytes)
}
