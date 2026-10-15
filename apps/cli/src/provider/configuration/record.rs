//! One decoder for the durable record used by execution and attribution.

use super::{invalid, outcome, plan::Plan};
use crate::{error::Result, wire};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub(crate) const LIMIT: usize = super::plan::LIMIT + 8 * 1024 * 1024;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Record {
    pub schema_version: u32,
    pub plan_digest: String,
    pub plan: Value,
    pub state: String,
    pub result: Option<Value>,
}

impl Record {
    pub fn parse(detail: &str, kind: &str, state: &str) -> Result<(Self, Plan)> {
        if detail.len() > LIMIT {
            return Err(invalid());
        }
        let record: Self =
            serde_json::from_value(wire::parse(detail.as_bytes())?).map_err(|_| invalid())?;
        let plan = Plan::parse(
            &serde_json::to_vec(&record.plan).map_err(|_| invalid())?,
            &record.plan_digest,
        )?;
        if record.schema_version != 1
            || kind != plan.action
            || state != record.state
            || plan.value()? != record.plan
        {
            return Err(invalid());
        }
        match record.state.as_str() {
            "applying" if record.result.is_none() => (),
            "verified" => outcome::validate(
                record.result.as_ref().ok_or_else(invalid)?,
                &plan,
                &record.plan_digest,
            )?,
            "cancelled" => outcome::validate_cancellation(
                record.result.as_ref().ok_or_else(invalid)?,
                &plan,
                &record.plan_digest,
            )?,
            _ => return Err(invalid()),
        }
        Ok((record, plan))
    }
}
