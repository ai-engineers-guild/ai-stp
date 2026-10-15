//! Bounded canonical ZIP transport shared by component trees and projections.

pub(crate) mod external;

use std::{
    borrow::Cow,
    collections::BTreeMap,
    io::{Cursor, Read},
};

use unicode_normalization::UnicodeNormalization;

use crate::error::{Failure, Result};

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum Kind {
    File,
    Directory,
}

pub(crate) struct Entry<'a> {
    /// Portable path without a trailing slash; the kind owns its ZIP spelling.
    pub path: Cow<'a, str>,
    pub bytes: Cow<'a, [u8]>,
    pub mode: u32,
    pub kind: Kind,
}

#[derive(Clone, Copy)]
pub(crate) struct Limits {
    pub entries: usize,
    pub file_bytes: usize,
    pub content_bytes: usize,
    pub archive_bytes: usize,
}

fn invalid() -> Failure {
    Failure::precondition("the archive violates its portable paths, metadata, encoding or bounds")
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

fn validate(entries: &[Entry<'_>], limits: Limits) -> Result<()> {
    if entries.len() > limits.entries || entries.len() >= u16::MAX as usize {
        return Err(invalid());
    }
    let mut names = BTreeMap::new();
    let mut content: usize = 0;
    let mut archive: usize = 22;
    for entry in entries {
        content = content.checked_add(entry.bytes.len()).ok_or_else(invalid)?;
        archive = archive
            .checked_add(76 + 2 * (entry.path.len() + usize::from(entry.kind == Kind::Directory)))
            .and_then(|size| size.checked_add(entry.bytes.len()))
            .ok_or_else(invalid)?;
        if !safe_path(&entry.path)
            || entry.mode > 0o777
            || (entry.kind == Kind::Directory && !entry.bytes.is_empty())
            || entry.bytes.len() > limits.file_bytes
            || content > limits.content_bytes
            || archive > limits.archive_bytes
            || archive >= u32::MAX as usize
            || names
                .insert(unicase::UniCase::new(entry.path.as_ref()), entry.kind)
                .is_some()
        {
            return Err(invalid());
        }
    }
    // Adjacent folded paths expose every shared directory prefix without
    // allocating one tree node per segment of an adversarial deep archive.
    let mut previous: Option<&str> = None;
    for name in names.keys() {
        let path = name.as_ref();
        if let Some(previous) = previous {
            for (left, right) in previous.split('/').zip(path.split('/')) {
                if unicase::UniCase::new(left) != unicase::UniCase::new(right) {
                    break;
                }
                if left != right {
                    return Err(invalid());
                }
            }
        }
        previous = Some(path);
    }
    for entry in entries {
        let mut path = entry.path.as_ref();
        while let Some((parent, _)) = path.rsplit_once('/') {
            if names.get(&unicase::UniCase::new(parent)) == Some(&Kind::File) {
                return Err(invalid());
            }
            path = parent;
        }
    }
    Ok(())
}

/// Fixed PKWare 2.0, DOS 1980 timestamp, Unix metadata and uncompressed bytes.
/// The input order belongs to the enclosing format; this layer never reorders it.
pub(crate) fn encode(entries: &[Entry<'_>], limits: Limits) -> Result<Vec<u8>> {
    validate(entries, limits)?;
    let mut output = Vec::new();
    let mut central = Vec::new();
    for entry in entries {
        let name = if entry.kind == Kind::Directory {
            format!("{}/", entry.path).into_bytes()
        } else {
            entry.path.as_bytes().to_vec()
        };
        let flag: u16 = if name.is_ascii() { 0 } else { 1 << 11 };
        let size = entry.bytes.len() as u32;
        let crc = crc32fast::hash(&entry.bytes);
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
        output.extend(&name);
        output.extend(entry.bytes.as_ref());
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
        let kind = match entry.kind {
            Kind::File => 0o100000,
            Kind::Directory => 0o040000,
        };
        central.extend(((kind | entry.mode) << 16).to_le_bytes());
        central.extend(offset.to_le_bytes());
        central.extend(name);
    }
    let offset = output.len() as u32;
    let size = central.len() as u32;
    output.extend(central);
    output.extend(0x06054b50_u32.to_le_bytes());
    for field in [0_u16, 0, entries.len() as u16, entries.len() as u16] {
        output.extend(field.to_le_bytes());
    }
    output.extend(size.to_le_bytes());
    output.extend(offset.to_le_bytes());
    output.extend(0_u16.to_le_bytes());
    Ok(output)
}

pub(crate) fn decode(payload: &[u8], limits: Limits) -> Result<Vec<Entry<'static>>> {
    if payload.len() > limits.archive_bytes {
        return Err(invalid());
    }
    let end = payload.len().checked_sub(22).ok_or_else(invalid)?;
    let footer = &payload[end..];
    let count = u16::from_le_bytes([footer[10], footer[11]]) as usize;
    let size = u32::from_le_bytes(footer[12..16].try_into().map_err(|_| invalid())?) as usize;
    let start = u32::from_le_bytes(footer[16..20].try_into().map_err(|_| invalid())?) as usize;
    if &footer[..4] != b"PK\x05\x06"
        || footer[4..8] != [0; 4]
        || footer[8..10] != footer[10..12]
        || footer[20..22] != [0; 2]
        || count > limits.entries
        || start.checked_add(size) != Some(end)
    {
        return Err(invalid());
    }
    let mut archive = zip::ZipArchive::new(Cursor::new(payload)).map_err(|_| invalid())?;
    if archive.len() != count
        || archive.offset() != 0
        || archive.central_directory_start() != start as u64
    {
        return Err(invalid());
    }
    let mut entries = Vec::new();
    let mut total = 0_u64;
    for index in 0..count {
        let file = archive.by_index(index).map_err(|_| invalid())?;
        let mode = file.unix_mode().ok_or_else(invalid)?;
        let kind = match mode & 0o170000 {
            0o100000 => Kind::File,
            0o040000 => Kind::Directory,
            _ => return Err(invalid()),
        };
        let path = if kind == Kind::Directory {
            file.name().strip_suffix('/').ok_or_else(invalid)?
        } else {
            file.name()
        }
        .to_owned();
        total = total.checked_add(file.size()).ok_or_else(invalid)?;
        if !safe_path(&path)
            || mode & 0o7777 > 0o777
            || file.compression() != zip::CompressionMethod::Stored
            || file.encrypted()
            || file.is_dir() != (kind == Kind::Directory)
            || (kind == Kind::Directory && file.size() != 0)
            || file.size() > limits.file_bytes as u64
            || total > limits.content_bytes as u64
        {
            return Err(invalid());
        }
        let size = file.size();
        let mut bytes = Vec::new();
        file.take(limits.file_bytes as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| invalid())?;
        if bytes.len() as u64 != size {
            return Err(invalid());
        }
        entries.push(Entry {
            path: path.into(),
            bytes: bytes.into(),
            mode: mode & 0o777,
            kind,
        });
    }
    if encode(&entries, limits)? != payload {
        return Err(invalid());
    }
    Ok(entries)
}
