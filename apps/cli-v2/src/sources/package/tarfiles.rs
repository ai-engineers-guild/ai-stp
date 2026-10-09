//! Bounded metadata reads. Registry archives are never unpacked onto the filesystem.

use std::{collections::BTreeSet, io::Read};

use crate::{
    artifacts::Member,
    error::{Failure, Result},
    sources::snapshot,
};

pub(super) const MAX_ARCHIVE: u64 = 20 * 1024 * 1024;
const MAX_EXPANDED: u64 = 50 * 1024 * 1024;

fn invalid() -> Failure {
    Failure::precondition("the registry TAR archive is unsafe, ambiguous or exceeds its bounds")
}

pub(super) fn read(bytes: &[u8], root: &str, wanted: &[&str]) -> Result<Vec<Member>> {
    if bytes.is_empty() || bytes.len() as u64 > MAX_ARCHIVE {
        return Err(invalid());
    }
    let mut decoder = flate2::bufread::GzDecoder::new(bytes);
    let mut expanded = Vec::new();
    decoder
        .by_ref()
        .take(MAX_EXPANDED + 1)
        .read_to_end(&mut expanded)
        .map_err(|_| invalid())?;
    if expanded.len() as u64 > MAX_EXPANDED || !decoder.into_inner().is_empty() {
        return Err(invalid());
    }
    let mut archive = tar::Archive::new(expanded.as_slice());
    // Inspect records after zero blocks too; concatenation must not hide duplicate metadata.
    archive.set_ignore_zeros(true);
    let mut names = BTreeSet::new();
    let mut files = Vec::new();
    let mut selected = 0;
    for (index, entry) in archive.entries().map_err(|_| invalid())?.enumerate() {
        if index >= 20_000 {
            return Err(invalid());
        }
        let mut entry = entry.map_err(|_| invalid())?;
        let raw = entry.path_bytes();
        let path = std::str::from_utf8(&raw).map_err(|_| invalid())?;
        let path = path
            .strip_prefix("./")
            .unwrap_or(path)
            .trim_end_matches('/');
        let kind = entry.header().entry_type();
        if path.is_empty()
            || path.len() > 4096
            || path.contains('\\')
            || path.chars().any(char::is_control)
            || path.split('/').any(|part| matches!(part, "" | "." | ".."))
            || !names.insert(path.to_owned())
            || !(kind.is_file() || kind.is_dir())
            || (!root.is_empty() && path != root.trim_end_matches('/') && !path.starts_with(root))
        {
            return Err(invalid());
        }
        if kind.is_dir() {
            if entry.size() != 0 {
                return Err(invalid());
            }
            continue;
        }
        let Some(name) = path.strip_prefix(root).filter(|name| wanted.contains(name)) else {
            continue;
        };
        if entry.size() > 4 * 1024 * 1024 {
            return Err(invalid());
        }
        selected += entry.size() as usize;
        if selected > snapshot::MAX_BYTES {
            return Err(invalid());
        }
        let name = name.to_owned();
        let size = entry.size();
        let mut content = Vec::with_capacity(size as usize);
        entry.read_to_end(&mut content).map_err(|_| invalid())?;
        if content.len() as u64 != size
            || content.contains(&0)
            || std::str::from_utf8(&content).is_err()
        {
            return Err(invalid());
        }
        files.push(Member {
            path: name,
            bytes: content,
            mode: 0o644,
        });
    }
    Ok(files)
}

#[cfg(test)]
pub(super) fn fixture(entries: &[(&str, &[u8], tar::EntryType)]) -> std::io::Result<Vec<u8>> {
    let encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::fast());
    let mut archive = tar::Builder::new(encoder);
    for (path, content, kind) in entries {
        let mut header = tar::Header::new_gnu();
        header.set_mode(0o644);
        header.set_size(content.len() as u64);
        header.set_entry_type(*kind);
        archive.append_data(&mut header, path, *content)?;
    }
    archive.into_inner()?.finish()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::error::Error;

    #[test]
    fn root_metadata_is_bounded_and_ambiguous_archives_refuse()
    -> std::result::Result<(), Box<dyn Error>> {
        let file = tar::EntryType::Regular;
        let bytes = fixture(&[
            ("package/test/package.json", b"nested", file),
            ("package/package.json", b"root", file),
        ])?;
        let selected = read(&bytes, "package/", &["package.json"])?;
        assert_eq!(selected.len(), 1);
        assert_eq!(selected[0].bytes, b"root");
        assert_eq!(selected[0].mode, 0o644);
        assert!(read(&bytes, "other/", &["package.json"]).is_err());
        for entries in [
            vec![
                ("package/package.json", b"first".as_slice(), file),
                ("package/package.json", b"second", file),
            ],
            vec![(
                "package/package.json",
                b"link".as_slice(),
                tar::EntryType::Symlink,
            )],
            vec![("package/package.json", b"bad\0".as_slice(), file)],
            vec![("package/evil\\path", b"bad".as_slice(), file)],
        ] {
            assert!(read(&fixture(&entries)?, "package/", &["package.json"]).is_err());
        }
        let excessive = vec![b'x'; 4 * 1024 * 1024 + 1];
        assert!(
            read(
                &fixture(&[("package/package.json", &excessive, file)])?,
                "package/",
                &["package.json"]
            )
            .is_err()
        );
        let mut concat = bytes.clone();
        concat.extend_from_slice(&bytes);
        assert!(read(&concat, "package/", &["package.json"]).is_err());
        let mut corrupt = bytes.clone();
        let len = corrupt.len();
        corrupt[len - 8] ^= 1;
        assert!(read(&corrupt, "package/", &["package.json"]).is_err());
        assert!(read(&bytes[..bytes.len() - 8], "package/", &["package.json"]).is_err());
        Ok(())
    }
}
