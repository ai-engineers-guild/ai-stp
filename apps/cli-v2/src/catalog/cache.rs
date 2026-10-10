//! Discardable public cache, isolated below an explicitly supplied directory.

use crate::{
    canonical, digest,
    error::{Failure, Result},
    files,
    http::MAX_BODY,
    passport, wire,
};
use serde_json::{Value, json};
use std::{path::Path, time::SystemTime};

const OWNER: &[u8] = b"ai-stp-cli-v2 public catalog cache v1\n";
const MAX_CACHE: u64 = 64 * 1024 * 1024;
const MAX_ENTRIES: usize = 64;
pub struct Cache {
    storage: files::OwnedDirectory,
}
pub struct Entry {
    pub document: Value,
    pub checked_at: String,
}
fn invalid() -> Failure {
    Failure::precondition("explicit catalog cache is invalid, busy or inaccessible")
}

impl Cache {
    pub fn open(root: &Path, create: bool) -> Result<Option<Self>> {
        files::OwnedDirectory::open(root, "ai-stp-v2-catalog", OWNER, create)
            .map(|owned| owned.map(|storage| Self { storage }))
    }

    pub fn load(&self, url: &str) -> Result<Option<Entry>> {
        let key = digest::sha256(url.as_bytes());
        let filename = format!("{}.json", &key[7..]);
        let Some(bytes) = self.storage.read_file(&filename, MAX_BODY + 4096)? else {
            return Ok(None);
        };
        let entry = wire::parse(&bytes)?;
        let checked_at = entry["checked_at"]
            .as_str()
            .filter(|v| passport::timestamp(v))
            .ok_or_else(invalid)?;
        if entry["schema_version"] != 1
            || entry["url"] != url
            || entry["key"] != key
            || entry["document_digest"] != digest::sha256(&canonical::bytes(&entry["document"])?)
        {
            return Err(invalid());
        }
        Ok(Some(Entry {
            document: entry["document"].clone(),
            checked_at: checked_at.into(),
        }))
    }

    pub fn store(&self, url: &str, document: &Value, checked_at: &str) -> Result<()> {
        let key = digest::sha256(url.as_bytes());
        let name = format!("{}.json", &key[7..]);
        let bytes = serde_json::to_vec(&json!({"schema_version": 1, "url": url, "key": key,
            "checked_at": checked_at, "document": document, "document_digest": digest::sha256(&canonical::bytes(document)?)})).map_err(|_| invalid())?;
        if bytes.len() as u64 > MAX_BODY + 4096 {
            return Err(invalid());
        }
        let held = self
            .storage
            .directory
            .entries()
            .map_err(|_| invalid())?
            .take(MAX_ENTRIES + 17)
            .collect::<std::io::Result<Vec<_>>>()
            .map_err(|_| invalid())?;
        if held.len() > MAX_ENTRIES + 16 {
            return Err(invalid());
        }
        let mut entries = Vec::new();
        for entry in held {
            let filename = entry.file_name().into_string().map_err(|_| invalid())?;
            if ["lock", "owner"].contains(&filename.as_str()) {
                continue;
            }
            if filename.starts_with(".tmp-") {
                self.storage
                    .directory
                    .remove_file(&filename)
                    .map_err(|_| invalid())?;
                continue;
            }
            if !filename.is_ascii()
                || filename.len() != 69
                || !filename.ends_with(".json")
                || !filename[..64]
                    .bytes()
                    .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
            {
                return Err(invalid());
            }
            let metadata = entry.metadata().map_err(|_| invalid())?;
            if !metadata.is_file() {
                return Err(invalid());
            }
            entries.push((
                metadata
                    .modified()
                    .map(|t| t.into_std())
                    .unwrap_or(SystemTime::UNIX_EPOCH),
                filename,
                metadata.len(),
            ));
        }
        if entries.len() > MAX_ENTRIES {
            return Err(invalid());
        }
        entries.retain(|(_, held, _)| held != &name);
        entries.sort();
        let mut total = bytes.len() as u64 + entries.iter().map(|(_, _, size)| size).sum::<u64>();
        while total > MAX_CACHE || entries.len() >= MAX_ENTRIES {
            let (_, oldest, size) = entries.remove(0);
            self.storage
                .directory
                .remove_file(oldest)
                .map_err(|_| invalid())?;
            total -= size;
        }
        self.storage.atomic(&name, &bytes)
    }
}
