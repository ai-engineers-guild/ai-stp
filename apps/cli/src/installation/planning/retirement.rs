//! Explicit OS-user custody retirement for positively absent target folders.
//! This releases metadata refs, never files, private access or source authority.

use super::model::Directory;
use super::{Operation, Plan, binding, invalid, native, value};
use crate::{
    authoring::{Identity, runtime},
    digest,
    error::Result,
    files::{self, absence::Parent},
    installation::{
        custody::{Custody, Review},
        target::Target,
    },
    passport,
    projection::Scope,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Record {
    format: String,
    source_operation: String,
    source_review_digest: String,
    original_plan: Value,
    controller: Directory,
    controller_identity: Identity,
    created_at: String,
    expires_at: String,
    missing: BTreeMap<Scope, Parent>,
}
impl Record {
    fn original(&self) -> Result<Plan> {
        Plan::parse(
            &crate::canonical::bytes(&self.original_plan)?,
            &digest::canonical("ai-stp:installation-operation:v1", &self.original_plan)?,
        )
    }
    fn validate(&self) -> Result<()> {
        let original = self.original()?;
        self.controller.physical.validate()?;
        if self.format != "ai-stp-native-missing-target-retirement/1"
            || original.operation_id != self.source_operation
            || original.operation == Operation::Remove
            || !crate::provider::plan::hash(&self.source_review_digest)
            || !self.controller.path.is_absolute()
            || !passport::stable_id(&self.controller_identity.account_id, "account")
            || !passport::stable_id(&self.controller_identity.device_id, "device")
            || !(1..=3).contains(&self.missing.len())
            || self.expires_at != crate::authoring::expiry(&self.created_at)?
        {
            return Err(invalid());
        }
        for (scope, parent) in &self.missing {
            parent.validate(
                &original
                    .roots
                    .get(scope)
                    .ok_or_else(invalid)?
                    .directory
                    .path,
            )?;
        }
        Ok(())
    }
    fn revalidate(&self) -> Result<()> {
        self.validate()?;
        let owner = runtime::owner(&self.controller.path)?;
        if owner.account_id != self.controller_identity.account_id
            || owner.device_id != self.controller_identity.device_id
            || crate::files::physical::DirectoryIdentity::capture(owner.root_directory())?
                != self.controller.physical
        {
            return Err(invalid());
        }
        drop(owner);
        let original = self.original()?;
        for (scope, parent) in &self.missing {
            parent.open(
                &original
                    .roots
                    .get(scope)
                    .ok_or_else(invalid)?
                    .directory
                    .path,
            )?;
        }
        Ok(())
    }
}
fn parse(data: &Value) -> Result<Record> {
    let record: Record = serde_json::from_value(data.clone()).map_err(|_| invalid())?;
    record.validate()?;
    if value(&record)? != *data {
        return Err(invalid());
    }
    Ok(record)
}
pub(crate) fn validate(data: &Value) -> Result<()> {
    parse(data).map(|_| ())
}
pub(crate) fn revalidate(data: &Value) -> Result<()> {
    parse(data)?.revalidate()
}

fn capture(
    root: &Path,
    custody: &Custody,
    source: &str,
    source_digest: &str,
    operation: String,
    at: &str,
) -> Result<Review> {
    let original = custody.retained(source)?.ok_or_else(invalid)?;
    if original.digest()? != source_digest || custody.status(&original)?["state"] != "completed" {
        return Err(invalid());
    }
    let plan = original.original_plan()?.ok_or_else(invalid)?;
    if plan.operation == Operation::Remove {
        return Err(invalid());
    }
    let current = custody.current_scopes(source)?;
    let owner = runtime::owner(root)?;
    let controller_identity = Identity {
        account_id: owner.account_id.clone(),
        device_id: owner.device_id.clone(),
    };
    drop(owner);
    let controller = binding(&native(Target::resolve(root, super::CONTROL))?)?;
    let mut missing = BTreeMap::new();
    for (scope, held) in &plan.roots {
        if current.contains(scope)
            && let Ok(observed) = Parent::observe(&held.directory.path)
        {
            missing.insert(*scope, observed.parent);
        }
    }
    let record = Record {
        format: "ai-stp-native-missing-target-retirement/1".into(),
        source_operation: source.into(),
        source_review_digest: source_digest.into(),
        original_plan: plan.value()?,
        controller,
        controller_identity,
        created_at: at.into(),
        expires_at: crate::authoring::expiry(at)?,
        missing,
    };
    record.revalidate()?;
    let scopes = record.missing.keys().copied().collect::<BTreeSet<_>>();
    custody.review_missing(operation, source, &scopes, value(&record)?)
}
pub fn plan(
    root: &Path,
    custody: &Custody,
    source: &str,
    source_digest: &str,
    at: &str,
) -> Result<Value> {
    let review = capture(
        root,
        custody,
        source,
        source_digest,
        format!("operation_{}", ulid::Ulid::generate()),
        at,
    )?;
    Ok(
        json!({"plan":review.value()?,"plan_digest":review.digest()?,"configuration_changed":false,"metadata_only":true,"execution_authorized":false}),
    )
}
fn record(root: &Path, review: &Review) -> Result<Record> {
    let record = parse(review.retirement().ok_or_else(invalid)?)?;
    if record.controller.path != root {
        return Err(invalid());
    }
    Ok(record)
}
fn outcome(review: &Review, data: &Record) -> Result<Value> {
    let original = data.original()?;
    Ok(
        json!({"schema_version":1,"kind":"native.configuration.retired_missing","state":"retired",
        "operation_id":review.operation_id(),"review_digest":review.digest()?,
        "source_operation":data.source_operation,"original_context":value(&original.context)?,
        "controller":value(&data.controller)?,"harness_id":original.target.harness_id,
        "retired_scopes":data.missing.keys().collect::<Vec<_>>(),
        "configuration_changed":false,"restart_required":false,"load_state":"not_observed"}),
    )
}
pub fn prepare(
    root: &Path,
    custody: &mut Custody,
    review: &Review,
    expected: &str,
    at: &str,
) -> Result<Value> {
    if review.digest()? != expected {
        return Err(invalid());
    }
    let data = record(root, review)?;
    let status = custody.status(review)?;
    if status["state"] != "absent" {
        let retained = custody
            .retained(review.operation_id())?
            .ok_or_else(invalid)?;
        if retained.value()? != review.value()? {
            return Err(invalid());
        }
        return Ok(status);
    }
    let now = at.parse::<jiff::Timestamp>().map_err(|_| invalid())?;
    if now
        < data
            .created_at
            .parse::<jiff::Timestamp>()
            .map_err(|_| invalid())?
        || now
            >= data
                .expires_at
                .parse::<jiff::Timestamp>()
                .map_err(|_| invalid())?
    {
        return Err(invalid());
    }
    let rebuilt = capture(
        root,
        custody,
        &data.source_operation,
        &data.source_review_digest,
        review.operation_id().into(),
        &data.created_at,
    )?;
    if rebuilt.value()? != review.value()? {
        return Err(invalid());
    }
    custody.prepare(review, expected)?;
    Ok(
        json!({"operation_id":review.operation_id(),"review_digest":expected,"state":"prepared","metadata_only":true,"configuration_changed":false}),
    )
}
pub fn apply(root: &Path, custody: &mut Custody, review: &Review) -> Result<Value> {
    let data = record(root, review)?;
    let status = custody.status(review)?;
    if status["state"] == "completed" {
        return Ok(status["result"]["native_result"].clone());
    }
    if status["state"] == "prepared" {
        data.revalidate()?;
        custody.start(review)?;
    } else if !matches!(status["state"].as_str(), Some("applying" | "finishing")) {
        return Err(invalid());
    }
    let result = outcome(review, &data)?;
    custody.complete_with_result(review, &result)?;
    Ok(result)
}
pub fn status(root: &Path, custody: &Custody, review: &Review) -> Result<Value> {
    let data = record(root, review)?;
    let original = data.original()?;
    let held = custody.status(review)?;
    Ok(
        json!({"operation_id":review.operation_id(),"review_digest":review.digest()?,
        "original_context":value(&original.context)?,"harness_id":original.target.harness_id,
        "state":if held["state"]=="completed"{"retired"}else{held["state"].as_str().ok_or_else(invalid)?},
        "receipt":held["result"]["native_result"],"custody":held,"metadata_only":true}),
    )
}
pub fn cancel(root: &Path, custody: &mut Custody, review: &Review) -> Result<Value> {
    record(root, review)?;
    custody.cancel(review)
}
pub(crate) fn pending(root: &Path, custody: &Custody, review: &Review) -> Result<Value> {
    let data = parse(review.retirement().ok_or_else(invalid)?)?;
    if data.controller.path != root {
        return Ok(json!({"pending":null,"other_state_pending":true}));
    }
    let original = data.original()?;
    Ok(
        json!({"pending":{"kind":"retire_missing","operation_id":review.operation_id(),"plan_digest":review.digest()?,
        "original_context":value(&original.context)?,"harness_id":original.target.harness_id,
        "custody":custody.status(review)?},"other_state_pending":false}),
    )
}
pub fn read(path: &Path, expected: &str) -> Result<Review> {
    Review::parse(&files::read(path, 8 * 1024 * 1024)?, expected)
}
