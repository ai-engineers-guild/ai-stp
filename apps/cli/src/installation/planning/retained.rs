//! An exact original intent and its old-writer fence share one SQLite commit.

use super::{Plan, invalid, value};
use crate::{
    authoring::runtime,
    error::Result,
    store::{self, NATIVE_CONFIGURATION_SCHEMA, journal},
};
use serde_json::{Value, json};
use std::path::Path;

pub(crate) const KIND: &str = "installation.native";

impl Plan {
    fn admission_detail(&self, expected: &str, custody_review_digest: &str) -> Result<String> {
        if self.digest()? != expected || !crate::provider::plan::hash(custody_review_digest) {
            return Err(invalid());
        }
        let detail = json!({"format":"ai-stp-native-intent/1", "plan":self.value()?,
            "plan_digest":expected,"custody_review_digest":custody_review_digest});
        String::from_utf8(crate::canonical::bytes(&detail)?).map_err(|_| invalid())
    }

    fn admission_result(&self, custody_review_digest: &str, state: &str) -> Result<Value> {
        Ok(
            json!({"operation_id":self.operation_id,"kind":KIND,"state":state,
            "plan_digest":self.digest()?,"custody_review_digest":custody_review_digest,
            "original_context":value(&self.context)?,"writer_fence":NATIVE_CONFIGURATION_SCHEMA,
            "authorization_granted":false}),
        )
    }

    /// Explicit preparation retains the full original plan and exact shared
    /// custody review. It neither writes configuration nor grants later effects.
    /// A replay is a read of the original intent, including after expiry.
    pub fn admit(
        &self,
        root: &Path,
        expected: &str,
        custody_review_digest: &str,
        at: &str,
    ) -> Result<Value> {
        let detail = self.admission_detail(expected, custody_review_digest)?;
        if root != self.state.path {
            return Err(invalid());
        }
        let owner = runtime::owner(root)?;
        if crate::files::physical::DirectoryIdentity::capture(owner.root_directory())?
            != self.state.physical
        {
            return Err(invalid());
        }
        {
            let store = owner.planning()?;
            if let Some(state) =
                journal::state(&store.connection, &self.operation_id, KIND, &detail)?
            {
                return self.admission_result(custody_review_digest, &state);
            }
        }
        self.revalidate(root, at)?;
        let mut store = owner.open(false)?;
        store.native_configuration_transaction(|transaction| {
            if let Some(state) = journal::state(transaction, &self.operation_id, KIND, &detail)? {
                return self.admission_result(custody_review_digest, &state);
            }
            transaction.execute(
                "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'prepared',?,NULL,?)",
                rusqlite::params![self.operation_id,KIND,at,detail],
            ).map_err(store::database)?;
            self.admission_result(custody_review_digest, "prepared")
        })
    }
}
