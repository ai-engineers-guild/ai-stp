//! Stream exact authenticated plan artifacts into isolated content-addressed state.

use std::{
    cell::RefCell,
    io::{Read, Seek, Write},
    path::Path,
    time::{Duration, Instant},
};

use cap_fs_ext::MetadataExt;
use cap_std::fs::{Dir, File, Metadata};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use url::Url;

use super::Download;
use crate::{
    error::{ErrorKind, Failure, Result},
    files::{self, OwnedDirectory},
    http,
};

const BUDGET: Duration = Duration::from_secs(600);
const OWNER: &[u8] = b"ai-stp-cli-v2:software-artifacts/v1\n";

/// An opened immutable cache member; component invocation never receives its
/// parent directory or a writable handle.
pub(crate) struct HeldArtifact {
    pub file: std::fs::File,
    pub entry_point: String,
    digest: String,
    bytes: u64,
}

impl HeldArtifact {
    pub fn verify(&mut self) -> Result<()> {
        self.file.rewind().map_err(|_| invalid())?;
        let mut hash = Sha256::new();
        let mut length = 0u64;
        let mut buffer = [0; 64 * 1024];
        let started = Instant::now();
        loop {
            remaining(started)?;
            let read = self.file.read(&mut buffer).map_err(|_| invalid())?;
            if read == 0 {
                break;
            }
            length += read as u64;
            if length > self.bytes {
                return Err(invalid());
            }
            hash.update(&buffer[..read]);
        }
        if length != self.bytes || crate::digest::representation(&hash.finalize()) != self.digest {
            return Err(invalid());
        }
        self.file.rewind().map_err(|_| invalid())?;
        Ok(())
    }
}

pub(crate) fn hold(parent: &Dir, planned: &Value) -> Result<HeldArtifact> {
    let records = planned["plan"]["software_artifacts"]
        .as_array()
        .ok_or_else(invalid)?;
    // The seven managed components each consume one vendor artifact. Refuse a
    // future multipart format until its independent verifier is implemented.
    if records.len() != 1 {
        return Err(invalid());
    }
    let record: Download = serde_json::from_value(records[0].clone()).map_err(|_| invalid())?;
    record.check(crate::provider::runtime::platform()?)?;
    let owned =
        OwnedDirectory::open_at(parent, "software-artifacts", OWNER, false)?.ok_or_else(invalid)?;
    let name = record.sha256.strip_prefix("sha256:").ok_or_else(invalid)?;
    let file =
        verified_file(&owned.directory, name, &record, Instant::now())?.ok_or_else(invalid)?;
    Ok(HeldArtifact {
        file: file.into_std(),
        entry_point: record.entry_point,
        digest: record.sha256,
        bytes: record.byte_length,
    })
}

fn invalid() -> Failure {
    Failure::precondition(
        "software artifact transport, stored bytes or exact plan binding was refused",
    )
}

fn unavailable() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "software artifact transfer is unavailable",
    )
}

fn remaining(started: Instant) -> Result<Duration> {
    BUDGET
        .checked_sub(started.elapsed())
        .filter(|v| !v.is_zero())
        .ok_or_else(unavailable)
}

fn authority(harness: &str, url: &Url, redirect: bool) -> bool {
    let allowed = match harness {
        "codex" | "claude-code" | "opencode" => url.host_str() == Some("registry.npmjs.org"),
        "cursor" => url.host_str() == Some("downloads.cursor.com"),
        "grok-build" => url.host_str() == Some("x.ai"),
        "antigravity" => url.host_str() == Some("storage.googleapis.com"),
        "pi" => {
            url.host_str() == Some("github.com")
                || (redirect && url.host_str() == Some("release-assets.githubusercontent.com"))
        }
        _ => false,
    };
    allowed
        && url.scheme() == "https"
        && url.port().is_none()
        && url.username().is_empty()
        && url.password().is_none()
        && url.fragment().is_none()
        && (url.query().is_none()
            || (redirect && url.host_str() == Some("release-assets.githubusercontent.com")))
}

