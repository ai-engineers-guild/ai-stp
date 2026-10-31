//! The durable journal that makes an interrupted mutation legible.
//!
//! Before the first write, a mutation publishes a journal in phase
//! [`Phase::Prepared`], bound to the exact plan digest, the operation id and the
//! target-bound backup reference. After the result is verified the journal moves
//! atomically to [`Phase::Committed`]. It is cleared only once the new state is
//! durable.
//!
//! The phase is not a progress indicator. It answers one question — *was the
//! effect applied?* — and the answer decides who may clean up:
//!
//! | Phase       | What is known                    | Recovery does                    |
//! | ----------- | -------------------------------- | -------------------------------- |
//! | `prepared`  | the effect may be partial        | restore the exact pre-state      |
//! | `committed` | the effect is complete           | verify the result, clear tails   |
//!
//! While a journal exists, planning refuses with
//! [`ReasonCode::RecoveryRequired`] rather than guessing. Guessing is what turns
//! one interrupted operation into two conflicting ones.

use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::installation::error::{Error, ReasonCode, Result};
use crate::installation::lock;

/// The journal file name inside the control directory.
pub const JOURNAL_FILE_NAME: &str = "journal.json";

/// The schema this kernel writes and is willing to read.
pub const JOURNAL_SCHEMA: u32 = 1;

/// Which side of the effect the operation is on.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    /// Published before the first write. The effect may be partial.
    Prepared,
    /// Published after the result is verified. The effect is complete.
    Committed,
}

impl Phase {
    /// The exact string the wire surface emits.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Prepared => "prepared",
            Self::Committed => "committed",
        }
    }
}

/// A durable record of one in-flight or just-completed mutation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Journal {
    /// Schema of this record.
    pub schema_version: u32,
    /// Which side of the effect this operation is on.
    pub phase: Phase,
    /// The stable identifier of the operation.
    pub operation_id: String,
    /// The operation being performed, from the closed core/optional sets.
    pub operation: String,
    /// The exact plan digest this mutation was authorized by.
    pub plan_digest: String,
    /// The target identity digest observed after the lock was taken.
    pub target_precondition_digest: String,
    /// The target-bound backup captured before the first write, when one exists.
    pub backup_ref: Option<String>,
    /// The scope the interrupted operation named, when it named one.
    ///
    /// `recover-operation` takes no arguments — that is the argv contract — so
    /// the only place a scope can reach a recovery is the record the operation
    /// left behind. Without it a recovery of a scoped operation would put the
    /// payload back over the *global* namespaces, which under `~/.agents` or a
    /// workspace names nothing and silently restores nothing.
    ///
    /// Additive and defaulted rather than a schema bump: a journal written by
    /// an older build carries no scope because that build had no scope to act
    /// on, so absent means global and says something true. Bumping the schema
    /// would instead make every in-flight journal from the previous release
    /// unrecoverable, which is a worse answer to a question that has a right
    /// one.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_scope: Option<String>,
}

impl Journal {
    /// The journal path inside a control directory.
    #[must_use]
    pub fn path(control_directory: &Path) -> PathBuf {
        control_directory.join(JOURNAL_FILE_NAME)
    }

    /// Read the journal, if one is published.
    ///
    /// # Errors
    ///
    /// Returns [`ReasonCode::RecoveryRequired`] if a journal exists but cannot
    /// be parsed. An unreadable journal is still evidence that a mutation was
    /// in flight, and treating it as absence would let the next plan write over
    /// an unfinished one.
    pub fn read(control_directory: &Path) -> Result<Option<Self>> {
        let path = Self::path(control_directory);
        let bytes = match fs::read(&path) {
            Ok(bytes) => bytes,
            Err(source) if source.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(source) => {
                return Err(Error::new(
                    ReasonCode::RecoveryRequired,
                    format!("a journal exists at {} but cannot be read", path.display()),
                )
                .with_source(source));
            }
        };
        let journal: Self = serde_json::from_slice(&bytes).map_err(|source| {
            Error::new(
                ReasonCode::RecoveryRequired,
                format!("a journal exists at {} but does not parse", path.display()),
            )
            .with_source(source)
        })?;
        if journal.schema_version != JOURNAL_SCHEMA {
            return Err(Error::new(
                ReasonCode::RecoveryRequired,
                format!(
                    "journal schema {} is not the {JOURNAL_SCHEMA} this build writes",
                    journal.schema_version
                ),
            ));
        }
        // Recovery joins the reference to the pool unchecked; a journal cannot
        // name a slot this kernel would refuse to mint.
        if let Some(reference) = &journal.backup_ref
            && !valid_legacy_backup_ref(reference)
        {
            return Err(Error::new(
                ReasonCode::RecoveryRequired,
                format!("journal backup reference {reference:?} is not valid"),
            ));
        }
        Ok(Some(journal))
    }

