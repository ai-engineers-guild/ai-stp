//! A held read-only target directory; path lookup never follows an alias.

use cap_fs_ext::DirExt;
use cap_std::fs::Dir;
use serde_json::Value;
use std::{
    fs::File,
    os::{fd::OwnedFd, unix::fs::MetadataExt},
    path::{Component, Path, PathBuf},
};

use crate::{
    error::{Failure, Result},
    provider::Info,
    wire::{self, Schema},
};

static STATUS: Schema = Schema::new(include_str!(
    "../../../../../provider-kit/v3/status-response.schema.json"
));

fn invalid() -> Failure {
    Failure::precondition("the provider target is invalid, aliased or changed during observation")
}

pub(crate) struct Target {
    directory: File,
    path: PathBuf,
}

impl Target {
    pub(crate) fn open(path: &Path) -> Result<Self> {
        if !path.is_absolute() || path.as_os_str().len() > 4096 || path.to_str().is_none() {
            return Err(invalid());
        }
        let mut directory =
            Dir::open_ambient_dir("/", cap_std::ambient_authority()).map_err(|_| invalid())?;
        let mut normalized = PathBuf::from("/");
        for part in path.components() {
            match part {
                Component::RootDir => (),
                Component::Normal(name) => {
                    directory = directory.open_dir_nofollow(name).map_err(|_| invalid())?;
                    normalized.push(name);
                }
                _ => return Err(invalid()),
            }
        }
        // The explicit target must not replace a sandbox root or runtime mount.
        if ["/", "/home", "/tmp"]
            .iter()
            .any(|p| normalized == Path::new(p))
            || [
                "/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc", "/dev", "/proc", "/sys", "/run",
            ]
            .iter()
            .any(|p| normalized.starts_with(p))
        {
            return Err(invalid());
        }
        Ok(Self {
            directory: directory.into_std_file(),
            path: normalized,
        })
    }

    pub(crate) fn path(&self) -> &Path {
        &self.path
    }

    pub(super) fn handle(&self) -> Result<OwnedFd> {
        rustix::io::fcntl_dupfd_cloexec(&self.directory, 3).map_err(|_| invalid())
    }

    pub(crate) fn identity(&self) -> Result<(u64, u64)> {
        let metadata = self.directory.metadata().map_err(|_| invalid())?;
        Ok((metadata.dev(), metadata.ino()))
    }

    pub(super) fn verify_mount(&self, expected: (u64, u64)) -> Result<()> {
        let mounted = rustix::fs::fstatvfs(&self.directory).map_err(|_| invalid())?;
        if self.identity()? != expected
            || !mounted
                .f_flag
                .contains(rustix::fs::StatVfsMountFlags::RDONLY)
        {
            return Err(invalid());
        }
        Ok(())
    }

    /// Hold the state parent before any write and reject either ancestry direction.
    pub(crate) fn state_parent(&self, path: &Path) -> Result<Dir> {
        let parent =
            Dir::open_ambient_dir(path, cap_std::ambient_authority()).map_err(|_| invalid())?;
        self.disjoint(&parent)?;
        Ok(parent)
    }

    /// Check ancestry using held directories, including aliases and bind mounts.
    pub(super) fn disjoint(&self, other: &Dir) -> Result<()> {
        let target = Dir::from_std_file(self.directory.try_clone().map_err(|_| invalid())?);
        self.revalidate()?;
        if contains(other, &target)? || contains(&target, other)? {
            return Err(Failure::precondition(
                "the provider target, program prefix and trust state must be disjoint directories",
            ));
        }
        Ok(())
    }

    pub(crate) fn revalidate(&self) -> Result<()> {
        let current = Self::open(&self.path)?;
        let before = self.directory.metadata().map_err(|_| invalid())?;
        let after = current.directory.metadata().map_err(|_| invalid())?;
        if before.dev() != after.dev() || before.ino() != after.ino() {
            return Err(invalid());
        }
        Ok(())
    }

    pub(crate) fn directory(&self) -> Result<Dir> {
        self.revalidate()?;
        Ok(Dir::from_std_file(
            self.directory.try_clone().map_err(|_| invalid())?,
        ))
    }

    /// Generated artifacts may be siblings of a target, but never written
    /// inside it. The final target remains exclusively the provider's surface.
    pub(crate) fn outside(&self, parent: &Path) -> Result<()> {
        let parent =
            Dir::open_ambient_dir(parent, cap_std::ambient_authority()).map_err(|_| invalid())?;
        if contains(&self.directory()?, &parent)? {
            return Err(Failure::precondition(
                "bundle output must be outside the provider target",
            ));
        }
        Ok(())
    }

    pub(super) fn response(&self, bytes: &[u8], provider: &Info) -> Result<Value> {
        if bytes.len() > 1024 * 1024 {
            return Err(invalid());
        }
        let document = wire::parse(bytes)?;
        STATUS.validate(&document)?;
        if document["canonical_target"].as_str() != self.path.to_str()
            || document["harness_id"] != provider.document()["harness_id"]
            || document["provider_id"] != provider.document()["provider_id"]
        {
            return Err(Failure::precondition(
                "the provider status belongs to another target or provider",
            ));
        }
        self.revalidate()?;
        Ok(document)
    }
}

fn identity(directory: &Dir) -> Result<(u64, u64)> {
    let metadata = directory.dir_metadata().map_err(|_| invalid())?;
    Ok((
        cap_fs_ext::MetadataExt::dev(&metadata),
        cap_fs_ext::MetadataExt::ino(&metadata),
    ))
}

fn contains(ancestor: &Dir, descendant: &Dir) -> Result<bool> {
    let expected = identity(ancestor)?;
    let mut current = descendant.try_clone().map_err(|_| invalid())?;
    for _ in 0..256 {
        let before = identity(&current)?;
        if before == expected {
            return Ok(true);
        }
        let parent = current
            .open_parent_dir(cap_std::ambient_authority())
            .map_err(|_| invalid())?;
        if before == identity(&parent)? {
            return Ok(false);
        }
        current = parent;
    }
    Err(invalid())
}
