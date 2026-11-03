//! An exact original intent and its old-writer fence share one SQLite commit.

use super::{Plan, invalid, value};
use crate::{
    authoring::runtime,
    error::Result,
    store::{self, NATIVE_CONFIGURATION_SCHEMA, journal},
};
use rusqlite::OptionalExtension;
use serde_json::{Value, json};
use std::path::Path;

pub(crate) const KIND: &str = "installation.native";

impl Plan {
    pub(super) fn admission_detail(
        &self,
        expected: &str,
        custody_review_digest: &str,
    ) -> Result<String> {
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
    pub(super) fn cancel_intent(
        &self,
        root: &Path,
        review: &str,
        at: &str,
    ) -> Result<Option<Value>> {
        let detail = self.admission_detail(&self.digest()?, review)?;
        let at_value = at.parse::<jiff::Timestamp>().map_err(|_| invalid())?;
        if root != self.state.path
            || at_value
                < self
                    .created_at
                    .parse::<jiff::Timestamp>()
                    .map_err(|_| invalid())?
        {
            return Err(invalid());
        }
        let owner = runtime::owner(root)?;
        self.context.require_current_native_identity(&owner)?;
        if crate::files::physical::DirectoryIdentity::capture(owner.root_directory())?
            != self.state.physical
        {
            return Err(invalid());
        }
        let mut store = owner.open(false)?;
        store.transaction(|transaction| {
            match journal::state(transaction,&self.operation_id,KIND,&detail)?.as_deref() {
                None=>return Ok(None),
                Some("cancelled")=>(),
                Some("prepared")=>{
                    let rows=transaction.execute("UPDATE operation SET state='cancelled',finished_at=? WHERE operation_id=? AND kind=? AND state='prepared' AND detail=?",rusqlite::params![at,self.operation_id,KIND,detail]).map_err(store::database)?;
                    if rows!=1 {return Err(invalid());}
                },
                _=>return Err(invalid()),
            }
            Ok(Some(self.admission_result(review,"cancelled")?))
        })
    }
    pub(super) fn native_state(
        &self,
        root: &Path,
        review: &str,
    ) -> Result<(String, Option<Value>)> {
        let detail = self.admission_detail(&self.digest()?, review)?;
        if root != self.state.path {
            return Err(invalid());
        }
        let owner = runtime::owner(root)?;
        if crate::files::physical::DirectoryIdentity::capture(owner.root_directory())?
            != self.state.physical
        {
            return Err(invalid());
        }
        let store = owner.planning()?;
        let state = journal::state(&store.connection, &self.operation_id, KIND, &detail)?
            .ok_or_else(invalid)?;
        let receipt:Option<String>=store.connection.query_row(
            "SELECT result FROM operation_event WHERE operation_id=? ORDER BY sequence DESC LIMIT 1",
            [&self.operation_id],|row|row.get(0)).optional().map_err(store::database)?;
        Ok((
            state,
            receipt
                .map(|v| crate::wire::parse(v.as_bytes()))
                .transpose()?,
        ))
    }
    pub(super) fn transition(
        &self,
        root: &Path,
        review: &str,
        to: &str,
        result: &Value,
        at: &str,
    ) -> Result<Value> {
        let detail = self.admission_detail(&self.digest()?, review)?;
        if root != self.state.path || !crate::passport::timestamp(at) {
            return Err(invalid());
        }
        let owner = runtime::owner(root)?;
        self.context.require_current_native_identity(&owner)?;
        if crate::files::physical::DirectoryIdentity::capture(owner.root_directory())?
            != self.state.physical
        {
            return Err(invalid());
        }
        let result = String::from_utf8(crate::canonical::bytes(result)?).map_err(|_| invalid())?;
        if result.len() > 256 * 1024 {
            return Err(invalid());
        }
        let mut store = owner.open(false)?;
        store.transaction(|transaction| {
            let before=journal::state(transaction,&self.operation_id,KIND,&detail)?.ok_or_else(invalid)?;
            if before==to {
                let result:String=transaction.query_row("SELECT result FROM operation_event WHERE operation_id=? ORDER BY sequence DESC LIMIT 1",[&self.operation_id],|row|row.get(0)).map_err(store::database)?;
                return crate::wire::parse(result.as_bytes());
            }
            if !matches!((before.as_str(),to),("prepared","applying")|("applying","configured")|("configured","confirmed")) {return Err(invalid());}
            let sequence:i64=transaction.query_row("SELECT coalesce(max(sequence),0)+1 FROM operation_event WHERE operation_id=?",[&self.operation_id],|row|row.get(0)).map_err(store::database)?;
            transaction.execute("INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence,global_sequence) VALUES (?,?,?,?,?,?,NULL,NULL)",rusqlite::params![self.operation_id,sequence,at,before,to,result]).map_err(store::database)?;
            let rows=transaction.execute("UPDATE operation SET state=?,finished_at=? WHERE operation_id=? AND kind=? AND state=? AND detail=?",rusqlite::params![to,if to=="confirmed"{Some(at)}else{None},self.operation_id,KIND,before,detail]).map_err(store::database)?;
            if rows!=1 {return Err(invalid());}
            crate::wire::parse(result.as_bytes())
        })
    }
}
