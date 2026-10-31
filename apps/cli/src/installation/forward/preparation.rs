//! Durable preparation is distinct from the first configuration publication.

use super::{Admission, Change, Progress, Result, Writer, invalid, io};

impl Writer {
    /// Retain desired bytes and publish the legacy-writer guard without applying
    /// a configuration change. Repeated preparation verifies the original state.
    ///
    /// # Errors
    /// Refuses changed observations, another active request or begun publication.
    pub fn prepare(
        &mut self,
        admission: &Admission,
        context: &serde_json::Value,
        changes: &[Change],
    ) -> Result<serde_json::Value> {
        match self.progress(admission)? {
            Progress::Absent => self.admit_inner(admission, context, changes, true)?,
            Progress::Prepared(_) => (),
            Progress::Completed(outcome) | Progress::Cancelled(outcome) => return Ok(outcome),
            Progress::Applying(_) | Progress::Finishing => return Err(invalid()),
        }
        self.prepared(admission)
    }

    /// Finish or replay preparation from its durable record without source bytes.
    ///
    /// # Errors
    /// Refuses missing preparation, physical substitution or configuration drift.
    pub fn prepared(&self, admission: &Admission) -> Result<serde_json::Value> {
        let record = self.store.record(admission)?.ok_or_else(invalid)?;
        if record.phase != "prepared" {
            return Err(invalid());
        }
        self.unchanged(admission)?;
        let staging = self.staging(&record)?;
        if io(staging.entries())?.next().is_some() {
            return Err(invalid());
        }
        self.revalidate()?;
        Ok(
            serde_json::json!({"state":"prepared", "operation_id":admission.operation_id,
            "operation":admission.operation, "plan_digest":admission.plan_digest,
            "expected_target_digest":admission.target_precondition_digest,
            "configuration_changed":false}),
        )
    }

    /// Durably close the cancellation window before any configuration effect.
    ///
    /// # Errors
    /// Refuses absent preparation, drift or a changed operational guard.
    pub fn start(&self, admission: &Admission) -> Result<()> {
        self.prepared(admission)?;
        self.store.start(&admission.operation_id)
    }
}
