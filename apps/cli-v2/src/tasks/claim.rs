//! A task lease survives registry connections, never a child process or restart.

use crate::{
    authoring::runtime::Owner,
    digest,
    error::{Failure, Result},
    files::{self, OwnedDirectory},
};
use std::path::{Path, PathBuf};

pub(super) struct Claim {
    held: OwnedDirectory,
    output: PathBuf,
}
impl Claim {
    pub fn open(parent: &Path, owner: &Owner, key: &str) -> Result<Self> {
        let invalid = || Failure::precondition("the native task lease or state parent changed");
        let name = digest::sha256(key.as_bytes());
        let name = name.strip_prefix("sha256:").ok_or_else(invalid)?;
        let root = owner.root_directory();
        let namespace =
            OwnedDirectory::open_at(root, "ai-stp-task-work", b"ai-stp:task-work/v1\n", true)?
                .ok_or_else(invalid)?;
        let held = OwnedDirectory::open_at(
            &namespace.directory,
            name,
            format!("ai-stp:task-lease/v1\n{key}\n").as_bytes(),
            true,
        )?
        .ok_or_else(invalid)?;
        let output = PathBuf::from(files::location(parent)?)
            .join("ai-stp-task-work")
            .join(name)
            .join("bundles");
        // Owner opens against its held physical directory, not an ambient path.
        owner.planning()?;
        drop(namespace);
        Ok(Self { held, output })
    }
    pub fn output(&self) -> Result<&Path> {
        self.held.validate_lock()?;
        Ok(&self.output)
    }
}
