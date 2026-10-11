//! Closed component artifacts and the canonical uncompressed ZIP wire encoding.

use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

pub use crate::archive::safe_path;
use crate::archive::{self, Entry, Kind, Limits};

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

/// Canonical regular-file archive with caller-defined member order.
pub fn zip_stored(files: &[Member]) -> Result<Vec<u8>> {
    validate(files, 2000, 64 * 1024 * 1024)?;
    let entries: Vec<_> = files
        .iter()
        .map(|file| Entry {
            path: file.path.as_str().into(),
            bytes: file.bytes.as_slice().into(),
            mode: file.mode,
            kind: Kind::File,
        })
        .collect();
    archive::encode(
        &entries,
        Limits {
            entries: 2000,
            file_bytes: MAX_FILE_BYTES,
            content_bytes: 64 * 1024 * 1024,
            archive_bytes: 68 * 1024 * 1024,
        },
    )
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
    let entries = archive::decode(
        payload,
        Limits {
            entries: MAX_FILES + 1,
            file_bytes: MAX_FILE_BYTES,
            content_bytes: MAX_TREE_BYTES,
            archive_bytes: MAX_TREE_BYTES + 4 * 1024 * 1024,
        },
    )?;
    let mut members = BTreeMap::new();
    for entry in entries {
        if entry.kind != Kind::File || !matches!(entry.mode, 0o644 | 0o755) {
            return Err(invalid());
        }
        members.insert(
            entry.path.into_owned(),
            (entry.bytes.into_owned(), entry.mode),
        );
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
