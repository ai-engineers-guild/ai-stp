//! Publish a fully verified new directory. Existing paths never move.

use std::{
    collections::{BTreeMap, BTreeSet},
    io::{Read, Write},
    path::{Path, PathBuf},
};

use cap_fs_ext::{DirExt, MetadataExt};
use cap_std::fs::{Dir, DirBuilder, Metadata};

use crate::{
    error::{Failure, Result},
    files::{self, OwnedDirectory, private_options},
};

pub(crate) enum Purpose {
    Scaffold,
    SetupExport,
    ProviderBundle,
}

impl Purpose {
    fn label(&self) -> &'static str {
        match self {
            Self::Scaffold => "scaffold",
            Self::SetupExport => "setup-export",
            Self::ProviderBundle => "provider-bundle",
        }
    }
}

/// Domain callers recompute these exact files before publication.
pub(crate) struct Tree<'a, T: AsRef<[u8]> = String> {
    pub output: &'a str,
    pub parent_identity: &'a [String; 2],
    pub files: &'a BTreeMap<String, T>,
    pub purpose: Purpose,
}

fn refused() -> Failure {
    Failure::precondition(
        "the output destination or staging tree changed, is unsafe or inaccessible",
    )
}

fn identity(metadata: &Metadata) -> [String; 2] {
    [metadata.dev().to_string(), metadata.ino().to_string()]
}

pub(crate) fn destination(output: &Path) -> Result<(String, [String; 2])> {
    let leaf = output.file_name().ok_or_else(refused)?;
    let parent = output
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let parent = files::location(parent)?;
    let directory =
        Dir::open_ambient_dir(&parent, cap_std::ambient_authority()).map_err(|_| refused())?;
    let output = Path::new(&parent)
        .join(leaf)
        .to_str()
        .ok_or_else(refused)?
        .to_owned();
    Ok((
        output,
        identity(&directory.dir_metadata().map_err(|_| refused())?),
    ))
}

fn plain(metadata: &Metadata, directory: bool) -> bool {
    if metadata.file_type().is_symlink()
        || metadata.is_dir() != directory
        || (!directory && (!metadata.is_file() || metadata.nlink() != 1))
    {
        return false;
    }
    #[cfg(windows)]
    {
        use cap_std::fs::MetadataExt as _;
        if metadata.file_attributes() & 0x400 != 0 {
            return false;
        }
    }
    #[cfg(unix)]
    {
        use cap_std::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o777 != if directory { 0o700 } else { 0o600 } {
            return false;
        }
    }
    true
}

fn mkdir(parent: &Dir, name: &str) -> Result<Dir> {
    let mut builder = DirBuilder::new();
    builder.recursive(false);
    #[cfg(unix)]
    {
        use cap_std::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    match parent.create_dir_with(name, &builder) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(_) => return Err(refused()),
    }
    let child = parent.open_dir_nofollow(name).map_err(|_| refused())?;
    if !plain(&child.dir_metadata().map_err(|_| refused())?, true) {
        return Err(refused());
    }
    Ok(child)
}

fn sync(directory: &Dir) -> Result<()> {
    let _ = directory;
    #[cfg(unix)]
    directory
        .open(".")
        .and_then(|f| f.sync_all())
        .map_err(|_| refused())?;
    Ok(())
}

