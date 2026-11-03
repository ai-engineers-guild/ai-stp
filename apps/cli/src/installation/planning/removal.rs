//! Withdraw only the current setup's qualified physical references.

use super::{Operation, Plan, Planned, binding, invalid, native};
use crate::{
    authoring::runtime,
    error::Result,
    installation::{custody::Custody, forward, target::Target},
};
use std::{collections::BTreeMap, path::Path};

fn capture(
    root: &Path,
    custody: &Custody,
    source: &str,
    source_digest: &str,
    operation: String,
    at: &str,
) -> Result<Plan> {
    let original = custody.retained(source)?.ok_or_else(invalid)?;
    if original.digest()? != source_digest || custody.status(&original)?["state"] != "completed" {
        return Err(invalid());
    }
    let mut plan = original.original_plan()?.ok_or_else(invalid)?;
    if plan.operation == Operation::Remove || root != plan.state.path {
        return Err(invalid());
    }
    let owner = runtime::owner(root)?;
    plan.context.require_current_native_identity(&owner)?;
    if crate::files::physical::DirectoryIdentity::capture(owner.root_directory())?
        != plan.state.physical
    {
        return Err(invalid());
    }
    for (scope, held) in &plan.roots {
        let target = native(Target::resolve(&held.directory.path, super::CONTROL))?;
        if binding(&target)? != held.directory {
            return Err(invalid());
        }
        custody.require_origin(&[plan.subject(*scope, &target)?], source)?;
    }
    plan.operation_id = operation;
    plan.operation = Operation::Remove;
    plan.source_operation = Some(source.into());
    plan.created_at = at.into();
    plan.expires_at = crate::authoring::expiry(at)?;
    for held in plan.roots.values_mut() {
        let target = native(Target::resolve(&held.directory.path, super::CONTROL))?;
        for (path, file) in &mut held.files {
            let (before, content) = native(forward::observe(&target, path))?;
            file.before = before;
            file.after_digest = None;
            file.after_bytes = None;
            file.after_mode = None;
            if let Some(claim) = &mut file.contribution {
                claim.host_digest = content.map(|v| crate::digest::sha256(&v.bytes));
            }
        }
    }
    plan.digest()?;
    Ok(plan)
}
/// Source payloads and online acquisition rights are unnecessary for explicit
/// local removal. Original-context custody and process handoff still apply.
pub fn create_removal(
    root: &Path,
    custody: &Custody,
    source: &str,
    source_digest: &str,
    at: &str,
) -> Result<Plan> {
    capture(
        root,
        custody,
        source,
        source_digest,
        format!("operation_{}", ulid::Ulid::generate()),
        at,
    )
}
pub(super) fn rebuild(root: &Path, plan: &Plan, custody: &Custody) -> Result<Planned> {
    let source = plan.source_operation.as_deref().ok_or_else(invalid)?;
    let original = custody.retained(source)?.ok_or_else(invalid)?;
    let rebuilt = capture(
        root,
        custody,
        source,
        &original.digest()?,
        plan.operation_id.clone(),
        &plan.created_at,
    )?;
    if rebuilt.value()? != plan.value()? {
        return Err(invalid());
    }
    Ok(Planned {
        plan: rebuilt,
        packages: BTreeMap::new(),
    })
}
