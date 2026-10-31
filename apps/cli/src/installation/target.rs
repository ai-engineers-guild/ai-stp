//! Explicit physical directory bindings for first-party configuration effects.

use std::path::{Component, Path, PathBuf};
use cap_fs_ext::DirExt;
use cap_std::fs::Dir;
use super::{Error, ReasonCode, Result};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Target {
    root: PathBuf,
    control: String,
}

impl Target {
    pub fn resolve(path: &Path, control: &str) -> Result<Self> {
        if !path.is_absolute() || path.file_name().is_none()
            || path.components().any(|part| matches!(part, Component::CurDir | Component::ParentDir))
            || control.is_empty() || control.contains(['/', '\\']) || matches!(control, "." | "..") {
            return Err(invalid());
        }
        let target = Self { root: path.to_owned(), control: control.into() };
        target.directory()?;
        Ok(target)
    }

    pub fn root(&self) -> &Path { &self.root }
    pub fn control_directory(&self) -> PathBuf { self.root.join(&self.control) }

    pub(crate) fn directory(&self) -> Result<Dir> {
        open(&self.root)
    }
}

pub(crate) fn open(path: &Path) -> Result<Dir> {
    let mut components = path.components();
    let first = components.next().ok_or_else(invalid)?;
    let root = match first {
        Component::RootDir => PathBuf::from(std::path::MAIN_SEPARATOR_STR),
        Component::Prefix(prefix) => {
            if components.next() != Some(Component::RootDir) { return Err(invalid()); }
            PathBuf::from(prefix.as_os_str()).join(std::path::MAIN_SEPARATOR_STR)
        }
        _ => return Err(invalid()),
    };
    let mut directory = Dir::open_ambient_dir(root, cap_std::ambient_authority())
        .map_err(|source| invalid().with_source(source))?;
    for part in components {
        let Component::Normal(name) = part else { return Err(invalid()); };
        directory = directory.open_dir_nofollow(name)
            .map_err(|source| invalid().with_source(source))?;
    }
    Ok(directory)
}

fn invalid() -> Error {
    Error::new(ReasonCode::InvalidTarget, "installation target must be an explicit plain existing physical directory")
}
