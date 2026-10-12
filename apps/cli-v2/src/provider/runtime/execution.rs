//! Explicit component write surfaces: one held program directory or configuration target.

use serde_json::Value;
use std::{
    ffi::OsString,
    fs::File,
    os::fd::{AsRawFd, OwnedFd},
    path::Path,
};

use super::{linux, target::Target, unavailable};
use crate::{digest, error::Result};

#[derive(Clone, Copy)]
pub(super) enum Execution<'a> {
    Program(&'a Installation<'a>),
    Configuration(&'a Configuration<'a>),
}

impl Execution<'_> {
    pub fn mount(
        &self,
        arguments: &mut Vec<OsString>,
        handles: &mut Vec<(usize, OwnedFd)>,
    ) -> Result<()> {
        match self {
            Self::Program(installation) => installation.mount(arguments, handles),
            Self::Configuration(configuration) => mount_plan(
                configuration.plan,
                "/run/configuration-plan",
                crate::provider::plan::MAX_RESPONSE_BYTES,
                arguments,
                handles,
            ),
        }
    }
}

pub(super) struct Configuration<'a> {
    pub plan: &'a Value,
    pub request: &'a crate::provider::plan::Request,
    pub cancel: bool,
}

impl Configuration<'_> {
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

pub(super) struct Installation<'a> {
    pub stage: &'a Target,
    pub prefix: &'a Path,
    pub plan: &'a Value,
    pub archive: Option<&'a File>,
}

impl Installation<'_> {
    pub fn command(&self, component: &[u8], target: &Target) -> Result<Vec<OsString>> {
        let mut command = vec![
            "apply-operation".into(),
            "--json".into(),
            "--target".into(),
            target.path().as_os_str().into(),
            "--prefix".into(),
            self.prefix.as_os_str().into(),
            "--plan".into(),
            "/run/install-plan".into(),
            "--plan-digest".into(),
            self.plan["plan_digest"]
                .as_str()
                .ok_or_else(unavailable)?
                .into(),
            "--provider-release-digest".into(),
            digest::sha256(component).into(),
        ];
        if self.archive.is_some() {
            command.extend(["--software-artifact".into(), "/run/vendor-artifact".into()]);
        }
        Ok(command)
    }

    pub fn mount(
        &self,
        arguments: &mut Vec<OsString>,
        handles: &mut Vec<(usize, OwnedFd)>,
    ) -> Result<()> {
        self.stage.revalidate()?;
        let root = self.stage.handle()?;
        arguments.extend([
            "--bind-fd".into(),
            root.as_raw_fd().to_string().into(),
            self.prefix.as_os_str().into(),
        ]);
        handles.push((arguments.len() - 2, root));
        if let Some(archive) = self.archive {
            let source = rustix::io::fcntl_dupfd_cloexec(archive, 3).map_err(|_| unavailable())?;
            arguments.extend([
                "--ro-bind-fd".into(),
                source.as_raw_fd().to_string().into(),
                "/run/vendor-artifact".into(),
            ]);
            handles.push((arguments.len() - 2, source));
        }
        mount_plan(
            self.plan,
            "/run/install-plan",
            64 * 1024,
            arguments,
            handles,
        )
    }
}
