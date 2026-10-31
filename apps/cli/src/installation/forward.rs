//! Forward-only configuration transactions with no before-image payloads.
//!
//! A pending transaction retains desired bytes, physical directory bindings and
//! before/after fingerprints. The legacy journal blocks older writers until all
//! effects and metadata are verified. Completion removes the desired payloads
//! and retains the original request and historical outcome.
//!
//! This is a sequence of atomic file replacements, not a simultaneous switch
//! of a running harness. The consumer must stage active environments separately.
//! Existing parent directories, root and metadata directories are physically
//! bound; links, hard-linked files, special files and structural file/directory
//! conversions are refused. User processes must not concurrently edit the same
//! managed files. Detected drift is preserved and refused, never rolled back.
//!
//! The database and its rollback journal are operational transaction state;
//! they contain no previous configuration payloads. Completed payload rows are
//! deleted with SQLite secure deletion enabled, not a promise of media erasure.
//! Directory durability is claimed only on platforms supporting directory fsync.
//! Empty content directories are retained; only admitted file paths are removed.

mod files;
mod preparation;
mod store;

#[cfg(test)]
mod tests;

use std::path::PathBuf;

use cap_fs_ext::DirExt;
use cap_std::fs::Dir;
use serde::{Deserialize, Serialize};

use crate::installation::{
    Error, ReasonCode, Result,
    journal::{JOURNAL_SCHEMA, Journal, Phase},
    lock::TargetLock,
    target::Target,
};

pub use files::Observation;
use files::{dir_id, io, open_root};

const STAGING: &str = "transaction";

/// Observe a target-relative file for pure planning, creating no control state.
///
/// # Errors
/// Refuses links, aliases, oversized files or a replaced physical target.
pub fn observe(target: &Target, path: &str) -> Result<(Observation, Option<Content>)> {
    if target.is_internal(path) {
        return Err(invalid());
    }
    let root = target.directory()?;
    let identity = dir_id(&root)?;
    let result = files::read(&root, path)?;
    if dir_id(&open_root(target.root())?)? != identity {
        return Err(invalid());
    }
    Ok(result)
}

fn invalid() -> Error {
    Error::new(
        ReasonCode::RecoveryRequired,
        "forward configuration request, content or physical target changed; recovery requires the original request",
    )
}

/// Desired file bytes and portable permission bits, never a before-image.
#[derive(Clone, Debug)]
pub struct Content {
    /// The complete final bytes, including any retained user-owned fields.
    pub bytes: Vec<u8>,
    /// Unix access bits; Windows uses the neutral value `0o600`.
    pub mode: u32,
}

impl Content {
    /// Construct bounded desired contents with a platform-appropriate mode.
    ///
    /// # Errors
    /// Refuses oversized files, special permission bits or a non-owner-readable file.
    pub fn new(bytes: Vec<u8>, mode: u32) -> Result<Self> {
        #[cfg(not(unix))]
        let mode = {
            let _ = mode;
            0o600
        };
        let content = Self { bytes, mode };
        content.validate()?;
        Ok(content)
    }

    fn validate(&self) -> Result<()> {
        if self.bytes.len() > files::FILE_LIMIT || self.mode & !0o777 != 0 || self.mode & 0o400 == 0
        {
            return Err(invalid());
        }
        Ok(())
    }
}

/// One exact file replacement or removal, bound to a prior observation.
#[derive(Clone, Debug)]
pub struct Change {
    /// Slash-separated target-relative path.
    pub path: String,
    /// The physical directory chain and file observed before admission.
    pub before: Observation,
    /// Final file contents, or absence for a removal.
    pub after: Option<Content>,
}

/// Validate a complete configuration effect list before planning or admission.
///
/// # Errors
/// Refuses duplicate paths, excessive files or more than 64 MiB of desired bytes.
pub fn validate_changes(changes: &[Change]) -> Result<()> {
    validate_effects(changes.iter(), store::CHANGE_LIMIT - 2, 64 * 1024 * 1024)
}