fn metadata(file: &File, directory: &Dir, name: &str, limit: u64) -> Result<Metadata> {
    let held = file.metadata().map_err(|_| invalid())?;
    let named = directory.symlink_metadata(name).map_err(|_| invalid())?;
    if !held.is_file()
        || held.nlink() != 1
        || held.len() > limit
        || named.is_symlink()
        || held.dev() != named.dev()
        || held.ino() != named.ino()
    {
        return Err(invalid());
    }
    #[cfg(windows)]
    {
        use cap_std::fs::MetadataExt as _;
        if held.file_attributes() & 0x400 != 0 {
            return Err(invalid());
        }
    }
    #[cfg(unix)]
    {
        use cap_std::fs::PermissionsExt;
        if held.permissions().mode() & 0o077 != 0 {
            return Err(invalid());
        }
    }
    Ok(held)
}

fn verified(directory: &Dir, name: &str, record: &Download, started: Instant) -> Result<bool> {
    Ok(verified_file(directory, name, record, started)?.is_some())
}

/// Keep the same opened file through verification and component handoff.
fn verified_file(
    directory: &Dir,
    name: &str,
    record: &Download,
    started: Instant,
) -> Result<Option<File>> {
    let mut file = match files::open_regular(directory, Path::new(name)) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(invalid()),
    };
    let before = metadata(&file, directory, name, record.byte_length)?;
    if before.len() != record.byte_length {
        return Err(invalid());
    }
    let mut hash = Sha256::new();
    let mut count = 0u64;
    let mut buffer = [0u8; 64 * 1024];
    loop {
        remaining(started)?;
        let size = file.read(&mut buffer).map_err(|_| invalid())?;
        if size == 0 {
            break;
        }
        count += size as u64;
        if count > record.byte_length {
            return Err(invalid());
        }
        hash.update(&buffer[..size]);
    }
    let after = metadata(&file, directory, name, record.byte_length)?;
    if count != record.byte_length
        || before.modified().ok() != after.modified().ok()
        || before.len() != after.len()
        || crate::digest::representation(&hash.finalize()) != record.sha256
    {
        return Err(invalid());
    }
    file.rewind().map_err(|_| invalid())?;
    Ok(Some(file))
}

/// A retained prefix is compared with the new response before any suffix is
/// appended. No truncation, guessed Range offset or unverified cache hit occurs.
fn receive(
    directory: &OwnedDirectory,
    record: &Download,
    mut reader: impl Read,
    started: Instant,
) -> Result<()> {
    let key = record.sha256.strip_prefix("sha256:").ok_or_else(invalid)?;
    let name = format!("{key}.partial");
    let options = files::private_options().read(true).clone();
    let mut file = match directory
        .directory
        .open_with(&name, options.clone().create_new(true))
    {
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => directory
            .directory
            .open_with(&name, &options)
            .map_err(|_| invalid())?,
        Ok(file) => file,
        Err(_) => return Err(invalid()),
    };
    let before = metadata(&file, &directory.directory, &name, record.byte_length)?;
    let mut retained = before.len();
    let mut hash = Sha256::new();
    let mut count = 0u64;
    let mut buffer = [0u8; 64 * 1024];
    let mut comparison = [0u8; 64 * 1024];
    loop {
        remaining(started)?;
        let size = reader.read(&mut buffer).map_err(|_| unavailable())?;
        if size == 0 {
            break;
        }
        count += size as u64;
        if count > record.byte_length {
            return Err(invalid());
        }
        hash.update(&buffer[..size]);
        let existing = retained.min(size as u64) as usize;
        if existing > 0 {
            file.read_exact(&mut comparison[..existing])
                .map_err(|_| invalid())?;
            if comparison[..existing] != buffer[..existing] {
                return Err(invalid());
            }
            retained -= existing as u64;
        }
        file.write_all(&buffer[existing..size])
            .map_err(|_| unavailable())?;
    }
    if retained != 0
        || count != record.byte_length
        || crate::digest::representation(&hash.finalize()) != record.sha256
    {
        return Err(invalid());
    }
    file.sync_all().map_err(|_| unavailable())?;
    let after = metadata(&file, &directory.directory, &name, record.byte_length)?;
    if before.dev() != after.dev() || before.ino() != after.ino() || after.len() != count {
        return Err(invalid());
    }
    // Re-read disk bytes too: hashing the network stream alone cannot establish
    // what remains under the held path after a concurrent local change.
    drop(file);
    if !verified(&directory.directory, &name, record, started)? {
        return Err(invalid());
    }
    match directory.directory.symlink_metadata(key) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
        _ => return Err(invalid()),
    }
    directory
        .directory
        .rename(&name, &directory.directory, key)
        .map_err(|_| invalid())?;
    directory.sync()
}

