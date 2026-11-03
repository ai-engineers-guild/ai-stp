//! Protected forward application and original-operation receipts.

use super::{Plan, binding, execution::admission, invalid, native, value};
use crate::{
    error::Result,
    installation::{
        activation::Handoff,
        custody::{Custody, Review},
        forward::{self, Progress},
        target::Target,
    },
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, path::Path};

fn original(
    root: &Path,
    custody: &Custody,
    operation: &str,
    expected: &str,
) -> Result<(Review, Plan)> {
    let review = custody.retained(operation)?.ok_or_else(invalid)?;
    if review.digest()? != expected {
        return Err(invalid());
    }
    let plan = review.original_plan()?.ok_or_else(invalid)?;
    if root != plan.state.path {
        return Err(invalid());
    }
    Ok((review, plan))
}
fn handoff_result(review: &Review, plan: &Plan, result: &Value) -> Result<Handoff> {
    if result["kind"] != "native.configuration.configured"
        || result["operation_id"] != plan.operation_id
        || result["review_digest"] != review.digest()?
        || result["original_context"] != value(&plan.context)?
    {
        return Err(invalid());
    }
    let handoff = Handoff::parse(result["handoff"].clone())?;
    let mut original = review.handoff()?.ok_or_else(invalid)?.value()?;
    let mut current = handoff.value()?;
    for field in ["published", "confirmed"] {
        original.as_object_mut().ok_or_else(invalid)?.remove(field);
        current.as_object_mut().ok_or_else(invalid)?.remove(field);
    }
    if original != current {
        return Err(invalid());
    }
    Ok(handoff)
}
fn configured(plan: &Plan, review: &Review, handoff: &Handoff) -> Result<Value> {
    let changes = review.configuration_effect_count()?;
    Ok(
        json!({"schema_version":1,"kind":"native.configuration.configured","operation_id":plan.operation_id,
        "review_digest":review.digest()?,"original_context":value(&plan.context)?,"setup":plan.setup,
        "graph_digest":plan.graph_digest,"operation":plan.operation,"harness_id":plan.target.harness_id,"handoff":handoff.value()?,
        "configuration_changed":changes>0,"restart_required":changes>0,
        "activation":if changes>0{"restart_required"}else{"unchanged"},"load_state":"not_observed"}),
    )
}

