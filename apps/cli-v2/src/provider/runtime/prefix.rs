//! A program prefix may be absent; its existing parent is held but never exposed.

use cap_std::fs::Dir;
use std::{
    io::ErrorKind,
    path::{Path, PathBuf},
};

use super::target::{Target, contains};
use crate::error::{Failure, Result};

fn invalid() -> Failure {
    Failure::precondition(
        "the program prefix or its existing parent is invalid, aliased or changed",
    )
}

pub(super) enum Prefix {
    Existing(Target),
    Missing { parent: Target, path: PathBuf },
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum View {
    Observed,
    EmptyStage,
}

impl Prefix {
    pub(super) fn open(path: &Path) -> Result<Self> {
        if let Ok(target) = Target::open(path) {
            return Ok(Self::Existing(target));
        }
        let parent = Target::open(path.parent().ok_or_else(invalid)?)?;
        let path = parent.path().join(path.file_name().ok_or_else(invalid)?);
        if path.as_os_str().len() > 4096 || path.to_str().is_none() {
            return Err(invalid());
        }
        let prefix = Self::Missing { parent, path };
        prefix.revalidate()?;
        Ok(prefix)
    }

    pub(super) fn path(&self) -> &Path {
        match self {
            Self::Existing(target) => target.path(),
            Self::Missing { path, .. } => path,
        }
    }

    pub(super) fn mounted(&self) -> Option<&Target> {
        match self {
            Self::Existing(target) => Some(target),
            Self::Missing { .. } => None,
        }
    }

    pub(super) fn missing(&self) -> Option<&Path> {
        match self {
            Self::Existing(_) => None,
            Self::Missing { path, .. } => Some(path),
        }
    }

    pub(super) fn parent_identity(&self) -> Result<(u64, u64)> {
        self.revalidate()?;
        match self {
            Self::Missing { parent, .. } => parent.identity(),
            Self::Existing(_) => Err(Failure::precondition(
                "a new program installation requires an absent final prefix",
            )),
        }
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        match self {
            Self::Existing(target) => target.revalidate(),
            Self::Missing { parent, path } => {
                let directory = parent.directory()?;
                match directory.symlink_metadata(path.file_name().ok_or_else(invalid)?) {
                    Err(error) if error.kind() == ErrorKind::NotFound => Ok(()),
                    _ => Err(invalid()),
                }
            }
        }
    }

    pub(super) fn disjoint(&self, other: &Dir) -> Result<()> {
        self.revalidate()?;
        match self {
            Self::Existing(target) => target.disjoint(other),
            Self::Missing { parent, .. } => {
                // An absent child cannot contain an existing directory. Siblings
                // under its parent are valid, including trust state and target.
                if contains(other, &parent.directory()?)? {
                    return Err(invalid());
                }
                Ok(())
            }
        }
    }

    pub(super) fn verify_missing_mount(path: &Path) -> Result<()> {
        match Self::open(path)? {
            Self::Missing { parent, .. } => parent.verify_mount(parent.identity()?),
            Self::Existing(_) => Err(invalid()),
        }
    }

    pub(super) fn verify_empty_mount(path: &Path) -> Result<()> {
        let root = Target::open(path)?;
        root.verify_mount(root.identity()?)?;
        let parent = Target::open(path.parent().ok_or_else(invalid)?)?;
        parent.verify_mount(parent.identity()?)?;
        if root
            .directory()?
            .entries()
            .map_err(|_| invalid())?
            .next()
            .is_some()
        {
            return Err(invalid());
        }
        Ok(())
    }
}
