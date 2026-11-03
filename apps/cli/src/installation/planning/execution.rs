//! Native original-context review and durable multi-root preparation.
//!
//! Preparation retains desired payloads and compatibility barriers. Active
//! consumer observation and protected publication remain separate runtime steps.

use super::{Plan, Planned, Request, binding, capture, invalid, native, value};
use crate::{
    account::contexts::Authority,
    authoring::runtime,
    bundle::reader::Package,
    digest,
    error::Result,
    installation::{
        custody::{self, Custody},
        forward, legacy,
        target::Target,
    },
    projection::Scope,
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, path::Path};

impl Plan {
    /// Reassemble from original immutable local sources, never from caller
    /// payloads or an ambient context. Every observed field must remain exact.
    pub fn recompile(&self, root: &Path, at: &str) -> Result<Planned> {
        if self.operation == super::Operation::Remove {
            return Err(invalid());
        }
        self.revalidate(root, at)?;
        let owner = runtime::owner(root)?;
        let request = Request {
            operation: self.operation,
            setup: self.setup.clone(),
            target: self.target.clone(),
            evidence: self.evidence.clone(),
            roots: self
                .roots
                .iter()
                .map(|(scope, root)| (*scope, root.directory.path.clone()))
                .collect(),
            placements: self.scope_bindings.clone(),
            corporate_binding: self
                .corporate
                .as_ref()
                .map(|c| c.binding_operation_id.clone()),
        };
        let corporate = serde_json::from_value(value(&self.corporate)?).map_err(|_| invalid())?;
        let mut rebuilt = capture(
            &mut owner.planning()?,
            self.context.clone(),
            corporate,
            &request,
            &self.created_at,
        )?;
        rebuilt.plan.operation_id.clone_from(&self.operation_id);
        if rebuilt.plan.value()? != self.value()? {
            return Err(invalid());
        }
        Ok(rebuilt)
    }
    pub(super) fn subject(&self, scope: Scope, target: &Target) -> Result<custody::Subject> {
        let remote = match &self.context.authority {
            Authority::Local => Value::Null,
            Authority::Remote {
                account,
                organization,
                ..
            } => json!({
                "origin":account.origin,"account_id":account.account_id,"device_id":account.device_id,
                "connection_id":account.connection.as_ref().map(|c|&c.connection_id),
                "organization_id":organization["organization_id"],"organization_kind":organization["kind"],
            }),
        };
        let key = digest::canonical(
            "ai-stp:installation-operation:v1",
            &json!({
                "kind":"native.configuration.subject","state":self.state.physical,
                "context_id":self.context.context_id,"local_identity":self.context.local_identity,
                "remote":remote,"harness_id":self.target.harness_id,"scope":scope,
                "physical_root":binding(target)?.physical,
                "project":self.corporate.as_ref().map(|c|json!({"local_project_id":c.local_project_id,
                    "remote_project_id":c.remote_project_id,"link_id":c.link_id})),
            }),
        )?;
        custody::Subject::capture(key, self.target.harness_id.clone(), scope, target)
    }
}