/// Apply only the exact admitted original operation. Every protected file
/// publication re-establishes current native authority and process quiescence.
/// Desired bytes survive source loss; historical replay never republishes them.
pub fn apply_prepared(
    root: &Path,
    custody: &mut Custody,
    operation: &str,
    expected: &str,
    at: &str,
) -> Result<Value> {
    let (review, plan) = original(root, custody, operation, expected)?;
    let status = custody.status(&review)?;
    if status["state"] == "completed" {
        let result = status["result"]["native_result"].clone();
        handoff_result(&review, &plan, &result)?;
        return Ok(result);
    }
    if !matches!(
        status["state"].as_str(),
        Some("prepared" | "applying" | "finishing")
    ) {
        return Err(invalid());
    }
    let (state, _) = plan.native_state(root, expected)?;
    if !matches!(state.as_str(), "prepared" | "applying") {
        return Err(invalid());
    }
    let mut handoff = review.handoff()?.ok_or_else(invalid)?;
    let writes_configuration = review.configuration_effect_count()? > 0;
    let mut targets = BTreeMap::new();
    let mut writers = BTreeMap::new();
    let mut candidate: Option<Value> = None;
    for (scope, held) in &plan.roots {
        let target = native(Target::resolve(&held.directory.path, super::CONTROL))?;
        if binding(&target)? != held.directory {
            return Err(invalid());
        }
        let writer = native(forward::Writer::acquire(&target, super::CONTROL))?;
        let admission = admission(&plan, expected, *scope)?;
        let progress = native(writer.progress(&admission))?;
        if matches!(&progress, Progress::Absent | Progress::Cancelled(_)) {
            return Err(invalid());
        }
        if !matches!(&progress, Progress::Completed(_)) {
            let (_, context) = native(writer.retained(operation))?.ok_or_else(invalid)?;
            if context != review.value()? {
                return Err(invalid());
            }
            review.verify_publications(&target, &native(writer.desired(&admission))?)?;
        }
        if let Some(result) = native(writer.staged_result(&admission))? {
            handoff_result(&review, &plan, &result)?;
            if candidate.as_ref().is_some_and(|held| held != &result) {
                return Err(invalid());
            }
            candidate = Some(result);
        }
        targets.insert(*scope, target);
        writers.insert(*scope, writer);
    }
    let mut adoptions = BTreeMap::new();
    if let Some(proofs) = review.legacy() {
        for (scope, evidence) in proofs {
            let target = targets.get(scope).ok_or_else(invalid)?;
            adoptions.insert(
                *scope,
                crate::installation::legacy::adoption::Adoption::reopen(
                    target,
                    &plan.target.harness_id,
                    &plan.setup,
                    custody,
                    evidence,
                )?,
            );
        }
    }
    if candidate.is_none() {
        plan.authorize(root)?;
        let idle = if writes_configuration {
            Some(handoff.require_idle()?)
        } else {
            None
        };
        if status["state"] == "prepared" {
            custody.start(&review)?;
        }
        if state == "prepared" {
            plan.transition(root,expected,"applying",&json!({"kind":"native.configuration.applying","operation_id":operation,"review_digest":expected}),at)?;
        }
        for (scope, writer) in &mut writers {
            let admission = admission(&plan, expected, *scope)?;
            if matches!(native(writer.progress(&admission))?, Progress::Prepared(_)) {
                native(writer.start(&admission))?;
            }
            if !matches!(native(writer.progress(&admission))?, Progress::Applying(_)) {
                return Err(invalid());
            }
            native(writer.apply_checked(&admission, || {
                for (scope, proof) in &adoptions {
                    proof
                        .revalidate(
                            targets.get(scope).ok_or_else(|| {
                                crate::installation::Error::new(
                                    crate::installation::ReasonCode::StateUnavailable,
                                    "legacy root changed",
                                )
                            })?,
                            custody,
                        )
                        .map_err(|error| {
                            crate::installation::Error::new(
                                crate::installation::ReasonCode::StateUnavailable,
                                "legacy custody changed during adoption",
                            )
                            .with_source(error)
                        })?;
                }
                plan.authorize(root).map_err(|error| {
                    crate::installation::Error::new(
                        crate::installation::ReasonCode::StateUnavailable,
                        "current original-context authority refuses a native file effect",
                    )
                    .with_source(error)
                })?;
                if let Some(idle) = &idle {
                    idle.revalidate().map_err(|error| {
                        crate::installation::Error::new(
                            crate::installation::ReasonCode::StateUnavailable,
                            "a consumer became active during native publication",
                        )
                        .with_source(error)
                    })?;
                }
                Ok(())
            }))?;
        }
        if writes_configuration {
            handoff.published()?;
        }
        candidate = Some(configured(&plan, &review, &handoff)?);
    }
    let result = candidate.ok_or_else(invalid)?;
    for (scope, writer) in &mut writers {
        let admission = admission(&plan, expected, *scope)?;
        match native(writer.progress(&admission))? {
            Progress::Applying(_) => {
                native(writer.finish(&admission, &[], &result))?;
                native(writer.apply(&admission))?;
                native(writer.complete(&admission))?;
            }
            Progress::Finishing => {
                native(writer.apply(&admission))?;
                native(writer.complete(&admission))?;
            }
            Progress::Completed(held) if held == result => (),
            _ => return Err(invalid()),
        }
    }
    let committed = custody.complete_with_result(&review, &result)?;
    if committed["native_result"] != result {
        return Err(invalid());
    }
    plan.transition(root, expected, "configured", &result, at)?;
    Ok(result)
}

