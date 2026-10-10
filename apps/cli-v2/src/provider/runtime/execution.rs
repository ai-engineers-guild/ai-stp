//! The only writable provider mount is an owned, unpublished program stage.

use serde_json::Value;
use std::{
    ffi::OsString,
    fs::File,
    os::fd::{AsRawFd, OwnedFd},
    path::Path,
};

use super::{linux, target::Target, unavailable};
use crate::{digest, error::Result, projection::Scope};

pub(super) struct Installation<'a> {
    pub stage: &'a Target,
    pub prefix: &'a Path,
    pub plan: &'a Value,
    pub archive: &'a File,
    pub scope: Scope,
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
            "--software-artifact".into(),
            "/run/vendor-artifact".into(),
        ];
        if self.scope != Scope::Global {
            command.extend(["--target-scope".into(), self.scope.as_str().into()]);
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
        let source = rustix::io::fcntl_dupfd_cloexec(self.archive, 3).map_err(|_| unavailable())?;
        arguments.extend([
            "--ro-bind-fd".into(),
            source.as_raw_fd().to_string().into(),
            "/run/vendor-artifact".into(),
        ]);
        handles.push((arguments.len() - 2, source));
        let bytes = serde_json::to_vec(&self.plan["plan"]).map_err(|_| unavailable())?;
        if bytes.len() > 64 * 1024 {
            return Err(unavailable());
        }
        let plan = OwnedFd::from(linux::sealed(&bytes)?);
        arguments.extend([
            "--perms".into(),
            "0400".into(),
            "--ro-bind-data".into(),
            plan.as_raw_fd().to_string().into(),
            "/run/install-plan".into(),
        ]);
        handles.push((arguments.len() - 2, plan));
        Ok(())
    }
}