    /// Publish this journal in phase `prepared`, before the first write.
    ///
    /// # Errors
    ///
    /// Returns [`ReasonCode::RecoveryRequired`] if a journal is already
    /// published, and [`ReasonCode::StateUnavailable`] if the write fails.
    pub fn publish_prepared(self, control_directory: &Path) -> Result<Self> {
        if Self::path(control_directory).exists() {
            return Err(Error::new(
                ReasonCode::RecoveryRequired,
                "a journal is already published; only recovery may resolve it",
            ));
        }
        let prepared = Self {
            phase: Phase::Prepared,
            ..self
        };
        prepared.write(control_directory)?;
        Ok(prepared)
    }

    /// Move this journal to `committed` after the result is verified.
    ///
    /// # Errors
    ///
    /// Returns [`ReasonCode::StateUnavailable`] if the write fails.
    pub fn promote_to_committed(self, control_directory: &Path) -> Result<Self> {
        let committed = Self {
            phase: Phase::Committed,
            ..self
        };
        committed.write(control_directory)?;
        Ok(committed)
    }

    /// Remove the journal once the new state is durable.
    ///
    /// The unlink is flushed like a write is: an unflushed removal can
    /// resurrect the journal on the next mount and send recovery through a
    /// second time.
    ///
    /// # Errors
    ///
    /// Returns [`ReasonCode::StateUnavailable`] if the file cannot be removed.
    pub fn clear(control_directory: &Path) -> Result<()> {
        let path = Self::path(control_directory);
        match crate::installation::lock::remove_file(&path) {
            Ok(()) => Ok(()),
            Err(source) if source.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(source) => Err(Error::new(
                ReasonCode::StateUnavailable,
                format!("cannot clear {}", path.display()),
            )
            .with_source(source)),
        }
    }

    fn write(&self, control_directory: &Path) -> Result<()> {
        let value = serde_json::to_value(self).map_err(|source| {
            Error::new(ReasonCode::StateUnavailable, "cannot encode the journal")
                .with_source(source)
        })?;
        let bytes = crate::installation::canonical::to_canonical_bytes(&value)?;
        lock::atomic_write(&Self::path(control_directory), &bytes)
    }
}