fn fetch(
    harness: &str,
    record: &Download,
    directory: &OwnedDirectory,
    started: Instant,
) -> Result<()> {
    let agent = RefCell::new(http::anonymous_agent());
    let mut url = Url::parse(&record.url).map_err(|_| invalid())?;
    for hop in 0..=2 {
        if !authority(harness, &url, hop != 0) {
            return Err(invalid());
        }
        let mut response = agent
            .borrow()
            .get(url.as_str())
            .header("Accept", "application/octet-stream")
            .header("Accept-Encoding", "identity")
            .header(
                "User-Agent",
                concat!("ai-stp-cli-v2/", env!("CARGO_PKG_VERSION")),
            )
            .config()
            .timeout_global(Some(remaining(started)?))
            .build()
            .call()
            .map_err(|error| {
                if http::is_transient(&error) {
                    unavailable()
                } else {
                    invalid()
                }
            })?;
        http::discard_closed_pool(&agent, response.version());
        match response.status().as_u16() {
            200 => (),
            301 | 302 | 303 | 307 | 308 if hop < 2 => {
                let location = response
                    .headers()
                    .get("Location")
                    .and_then(|v| v.to_str().ok())
                    .ok_or_else(invalid)?;
                if location.len() > 8192
                    || location
                        .chars()
                        .any(|c| c.is_whitespace() || c.is_control() || c == '\\')
                {
                    return Err(invalid());
                }
                url = url.join(location).map_err(|_| invalid())?;
                continue;
            }
            403 | 408 | 425 | 429 | 500 | 502 | 503 | 504 => {
                return Err(http::retry::annotate(
                    unavailable(),
                    response.headers(),
                    matches!(url.host_str(), Some("api.github.com" | "github.com")),
                ));
            }
            _ => return Err(invalid()),
        }
        if response
            .headers()
            .get("Content-Encoding")
            .is_some_and(|v| v != "identity")
            || response
                .body()
                .content_length()
                .is_some_and(|n| n != record.byte_length)
        {
            return Err(invalid());
        }
        return receive(directory, record, response.body_mut().as_reader(), started);
    }
    Err(invalid())
}