fn validate_effects<'a>(
    changes: impl Iterator<Item = &'a Change>,
    limit: usize,
    byte_limit: usize,
) -> Result<()> {
    let mut paths = std::collections::BTreeMap::new();
    let mut bytes = 0_usize;
    for (index, change) in changes.enumerate() {
        if index >= limit
            || !files::valid_path(&change.path)
            || paths
                .insert(
                    unicase::UniCase::new(change.path.as_str()),
                    change.path.as_str(),
                )
                .is_some()
        {
            return Err(invalid());
        }
        if let Some(content) = &change.after {
            content.validate()?;
            bytes = bytes.checked_add(content.bytes.len()).ok_or_else(invalid)?;
        }
        if bytes > byte_limit {
            return Err(invalid());
        }
    }
    let mut previous: Option<&str> = None;
    for path in paths.values().copied() {
        if let Some(previous) = previous {
            for (left, right) in previous.split('/').zip(path.split('/')) {
                if unicase::UniCase::new(left) != unicase::UniCase::new(right) {
                    break;
                }
                if left != right {
                    return Err(invalid());
                }
            }
        }
        let mut parent = path;
        while let Some((ancestor, _)) = parent.rsplit_once('/') {
            if paths.contains_key(&unicase::UniCase::new(ancestor)) {
                return Err(invalid());
            }
            parent = ancestor;
        }
        previous = Some(path);
    }
    Ok(())
}

/// Original caller identity, retained across interruptions and response loss.
#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Admission {
    /// Original operation identifier.
    pub operation_id: String,
    /// Full provider plan digest, not a kernel-generated substitute.
    pub plan_digest: String,
    /// The configuration operation authorized by that plan.
    pub operation: String,
    /// Original target precondition digest.
    pub target_precondition_digest: String,
    /// Original declared scope, if any.
    pub target_scope: Option<String>,
}

impl Admission {
    fn validate(&self) -> Result<()> {
        let digest = |text: &str| {
            text.strip_prefix("sha256:").is_some_and(|hex| {
                hex.len() == 64
                    && hex
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            })
        };
        if self.operation_id.is_empty()
            || self.operation_id.len() > 128
            || !self
                .operation_id
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'))
            || !digest(&self.plan_digest)
            || !digest(&self.target_precondition_digest)
            || !matches!(self.operation.as_str(), "install" | "replace" | "remove")
            || self
                .target_scope
                .as_deref()
                .is_some_and(|v| !matches!(v, "project" | "user_root"))
        {
            return Err(invalid());
        }
        Ok(())
    }

    fn cancellation(&self) -> serde_json::Value {
        serde_json::json!({"state":"cancelled", "operation_id":self.operation_id,
            "operation":self.operation, "plan_digest":self.plan_digest,
            "expected_target_digest":self.target_precondition_digest,
            "configuration_changed":false})
    }

    fn journal(&self) -> Journal {
        Journal {
            schema_version: JOURNAL_SCHEMA,
            phase: Phase::Prepared,
            operation_id: self.operation_id.clone(),
            operation: self.operation.clone(),
            plan_digest: self.plan_digest.clone(),
            target_precondition_digest: self.target_precondition_digest.clone(),
            backup_ref: None,
            target_scope: self.target_scope.clone(),
        }
    }
}

/// The exact operation's current state; historical outcomes do not reapply files.
pub enum Progress {
    /// No request with this operation identifier has been admitted.
    Absent,
    /// Desired bytes are durable; configuration publication has not started.
    Prepared(serde_json::Value),
    /// Resume desired file publication, using the retained runtime context.
    Applying(serde_json::Value),
    /// Final metadata and outcome have been admitted; resume their publication.
    Finishing,
    /// An immutable historical outcome, even if a later operation changed files.
    Completed(serde_json::Value),
    /// An exact cancellation tombstone; delayed application must stay refused.
    Cancelled(serde_json::Value),
}

/// One target writer, sharing the legacy target lock and held directory identities.
pub struct Writer {
    // Keep SQLite and its VFS scope alive only while the target lock is held.
    store: store::Store,
    root: Dir,
    control: Dir,
    path: PathBuf,
    control_name: String,
    identity: files::Identity,
    control_identity: files::Identity,
    lock: TargetLock,
}