/// Partial recovery accepts only prefixes of planned files in the private stage.
fn verify<T: AsRef<[u8]>>(directory: &Dir, plan: &Tree<'_, T>, partial: bool) -> Result<bool> {
    let mut expected_dirs = BTreeSet::new();
    for name in plan.files.keys() {
        let mut path = Path::new(name).parent();
        while let Some(parent) = path.filter(|p| !p.as_os_str().is_empty()) {
            expected_dirs.insert(parent.to_str().ok_or_else(refused)?.replace('\\', "/"));
            path = parent.parent();
        }
    }
    let mut visited = BTreeSet::new();
    let mut queue = vec![(String::new(), directory.try_clone().map_err(|_| refused())?)];
    let mut complete = true;
    while let Some((prefix, current)) = queue.pop() {
        if !plain(&current.dir_metadata().map_err(|_| refused())?, true) {
            return Err(refused());
        }
        for entry in current.entries().map_err(|_| refused())? {
            let entry = entry.map_err(|_| refused())?;
            let leaf = entry.file_name().into_string().map_err(|_| refused())?;
            let name = if prefix.is_empty() {
                leaf.clone()
            } else {
                format!("{prefix}/{leaf}")
            };
            if visited.len() >= 128 || !visited.insert(name.clone()) {
                return Err(refused());
            }
            let metadata = current.symlink_metadata(&leaf).map_err(|_| refused())?;
            if expected_dirs.contains(&name) {
                if !plain(&metadata, true) {
                    return Err(refused());
                }
                queue.push((
                    name,
                    current.open_dir_nofollow(&leaf).map_err(|_| refused())?,
                ));
            } else {
                let expected = plan.files.get(&name).ok_or_else(refused)?.as_ref();
                if !plain(&metadata, false) {
                    return Err(refused());
                }
                let file =
                    files::open_regular(&current, Path::new(&leaf)).map_err(|_| refused())?;
                if !plain(&file.metadata().map_err(|_| refused())?, false) {
                    return Err(refused());
                }
                let mut bytes = Vec::new();
                file.take(expected.len() as u64 + 1)
                    .read_to_end(&mut bytes)
                    .map_err(|_| refused())?;
                if !expected.starts_with(&bytes) {
                    return Err(refused());
                }
                complete &= bytes == expected;
            }
        }
    }
    complete &= visited.len() == expected_dirs.len() + plan.files.len();
    if !partial && !complete {
        return Err(refused());
    }
    Ok(complete)
}

fn existing<T: AsRef<[u8]>>(parent: &Dir, leaf: &Path, plan: &Tree<'_, T>) -> Result<bool> {
    match parent.symlink_metadata(leaf) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(_) => Err(refused()),
        Ok(metadata) if plain(&metadata, true) => {
            let directory = parent.open_dir_nofollow(leaf).map_err(|_| refused())?;
            verify(&directory, plan, false)
        }
        _ => Err(refused()),
    }
}

fn fill<T: AsRef<[u8]>>(directory: &Dir, plan: &Tree<'_, T>) -> Result<()> {
    verify(directory, plan, true)?;
    for (name, content) in plan.files {
        let content = content.as_ref();
        let parts: Vec<_> = name.split('/').collect();
        let (leaf, ancestors) = parts.split_last().ok_or_else(refused)?;
        let mut parents = vec![directory.try_clone().map_err(|_| refused())?];
        for part in ancestors {
            parents.push(mkdir(parents.last().ok_or_else(refused)?, part)?);
        }
        let parent = parents.last().ok_or_else(refused)?;
        let mut file = parent
            .open_with(leaf, private_options().read(true).create(true))
            .map_err(|_| refused())?;
        if !plain(&file.metadata().map_err(|_| refused())?, false) {
            return Err(refused());
        }
        let mut prefix = Vec::new();
        Read::by_ref(&mut file)
            .take(content.len() as u64 + 1)
            .read_to_end(&mut prefix)
            .map_err(|_| refused())?;
        if !content.starts_with(&prefix) {
            return Err(refused());
        }
        file.write_all(&content[prefix.len()..])
            .and_then(|_| file.sync_all())
            .map_err(|_| refused())?;
        for parent in parents.iter().rev() {
            sync(parent)?;
        }
    }
    verify(directory, plan, false)?;
    Ok(())
}