/// Read the original operation's current and immutable custody outcomes.
pub fn configuration_status(
    root: &Path,
    custody: &Custody,
    operation: &str,
    expected: &str,
) -> Result<Value> {
    let (review, plan) = original(root, custody, operation, expected)?;
    let (state, receipt) = plan.native_state(root, expected)?;
    Ok(
        json!({"operation_id":operation,"review_digest":expected,"original_context":value(&plan.context)?,
        "state":state,"receipt":receipt,"custody":custody.status(&review)?,"authorization_granted":false}),
    )
}

/// Confirm from an actual later selected-harness process after owned values and
/// the original account policy have been checked again. This does not claim a
/// vendor loading/health probe that the native engine has not observed.
pub fn confirm_session(
    root: &Path,
    custody: &Custody,
    operation: &str,
    expected: &str,
    at: &str,
) -> Result<Value> {
    let (review, plan) = original(root, custody, operation, expected)?;
    let (state, receipt) = plan.native_state(root, expected)?;
    if state == "confirmed" {
        return receipt.ok_or_else(invalid);
    }
    let status = custody.status(&review)?;
    if status["state"] != "completed" {
        return Err(invalid());
    }
    let mut result = status["result"]["native_result"].clone();
    let mut handoff = handoff_result(&review, &plan, &result)?;
    if state == "applying" {
        plan.transition(root, expected, "configured", &result, at)?;
    } else if state != "configured" {
        return Err(invalid());
    }
    plan.authorize(root)?;
    review.verify_configuration()?;
    if result["restart_required"] == true {
        let session = handoff.confirm()?;
        result["session"] = value(&session)?;
        result["handoff"] = handoff.value()?;
        result["activation"] = "new_session_confirmed".into();
    }
    result["kind"] = "native.configuration.confirmed".into();
    plan.transition(root, expected, "confirmed", &result, at)
}

/// Current references, scoped to the requested original saved context.
pub fn effective(
    root: &Path,
    custody: &Custody,
    context: &crate::account::contexts::Context,
) -> Result<Value> {
    let mut setups = Vec::new();
    for operation in custody.current_operations()? {
        let Some(review) = custody.retained(&operation)? else {
            continue;
        };
        let Some(plan) = review.original_plan()? else {
            continue;
        };
        if plan.state.path != root || plan.context.context_id != context.context_id {
            continue;
        }
        let (state, receipt) = plan.native_state(root, &review.digest()?)?;
        let current_scopes = custody.current_scopes(&operation)?;
        setups.push(json!({"operation_id":operation,"plan_digest":review.digest()?,"setup":plan.setup,
            "harness_id":plan.target.harness_id,"context_id":plan.context.context_id,
            "roots":plan.roots.iter().filter(|(scope,_)|current_scopes.contains(scope)).map(|(scope,root)|Ok((scope.as_str(),value(&root.directory)?))).collect::<Result<BTreeMap<_,_>>>()?,
            "state":state,"receipt":receipt,
            "ownership_state":if custody.verify_operation(&plan.operation_id).is_ok(){"matching"}else{"drifted_or_unavailable"},
            "load_state":"not_observed"}));
    }
    Ok(json!({"context_id":context.context_id,"setups":setups,"authorization_granted":false}))
}
/// Recover the original active operation without a caller plan file.
pub fn pending(root: &Path, custody: &Custody) -> Result<Value> {
    let Some(review) = custody.pending()? else {
        return Ok(json!({"pending":null,"other_state_pending":false}));
    };
    if review.retirement().is_some() {
        return super::retirement::pending(root, custody, &review);
    }
    let plan = review.original_plan()?.ok_or_else(invalid)?;
    if plan.state.path != root {
        return Ok(json!({"pending":null,"other_state_pending":true}));
    }
    Ok(
        json!({"pending":{"operation_id":plan.operation_id,"plan_digest":review.digest()?,
        "original_context":value(&plan.context)?,"setup":plan.setup,"harness_id":plan.target.harness_id,
        "custody":custody.status(&review)?},"other_state_pending":false}),
    )
}
