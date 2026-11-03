//! OS-user placement is independent of per-workspace/environment selectors.

use super::invalid;
use crate::{error::Result, files::OwnedDirectory};
use std::path::PathBuf;
const LEAF: &str = "ai-stp-custody";
const OWNER: &[u8] = b"ai-stp native OS-user custody directory v1\n";

#[cfg(unix)]
fn home() -> Result<PathBuf> {
    use std::{ffi::OsString, path::Path, time::Duration};
    let uid = rustix::process::geteuid().as_raw().to_string();
    #[cfg(target_os = "linux")]
    let (executable, arguments) = (
        Path::new("/usr/bin/getent"),
        vec![OsString::from("passwd"), uid.clone().into()],
    );
    #[cfg(target_os = "macos")]
    let (executable, arguments) = (
        Path::new("/usr/bin/dscacheutil"),
        vec![
            OsString::from("-q"),
            "user".into(),
            "-a".into(),
            "uid".into(),
            uid.clone().into(),
        ],
    );
    let output = crate::process::run(crate::process::Request {
        executable,
        arguments: &arguments,
        directory: Path::new("/"),
        environment: &[("LC_ALL".into(), "C".into())],
        timeout: Duration::from_secs(5),
        output_limit: 16384,
    })?;
    if !output.status.success() {
        return Err(invalid());
    }
    let answer = std::str::from_utf8(&output.stdout).map_err(|_| invalid())?;
    #[cfg(target_os = "linux")]
    let path = {
        let mut lines = answer.lines();
        let line = lines.next().ok_or_else(invalid)?;
        if lines.next().is_some() {
            return Err(invalid());
        }
        let fields: Vec<_> = line.split(':').collect();
        if fields.len() != 7 || fields[2] != uid {
            return Err(invalid());
        }
        PathBuf::from(fields[5])
    };
    #[cfg(target_os = "macos")]
    let path = {
        let mut fields = std::collections::BTreeMap::new();
        for line in answer.lines().filter(|line| !line.trim().is_empty()) {
            let (key, value) = line.split_once(':').ok_or_else(invalid)?;
            if fields.insert(key.trim(), value.trim()).is_some() {
                return Err(invalid());
            }
        }
        if fields.get("uid").copied() != Some(uid.as_str()) {
            return Err(invalid());
        }
        PathBuf::from(fields.get("dir").ok_or_else(invalid)?)
    };
    if !path.is_absolute() || path.as_os_str().is_empty() {
        return Err(invalid());
    }
    // This is the OS-selected account directory, not a normalization of a
    // caller's planned filesystem spelling.
    path.canonicalize().map_err(|_| invalid())
}

fn parent() -> Result<(PathBuf, Vec<&'static str>)> {
    #[cfg(target_os = "linux")]
    {
        Ok((home()?, vec![".local", "share"]))
    }
    #[cfg(target_os = "macos")]
    {
        Ok((home()?, vec!["Library", "Application Support"]))
    }
    #[cfg(windows)]
    {
        let path = winsafe::SHGetKnownFolderPath(
            &winsafe::co::KNOWNFOLDERID::LocalAppData,
            winsafe::co::KF::DEFAULT,
            None,
        )
        .map_err(|_| invalid())?;
        Ok((
            PathBuf::from(path).canonicalize().map_err(|_| invalid())?,
            vec![],
        ))
    }
}

/// Discover the fixed OS-user coordinator without creating any state.
pub fn user_directory() -> Result<PathBuf> {
    let (mut path, parts) = parent()?;
    for part in parts {
        path.push(part);
    }
    Ok(path.join(LEAF))
}

pub(super) fn initialize() -> Result<(PathBuf, OwnedDirectory)> {
    let (mut path, parts) = parent()?;
    let mut directory = crate::installation::target::open(&path).map_err(|_| invalid())?;
    for part in parts {
        match crate::installation::target::child(&directory, std::ffi::OsStr::new(part)) {
            Ok(child) => directory = child,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let mut builder = cap_std::fs::DirBuilder::new();
                #[cfg(unix)]
                {
                    use cap_std::fs::DirBuilderExt;
                    builder.mode(0o700);
                }
                directory
                    .create_dir_with(part, &builder)
                    .map_err(|_| invalid())?;
                directory =
                    crate::installation::target::child(&directory, std::ffi::OsStr::new(part))
                        .map_err(|_| invalid())?;
            }
            Err(_) => return Err(invalid()),
        }
        path.push(part);
    }
    let namespace = OwnedDirectory::open_at(&directory, LEAF, OWNER, true)?.ok_or_else(invalid)?;
    Ok((path.join(LEAF), namespace))
}
