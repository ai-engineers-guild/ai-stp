//! A fresh missing-leaf observation is distinct from retained binding history.

use std::path::{Component, Path, PathBuf};

use cap_std::fs::Dir;
use serde::{Deserialize, Serialize};

use crate::{
    error::{Failure, Result},
    files::{self, physical::DirectoryIdentity},
};

fn invalid() -> Failure {
    Failure::precondition(
        "the reviewed checkout is present, inaccessible or its physical parent changed",
    )
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(super) struct Parent {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    path: PathBuf,
    physical: DirectoryIdentity,
}

pub(super) struct Observation {
    pub parent: Parent,
    directory: Dir,
    checkout: PathBuf,
}

fn current_parent(path: &Path) -> Result<Dir> {
    if PathBuf::from(files::location(path)?).as_os_str() != path.as_os_str() {
        return Err(invalid());
    }
    Dir::open_ambient_dir(path, cap_std::ambient_authority()).map_err(|_| invalid())
}

impl Parent {
    /// Retained receipt validation must remain possible after this path is gone.
    pub fn validate(&self, checkout: &Path) -> Result<()> {
        self.physical.validate()?;
        if !self.path.is_absolute()
            || !checkout.is_absolute()
            || checkout
                .parent()
                .is_none_or(|parent| parent.as_os_str() != self.path.as_os_str())
            || checkout
                .file_name()
                .is_none_or(|leaf| self.path.join(leaf).as_os_str() != checkout.as_os_str())
            || checkout
                .components()
                .any(|part| matches!(part, Component::CurDir | Component::ParentDir))
        {
            return Err(invalid());
        }
        Ok(())
    }

    pub fn observe(checkout: &Path) -> Result<Observation> {
        let path = checkout.parent().ok_or_else(invalid)?.to_path_buf();
        let directory = current_parent(&path)?;
        let observed = Observation {
            parent: Self {
                path,
                physical: DirectoryIdentity::capture(&directory)?,
            },
            directory,
            checkout: checkout.to_path_buf(),
        };
        observed.revalidate(checkout)?;
        Ok(observed)
    }

    pub fn open(&self, checkout: &Path) -> Result<Observation> {
        self.validate(checkout)?;
        let observed = Observation {
            parent: self.clone(),
            directory: current_parent(&self.path)?,
            checkout: checkout.to_path_buf(),
        };
        observed.revalidate(checkout)?;
        Ok(observed)
    }
}

impl Observation {
    pub fn revalidate(&self, checkout: &Path) -> Result<()> {
        self.parent.validate(checkout)?;
        if self.checkout.as_os_str() != checkout.as_os_str()
            || DirectoryIdentity::capture(&self.directory)? != self.parent.physical
            || DirectoryIdentity::capture(&current_parent(&self.parent.path)?)?
                != self.parent.physical
        {
            return Err(invalid());
        }
        let leaf = Path::new(checkout.file_name().ok_or_else(invalid)?);
        match self.directory.symlink_metadata(leaf) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            _ => Err(invalid()),
        }
    }
}

#[cfg(all(test, any(unix, windows)))]
mod tests {
    use super::*;
    use cap_fs_ext::DirExt;
    use std::{error::Error, fs};

    #[test]
    fn only_a_missing_leaf_under_the_reviewed_parent_is_accepted()
    -> std::result::Result<(), Box<dyn Error>> {
        let tree = tempfile::tempdir()?;
        let parent = PathBuf::from(files::location(tree.path())?);
        let checkout = parent.join("checkout");
        let other = parent.join("other");
        let observed = Parent::observe(&checkout)?;
        observed.revalidate(&checkout)?;
        assert!(observed.revalidate(&other).is_err());
        let proof: Parent = serde_json::from_value(serde_json::to_value(&observed.parent)?)?;
        proof.open(&checkout)?;

        fs::write(&checkout, b"unowned file stays here\n")?;
        assert!(observed.revalidate(&checkout).is_err());
        assert!(proof.open(&checkout).is_err());
        assert_eq!(fs::read(&checkout)?, b"unowned file stays here\n");
        fs::remove_file(&checkout)?;
        fs::create_dir(&checkout)?;
        fs::write(checkout.join("keep"), b"unowned directory stays here\n")?;
        assert!(observed.revalidate(&checkout).is_err());
        assert!(proof.open(&checkout).is_err());
        assert_eq!(
            fs::read(checkout.join("keep"))?,
            b"unowned directory stays here\n"
        );
        Ok(())
    }

    #[test]
    fn parent_replacement_refuses_and_retained_validation_does_not_reopen_it()
    -> std::result::Result<(), Box<dyn Error>> {
        let tree = tempfile::tempdir()?;
        let base = PathBuf::from(files::location(tree.path())?);
        let parent = base.join("parent");
        let retained = base.join("retained-parent");
        fs::create_dir(&parent)?;
        fs::write(parent.join("keep"), b"original parent\n")?;
        let checkout = parent.join("checkout");
        let proof = Parent::observe(&checkout)?.parent;
        // Planning releases handles before an external rename, including Windows.
        fs::rename(&parent, &retained)?;
        proof.validate(&checkout)?;
        assert!(proof.open(&checkout).is_err());
        fs::create_dir(&parent)?;
        fs::write(parent.join("keep"), b"replacement parent\n")?;
        assert!(proof.open(&checkout).is_err());
        assert_eq!(fs::read(retained.join("keep"))?, b"original parent\n");
        assert_eq!(fs::read(parent.join("keep"))?, b"replacement parent\n");
        let raw = serde_json::to_value(&proof)?;
        let mut changed = raw.clone();
        changed["unexpected"] = true.into();
        assert!(serde_json::from_value::<Parent>(changed).is_err());
        let restored: Parent = serde_json::from_value(raw)?;
        restored.validate(&checkout)?;
        assert!(restored.open(&checkout).is_err());
        Ok(())
    }

    #[test]
    fn a_dangling_directory_link_is_present_and_its_target_stays_absent()
    -> std::result::Result<(), Box<dyn Error>> {
        let tree = tempfile::tempdir()?;
        let parent = PathBuf::from(files::location(tree.path())?);
        let checkout = parent.join("checkout");
        let observed = Parent::observe(&checkout)?;
        let directory = current_parent(&parent)?;
        directory.symlink_dir("missing-target", "checkout")?;
        assert!(observed.revalidate(&checkout).is_err());
        assert!(observed.parent.open(&checkout).is_err());
        assert!(Parent::observe(&checkout).is_err());
        assert!(
            parent
                .join("missing-target")
                .symlink_metadata()
                .is_err_and(|error| error.kind() == std::io::ErrorKind::NotFound)
        );
        assert!(checkout.symlink_metadata()?.is_symlink());
        Ok(())
    }
}
