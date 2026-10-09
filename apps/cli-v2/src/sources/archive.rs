//! Bound external ZIP indexes before allocation; canonical artifacts have their own reader.

use crate::error::{Failure, Result};
use std::io::Cursor;

fn invalid() -> Failure {
    Failure::precondition("the external ZIP directory is ambiguous or exceeds its bounds")
}

// Bound central-directory allocation before asking the ZIP parser to build its index.
pub(super) fn directory(bytes: &[u8], limit: usize) -> Result<(usize, usize)> {
    if bytes.len() < 22 || bytes.len() > limit {
        return Err(invalid());
    }
    let lower = bytes.len().saturating_sub(22 + 65535);
    let offset = (lower..=bytes.len() - 22)
        .rev()
        .find(|at| bytes[*at..].starts_with(b"PK\x05\x06"))
        .ok_or_else(invalid)?;
    let record = &bytes[offset..];
    let short = |at| u16::from_le_bytes([record[at], record[at + 1]]);
    let count = short(10);
    if short(4) != 0
        || short(6) != 0
        || short(8) != count
        || count == 0
        || count > 20_000
        || record.len() != 22 + usize::from(short(20))
    {
        return Err(invalid());
    }
    let start = u32::from_le_bytes(record[16..20].try_into().map_err(|_| invalid())?) as usize;
    let size = u32::from_le_bytes(record[12..16].try_into().map_err(|_| invalid())?) as usize;
    if start.checked_add(size) != Some(offset) {
        return Err(invalid());
    }
    Ok((usize::from(count), start))
}

pub(super) fn open(bytes: &[u8], limit: usize) -> Result<zip::ZipArchive<Cursor<&[u8]>>> {
    let (count, start) = directory(bytes, limit)?;
    let archive = zip::ZipArchive::new(Cursor::new(bytes)).map_err(|_| invalid())?;
    // The ZIP library indexes by name and silently replaces duplicate records.
    if archive.len() != count
        || archive.offset() != 0
        || archive.central_directory_start() != start as u64
    {
        return Err(invalid());
    }
    Ok(archive)
}
