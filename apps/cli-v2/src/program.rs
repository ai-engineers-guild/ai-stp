//! Bounded software-prefix observations; local records never establish trust.

use std::{
    io::Read,
    path::{Component, Path, PathBuf},
};

use cap_fs_ext::{DirExt, MetadataExt};
use cap_std::fs::{Dir, Metadata};
use serde_json::{Value, json};

use crate::{
    digest,
    error::{ErrorKind, Failure, Result},
    files,
};

fn invalid() -> Failure {
    Failure::precondition(
        "the program prefix is invalid, aliased, changed or exceeds observation bounds",
    )
}

fn optional<T>(result: std::io::Result<T>) -> Result<Option<T>> {
    match result {
        Ok(value) => Ok(Some(value)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(Failure::new(
            ErrorKind::Unavailable,
            "the program prefix could not be inspected",
        )
        .with_details([("os_error".into(), error.raw_os_error().into())])),
    }
}

fn label(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && !value.starts_with('.')
        && !value.ends_with('.')
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-' | b'+'))
}

fn same(left: &Metadata, right: &Metadata) -> bool {
    left.dev() == right.dev() && left.ino() == right.ino()
}

fn reparse(metadata: &Metadata) -> bool {
    #[cfg(windows)]
    {
        use cap_std::fs::MetadataExt;
        metadata.file_attributes() & 0x400 != 0
    }
    #[cfg(not(windows))]
    {
        let _ = metadata;
        false
    }
}

fn directory(parent: &Dir, name: &Path) -> Result<Option<Dir>> {
    let Some(before) = optional(parent.symlink_metadata(name))? else {
        return Ok(None);
    };
    if !before.is_dir() || before.is_symlink() || reparse(&before) {
        return Err(invalid());
    }
    let opened = parent.open_dir_nofollow(name).map_err(|_| invalid())?;
    let after = opened.dir_metadata().map_err(|_| invalid())?;
    if !same(&before, &after) || reparse(&after) {
        return Err(invalid());
    }
    Ok(Some(opened))
}

fn link_path(parent: &Path, path: &Path, prefix: &Path) -> Result<PathBuf> {
    if path.as_os_str().len() > 4096 || path.to_str().is_none() {
        return Err(invalid());
    }
    let (mut result, path, mut descended) = if path.is_absolute() {
        (
            PathBuf::new(),
            path.strip_prefix(prefix).map_err(|_| invalid())?,
            true,
        )
    } else {
        (parent.to_owned(), path, false)
    };
    for part in path.components() {
        match part {
            Component::Normal(name) => {
                result.push(name);
                descended = true;
            }
            Component::CurDir => (),
            // Only ascend from directories already opened without following links.
            // Collapsing a later `name/..` could conceal an aliased or missing name.
            Component::ParentDir if !descended && result.pop() => (),
            _ => return Err(invalid()),
        }
    }
    if result.as_os_str().is_empty() || result.components().count() > 32 {
        return Err(invalid());
    }
    Ok(result)
}

/// Follow only a final entry-point link, resolving its spelling inside the held
/// prefix. Intermediate directories never follow links or reparse aliases.
fn entry(root: &Dir, prefix: &Path, relative: &Path) -> Result<Value> {
    let mut path = relative.to_owned();
    let mut linked = false;
    for _ in 0..16 {
        let path_parent = path.parent().ok_or_else(invalid)?;
        let mut parent = root.try_clone().map_err(|_| invalid())?;
        for component in path_parent.components() {
            let Component::Normal(name) = component else {
                return Err(invalid());
            };
            let Some(next) = directory(&parent, Path::new(name))? else {
                return Ok(json!({"state":if linked {"dangling"} else {"missing"}}));
            };
            parent = next;
        }
        let name = path.file_name().ok_or_else(invalid)?;
        let Some(metadata) = optional(parent.symlink_metadata(name))? else {
            return Ok(json!({"state":if linked {"dangling"} else {"missing"}}));
        };
        if metadata.is_symlink() {
            let to = parent.read_link_contents(name).map_err(|_| invalid())?;
            path = link_path(path_parent, &to, prefix)?;
            linked = true;
        } else if metadata.is_file() && !reparse(&metadata) {
            // Reopen the same leaf without following a raced link or FIFO.
            let file = files::open_regular(&parent, Path::new(name)).map_err(|_| invalid())?;
            let after = file.metadata().map_err(|_| invalid())?;
            if !same(&metadata, &after) || reparse(&after) {
                return Err(invalid());
            }
            return Ok(
                json!({"state":"regular","kind":if linked {"link"} else {"file"},
                "resolved_relative":path,"size_bytes":metadata.len()}),
            );
        } else {
            return Err(invalid());
        }
    }
    Err(invalid())
}

fn observe(root: &Dir, prefix: &Path, entry_point: &str, command: &str) -> Result<Value> {
    let mut versions = Vec::new();
    let mut unfinished = Vec::new();
    for (index, item) in root.entries().map_err(|_| invalid())?.enumerate() {
        if index >= 1024 {
            return Err(invalid());
        }
        let item = item.map_err(|_| invalid())?;
        let name = item.file_name().into_string().map_err(|_| invalid())?;
        let metadata = root.symlink_metadata(&name).map_err(|_| invalid())?;
        let kind = metadata.file_type();
        if let Some(version) = name
            .strip_prefix(".incoming-")
            .or_else(|| name.strip_prefix(".replaced-"))
        {
            if !label(version) || !kind.is_dir() || reparse(&metadata) {
                return Err(invalid());
            }
            unfinished.push(name);
        } else if name != "bin" && !name.starts_with('.') && kind.is_dir() {
            if !label(&name) || reparse(&metadata) {
                return Err(invalid());
            }
            versions.push(name);
        } else if kind.is_symlink() && !name.starts_with('.') {
            return Err(invalid());
        }
    }
    versions.sort();
    let mut recorded: Option<String> = None;
    let mut marker_digest: Option<String> = None;
    if let Some(bin) = directory(root, Path::new("bin"))? {
        let marker = format!(".{command}.version");
        if let Some(file) = optional(files::open_regular(&bin, Path::new(&marker)))? {
            if reparse(&file.metadata().map_err(|_| invalid())?) {
                return Err(invalid());
            }
            let mut bytes = Vec::new();
            file.take(1025)
                .read_to_end(&mut bytes)
                .map_err(|_| invalid())?;
            let text = std::str::from_utf8(&bytes).map_err(|_| invalid())?.trim();
            if bytes.len() > 1024 || !label(text) {
                return Err(invalid());
            }
            recorded = Some(text.to_owned());
            marker_digest = Some(digest::sha256(&bytes));
        }
        for name in [
            format!("{marker}.incoming"),
            format!(".{command}.manifest.json.incoming"),
        ] {
            if let Some(metadata) = optional(bin.symlink_metadata(&name))? {
                if !metadata.is_file() || reparse(&metadata) {
                    return Err(invalid());
                }
                unfinished.push(format!("bin/{name}"));
            }
        }
    }
    unfinished.sort();
    let entry = entry(root, prefix, Path::new(entry_point))?;
    let linked = (entry["kind"] == "link")
        .then(|| entry["resolved_relative"].as_str())
        .flatten()
        .and_then(|path| Path::new(path).components().next())
        .and_then(|part| part.as_os_str().to_str().map(str::to_owned))
        .filter(|name| versions.contains(name));
    Ok(
        json!({"versions":versions,"unfinished":unfinished,"entry_point":entry,
        "recorded_version":recorded,"marker_digest":marker_digest,
        "recorded_version_present":recorded.as_ref().map(|value| versions.contains(value)),
        "link_version":linked,"marker_matches_link":recorded.as_ref().zip(linked.as_ref()).map(|(a,b)|a==b)}),
    )
}

/// Report an explicit prefix layout without executing or trusting its contents.
pub fn inspect(prefix: &Path, entry_point: &str) -> Result<Value> {
    let command = entry_point.strip_prefix("bin/").ok_or_else(invalid)?;
    if !label(command)
        || command.contains('/')
        || !prefix.is_absolute()
        || prefix.to_str().is_none()
    {
        return Err(invalid());
    }
    let lower = command.to_ascii_lowercase();
    let command = if [".cmd", ".exe", ".bat"]
        .iter()
        .any(|suffix| lower.ends_with(suffix))
    {
        &command[..command.len() - 4]
    } else {
        command
    };
    if !label(command) || prefix.as_os_str().len() > 4096 {
        return Err(invalid());
    }
    let parent_path = PathBuf::from(files::location(prefix.parent().ok_or_else(invalid)?)?);
    let name = prefix.file_name().ok_or_else(invalid)?;
    let prefix = parent_path.join(name);
    let parent =
        Dir::open_ambient_dir(&parent_path, cap_std::ambient_authority()).map_err(|_| invalid())?;
    let before = parent.dir_metadata().map_err(|_| invalid())?;
    let opened = directory(&parent, Path::new(name))?;
    let (state, observation) = if let Some(root) = opened {
        let first = observe(&root, &prefix, entry_point, command)?;
        if first != observe(&root, &prefix, entry_point, command)?
            || !same(
                &root.dir_metadata().map_err(|_| invalid())?,
                &directory(&parent, Path::new(name))?
                    .ok_or_else(invalid)?
                    .dir_metadata()
                    .map_err(|_| invalid())?,
            )
        {
            return Err(invalid());
        }
        ("present", first)
    } else {
        if optional(parent.symlink_metadata(name))?.is_some() {
            return Err(invalid());
        }
        ("missing", Value::Null)
    };
    let after = Dir::open_ambient_dir(&parent_path, cap_std::ambient_authority())
        .and_then(|dir| dir.dir_metadata())
        .map_err(|_| invalid())?;
    if !same(&before, &after) {
        return Err(invalid());
    }
    Ok(
        json!({"schema_version":1,"prefix":prefix,"prefix_state":state,"entry_point":entry_point,
        "observation":observation,"observed_at":jiff::Timestamp::now().to_string(),
        "installation_verified":false,"execution_authorized":false}),
    )
}
