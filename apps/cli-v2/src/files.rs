//! Bounded input and display paths shared by read services.

use std::{
    fs::File,
    io::Read,
    path::{Path, PathBuf},
};

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
    let file = File::open(path).map_err(|_| Failure::input("input cannot be read"))?;
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