fn rename_new(stage: &Dir, parent: &Dir, leaf: &Path) -> Result<()> {
    #[cfg(any(target_os = "linux", target_os = "macos"))]
    rustix::fs::renameat_with(
        stage,
        "tree",
        parent,
        leaf,
        rustix::fs::RenameFlags::NOREPLACE,
    )
    .map_err(|_| refused())?;
    #[cfg(windows)]
    {
        // std::fs::rename can replace empty directories through its Windows
        // fallback. Call MoveFileExW with no replacement or copy fallback.
        let from =
            winx::file::get_file_path(&stage.try_clone().map_err(|_| refused())?.into_std_file())
                .map_err(|_| refused())?
                .join("tree");
        let to =
            winx::file::get_file_path(&parent.try_clone().map_err(|_| refused())?.into_std_file())
                .map_err(|_| refused())?
                .join(leaf);
        winsafe::MoveFileEx(
            from.to_str().ok_or_else(refused)?,
            Some(to.to_str().ok_or_else(refused)?),
            winsafe::co::MOVEFILE::WRITE_THROUGH,
        )
        .map_err(|_| refused())?;
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    return Err(refused());
    Ok(())
}

fn stage_name(purpose: &Purpose, digest: &str) -> String {
    format!(
        ".ai-stp-{}-{}",
        purpose.label(),
        digest.strip_prefix("sha256:").unwrap_or(digest)
    )
}

fn owner(purpose: &Purpose, digest: &str) -> Vec<u8> {
    format!("ai-stp-{}/1\n{digest}\n", purpose.label()).into_bytes()
}

fn clean(parent: &Dir, name: &str, stage: OwnedDirectory) {
    // Never recursively remove a stage: an unknown entry preserves the whole tree.
    if stage.directory.entries().is_ok_and(|mut entries| {
        entries.all(|e| e.is_ok_and(|e| matches!(e.file_name().to_str(), Some("owner" | "lock"))))
    }) {
        if stage.directory.remove_file("lock").is_ok() {
            let _ = stage.directory.remove_file("owner");
        }
        drop(stage);
        let _ = parent.remove_dir(name);
        let _ = sync(parent);
    }
}

fn outcome(parent: &Dir, name: &str, created: bool) -> (bool, bool) {
    let removed = parent
        .symlink_metadata(name)
        .is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound);
    (created, !removed)
}

pub(crate) fn publish<T: AsRef<[u8]>>(plan: &Tree<'_, T>, digest: &str) -> Result<(bool, bool)> {
    let output = Path::new(plan.output);
    if destination(output)? != (plan.output.to_owned(), plan.parent_identity.clone()) {
        return Err(refused());
    }
    let root = output.parent().ok_or_else(refused)?;
    let leaf = PathBuf::from(output.file_name().ok_or_else(refused)?);
    let parent =
        Dir::open_ambient_dir(root, cap_std::ambient_authority()).map_err(|_| refused())?;
    if &identity(&parent.dir_metadata().map_err(|_| refused())?) != plan.parent_identity {
        return Err(refused());
    }
    let name = stage_name(&plan.purpose, digest);
    if existing(&parent, &leaf, plan)? {
        if let Ok(Some(stage)) =
            OwnedDirectory::open_at(&parent, &name, &owner(&plan.purpose, digest), false)
        {
            clean(&parent, &name, stage);
        }
        let _ = parent.remove_dir(&name);
        return Ok(outcome(&parent, &name, false));
    }
    let stage = match OwnedDirectory::open_at(&parent, &name, &owner(&plan.purpose, digest), true) {
        Ok(Some(stage)) => stage,
        result => {
            // A concurrent replay can remove its stage while this caller waits
            // for the old lock. The verified final bytes decide the outcome.
            if existing(&parent, &leaf, plan)? {
                return Ok(outcome(&parent, &name, false));
            }
            return Err(result.err().unwrap_or_else(refused));
        }
    };
    if existing(&parent, &leaf, plan)? {
        clean(&parent, &name, stage);
        return Ok(outcome(&parent, &name, false));
    }
    for entry in stage.directory.entries().map_err(|_| refused())? {
        let entry = entry.map_err(|_| refused())?;
        if !matches!(entry.file_name().to_str(), Some("owner" | "lock" | "tree")) {
            return Err(refused());
        }
    }
    let directory = mkdir(&stage.directory, "tree")?;
    fill(&directory, plan)?;
    drop(directory);
    stage.sync()?;
    sync(&parent)?;
    if destination(output)? != (plan.output.to_owned(), plan.parent_identity.clone()) {
        return Err(refused());
    }
    rename_new(&stage.directory, &parent, &leaf)?;
    stage.sync()?;
    sync(&parent)?;
    clean(&parent, &name, stage);
    Ok(outcome(&parent, &name, true))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn final_publish_never_replaces_a_raced_destination()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let temporary = tempfile::tempdir()?;
        let parent = Dir::open_ambient_dir(temporary.path(), cap_std::ambient_authority())?;
        let stage = mkdir(&parent, "stage")?;
        mkdir(&stage, "tree")?;
        mkdir(&parent, "destination")?;
        assert!(rename_new(&stage, &parent, Path::new("destination")).is_err());
        parent.remove_dir("destination")?;
        parent.write("destination", b"keep")?;
        assert!(rename_new(&stage, &parent, Path::new("destination")).is_err());
        assert_eq!(parent.read("destination")?, b"keep");
        assert!(stage.is_dir("tree"));
        Ok(())
    }
}
