//! Inspect a native provider distribution without installing or executing it.

mod metadata;
mod native;

use std::{
    collections::{BTreeMap, BTreeSet},
    io::Read,
};

use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use sha2::{Digest, Sha256, Sha384, Sha512};

use crate::{
    archive,
    error::{Failure, Result},
};

const MAX_ARCHIVE: usize = 64 * 1024 * 1024;
const MAX_CONTENT: u64 = 128 * 1024 * 1024;
const MAX_METADATA: usize = 1024 * 1024;
const MAX_FILES: usize = 1000;

/// Integrity-checked bytes, not publisher authentication or installation consent.
pub struct Payload {
    pub executable_name: String,
    pub executable: Vec<u8>,
    pub license: String,
    pub version: String,
}

fn invalid() -> Failure {
    Failure::precondition("the native provider wheel identity, inventory or integrity was refused")
}

fn files(bytes: &[u8]) -> Result<BTreeMap<String, Vec<u8>>> {
    let mut archive = archive::external::open(bytes, MAX_ARCHIVE)?;
    if archive.len() > MAX_FILES {
        return Err(invalid());
    }
    let mut paths = BTreeMap::new();
    let mut files = BTreeMap::new();
    let mut total = 0_u64;
    for index in 0..archive.len() {
        let file = archive.by_index(index).map_err(|_| invalid())?;
        let directory = file.is_dir();
        let name = std::str::from_utf8(file.name_raw()).map_err(|_| invalid())?;
        if name != file.name() {
            return Err(invalid());
        }
        let name = if directory {
            name.strip_suffix('/').ok_or_else(invalid)?
        } else {
            name
        }
        .to_owned();
        let mode = file.unix_mode().unwrap_or(0);
        let kind = mode & 0o170000;
        total = total.checked_add(file.size()).ok_or_else(invalid)?;
        if !archive::safe_path(&name)
            || (kind != 0 && kind != if directory { 0o040000 } else { 0o100000 })
            || mode & 0o7000 != 0
            || file.encrypted()
            || !matches!(
                file.compression(),
                zip::CompressionMethod::Stored | zip::CompressionMethod::Deflated
            )
            || file.size() > MAX_ARCHIVE as u64
            || total > MAX_CONTENT
            || (directory && file.size() != 0)
            || paths
                .insert(unicase::UniCase::new(name.clone()), directory)
                .is_some()
        {
            return Err(invalid());
        }
        let size = file.size();
        let mut content = Vec::new();
        file.take(MAX_ARCHIVE as u64 + 1)
            .read_to_end(&mut content)
            .map_err(|_| invalid())?;
        if content.len() as u64 != size {
            return Err(invalid());
        }
        if !directory {
            files.insert(name, content);
        }
    }
    let mut previous: Option<&str> = None;
    for path in paths.keys() {
        let name = path.as_ref();
        if let Some(previous) = previous {
            for (left, right) in previous.split('/').zip(name.split('/')) {
                if unicase::UniCase::new(left) != unicase::UniCase::new(right) {
                    break;
                }
                if left != right {
                    return Err(invalid());
                }
            }
        }
        previous = Some(name);
        let mut ancestor = name;
        while let Some((parent, _)) = ancestor.rsplit_once('/') {
            if paths.get(&unicase::UniCase::new(parent.to_owned())) == Some(&false) {
                return Err(invalid());
            }
            ancestor = parent;
        }
    }
    Ok(files)
}

fn record(files: &BTreeMap<String, Vec<u8>>, path: &str) -> Result<()> {
    let bytes = files
        .get(path)
        .filter(|b| b.len() <= MAX_METADATA)
        .ok_or_else(invalid)?;
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(false)
        .from_reader(bytes.as_slice());
    let mut seen = BTreeSet::new();
    for row in reader.records() {
        let row = row.map_err(|_| invalid())?;
        if row.len() != 3 || seen.len() >= MAX_FILES || !seen.insert(row[0].to_owned()) {
            return Err(invalid());
        }
        let content = files.get(&row[0]).ok_or_else(invalid)?;
        if &row[0] == path {
            if !row[1].is_empty() || !row[2].is_empty() {
                return Err(invalid());
            }
            continue;
        }
        if row[2] != content.len().to_string() {
            return Err(invalid());
        }
        let (algorithm, expected) = row[1].split_once('=').ok_or_else(invalid)?;
        let actual = match algorithm {
            "sha256" => URL_SAFE_NO_PAD.encode(Sha256::digest(content)),
            "sha384" => URL_SAFE_NO_PAD.encode(Sha384::digest(content)),
            "sha512" => URL_SAFE_NO_PAD.encode(Sha512::digest(content)),
            _ => return Err(invalid()),
        };
        if actual != expected {
            return Err(invalid());
        }
    }
    if seen.len() != files.len() {
        return Err(invalid());
    }
    Ok(())
}

/// The fixed native provider wheel layout is intentionally narrower than pip's.
/// The caller must separately authenticate these exact archive bytes and publisher.
pub fn inspect(bytes: &[u8], project: &str, version: &str, platform: &str) -> Result<Payload> {
    let tag = metadata::platform_tag(platform)?;
    if project.is_empty()
        || project.len() > 128
        || !project
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
        || project.starts_with('-')
        || project.ends_with('-')
        || project.contains("--")
        || version.is_empty()
        || version.len() > 128
        || !version.as_bytes()[0].is_ascii_digit()
        || !version
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'+' | b'!'))
    {
        return Err(invalid());
    }
    let package = project.replace('-', "_");
    let info = format!("{package}-{version}.dist-info");
    let mut files = files(bytes)?;
    let suffix = if platform.starts_with("windows/") {
        ".exe"
    } else {
        ""
    };
    let executable_name = format!("{project}{suffix}");
    let executable_path = format!("{package}/bin/{executable_name}");
    for path in files.keys() {
        let first = path.split('/').next().ok_or_else(invalid)?;
        if (first.ends_with(".dist-info") && first != info)
            || (path.contains("/bin/") && path != &executable_path)
        {
            return Err(invalid());
        }
    }
    record(&files, &format!("{info}/RECORD"))?;
    let license = metadata::validate(&files, &info, project, version, tag)?;
    let executable = files
        .remove(&executable_path)
        .filter(|b| !b.is_empty())
        .ok_or_else(invalid)?;
    native::validate(&executable, platform)?;
    Ok(Payload {
        executable_name,
        executable,
        license,
        version: version.into(),
    })
}
