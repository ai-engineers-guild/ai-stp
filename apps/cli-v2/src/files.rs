//! Bounded input and display paths shared by read services.

mod owned;
pub(crate) use owned::{OwnedDirectory, private_options};

use std::{
    io::Read,
    path::{Path, PathBuf},
};

use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::{Dir, File, OpenOptions};

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