/// Owns runtime-rebuilt desired effects. Serialized reviews alone cannot supply
/// bytes or select another account, source graph or physical root.
pub struct Reviewed {
    plan: Plan,
    review: custody::Review,
    targets: BTreeMap<Scope, Target>,
    changes: BTreeMap<Scope, Vec<forward::Change>>,
}
impl Reviewed {
    pub fn create(root: &Path, plan: &Plan, custody: &Custody, at: &str) -> Result<Self> {
        let rebuilt = if plan.operation == super::Operation::Remove {
            plan.revalidate(root, at)?;
            super::removal::rebuild(root, plan, custody)?
        } else {
            plan.recompile(root, at)?
        };
        let plan = rebuilt.plan;
        let mut targets = BTreeMap::new();
        let mut desired = BTreeMap::new();
        let mut ownership = Vec::new();
        for (scope, root) in &plan.roots {
            let target = native(Target::resolve(&root.directory.path, super::CONTROL))?;
            if binding(&target)? != root.directory {
                return Err(invalid());
            }
            if plan.operation == super::Operation::Remove {
                let subject = plan.subject(*scope, &target)?;
                custody.require_origin(
                    std::slice::from_ref(&subject),
                    plan.source_operation.as_deref().ok_or_else(invalid)?,
                )?;
                ownership.push(custody::Change {
                    subject,
                    desired: vec![],
                });
                targets.insert(*scope, target);
                desired.insert(*scope, BTreeMap::new());
                continue;
            }
            let package = Package::read(rebuilt.packages.get(scope).ok_or_else(invalid)?)?;
            if value(&package.binding)? != value(&root.package)?
                || package.files.len() != root.files.len()
            {
                return Err(invalid());
            }
            let mut files = BTreeMap::new();
            let mut claims = Vec::new();
            for (path, file) in package.files {
                let expected = root.files.get(&path).ok_or_else(invalid)?;
                if file.owner != expected.owner
                    || Some(digest::sha256(&file.bytes)) != expected.after_digest
                    || Some(file.bytes.len()) != expected.after_bytes
                {
                    return Err(invalid());
                }
                let owner = plan
                    .graph_nodes
                    .iter()
                    .find(|node| node.stable_id == file.owner)
                    .ok_or_else(invalid)?;
                let kind = match &expected.contribution {
                    Some(c) => custody::Ownership::Contribution {
                        parser_id: c.parser_id.clone(),
                        key: c.ownership_key.clone(),
                    },
                    None => custody::Ownership::Whole,
                };
                claims.push(custody::Desired::capture(
                    &target,
                    &path,
                    kind,
                    &file.bytes,
                    expected.after_mode.ok_or_else(invalid)?,
                    custody::Source {
                        stable_id: owner.stable_id.clone(),
                        version: owner.version.clone(),
                        passport_digest: owner.passport_digest.clone(),
                    },
                )?);
                files.insert(
                    path,
                    native(forward::Content::new(
                        file.bytes,
                        expected.after_mode.ok_or_else(invalid)?,
                    ))?,
                );
            }
            ownership.push(custody::Change {
                subject: plan.subject(*scope, &target)?,
                desired: claims,
            });
            targets.insert(*scope, target);
            desired.insert(*scope, files);
        }
        let review = custody
            .review(plan.operation_id.clone(), &ownership)?
            .bind_native(&plan)?;
        let mut changes = BTreeMap::new();
        for (scope, target) in &targets {
            // A physical legacy barrier precedes every configuration effect.
            let mut effects = legacy::review(target, custody)?;
            effects.extend(
                review.configuration_changes(target, desired.get(scope).ok_or_else(invalid)?)?,
            );
            native(forward::validate_changes(&effects))?;
            changes.insert(*scope, effects);
        }
        let roots = targets
            .iter()
            .map(|(scope, target)| Ok((target, changes.get(scope).ok_or_else(invalid)?.as_slice())))
            .collect::<Result<Vec<_>>>()?;
        let handoff = crate::installation::activation::Handoff::prepare(
            &plan.target.harness_id,
            &targets.values().collect::<Vec<_>>(),
        )?;
        let review = review.bind_publications(&roots)?.bind_handoff(handoff)?;
        Ok(Self {
            plan,
            review,
            targets,
            changes,
        })
    }
    pub fn value(&self) -> Result<Value> {
        self.review.value()
    }
    pub fn digest(&self) -> Result<String> {
        self.review.digest()
    }
    fn admission(&self, scope: Scope) -> Result<forward::Admission> {
        admission(&self.plan, &self.digest()?, scope)
    }
    /// Prepare the exact reviewed operation. Configuration files and legacy
    /// guards remain unpublished; the original pending review is recoverable.
    pub fn prepare(
        &self,
        root: &Path,
        custody: &mut Custody,
        expected: &str,
        at: &str,
    ) -> Result<Value> {
        if self.digest()? != expected {
            return Err(invalid());
        }
        match custody.status(&self.review)?["state"].as_str() {
            Some("cancelled" | "completed") => {
                return Ok(custody.status(&self.review)?["result"].clone());
            }
            Some("absent" | "prepared") => (),
            _ => return Err(invalid()),
        }
        self.plan.revalidate(root, at)?;
        for (scope, target) in &self.targets {
            self.review
                .verify_publications(target, self.changes.get(scope).ok_or_else(invalid)?)?;
        }
        custody.prepare(&self.review, expected)?;
        let intent = self.plan.admit(root, &self.plan.digest()?, expected, at)?;
        if intent["state"] != "prepared" {
            return Err(invalid());
        }
        let mut children = BTreeMap::new();
        for (scope, target) in &self.targets {
            let mut writer = native(forward::Writer::acquire(target, super::CONTROL))?;
            let child = native(writer.prepare(
                &self.admission(*scope)?,
                &self.value()?,
                self.changes.get(scope).ok_or_else(invalid)?,
            ))?;
            children.insert(*scope, child);
        }
        Ok(
            json!({"kind":"native.configuration.preparation","operation_id":self.plan.operation_id,
            "review_digest":expected,"intent":intent,"children":children,
            "configuration_changed":false,"execution_authorized":false}),
        )
    }
}

pub(super) fn admission(plan: &Plan, digest: &str, scope: Scope) -> Result<forward::Admission> {
    Ok(forward::Admission {
        operation_id: plan.operation_id.clone(),
        plan_digest: digest.into(),
        operation: match plan.operation {
            super::Operation::Install => "install",
            super::Operation::Replace => "replace",
            super::Operation::Remove => "remove",
        }
        .into(),
        target_precondition_digest: digest::canonical(
            "ai-stp:installation-operation:v1",
            &value(plan.roots.get(&scope).ok_or_else(invalid)?)?,
        )?,
        target_scope: if scope == Scope::Global {
            None
        } else {
            Some(scope.as_str().into())
        },
    })
}

/// Cancel the original prepared operation after restart without a bundle or
/// caller plan file. A selected context never redirects this metadata action.
pub fn cancel_preparation(
    root: &Path,
    custody: &mut Custody,
    operation: &str,
    expected: &str,
    at: &str,
) -> Result<Value> {
    let review = custody.retained(operation)?.ok_or_else(invalid)?;
    if review.digest()? != expected {
        return Err(invalid());
    }
    let plan = review.original_plan()?.ok_or_else(invalid)?;
    if root != plan.state.path {
        return Err(invalid());
    }
    let status = custody.status(&review)?;
    if status["state"] == "cancelled" {
        return Ok(status["result"].clone());
    }
    if status["state"] != "prepared" {
        return Err(invalid());
    }
    // Verify the original local actor before touching child journals. No online
    // account observation is required to withdraw an unpublished preparation.
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
        let mut writer = native(forward::Writer::acquire(&target, super::CONTROL))?;
        native(writer.cancel(&admission(&plan, expected, *scope)?))?;
    }
    plan.cancel_intent(root, expected, at)?;
    custody.cancel(&review)
}