/// Call only with a plan observed through the authenticated runtime in this call.
pub(crate) fn acquire(parent: &Dir, harness: &str, planned: &Value) -> Result<Value> {
    let artifacts = planned["plan"]["software_artifacts"]
        .as_array()
        .ok_or_else(invalid)?;
    if artifacts.is_empty() || artifacts.len() > 16 {
        return Err(invalid());
    }
    let mut total = 0u64;
    let records = artifacts
        .iter()
        .map(|value| {
            let record: Download = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
            record.check(crate::provider::runtime::platform()?)?;
            total = total.checked_add(record.byte_length).ok_or_else(invalid)?;
            if total > 2 * 1024 * 1024 * 1024
                || !authority(
                    harness,
                    &Url::parse(&record.url).map_err(|_| invalid())?,
                    false,
                )
            {
                return Err(invalid());
            }
            Ok(record)
        })
        .collect::<Result<Vec<_>>>()?;
    let directory =
        OwnedDirectory::open_at(parent, "software-artifacts", OWNER, true)?.ok_or_else(invalid)?;
    let started = Instant::now();
    let mut acquired = Vec::new();
    for record in records {
        let name = record.sha256.strip_prefix("sha256:").ok_or_else(invalid)?;
        let cached = verified(&directory.directory, name, &record, started)?;
        if !cached {
            fetch(harness, &record, &directory, started)?;
        }
        acquired.push(json!({"digest":record.sha256,"byte_length":record.byte_length,"entry_point":record.entry_point,
            "cache_key":name,"cache_hit":cached,"verification":"exact_authenticated_plan_bytes"}));
    }
    Ok(json!({"directory":"software-artifacts","artifacts":acquired,"artifact_bytes":total}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn partial_transfer_retries_bind_disk_bytes_and_vendor_authorities() -> Result<()> {
        let path = std::env::temp_dir().join(format!(
            "ai-stp-software-download-{}",
            ulid::Ulid::generate()
        ));
        std::fs::create_dir(&path).map_err(|_| invalid())?;
        let owned = OwnedDirectory::open(&path, "cache", OWNER, true)?.ok_or_else(invalid)?;
        let bytes = b"exact artifact bytes";
        let record = Download {
            platform: crate::provider::runtime::platform()?.into(),
            url: "https://registry.npmjs.org/@openai/codex/-/codex.tgz".into(),
            sha256: crate::digest::sha256(bytes),
            byte_length: bytes.len() as u64,
            entry_point: "bin/codex".into(),
        };
        let key = record.sha256.strip_prefix("sha256:").ok_or_else(invalid)?;
        let partial = format!("{key}.partial");
        assert!(receive(&owned, &record, &bytes[..5], Instant::now()).is_err());
        assert_eq!(owned.read_file(&partial, 100)?, Some(bytes[..5].to_vec()));
        assert!(!verified(&owned.directory, key, &record, Instant::now())?);
        receive(&owned, &record, &bytes[..], Instant::now())?;
        assert!(verified(&owned.directory, key, &record, Instant::now())?);
        assert!(owned.read_file(&partial, 100)?.is_none());
        let mut held =
            verified_file(&owned.directory, key, &record, Instant::now())?.ok_or_else(invalid)?;
        owned
            .directory
            .rename(key, &owned.directory, "held")
            .map_err(|_| invalid())?;
        let mut replacement = owned
            .directory
            .open_with(key, files::private_options().create_new(true))
            .map_err(|_| invalid())?;
        replacement
            .write_all(b"other artifact bytes")
            .map_err(|_| invalid())?;
        drop(replacement);
        let mut retained = Vec::new();
        held.read_to_end(&mut retained).map_err(|_| invalid())?;
        assert_eq!(retained, bytes);
        assert!(verified_file(&owned.directory, key, &record, Instant::now()).is_err());
        drop(held);
        owned.directory.remove_file(key).map_err(|_| invalid())?;
        owned
            .directory
            .rename("held", &owned.directory, key)
            .map_err(|_| invalid())?;
        owned
            .directory
            .rename(key, &owned.directory, &partial)
            .map_err(|_| invalid())?;
        let mut file = owned
            .directory
            .open_with(&partial, &files::private_options())
            .map_err(|_| invalid())?;
        file.write_all(b"other").map_err(|_| invalid())?;
        drop(file);
        let changed = owned.read_file(&partial, 100)?;
        assert!(receive(&owned, &record, &bytes[..], Instant::now()).is_err());
        assert_eq!(owned.read_file(&partial, 100)?, changed);
        assert!(!verified(&owned.directory, key, &record, Instant::now())?);
        owned
            .directory
            .rename(&partial, &owned.directory, key)
            .map_err(|_| invalid())?;
        assert!(verified(&owned.directory, key, &record, Instant::now()).is_err());
        owned.directory.remove_file(key).map_err(|_| invalid())?;
        assert!(
            receive(
                &owned,
                &record,
                b"exact artifact bytes surplus".as_slice(),
                Instant::now()
            )
            .is_err()
        );
        assert!(!verified(&owned.directory, key, &record, Instant::now())?);
        owned
            .directory
            .remove_file(&partial)
            .map_err(|_| invalid())?;
        assert!(
            receive(
                &owned,
                &record,
                b"wrong artifact bytes".as_slice(),
                Instant::now()
            )
            .is_err()
        );
        assert!(!verified(&owned.directory, key, &record, Instant::now())?);
        assert_eq!(
            owned.read_file(&partial, 100)?,
            Some(b"wrong artifact bytes".to_vec())
        );
        for (harness, text, redirect, allowed) in [
            ("codex", "https://registry.npmjs.org/a", false, true),
            ("codex", "https://github.com/a", true, false),
            (
                "codex",
                "https://registry.npmjs.org.evil.invalid/a",
                false,
                false,
            ),
            ("codex", "https://u:p@registry.npmjs.org/a", false, false),
            ("codex", "http://registry.npmjs.org/a", false, false),
            ("codex", "https://127.0.0.1/a", false, false),
            (
                "pi",
                "https://release-assets.githubusercontent.com/a?sig=value",
                false,
                false,
            ),
            (
                "pi",
                "https://release-assets.githubusercontent.com/a?sig=value",
                true,
                true,
            ),
        ] {
            assert_eq!(
                authority(harness, &Url::parse(text).map_err(|_| invalid())?, redirect),
                allowed
            );
        }
        drop(owned);
        std::fs::remove_dir_all(path).map_err(|_| invalid())?;
        Ok(())
    }
}
