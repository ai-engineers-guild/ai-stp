//! Canonical projection bytes closed over an exact scope's ownership declaration.

use std::collections::BTreeMap;

use serde_json::Value;

use crate::{
    archive::{self, Entry, Kind, Limits},
    artifacts::Member,
    digest,
    error::{Failure, Result},
    passport::versions,
};

pub const FORMAT: &str = "ai-stp-adaptation-projection/1";
const LIMITS: Limits = Limits {
    entries: 8192,
    file_bytes: 64 * 1024 * 1024,
    content_bytes: 64 * 1024 * 1024,
    archive_bytes: 64 * 1024 * 1024,
};

fn invalid() -> Failure {
    Failure::precondition("the projection bytes disagree with their scope declaration")
}

pub fn build(scope: &Value, files: &[Member]) -> Result<Vec<u8>> {
    versions::validate_scope(scope)?;
    build_members(scope["members"].as_array().ok_or_else(invalid)?, files)
}

/// Construct bytes before the scope can bind their digest and length.
pub fn build_members(members: &[Value], files: &[Member]) -> Result<Vec<u8>> {
    if members.is_empty() || members.len() > LIMITS.entries || files.len() > LIMITS.entries {
        return Err(invalid());
    }
    let mut contents = BTreeMap::new();
    for file in files {
        if contents.insert(file.path.as_str(), file).is_some() {
            return Err(invalid());
        }
    }
    let mut entries = Vec::new();
    for member in members {
        versions::validate_member(member)?;
        let path = member["path"].as_str().ok_or_else(invalid)?;
        let mode = member["mode"].as_u64().ok_or_else(invalid)? as u32;
        let (kind, bytes) = if member["object_type"] == "directory" {
            (Kind::Directory, &[][..])
        } else {
            let file = contents.remove(path).ok_or_else(invalid)?;
            if file.mode != mode
                || member["content_artifact"]["size_bytes"] != file.bytes.len()
                || member["content_artifact"]["digest"]
                    != digest::bytes("ai-stp:artifact:v1", &file.bytes)?
            {
                return Err(invalid());
            }
            (Kind::File, file.bytes.as_slice())
        };
        entries.push(Entry {
            path: path.into(),
            bytes: bytes.into(),
            mode,
            kind,
        });
    }
    if !contents.is_empty() {
        return Err(invalid());
    }
    entries.sort_by(|a, b| a.path.cmp(&b.path));
    archive::encode(&entries, LIMITS)
}

pub fn verify(scope: &Value, payload: &[u8]) -> Result<Vec<Member>> {
    versions::validate_scope(scope)?;
    if payload.len() > LIMITS.archive_bytes
        || scope["projection_artifact"]["size_bytes"] != payload.len()
        || scope["projection_artifact"]["digest"] != digest::bytes("ai-stp:artifact:v1", payload)?
    {
        return Err(invalid());
    }
    let files: Vec<_> = archive::decode(payload, LIMITS)?
        .into_iter()
        .filter(|entry| entry.kind == Kind::File)
        .map(|entry| Member {
            path: entry.path.into_owned(),
            bytes: entry.bytes.into_owned(),
            mode: entry.mode,
        })
        .collect();
    if build(scope, &files)? != payload {
        return Err(invalid());
    }
    Ok(files)
}
