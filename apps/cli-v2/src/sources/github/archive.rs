//! Bounded GitHub ZIP decoding into memory; never extract paths to a filesystem.

use std::{
    collections::BTreeSet,
    io::{Cursor, Read},
};

use crate::{
    artifacts::{self, Member},
    error::{Failure, Result},
    projects,
    sources::snapshot,
};

pub(super) const MAX_ARCHIVE: usize = 100 * 1024 * 1024;

fn invalid() -> Failure {
    Failure::precondition("the GitHub archive violates its selected source boundaries")
}

// Bound central-directory allocation before asking the ZIP parser to build its index.
fn preflight(bytes: &[u8]) -> Result<(usize, usize)> {
    if bytes.len() < 22 || bytes.len() > MAX_ARCHIVE {
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

pub(super) fn selected(bytes: &[u8], subpath: Option<&str>) -> Result<Vec<Member>> {
    let (count, start) = preflight(bytes)?;
    if subpath.is_some_and(|path| !artifacts::safe_path(path)) {
        return Err(invalid());
    }
    let mut archive = zip::ZipArchive::new(Cursor::new(bytes)).map_err(|_| invalid())?;
    // zip indexes by name and silently replaces duplicate central records.
    // It must describe exactly the bounded directory we checked, without a prefix.
    if archive.len() != count
        || archive.offset() != 0
        || archive.central_directory_start() != start as u64
    {
        return Err(invalid());
    }
    let mut root = None;
    let mut names = BTreeSet::new();
    let mut files = Vec::new();
    let mut total = 0usize;
    for index in 0..archive.len() {
        let mut member = archive.by_index(index).map_err(|_| invalid())?;
        let name = std::str::from_utf8(member.name_raw())
            .map_err(|_| invalid())?
            .to_owned();
        let name = name.strip_suffix('/').unwrap_or(&name);
        if !artifacts::safe_path(name) || !names.insert(name.to_owned()) {
            return Err(invalid());
        }
        let (prefix, relative) = name.split_once('/').unwrap_or((name, ""));
        if root.as_ref().is_some_and(|root| root != prefix) {
            return Err(invalid());
        }
        root = Some(prefix.to_owned());
        if member.is_dir() {
            continue;
        }
        let selected = match subpath {
            None => Some(relative),
            Some(path) if relative == path => path.rsplit('/').next(),
            Some(path) => relative
                .strip_prefix(path)
                .and_then(|tail| tail.strip_prefix('/')),
        };
        let Some(path) = selected else {
            continue;
        };
        let mode = member.unix_mode().unwrap_or(0o644);
        if member.encrypted()
            || !matches!(mode & 0o170000, 0 | 0o100000)
            || !artifacts::safe_path(path)
            || path
                .split('/')
                .any(|part| projects::secret_name(part) || part.eq_ignore_ascii_case(".git"))
            || member.size() > artifacts::MAX_FILE_BYTES as u64
            || !matches!(
                member.compression(),
                zip::CompressionMethod::Stored | zip::CompressionMethod::Deflated
            )
            || files.len() >= artifacts::MAX_FILES
        {
            return Err(invalid());
        }
        let length = usize::try_from(member.size()).map_err(|_| invalid())?;
        total = total
            .checked_add(length)
            .filter(|total| *total <= snapshot::MAX_BYTES)
            .ok_or_else(invalid)?;
        let mut payload = Vec::with_capacity(length);
        member
            .by_ref()
            .take(length as u64 + 1)
            .read_to_end(&mut payload)
            .map_err(|_| invalid())?;
        if payload.len() != length {
            return Err(invalid());
        }
        files.push(Member {
            path: path.into(),
            bytes: payload,
            mode: if mode & 0o111 != 0 { 0o755 } else { 0o644 },
        });
    }
    Ok(files)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{error::Error, io::Write};

    fn zip(entries: &[(&str, &[u8])]) -> std::result::Result<Vec<u8>, Box<dyn Error>> {
        let mut writer = zip::ZipWriter::new(Cursor::new(Vec::new()));
        let options = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .unix_permissions(0o755);
        writer.add_directory("owner-repo-sha/", options)?;
        for (path, bytes) in entries {
            writer.start_file(*path, options)?;
            writer.write_all(bytes)?;
        }
        Ok(writer.finish()?.into_inner())
    }

    #[test]
    fn deflated_source_selection_is_bounded_and_never_extracts_paths()
    -> std::result::Result<(), Box<dyn Error>> {
        let bytes = "Original e\u{301} bytes.\n".as_bytes();
        let archive = zip(&[
            ("owner-repo-sha/skills/demo/SKILL.md", bytes),
            ("owner-repo-sha/unselected/image.bin", b"\0\xff"),
        ])?;
        let files = selected(&archive, Some("skills/demo"))?;
        assert_eq!(files.len(), 1);
        assert_eq!(
            files[0],
            Member {
                path: "SKILL.md".into(),
                bytes: bytes.into(),
                mode: 0o755
            }
        );
        snapshot::encode(files)?;
        assert!(snapshot::encode(selected(&archive, None)?).is_err());
        assert!(selected(&archive[..archive.len() - 1], Some("skills/demo")).is_err());
        for path in [
            "owner-repo-sha/../outside",
            "other-root/file.txt",
            "owner-repo-sha/skills/demo/.env",
        ] {
            let unsafe_archive = zip(&[
                ("owner-repo-sha/skills/demo/SKILL.md", bytes),
                (path, b"fixture"),
            ])?;
            assert!(selected(&unsafe_archive, Some("skills/demo")).is_err());
        }
        let mut excessive_count = archive.clone();
        let end = excessive_count.len() - 22;
        excessive_count[end + 8..end + 12].copy_from_slice(&[255, 255, 255, 255]);
        assert!(selected(&excessive_count, Some("skills/demo")).is_err());
        let (count, start) = preflight(&archive)?;
        let field = |at| {
            usize::from(u16::from_le_bytes([
                archive[start + at],
                archive[start + at + 1],
            ]))
        };
        let length = 46 + field(28) + field(30) + field(32);
        let mut duplicate = archive[..end].to_vec();
        duplicate.extend_from_slice(&archive[start..start + length]);
        duplicate.extend_from_slice(&archive[end..]);
        let end = duplicate.len() - 22;
        let count = u16::try_from(count + 1)?;
        duplicate[end + 8..end + 10].copy_from_slice(&count.to_le_bytes());
        duplicate[end + 10..end + 12].copy_from_slice(&count.to_le_bytes());
        duplicate[end + 12..end + 16].copy_from_slice(&u32::try_from(end - start)?.to_le_bytes());
        assert!(selected(&duplicate, Some("skills/demo")).is_err());
        let oversized = vec![b'a'; artifacts::MAX_FILE_BYTES + 1];
        assert!(selected(&zip(&[("owner-repo-sha/large.txt", &oversized)])?, None).is_err());
        let mut linked = zip::ZipWriter::new(Cursor::new(Vec::new()));
        linked.add_symlink(
            "owner-repo-sha/skills/link",
            "/outside",
            zip::write::SimpleFileOptions::default(),
        )?;
        assert!(selected(&linked.finish()?.into_inner(), Some("skills")).is_err());
        for address in [
            "http://api.github.com/repos/o/r",
            "https://evil.example/archive",
            "https://token@api.github.com/repos/o/r",
            "https://api.github.com:8443/repos/o/r",
        ] {
            assert!(!super::super::transport::allowed(&url::Url::parse(
                address
            )?));
        }
        for source in ["gh:owner/repo@main", "@owner/name", "./local"] {
            assert!(super::super::fetch(source).is_err());
        }
        Ok(())
    }
}