impl Writer {
    /// Acquire a plain existing target and initialize only transaction metadata.
    ///
    /// # Errors
    /// Refuses contending writers, links, replaced directories or foreign records.
    pub fn acquire(target: &Target, control_name: &str) -> Result<Self> {
        if !files::valid_path(control_name) || control_name.contains('/') {
            return Err(invalid());
        }
        if target.control_directory() != target.root().join(control_name) {
            return Err(invalid());
        }
        let root = target.directory()?;
        let identity = dir_id(&root)?;
        let created = match root.create_dir(control_name) {
            Ok(()) => true,
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => false,
            Err(error) => return Err(invalid().with_source(error)),
        };
        let control = io(root.open_dir_nofollow(control_name))?;
        if created {
            #[cfg(unix)]
            {
                use cap_std::fs::PermissionsExt;
                io(control.set_permissions(".", cap_std::fs::Permissions::from_mode(0o700)))?;
            }
            files::sync(&control)?;
            files::sync(&root)?;
        }
        let control_identity = dir_id(&control)?;
        let lock = TargetLock::acquire_at(&control, &target.control_directory())?;
        let store = store::Store::open(&control, identity)?;
        let writer = Self {
            store,
            root,
            control,
            path: target.root().to_owned(),
            control_name: control_name.to_owned(),
            identity,
            control_identity,
            lock,
        };
        writer.revalidate()?;
        Ok(writer)
    }

    fn revalidate(&self) -> Result<()> {
        let root = open_root(&self.path)?;
        if dir_id(&root)? != self.identity
            || dir_id(&io(root.open_dir_nofollow(&self.control_name))?)? != self.control_identity
        {
            return Err(invalid());
        }
        self.lock.revalidate()
    }

    fn journal(&self) -> Result<Option<Journal>> {
        self.revalidate()?;
        let (_, content) = files::read(
            &self.control,
            crate::installation::journal::JOURNAL_FILE_NAME,
        )?;
        content
            .map(|content| {
                if content.bytes.len() > 64 * 1024 {
                    return Err(invalid());
                }
                let value: serde_json::Value =
                    crate::wire::parse(&content.bytes).map_err(|_| invalid())?;
                let journal: Journal =
                    serde_json::from_value(value.clone()).map_err(|_| invalid())?;
                if journal.schema_version != JOURNAL_SCHEMA
                    || serde_json::to_value(&journal).map_err(|_| invalid())? != value
                {
                    return Err(invalid());
                }
                Ok(journal)
            })
            .transpose()
    }

    /// Read a bounded plain file without following any target-relative links.
    ///
    /// # Errors
    /// Refuses special files, aliases, changed ancestors, or oversized contents.
    pub fn read(&self, path: &str) -> Result<(Observation, Option<Content>)> {
        if crate::installation::target::internal_path(path, &self.control_name) {
            return Err(invalid());
        }
        self.revalidate()?;
        files::read(&self.root, path)
    }

    /// Bind final bytes to the current file observation.
    ///
    /// # Errors
    /// Propagates the bounded observation refusal.
    pub fn change(&self, path: &str, after: Option<Content>) -> Result<Change> {
        let (before, _) = self.read(path)?;
        Ok(Change {
            path: path.into(),
            before,
            after,
        })
    }

    /// Inspect exactly this original request, never another pending operation.
    ///
    /// # Errors
    /// Refuses operation-id reuse with a different plan or replaced physical state.
    pub fn progress(&self, admission: &Admission) -> Result<Progress> {
        admission.validate()?;
        self.revalidate()?;
        let Some(record) = self.store.record(admission)? else {
            return Ok(Progress::Absent);
        };
        match record.phase.as_str() {
            "prepared" => Ok(Progress::Prepared(record.context)),
            "applying" => Ok(Progress::Applying(record.context)),
            "finishing" => Ok(Progress::Finishing),
            "completed" => {
                if record.outcome == Some(admission.cancellation()) {
                    self.clear_completed(&record)?;
                    return Ok(Progress::Cancelled(record.outcome.ok_or_else(invalid)?));
                }
                self.clear_completed(&record)?;
                Ok(Progress::Completed(record.outcome.ok_or_else(invalid)?))
            }
            _ => Err(invalid()),
        }
    }

    /// Admit a checked request and desired file bytes before the first file effect.
    ///
    /// # Errors
    /// Refuses stale observations, an unfinished legacy operation or another request.
    pub fn admit(
        &mut self,
        admission: &Admission,
        context: &serde_json::Value,
        changes: &[Change],
    ) -> Result<()> {
        self.admit_inner(admission, context, changes, false)
    }

