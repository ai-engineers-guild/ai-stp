//! Explicit physical directory bindings for first-party configuration effects.

use super::{Error, ReasonCode, Result};
use cap_fs_ext::DirExt;
use cap_std::fs::Dir;
use std::path::{Component, Path, PathBuf};

#[derive(Debug)]
pub struct Target {
    root: PathBuf,
    control: String,
    identity: super::identity::Identity,
    held: Dir,
}

impl Target {
    pub fn resolve(path: &Path, control: &str) -> Result<Self> {
        if !path.is_absolute()
            || path.file_name().is_none()
            || path
                .components()
                .any(|part| matches!(part, Component::CurDir | Component::ParentDir))
            || !crate::archive::safe_path(control)
            || control.contains(['/', '\\', ':'])
            || matches!(control, "." | "..")
        {
            return Err(invalid());
        }
        let directory = open(path)?;
        let identity = super::identity::directory(&directory)
            .map_err(|source| invalid().with_source(source))?;
        Ok(Self {
            root: path.to_owned(),
            control: control.into(),
            identity,
            held: directory,
        })
    }

    pub fn root(&self) -> &Path {
        &self.root
    }
    pub fn control_directory(&self) -> PathBuf {
        self.root.join(&self.control)
    }

    pub(crate) fn is_internal(&self, path: &str) -> bool {
        internal_path(path, &self.control)
    }

    pub(crate) fn directory(&self) -> Result<Dir> {
        let directory = open(&self.root)?;
        if super::identity::directory(&directory).map_err(|source| invalid().with_source(source))?
            != self.identity
        {
            return Err(invalid());
        }
        self.held
            .try_clone()
            .map_err(|source| invalid().with_source(source))
    }
}

pub(crate) fn internal_path(path: &str, control: &str) -> bool {
    path.split('/')
        .next()
        .is_some_and(|part| unicase::UniCase::new(part) == unicase::UniCase::new(control))
}

pub(crate) fn open(path: &Path) -> Result<Dir> {
    let mut components = path.components();
    let first = components.next().ok_or_else(invalid)?;
    let root = match first {
        Component::RootDir => PathBuf::from(std::path::MAIN_SEPARATOR_STR),
        Component::Prefix(prefix) => {
            if components.next() != Some(Component::RootDir) {
                return Err(invalid());
            }
            PathBuf::from(prefix.as_os_str()).join(std::path::MAIN_SEPARATOR_STR)
        }
        _ => return Err(invalid()),
    };
    let mut directory = Dir::open_ambient_dir(root, cap_std::ambient_authority())
        .map_err(|source| invalid().with_source(source))?;
    for part in components {
        let Component::Normal(name) = part else {
            return Err(invalid());
        };
        directory = child(&directory, name).map_err(|source| invalid().with_source(source))?;
    }
    Ok(directory)
}

pub(crate) fn child(parent: &Dir, name: &std::ffi::OsStr) -> std::io::Result<Dir> {
    let metadata = parent.symlink_metadata(name)?;
    if !metadata.is_dir() || metadata.is_symlink() {
        return Err(std::io::Error::other("installation directory is not plain"));
    }
    #[cfg(windows)]
    {
        use cap_std::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return Err(std::io::Error::other(
                "installation directory is a reparse point",
            ));
        }
    }
    parent.open_dir_nofollow(name)
}