/// Refuse to plan while any unresolved mutation state is present.
///
/// This is the gate that keeps a second operation from starting on top of a
/// first. It fails closed on a published journal, on a leftover transaction
/// directory, and on a backup slot that never finished being written.
///
/// # Errors
///
/// Returns [`ReasonCode::RecoveryRequired`] naming which of the three was found.
pub fn require_clean_for_planning(
    control_directory: &Path,
    transaction_directory: &Path,
    partial_backup_slots: &[PathBuf],
) -> Result<()> {
    if let Some(journal) = Journal::read(control_directory)? {
        return Err(Error::new(
            ReasonCode::RecoveryRequired,
            format!(
                "operation {} is journaled as {}; run recovery before planning",
                journal.operation_id,
                journal.phase.as_str()
            ),
        ));
    }
    if transaction_directory.exists() {
        return Err(Error::new(
            ReasonCode::RecoveryRequired,
            format!(
                "a transaction directory remains at {}; run recovery before planning",
                transaction_directory.display()
            ),
        ));
    }
    if let Some(slot) = partial_backup_slots.first() {
        return Err(Error::new(
            ReasonCode::RecoveryRequired,
            format!(
                "backup slot {} is incomplete; run recovery before planning",
                slot.display()
            ),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::panic)]

    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let base =
            std::env::temp_dir().join(format!("setup-core-journal-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(&base).unwrap();
        base
    }

    fn sample() -> Journal {
        Journal {
            schema_version: JOURNAL_SCHEMA,
            phase: Phase::Prepared,
            operation_id: "op_test".to_owned(),
            operation: "install".to_owned(),
            plan_digest: "sha256:plan".to_owned(),
            target_precondition_digest: "sha256:target".to_owned(),
            backup_ref: Some("slot-000000000001".to_owned()),
            target_scope: None,
        }
    }

    #[test]
    fn an_absent_journal_reads_as_none_not_as_an_error() {
        let control = scratch("absent");
        assert!(Journal::read(&control).unwrap().is_none());
    }

    #[test]
    fn a_published_journal_round_trips_through_its_canonical_bytes() {
        let control = scratch("roundtrip");
        let published = sample().publish_prepared(&control).unwrap();
        let read = Journal::read(&control).unwrap().unwrap();
        assert_eq!(read, published);
        assert_eq!(read.phase, Phase::Prepared);
    }

    #[test]
    fn publishing_over_an_existing_journal_is_refused() {
        let control = scratch("double");
        sample().publish_prepared(&control).unwrap();
        let error = sample().publish_prepared(&control).unwrap_err();
        assert_eq!(error.reason(), ReasonCode::RecoveryRequired);
    }

    #[test]
    fn promotion_changes_only_the_phase() {
        let control = scratch("promote");
        let prepared = sample().publish_prepared(&control).unwrap();
        let committed = prepared.clone().promote_to_committed(&control).unwrap();
        assert_eq!(committed.phase, Phase::Committed);
        assert_eq!(committed.operation_id, prepared.operation_id);
        assert_eq!(committed.plan_digest, prepared.plan_digest);
        assert_eq!(
            Journal::read(&control).unwrap().unwrap().phase,
            Phase::Committed
        );
    }

    #[test]
    fn an_unparseable_journal_demands_recovery_rather_than_reading_as_absent() {
        let control = scratch("corrupt");
        fs::write(Journal::path(&control), b"{ not json").unwrap();
        let error = Journal::read(&control).unwrap_err();
        assert_eq!(error.reason(), ReasonCode::RecoveryRequired);
    }

    /// Recovery joins the named reference to the pool unchecked; a journal
    /// that names an invalid one is corrupt state, not a recoverable pointer.
    #[test]
    fn a_journal_naming_an_invalid_backup_reference_demands_recovery() {
        let control = scratch("bad-ref");
        let mut value = serde_json::to_value(sample()).unwrap();
        value["backup_ref"] = serde_json::json!("../escape");
        fs::write(Journal::path(&control), serde_json::to_vec(&value).unwrap()).unwrap();
        let error = Journal::read(&control).unwrap_err();
        assert_eq!(error.reason(), ReasonCode::RecoveryRequired);
    }

    #[test]
    fn a_future_schema_demands_recovery_rather_than_optimistic_parsing() {
        let control = scratch("schema");
        let mut value = serde_json::to_value(sample()).unwrap();
        value["schema_version"] = serde_json::json!(JOURNAL_SCHEMA + 1);
        fs::write(Journal::path(&control), serde_json::to_vec(&value).unwrap()).unwrap();
        let error = Journal::read(&control).unwrap_err();
        assert_eq!(error.reason(), ReasonCode::RecoveryRequired);
    }

    #[test]
    fn clearing_an_absent_journal_is_not_an_error() {
        let control = scratch("clear-absent");
        assert!(Journal::clear(&control).is_ok());
    }

    #[test]
    fn planning_is_refused_by_each_of_the_three_leftovers_independently() {
        let base = scratch("gate");
        let control = base.join("control");
        let transaction = base.join("txn");
        fs::create_dir_all(&control).unwrap();

        // Nothing present: planning proceeds.
        require_clean_for_planning(&control, &transaction, &[]).unwrap();

        // A journal alone blocks.
        sample().publish_prepared(&control).unwrap();
        let error = require_clean_for_planning(&control, &transaction, &[]).unwrap_err();
        assert_eq!(error.reason(), ReasonCode::RecoveryRequired);
        Journal::clear(&control).unwrap();

        // A transaction directory alone blocks.
        fs::create_dir_all(&transaction).unwrap();
        let error = require_clean_for_planning(&control, &transaction, &[]).unwrap_err();
        assert_eq!(error.reason(), ReasonCode::RecoveryRequired);
        fs::remove_dir_all(&transaction).unwrap();

        // A partial backup slot alone blocks.
        let slot = base.join("slot-3");
        let error = require_clean_for_planning(&control, &transaction, &[slot]).unwrap_err();
        assert_eq!(error.reason(), ReasonCode::RecoveryRequired);
    }
}

fn valid_legacy_backup_ref(value: &str) -> bool {
    value.strip_prefix("slot-").is_some_and(|digits| {
        digits.len() == 12 && digits.bytes().all(|byte| byte.is_ascii_digit())
    })
}
