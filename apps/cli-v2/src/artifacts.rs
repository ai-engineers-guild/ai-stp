//! Closed component artifacts and the canonical uncompressed ZIP wire encoding.

use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::{Cursor, Read},
};
use unicode_normalization::UnicodeNormalization;

use crate::{
    canonical, digest,
    error::{Failure, Result},
};

pub const FILE_FORMAT: &str = "ai-stp-component-file/1";
pub const TREE_FORMAT: &str = "ai-stp-component-tree/1";
pub const MAX_FILE_BYTES: usize = 4 * 1024 * 1024;
pub const MAX_TREE_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_FILES: usize = 1000;

#[derive(Clone, Debug, PartialEq)]
pub struct Member {
    pub path: String,
    pub bytes: Vec<u8>,
    pub mode: u32,
}

fn invalid() -> Failure {
    Failure::precondition("the artifact violates its path, identity, metadata or size contract")
}

pub fn safe_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 1024
        && !path.starts_with(['/', '~'])
        && !path.contains(['\\', ':', '<', '>', '"', '|', '?', '*'])
        && path.nfc().eq(path.chars())
        && !path.chars().any(char::is_control)
        && path.split('/').all(|part| {
            !part.is_empty()
                && ![".", ".."].contains(&part)
                && part.len() <= 255
                && !part.ends_with(['.', ' '])
                && !reserved_device(part)
        })
}

fn reserved_device(part: &str) -> bool {
    let stem = part
        .split('.')
        .next()
        .unwrap_or_default()
        .to_ascii_uppercase();
    matches!(
        stem.as_str(),
        "CON" | "PRN" | "AUX" | "NUL" | "CONIN$" | "CONOUT$"
    ) || ["COM", "LPT"].iter().any(|prefix| {
        stem.strip_prefix(prefix).is_some_and(|suffix| {
            matches!(
                suffix,
                "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "¹" | "²" | "³"
            )
        })
    })
}

fn validate(files: &[Member], max_files: usize, max_bytes: usize) -> Result<()> {
    let mut names = BTreeSet::new();
    let mut total = 0;
    if files.len() > max_files {
        return Err(invalid());
    }
    for member in files {
        total += member.bytes.len();
        if !safe_path(&member.path)
            || !matches!(member.mode, 0o644 | 0o755)
            || member.bytes.len() > MAX_FILE_BYTES
            || total > max_bytes
            || !names.insert(unicase::UniCase::new(member.path.as_str()))
        {
            return Err(invalid());
        }
    }
    for member in files {
        let mut path = member.path.as_str();
        while let Some((parent, _)) = path.rsplit_once('/') {
            if names.contains(&unicase::UniCase::new(parent)) {
                return Err(invalid());
            }
            path = parent;
        }
    }
    Ok(())
}

/// Exact ZIP_STORED profile: fixed epoch, Unix regular files, UTF-8 names and
/// version 2.0 headers. zip's general writer chooses version 1.0 for stored
/// members; those different bytes would change existing artifact identities.
/// This bounded serializer owns only our wire profile; zip owns input decoding.
pub fn zip_stored(files: &[Member]) -> Result<Vec<u8>> {
    validate(files, 2000, 64 * 1024 * 1024)?;
    let mut output = Vec::new();
    let mut central = Vec::new();
    for member in files {
        let name = member.path.as_bytes();
        let flag: u16 = if name.is_ascii() { 0 } else { 1 << 11 };
        let size = member.bytes.len() as u32;
        let crc = crc32fast::hash(&member.bytes);
        let offset = output.len() as u32;
        output.extend(0x04034b50_u32.to_le_bytes());
        for field in [20_u16, flag, 0, 0, 33] {
            output.extend(field.to_le_bytes());
        }
        for field in [crc, size, size] {
            output.extend(field.to_le_bytes());
        }
        for field in [name.len() as u16, 0] {
            output.extend(field.to_le_bytes());
        }
        output.extend(name);
        output.extend(&member.bytes);
        central.extend(0x02014b50_u32.to_le_bytes());
        for field in [0x0314_u16, 20, flag, 0, 0, 33] {
            central.extend(field.to_le_bytes());
        }
        for field in [crc, size, size] {
            central.extend(field.to_le_bytes());
        }
        for field in [name.len() as u16, 0, 0, 0, 0] {
            central.extend(field.to_le_bytes());
        }
        central.extend(((0o100000 | member.mode) << 16).to_le_bytes());
        central.extend(offset.to_le_bytes());
        central.extend(name);
    }
    let offset = output.len() as u32;
    let size = central.len() as u32;
    output.extend(central);
    output.extend(0x06054b50_u32.to_le_bytes());
    for field in [0_u16, 0, files.len() as u16, files.len() as u16] {
        output.extend(field.to_le_bytes());
    }
    output.extend(size.to_le_bytes());
    output.extend(offset.to_le_bytes());
    output.extend(0_u16.to_le_bytes());
    Ok(output)
}