fn invalid() -> Error {
    Error::new(
        ReasonCode::InvalidTarget,
        "installation target must be an explicit plain existing physical directory",
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(unix)]
    #[test]
    fn original_directory_is_required_even_before_the_first_writer()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let physical = root.path().canonicalize()?;
        let path = physical.join("original");
        std::fs::create_dir(&path)?;
        let target = Target::resolve(&path, ".control")?;
        std::fs::rename(&path, physical.join("retained"))?;
        std::fs::create_dir(&path)?;
        assert!(target.directory().is_err());
        assert!(super::super::forward::Writer::acquire(&target, ".control").is_err());
        assert!(!path.join(".control").exists());
        Ok(())
    }

    #[cfg(windows)]
    #[test]
    fn held_original_directory_blocks_substitution_before_the_first_writer()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let physical = root.path().canonicalize()?;
        let original = physical.join("original");
        let moved = physical.join("retained");
        std::fs::create_dir(&original)?;
        let target = Target::resolve(&original, ".control")?;
        assert!(std::fs::rename(&original, &moved).is_err());
        assert!(target.directory().is_ok());
        assert!(!original.join(".control").exists());
        drop(target);
        std::fs::rename(&original, &moved)?;
        assert!(moved.is_dir());
        Ok(())
    }

    #[test]
    fn unsafe_target_and_control_names_refuse_without_writes()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        for control in ["", ".", "..", "child/other", "child\\other", "child:stream"] {
            assert!(Target::resolve(root.path(), control).is_err());
        }
        assert!(Target::resolve(Path::new("relative"), ".control").is_err());
        assert!(Target::resolve(&root.path().join("../outside"), ".control").is_err());
        assert!(std::fs::read_dir(root.path())?.next().is_none());
        Ok(())
    }

    #[test]
    fn actual_plain_target_and_owned_transaction_work()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let target = Target::resolve(&root.path().canonicalize()?, ".control")?;
        let writer = super::super::forward::Writer::acquire(&target, ".control")?;
        let change = writer.change(
            "nested/config",
            Some(super::super::forward::Content::new(
                b"desired".to_vec(),
                0o600,
            )?),
        )?;
        assert_eq!(change.path, "nested/config");
        assert!(!root.path().join("nested").exists());
        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn links_in_any_ancestor_refuse_before_configuration_metadata()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let real = root.path().canonicalize()?.join("real");
        std::fs::create_dir_all(real.join("child"))?;
        let link = root.path().canonicalize()?.join("alias");
        std::os::unix::fs::symlink(&real, &link)?;
        assert!(Target::resolve(&link.join("child"), ".control").is_err());
        assert!(Target::resolve(&link, ".control").is_err());
        assert!(!real.join("child/.control").exists());
        Ok(())
    }

    #[cfg(windows)]
    #[test]
    fn junctions_at_the_target_or_an_ancestor_refuse_without_target_effects()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        use std::os::windows::process::CommandExt;
        let root = tempfile::tempdir()?;
        let canonical = root.path().canonicalize()?;
        let text = canonical.to_str().ok_or("fixture is not Unicode")?;
        let ordinary = PathBuf::from(text.strip_prefix(r"\\?\").unwrap_or(text));
        assert_eq!(ordinary.canonicalize()?, canonical);
        let real = ordinary.join("real");
        let alias = ordinary.join("alias");
        std::fs::create_dir_all(real.join("child"))?;
        std::fs::write(real.join("child/unowned"), b"preserve")?;
        let command = PathBuf::from(std::env::var_os("SystemRoot").ok_or("SystemRoot absent")?)
            .join("System32")
            .join("cmd.exe");
        let result = std::process::Command::new(command)
            .env("AI_STP_INSTALLATION_JUNCTION", &alias)
            .env("AI_STP_INSTALLATION_REAL", &real)
            .args(["/D", "/V:OFF", "/S", "/C"])
            .raw_arg(r#""mklink /J "%AI_STP_INSTALLATION_JUNCTION%" "%AI_STP_INSTALLATION_REAL%"""#)
            .output()?;
        assert!(
            result.status.success(),
            "native junction fixture was not created: {}; stdout={}; stderr={}",
            result.status,
            String::from_utf8_lossy(&result.stdout)
                .chars()
                .take(1024)
                .collect::<String>(),
            String::from_utf8_lossy(&result.stderr)
                .chars()
                .take(1024)
                .collect::<String>()
        );
        assert!(Target::resolve(&alias, ".control").is_err());
        assert!(Target::resolve(&alias.join("child"), ".control").is_err());
        assert!(!real.join("child/.control").exists());
        assert_eq!(std::fs::read(real.join("child/unowned"))?, b"preserve");
        std::fs::remove_dir(alias)?;
        Ok(())
    }
}
