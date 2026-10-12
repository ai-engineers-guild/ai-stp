//! Explicit component write surfaces: one held configuration target.

use serde_json::Value;
use std::{
    ffi::OsString,
    os::fd::{AsRawFd, OwnedFd},
};

use super::{linux, target::Target, unavailable};
use crate::{digest, error::Result};

pub(super) struct Configuration<'a> {
    pub plan: &'a Value,
    pub request: &'a crate::provider::plan::Request,
    pub cancel: bool,
}

impl Configuration<'_> {
    pub fn mount(
        &self,
        arguments: &mut Vec<OsString>,
        handles: &mut Vec<(usize, OwnedFd)>,
    ) -> Result<()> {
        mount_plan(
            self.plan,
            "/run/configuration-plan",
            crate::provider::plan::MAX_RESPONSE_BYTES,
            arguments,
            handles,
        )
    }

    pub fn command(&self, component: &[u8], target: &Target) -> Result<Vec<OsString>> {
        let mut command = vec![
            "apply-operation".into(),
            "--json".into(),
            "--target".into(),
            target.path().as_os_str().into(),
            "--plan".into(),
            "/run/configuration-plan".into(),
            "--plan-digest".into(),
            self.plan["plan_digest"]
                .as_str()
                .ok_or_else(unavailable)?
                .into(),
            "--provider-release-digest".into(),
            digest::sha256(component).into(),
        ];
        command.extend(linux::bundle_arguments(self.request));
        if self.cancel {
            command.push("--cancel".into());
        }
        // Apply derives scope from the sealed plan, never a second argv claim.
        Ok(command)
    }
}

fn mount_plan(
    plan: &Value,
    path: &str,
    limit: usize,
    arguments: &mut Vec<OsString>,
    handles: &mut Vec<(usize, OwnedFd)>,
) -> Result<()> {
    let bytes = serde_json::to_vec(&plan["plan"]).map_err(|_| unavailable())?;
    if bytes.len() > limit {
        return Err(unavailable());
    }
    let plan = OwnedFd::from(linux::sealed(&bytes)?);
    arguments.extend([
        "--perms".into(),
        "0400".into(),
        "--ro-bind-data".into(),
        plan.as_raw_fd().to_string().into(),
        path.into(),
    ]);
    handles.push((arguments.len() - 2, plan));
    Ok(())
}
