//! Read-only compatibility guards for retained configuration transactions.
//!
//! The forward writer publishes and removes its own marker relative to held
//! directories. This module never captures a backup, writes an ambient path or
//! migrates another implementation's journal.

use super::{Error, ReasonCode, Result};
use cap_fs_ext::{FollowSymlinks, MetadataExt, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::OpenOptions;
use serde::{Deserialize, Serialize};
use std::{
    io::Read,
    path::{Path, PathBuf},
};

pub const JOURNAL_FILE_NAME: &str = "journal.json";
pub const JOURNAL_SCHEMA: u32 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Prepared,
    Committed,
}
impl Phase {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Prepared => "prepared",
            Self::Committed => "committed",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Journal {
    pub schema_version: u32,
    pub phase: Phase,
    pub operation_id: String,
    pub operation: String,
    pub plan_digest: String,
    pub target_precondition_digest: String,
    pub backup_ref: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_scope: Option<String>,
}

fn invalid() -> Error {
    Error::new(
        ReasonCode::RecoveryRequired,
        "the retained installation journal cannot be safely interpreted",
    )
}

impl Journal {
    pub fn path(directory: &Path) -> PathBuf {
        directory.join(JOURNAL_FILE_NAME)
    }

    pub fn read(path: &Path) -> Result<Option<Self>> {
        let directory = match super::target::open(path) {
            Ok(directory) => directory,
            Err(error) if error.is_missing_path() => return Ok(None),
            Err(error) => return Err(invalid().with_source(error)),
        };
        let mut options = OpenOptions::new();
        options.read(true).follow(FollowSymlinks::No).nonblock(true);
        let mut file = match directory.open_with(JOURNAL_FILE_NAME, &options) {
            Ok(file) => file,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(invalid().with_source(error)),
        };
        let metadata = file
            .metadata()
            .map_err(|source| invalid().with_source(source))?;
        if !metadata.is_file() || metadata.nlink() != 1 || metadata.len() > 65536 {
            return Err(invalid());
        }
        let identity =
            super::identity::file(&file).map_err(|source| invalid().with_source(source))?;
        let mut bytes = Vec::new();
        Read::by_ref(&mut file)
            .take(65537)
            .read_to_end(&mut bytes)
            .map_err(|source| invalid().with_source(source))?;
        if bytes.len() > 65536 {
            return Err(invalid());
        }
        let named = directory
            .open_with(JOURNAL_FILE_NAME, &options)
            .map_err(|source| invalid().with_source(source))?;
        if super::identity::file(&named).map_err(|source| invalid().with_source(source))?
            != identity
        {
            return Err(invalid());
        }
        let value = crate::wire::parse(&bytes).map_err(|source| invalid().with_source(source))?;
        let journal: Self =
            serde_json::from_value(value).map_err(|source| invalid().with_source(source))?;
        if journal.schema_version != JOURNAL_SCHEMA
            || journal
                .backup_ref
                .as_ref()
                .is_some_and(|reference| !valid_legacy_backup_ref(reference))
        {
            return Err(invalid());
        }
        Ok(Some(journal))
    }
}

fn valid_legacy_backup_ref(value: &str) -> bool {
    value.strip_prefix("slot-").is_some_and(|digits| {
        digits.len() == 12 && digits.bytes().all(|byte| byte.is_ascii_digit())
    })
}

pub fn require_clean_for_planning(
    control: &Path,
    transaction: &Path,
    partial_slots: &[PathBuf],
) -> Result<()> {
    let transaction_present = match transaction.symlink_metadata() {
        Ok(_) => true,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
        Err(error) => return Err(invalid().with_source(error)),
    };
    if Journal::read(control)?.is_some() || transaction_present || !partial_slots.is_empty() {
        return Err(invalid());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> Journal {
        Journal {
            schema_version: JOURNAL_SCHEMA,
            phase: Phase::Prepared,
            operation_id: "operation_ORIGINAL".into(),
            operation: "replace".into(),
            plan_digest: crate::digest::sha256(b"original"),
            target_precondition_digest: crate::digest::sha256(b"target"),
            backup_ref: None,
            target_scope: Some("project".into()),
        }
    }

    #[test]
    fn absent_and_valid_original_markers_are_read_without_publication()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let path = root.path().canonicalize()?;
        assert_eq!(Journal::read(&path)?, None);
        let bytes = serde_json::to_vec(&sample())?;
        std::fs::write(Journal::path(&path), &bytes)?;
        assert_eq!(Journal::read(&path)?, Some(sample()));
        assert_eq!(std::fs::read(Journal::path(&path))?, bytes);
        assert!(require_clean_for_planning(&path, &path.join("transaction"), &[]).is_err());
        Ok(())
    }

    #[test]
    fn malformed_future_foreign_and_aliased_markers_refuse_without_changes()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let path = root.path().canonicalize()?;
        let original = serde_json::to_value(sample())?;
        let mut future = original.clone();
        future["schema_version"] = 2.into();
        let mut foreign = original.clone();
        foreign["unknown"] = true.into();
        let mut bad_reference = original;
        bad_reference["backup_ref"] = "../foreign".into();
        let duplicate = serde_json::to_string(&sample())?.replacen(
            "\"phase\":\"prepared\"",
            "\"phase\":\"committed\",\"phase\":\"prepared\"",
            1,
        );
        for bytes in [
            b"not json".to_vec(),
            duplicate.into_bytes(),
            serde_json::to_vec(&future)?,
            serde_json::to_vec(&foreign)?,
            serde_json::to_vec(&bad_reference)?,
        ] {
            std::fs::write(Journal::path(&path), &bytes)?;
            assert!(Journal::read(&path).is_err());
            assert_eq!(std::fs::read(Journal::path(&path))?, bytes);
        }
        std::fs::remove_file(Journal::path(&path))?;
        let other = path.join("unowned");
        std::fs::write(&other, serde_json::to_vec(&sample())?)?;
        std::fs::hard_link(&other, Journal::path(&path))?;
        assert!(Journal::read(&path).is_err());
        assert_eq!(std::fs::read(other)?, serde_json::to_vec(&sample())?);
        Ok(())
    }

    #[test]
    fn unresolved_transaction_and_legacy_partial_slots_refuse()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let path = root.path().canonicalize()?;
        let transaction = path.join("transaction");
        assert!(require_clean_for_planning(&path, &transaction, &[]).is_ok());
        std::fs::create_dir(&transaction)?;
        assert!(require_clean_for_planning(&path, &transaction, &[]).is_err());
        std::fs::remove_dir(&transaction)?;
        assert!(
            require_clean_for_planning(&path, &transaction, &[path.join("legacy-partial")])
                .is_err()
        );
        Ok(())
    }
}