    fn admit_inner(
        &mut self,
        admission: &Admission,
        context: &serde_json::Value,
        changes: &[Change],
        prepared: bool,
    ) -> Result<()> {
        admission.validate()?;
        validate_changes(changes)?;
        self.revalidate()?;
        if self.journal()?.is_some() {
            return Err(invalid());
        }
        match self.control.symlink_metadata(STAGING) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            _ => return Err(invalid()),
        }
        for change in changes {
            if self.read(&change.path)?.0 != change.before {
                return Err(invalid());
            }
        }
        self.store.admit(admission, context, changes, prepared)
    }

    fn unchanged(&self, admission: &Admission) -> Result<()> {
        for change in self.store.changes(&admission.operation_id)? {
            if self.read(&change.path)?.0 != change.before {
                return Err(invalid());
            }
        }
        Ok(())
    }

    /// Cancel an exact request only while no configuration publication can have started.
    ///
    /// The durable tombstone also covers a request that never reached this writer.
    /// A public journal alone cannot establish absence of SQLite admission.
    ///
    /// # Errors
    /// Refuses changed observations, started or completed publication, and identity reuse.
    pub fn cancel(&mut self, admission: &Admission) -> Result<serde_json::Value> {
        admission.validate()?;
        self.revalidate()?;
        let outcome = admission.cancellation();
        let record = self.store.record(admission)?;
        if let Some(record) = &record {
            if record.phase == "completed" && record.outcome == Some(outcome.clone()) {
                self.clear_completed(record)?;
                return Ok(outcome);
            }
            if record.phase == "prepared" {
                // Complete an interrupted guard publication before retiring
                // the preparation. This never writes final configuration.
                self.prepared(admission)?;
            } else {
                if record.phase != "applying" || record.stage.is_some() || self.journal()?.is_some()
                {
                    return Err(invalid());
                }
                match self.control.symlink_metadata(STAGING) {
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
                    _ => return Err(invalid()),
                }
            }
            self.unchanged(admission)?;
        }
        self.store.cancel(admission, &outcome, record.is_some())?;
        self.clear_completed(&self.store.record(admission)?.ok_or_else(invalid)?)?;
        self.revalidate()?;
        Ok(outcome)
    }

    fn staging(&self, record: &store::Record) -> Result<Dir> {
        self.revalidate()?;
        let expected = record.admission.journal();
        let present = self.journal()?;
        if present.as_ref().is_some_and(|journal| *journal != expected) {
            return Err(invalid());
        }
        if present.is_none() {
            // Admission may precede guard publication. No target effect may
            // resume without the guard and all original file observations.
            for change in self.store.changes(&record.admission.operation_id)? {
                if self.read(&change.path)?.0 != change.before {
                    return Err(invalid());
                }
            }
        }
        let staging = match self.control.open_dir_nofollow(STAGING) {
            Ok(directory) => directory,
            Err(error)
                if error.kind() == std::io::ErrorKind::NotFound && record.stage.is_none() =>
            {
                io(self.control.create_dir(STAGING))?;
                files::sync(&self.control)?;
                io(self.control.open_dir_nofollow(STAGING))?
            }
            Err(error) => return Err(invalid().with_source(error)),
        };
        let id = dir_id(&staging)?;
        if let Some(expected) = record.stage {
            if id != expected {
                return Err(invalid());
            }
        } else {
            if io(staging.entries())?.next().is_some() {
                return Err(invalid());
            }
            self.store.set_stage(&record.admission.operation_id, id)?;
        }
        if present.is_none() {
            let value = serde_json::to_value(&expected).map_err(|_| invalid())?;
            let bytes = crate::installation::canonical::to_canonical_bytes(&value)?;
            let (before, _) = files::read(
                &self.control,
                crate::installation::journal::JOURNAL_FILE_NAME,
            )?;
            if before.file.is_some() {
                return Err(invalid());
            }
            let guard = Change {
                path: crate::installation::journal::JOURNAL_FILE_NAME.into(),
                before,
                after: Some(Content::new(bytes, 0o600)?),
            };
            files::publish(&self.control, &staging, "guard", &guard)?;
            self.revalidate()?;
        }
        Ok(staging)
    }

    /// Resume publication of the original desired bytes, accepting exact before/after states.
    ///
    /// # Errors
    /// Refuses foreign file changes, changed parent identities or an unrelated journal.
    pub fn apply(&self, admission: &Admission) -> Result<()> {
        let record = self.store.record(admission)?.ok_or_else(invalid)?;
        if !matches!(record.phase.as_str(), "applying" | "finishing") {
            return Err(invalid());
        }
        let staging = self.staging(&record)?;
        let changes = self.store.changes(&admission.operation_id)?;
        for (index, change) in changes.iter().enumerate() {
            self.revalidate()?;
            if dir_id(&io(self.control.open_dir_nofollow(STAGING))?)? != dir_id(&staging)? {
                return Err(invalid());
            }
            files::publish(&self.root, &staging, &index.to_string(), change)?;
        }
        self.verify(&changes)
    }

    fn verify(&self, changes: &[Change]) -> Result<()> {
        for change in changes {
            let (now, _) = self.read(&change.path)?;
            files::check_parents(&change.before, &now)?;
            if !files::same_content(now.file.as_ref(), change.after.as_ref()) {
                return Err(invalid());
            }
        }
        Ok(())
    }

    /// Freeze final provider metadata and its historical result after verifying file effects.
    ///
    /// # Errors
    /// Refuses changed effects, overlapping paths or an already finalized operation.
    pub fn finish(
        &mut self,
        admission: &Admission,
        changes: &[Change],
        outcome: &serde_json::Value,
    ) -> Result<()> {
        let record = self.store.record(admission)?.ok_or_else(invalid)?;
        if record.phase != "applying" {
            return Err(invalid());
        }
        let existing = self.store.changes(&admission.operation_id)?;
        // Final metadata shares the same namespace and aggregate payload bound
        // as the admitted configuration. Validate references without cloning
        // desired file bytes or admitting a later case/ancestor collision.
        validate_effects(
            existing.iter().chain(changes),
            store::CHANGE_LIMIT,
            store::PAYLOAD_LIMIT,
        )?;
        self.verify(&existing)?;
        for change in changes {
            if self.read(&change.path)?.0 != change.before {
                return Err(invalid());
            }
        }
        self.store.finish(&admission.operation_id, changes, outcome)
    }

    /// Verify the entire result and durably replace desired payloads with a receipt.
    ///
    /// # Errors
    /// Refuses incomplete metadata, changed files or unrecognized activation entries.
    pub fn complete(&mut self, admission: &Admission) -> Result<serde_json::Value> {
        let record = self.store.record(admission)?.ok_or_else(invalid)?;
        if record.phase != "finishing" {
            return Err(invalid());
        }
        self.verify(&self.store.changes(&admission.operation_id)?)?;
        let staging = self.staging(&record)?;
        if io(staging.entries())?.next().is_some() {
            return Err(invalid());
        }
        // Windows refuses removal while this directory handle remains open.
        // Cleanup reopens and verifies the recorded identity before removal.
        drop(staging);
        self.store.complete(&admission.operation_id)?;
        let completed = self.store.record(admission)?.ok_or_else(invalid)?;
        self.clear_completed(&completed)?;
        completed.outcome.ok_or_else(invalid)
    }

    fn clear_completed(&self, record: &store::Record) -> Result<()> {
        self.revalidate()?;
        // A historical replay must never clear a newer operation's guard.
        let journal = self.journal()?;
        if journal
            .as_ref()
            .is_some_and(|held| *held != record.admission.journal())
            || (journal.is_none() && (record.stage.is_none() || self.store.has_active()?))
        {
            return Ok(());
        }
        match self.control.open_dir_nofollow(STAGING) {
            Ok(directory) => {
                if Some(dir_id(&directory)?) != record.stage
                    || io(directory.entries())?.next().is_some()
                {
                    return Err(invalid());
                }
                drop(directory);
                io(self.control.remove_dir(STAGING))?;
                files::sync(&self.control)?;
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(invalid().with_source(error)),
        }
        if journal.is_some() {
            io(self
                .control
                .remove_file(crate::installation::journal::JOURNAL_FILE_NAME))?;
        }
        files::sync(&self.control)
    }
}
