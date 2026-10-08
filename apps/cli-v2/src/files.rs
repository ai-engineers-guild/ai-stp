//! Bounded input and display paths shared by read services.

mod owned;
pub(crate) use owned::{OwnedDirectory, private_options};

use std::{
    io::Read,
    path::{Path, PathBuf},
};

use base64::{Engine, engine::general_purpose::STANDARD};
use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::{Dir, File, OpenOptions};
use serde::{Deserialize, Serialize};
use unicode_normalization::UnicodeNormalization;

use crate::error::{ErrorKind, Failure, Result};

pub fn read(path: &Path, limit: u64) -> Result<Vec<u8>> {
    let metadata = path
        .symlink_metadata()
        .map_err(|_| Failure::new(ErrorKind::NotFound, "input file is not accessible"))?;
    if !metadata.is_file() {
        return Err(Failure::input(
            "input must be a regular file, not a symbolic link",
        ));
    }
    if metadata.len() > limit {
        return Err(Failure::input("input exceeds its byte limit"));
    }
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let directory = Dir::open_ambient_dir(parent, cap_std::ambient_authority())
        .map_err(|_| Failure::input("input directory cannot be opened"))?;
    let file = open_regular(
        &directory,
        Path::new(
            path.file_name()
                .ok_or_else(|| Failure::input("input must name a file"))?,
        ),
    )
    .map_err(|_| Failure::input("input cannot be read"))?;
    if !file.metadata().is_ok_and(|meta| meta.is_file()) {
        return Err(Failure::input("opened input is not a regular file"));
    }
    let mut bytes = Vec::new();
    file.take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| Failure::input("input cannot be read"))?;
    if bytes.len() as u64 > limit {
        return Err(Failure::input("input exceeds its byte limit"));
    }
    Ok(bytes)
}

/// Open relative to an already held directory, without following a final link
/// or blocking on a substituted FIFO. Metadata is checked on the actual handle.
pub fn open_regular(directory: &Dir, path: &Path) -> std::io::Result<File> {
    let mut options = OpenOptions::new();
    options.read(true).follow(FollowSymlinks::No).nonblock(true);
    let file = directory.open_with(path, &options)?;
    if !file.metadata()?.is_file() {
        return Err(std::io::Error::other("not a regular file"));
    }
    Ok(file)
}

pub fn home() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .filter(|v| !v.is_empty())
        .or_else(|| std::env::var_os("USERPROFILE").filter(|v| !v.is_empty()))
        .map(PathBuf::from)
}

pub fn display(path: &Path) -> String {
    if let Some(home) = home().filter(|p| p.is_absolute())
        && let Ok(relative) = path.strip_prefix(home)
    {
        return Path::new("~").join(relative).to_string_lossy().into_owned();
    }
    path.to_string_lossy().into_owned()
}

/// One resolved spelling for persisted local bindings. On Windows, remove a
/// verbatim drive/UNC prefix only when the ordinary spelling resolves identically.
pub(crate) fn location(path: &Path) -> Result<String> {
    let resolved = path
        .canonicalize()
        .map_err(|_| Failure::precondition("the source location cannot be resolved"))?;
    let value = resolved
        .to_str()
        .ok_or_else(|| Failure::input("the source location is not Unicode"))?;
    #[cfg(windows)]
    {
        let ordinary = if let Some(tail) = value.strip_prefix(r"\\?\UNC\") {
            Some(format!(r"\\{tail}"))
        } else if let Some(tail) = value.strip_prefix(r"\\?\") {
            (tail.as_bytes().get(1..3) == Some(b":\\")).then(|| tail.to_owned())
        } else {
            None
        };
        if let Some(ordinary) = ordinary
            && Path::new(&ordinary)
                .canonicalize()
                .is_ok_and(|path| path == resolved)
        {
            return Ok(ordinary);
        }
    }
    Ok(value.to_owned())
}

pub(crate) fn same_location(left: &Path, right: &Path) -> Result<bool> {
    let metadata = |path: &Path| {
        let parent = path
            .parent()
            .ok_or_else(|| Failure::input("source location has no parent"))?;
        let directory = Dir::open_ambient_dir(parent, cap_std::ambient_authority())
            .map_err(|_| Failure::precondition("source parent cannot be inspected"))?;
        directory
            .metadata(
                path.file_name()
                    .ok_or_else(|| Failure::input("source location has no name"))?,
            )
            .map_err(|_| Failure::precondition("source location cannot be inspected"))
    };
    let left = metadata(left)?;
    let right = metadata(right)?;
    Ok(
        cap_fs_ext::MetadataExt::dev(&left) == cap_fs_ext::MetadataExt::dev(&right)
            && cap_fs_ext::MetadataExt::ino(&left) == cap_fs_ext::MetadataExt::ino(&right),
    )
}

// Project JSON normalizes strings. Filesystem names need their exact UTF-8 bytes;
// the normalized display string is never used to reopen a planned source.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct LocalPath {
    display: String,
    utf8_base64: String,
}

pub(crate) fn serialize_location<S: serde::Serializer>(
    value: &str,
    serializer: S,
) -> std::result::Result<S::Ok, S::Error> {
    if value.len() > 32768 || value.contains('\0') || !Path::new(value).is_absolute() {
        return Err(serde::ser::Error::custom("invalid absolute local path"));
    }
    LocalPath {
        display: value.nfc().collect(),
        utf8_base64: STANDARD.encode(value.as_bytes()),
    }
    .serialize(serializer)
}

pub(crate) fn deserialize_location<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<String, D::Error> {
    let encoded = LocalPath::deserialize(deserializer)?;
    if encoded.utf8_base64.len() > 43692 {
        return Err(serde::de::Error::custom("local path exceeds its bound"));
    }
    let bytes = STANDARD
        .decode(&encoded.utf8_base64)
        .map_err(|_| serde::de::Error::custom("invalid local path bytes"))?;
    let value = String::from_utf8(bytes)
        .map_err(|_| serde::de::Error::custom("local path is not Unicode"))?;
    if value.len() > 32768
        || value.contains('\0')
        || !Path::new(&value).is_absolute()
        || STANDARD.encode(value.as_bytes()) != encoded.utf8_base64
        || value.nfc().collect::<String>() != encoded.display
    {
        return Err(serde::de::Error::custom(
            "local path display and bytes disagree",
        ));
    }
    Ok(value)
}

pub(crate) fn serialize_path<S: serde::Serializer>(
    path: &Path,
    serializer: S,
) -> std::result::Result<S::Ok, S::Error> {
    serialize_location(
        path.to_str()
            .ok_or_else(|| serde::ser::Error::custom("local path is not Unicode"))?,
        serializer,
    )
}

pub(crate) fn deserialize_path<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<PathBuf, D::Error> {
    deserialize_location(deserializer).map(PathBuf::from)
}