pub fn encode_tree(files: &[Member]) -> Result<Vec<u8>> {
    validate(files, MAX_FILES, MAX_TREE_BYTES)?;
    let mut ordered: Vec<_> = files.iter().collect();
    ordered.sort_by(|a, b| a.path.cmp(&b.path));
    let entries = ordered
        .iter()
        .map(|member| {
            Ok(json!({
                "path": member.path, "digest": digest::bytes("ai-stp:artifact:v1", &member.bytes)?,
                "byte_length": member.bytes.len(), "mode": member.mode
            }))
        })
        .collect::<Result<Vec<Value>>>()?;
    let manifest = canonical::bytes(&json!({"format": TREE_FORMAT, "files": entries}))?;
    if manifest.len() + files.iter().map(|item| item.bytes.len()).sum::<usize>() > MAX_TREE_BYTES {
        return Err(invalid());
    }
    let mut members = vec![Member {
        path: "component.json".into(),
        bytes: manifest,
        mode: 0o644,
    }];
    members.extend(ordered.into_iter().map(|member| Member {
        path: format!("files/{}", member.path),
        bytes: member.bytes.clone(),
        mode: member.mode,
    }));
    zip_stored(&members)
}

pub fn decode_tree(payload: &[u8]) -> Result<Vec<Member>> {
    if payload.len() > MAX_TREE_BYTES + 4 * 1024 * 1024 {
        return Err(invalid());
    }
    // Bound central-directory allocation before the general ZIP reader runs.
    // This profile has one disk, a 32-bit directory and no archive comment.
    let end = payload.len().checked_sub(22).ok_or_else(invalid)?;
    let footer = &payload[end..];
    let count = u16::from_le_bytes([footer[10], footer[11]]) as usize;
    let directory_size =
        u32::from_le_bytes(footer[12..16].try_into().map_err(|_| invalid())?) as usize;
    let directory_start =
        u32::from_le_bytes(footer[16..20].try_into().map_err(|_| invalid())?) as usize;
    if &footer[..4] != b"PK\x05\x06"
        || footer[4..8] != [0; 4]
        || footer[8..10] != footer[10..12]
        || footer[20..22] != [0; 2]
        || count > MAX_FILES + 1
        || directory_start.checked_add(directory_size) != Some(end)
    {
        return Err(invalid());
    }
    let mut archive = zip::ZipArchive::new(Cursor::new(payload)).map_err(|_| invalid())?;
    // zip indexes by name and otherwise hides repeated central-directory names.
    if archive.len() != count
        || archive.offset() != 0
        || archive.central_directory_start() != directory_start as u64
    {
        return Err(invalid());
    }
    let mut members = BTreeMap::new();
    let mut names = BTreeSet::new();
    let mut total: u64 = 0;
    for index in 0..archive.len() {
        let file = archive.by_index(index).map_err(|_| invalid())?;
        let path = file.name().to_owned();
        let mode = file.unix_mode().ok_or_else(invalid)?;
        total = total.checked_add(file.size()).ok_or_else(invalid)?;
        if !safe_path(&path)
            || !names.insert(unicase::UniCase::new(path.clone()))
            || file.compression() != zip::CompressionMethod::Stored
            || file.encrypted()
            || file.is_dir()
            || mode & 0o170000 != 0o100000
            || !matches!(mode & 0o7777, 0o644 | 0o755)
            || file.size() > MAX_FILE_BYTES as u64
            || total > MAX_TREE_BYTES as u64
        {
            return Err(invalid());
        }
        let size = file.size();
        let mut bytes = Vec::new();
        file.take(MAX_FILE_BYTES as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| invalid())?;
        if bytes.len() as u64 != size {
            return Err(invalid());
        }
        members.insert(path, (bytes, mode & 0o777));
    }
    let (manifest, mode) = members.remove("component.json").ok_or_else(invalid)?;
    let document = canonical::parse(&manifest)?;
    if mode != 0o644
        || canonical::bytes(&document)? != manifest
        || document.as_object().is_none_or(|fields| fields.len() != 2)
        || document["format"] != TREE_FORMAT
    {
        return Err(invalid());
    }
    let entries = document["files"].as_array().ok_or_else(invalid)?;
    if entries.len() > MAX_FILES {
        return Err(invalid());
    }
    let mut files = Vec::new();
    for entry in entries {
        let path = entry["path"]
            .as_str()
            .filter(|path| safe_path(path))
            .ok_or_else(invalid)?;
        if entry.as_object().is_none_or(|fields| fields.len() != 4) {
            return Err(invalid());
        }
        let (bytes, mode) = members
            .remove(&format!("files/{path}"))
            .ok_or_else(invalid)?;
        if entry["byte_length"] != bytes.len()
            || entry["mode"] != mode
            || entry["digest"] != digest::bytes("ai-stp:artifact:v1", &bytes)?
        {
            return Err(invalid());
        }
        files.push(Member {
            path: path.into(),
            bytes,
            mode,
        });
    }
    if !members.is_empty() {
        return Err(invalid());
    }
    validate(&files, MAX_FILES, MAX_TREE_BYTES)?;
    if encode_tree(&files)? != payload {
        return Err(invalid());
    }
    Ok(files)
}
