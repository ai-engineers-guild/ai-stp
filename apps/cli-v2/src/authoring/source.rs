//! Capture one explicit component without links, hidden partial reads or writes.

use std::{
    collections::BTreeSet,
    env,
    ffi::OsString,
    io::Read,
    path::Path,
    time::{Duration, Instant},
};

use cap_fs_ext::DirExt;
use cap_std::fs::Dir;

use crate::{
    artifacts::{self, Member},
    error::{ErrorKind, Failure, Result},
    files, process, projects,
};

pub struct Captured {
    pub format: &'static str,
    pub bytes: Vec<u8>,
    pub file_mode: Option<u32>,
}

fn invalid() -> Failure {
    Failure::precondition("component source is unsafe, changed or exceeds its capture limits")
}

type SourceMember = (String, Option<u32>);

fn git_members(root: &Path, selected: Option<&str>) -> Result<Option<Vec<SourceMember>>> {
    let mut repository = false;
    for parent in root.ancestors() {
        match parent.join(".git").symlink_metadata() {
            Ok(_) => {
                repository = true;
                break;
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err(invalid()),
        }
    }
    if !repository {
        return Ok(None);
    }
    let name = if cfg!(windows) { "git.exe" } else { "git" };
    let executable = env::var_os("PATH")
        .and_then(|paths| {
            env::split_paths(&paths)
                .filter(|path| path.is_absolute())
                .map(|path| path.join(name))
                .find(|path| path.is_file())
        })
        .ok_or_else(|| {
            Failure::new(
                ErrorKind::Unavailable,
                "Git is required to capture this repository",
            )
        })?;
    let mut environment: Vec<_> = env::vars_os()
        .filter(|(key, _)| {
            key.to_str().is_some_and(|key| {
                [
                    "HOME",
                    "USERPROFILE",
                    "PATH",
                    "SYSTEMROOT",
                    "WINDIR",
                    "TEMP",
                    "TMP",
                    "XDG_CONFIG_HOME",
                ]
                .iter()
                .any(|allowed| key.eq_ignore_ascii_case(allowed))
            })
        })
        .collect();
    environment.extend([
        ("GIT_OPTIONAL_LOCKS".into(), "0".into()),
        ("GIT_TERMINAL_PROMPT".into(), "0".into()),
        ("LC_ALL".into(), "C".into()),
    ]);
    let arguments = [
        "--no-pager",
        "--literal-pathspecs",
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "ls-files",
        "-z",
        "--stage",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        selected.unwrap_or("."),
    ]
    .map(OsString::from);
    let output = process::run(process::Request {
        executable: &executable,
        arguments: &arguments,
        directory: root,
        environment: &environment,
        timeout: Duration::from_secs(10),
        output_limit: 2 * 1024 * 1024,
    })?;
    if !output.status.success() || (!output.stdout.is_empty() && !output.stdout.ends_with(&[0])) {
        return Err(Failure::precondition(
            "Git could not determine the complete component file set",
        ));
    }
    let mut names = BTreeSet::new();
    let mut members = Vec::new();
    for name in output
        .stdout
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
    {
        let record = std::str::from_utf8(name).map_err(|_| invalid())?;
        let (name, mode) = if let Some((header, name)) = record.split_once('\t') {
            let fields: Vec<_> = header.split(' ').collect();
            if fields.len() != 3 || fields[2] != "0" {
                return Err(invalid());
            }
            let mode = match fields[0] {
                "100644" => 0o644,
                "100755" => 0o755,
                _ => return Err(invalid()),
            };
            (name, Some(mode))
        } else {
            (record, None)
        };
        if !artifacts::safe_path(name)
            || !names.insert(name.to_owned())
            || names.len() > artifacts::MAX_FILES
        {
            return Err(invalid());
        }
        members.push((name.into(), mode));
    }
    Ok(Some(members))
}

fn check_name(path: &str) -> Result<()> {
    if !artifacts::safe_path(path)
        || path
            .split('/')
            .any(|part| projects::secret_name(part) || part.eq_ignore_ascii_case(".git"))
    {
        return Err(invalid());
    }
    Ok(())
}

fn read(directory: &Dir, path: &str) -> Result<Member> {
    check_name(path)?;
    read_member(directory, path)
}

// Ordinary callers validate the path with check_name. The guarded Claude MCP
// reader is the sole exception and supplies a fixed single filename.
fn read_member(directory: &Dir, path: &str) -> Result<Member> {
    // Walk every ancestor without following links, then inspect the actual file.
    let mut directory = directory.try_clone().map_err(|_| invalid())?;
    let mut parts = path.split('/').peekable();
    while let Some(part) = parts.next() {
        if parts.peek().is_some() {
            directory = directory.open_dir_nofollow(part).map_err(|_| invalid())?;
            continue;
        }
        let mut file = files::open_regular(&directory, Path::new(part)).map_err(|_| invalid())?;
        let before = file.metadata().map_err(|_| invalid())?;
        if before.len() > artifacts::MAX_FILE_BYTES as u64
            || cap_fs_ext::MetadataExt::nlink(&before) != 1
        {
            return Err(invalid());
        }
        #[cfg(unix)]
        let mode = {
            use cap_std::fs::MetadataExt;
            if before.mode() & 0o111 != 0 {
                0o755
            } else {
                0o644
            }
        };
        #[cfg(windows)]
        let mode = {
            use cap_std::fs::MetadataExt;
            if before.file_attributes() & 0x400 != 0 {
                return Err(invalid());
            }
            0o644
        };
        let mut bytes = Vec::new();
        file.by_ref()
            .take(artifacts::MAX_FILE_BYTES as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| invalid())?;
        let after = file.metadata().map_err(|_| invalid())?;
        if bytes.len() as u64 != before.len()
            || before.len() != after.len()
            || cap_fs_ext::MetadataExt::nlink(&after) != 1
            || before.modified().map_err(|_| invalid())?
                != after.modified().map_err(|_| invalid())?
        {
            return Err(invalid());
        }
        return Ok(Member {
            path: path.into(),
            bytes,
            mode,
        });
    }
    Err(invalid())
}

fn walk(
    directory: &Dir,
    base: &str,
    names: &mut Vec<String>,
    entries: &mut usize,
    started: Instant,
) -> Result<()> {
    if base.split('/').count() > 32 || started.elapsed() > Duration::from_secs(10) {
        return Err(invalid());
    }
    for entry in directory.entries().map_err(|_| invalid())? {
        *entries += 1;
        if *entries > 4000 || names.len() >= artifacts::MAX_FILES {
            return Err(invalid());
        }
        let entry = entry.map_err(|_| invalid())?;
        let name = entry.file_name().into_string().map_err(|_| invalid())?;
        let path = if base.is_empty() {
            name.clone()
        } else {
            format!("{base}/{name}")
        };
        check_name(&path)?;
        let metadata = entry.metadata().map_err(|_| invalid())?;
        if metadata.is_dir() && !metadata.file_type().is_symlink() {
            walk(
                &directory.open_dir_nofollow(&name).map_err(|_| invalid())?,
                &path,
                names,
                entries,
                started,
            )?;
        } else if metadata.is_file() && !metadata.file_type().is_symlink() {
            names.push(path);
        } else {
            return Err(invalid());
        }
    }
    Ok(())
}

fn open_directory(root: &Path) -> Result<Dir> {
    let parent = root.parent().ok_or_else(invalid)?;
    let directory =
        Dir::open_ambient_dir(parent, cap_std::ambient_authority()).map_err(|_| invalid())?;
    directory
        .open_dir_nofollow(root.file_name().ok_or_else(invalid)?)
        .map_err(|_| invalid())
}

fn same_directory(root: &Path, directory: &Dir) -> Result<()> {
    let held = directory.dir_metadata().map_err(|_| invalid())?;
    let current = open_directory(root)?
        .dir_metadata()
        .map_err(|_| invalid())?;
    if cap_fs_ext::MetadataExt::dev(&held) != cap_fs_ext::MetadataExt::dev(&current)
        || cap_fs_ext::MetadataExt::ino(&held) != cap_fs_ext::MetadataExt::ino(&current)
    {
        return Err(invalid());
    }
    Ok(())
}

fn tree(root: &Path, directory: &Dir, require_manifest: bool) -> Result<Vec<Member>> {
    let started = Instant::now();
    same_directory(root, directory)?;
    let names = match git_members(root, None)? {
        Some(names) => names,
        None => {
            let mut names = Vec::new();
            walk(directory, "", &mut names, &mut 0, Instant::now())?;
            names.into_iter().map(|name| (name, None)).collect()
        }
    };
    if require_manifest
        && !names.iter().any(|(name, _)| {
            [
                "SKILL.md",
                "AGENTS.md",
                "plugin.json",
                ".claude-plugin/plugin.json",
                ".codex-plugin/plugin.json",
                ".cursor-plugin/plugin.json",
                "hooks.json",
                "package.json",
                "pyproject.toml",
            ]
            .contains(&name.as_str())
        })
    {
        return Err(Failure::precondition(
            "the component directory has no supported manifest",
        ));
    }
    let mut total = 0;
    let mut members = Vec::new();
    for (name, git_mode) in names {
        if started.elapsed() > Duration::from_secs(10) {
            return Err(invalid());
        }
        let mut member = read(directory, &name)?;
        if cfg!(windows)
            && let Some(mode) = git_mode
        {
            member.mode = mode;
        }
        total += member.bytes.len();
        if total > artifacts::MAX_TREE_BYTES {
            return Err(invalid());
        }
        members.push(member);
    }
    same_directory(root, directory)?;
    if started.elapsed() > Duration::from_secs(10) {
        return Err(invalid());
    }
    Ok(members)
}

pub fn capture(path: &Path) -> Result<Captured> {
    let metadata = path
        .symlink_metadata()
        .map_err(|_| Failure::new(ErrorKind::NotFound, "component source is absent"))?;
    if metadata.file_type().is_symlink() {
        return Err(invalid());
    }
    let absolute = path.canonicalize().map_err(|_| invalid())?;
    let parent = absolute.parent().ok_or_else(invalid)?;
    let name = absolute
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(invalid)?;
    let directory =
        Dir::open_ambient_dir(parent, cap_std::ambient_authority()).map_err(|_| invalid())?;
    capture_open(&directory, name, &absolute, true, true)
}

/// Authoring projects own metadata above source/, so no native manifest is implied.
pub(super) fn project(root: &Path) -> Result<Vec<Member>> {
    let metadata = root.symlink_metadata().map_err(|_| invalid())?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err(invalid());
    }
    let root = root.canonicalize().map_err(|_| invalid())?;
    if root.parent().is_none()
        || files::home()
            .and_then(|home| home.canonicalize().ok())
            .is_some_and(|home| home == root)
    {
        return Err(invalid());
    }
    tree(&root, &open_directory(&root)?, false)
}

/// Capture a catalog-selected source without following any layout ancestor link.
pub fn capture_scoped(root: &Path, relative: &str) -> Result<Captured> {
    capture_scoped_with(root, relative, true, true)
}

/// External snapshots select exactly one file or tree, without native siblings.
pub(crate) fn capture_external(root: &Path, relative: &str) -> Result<Captured> {
    capture_scoped_with(root, relative, false, false)
}

/// A discovered project MCP file is read only for subsequent data-only validation.
/// This exception never applies to generic file/tree capture or another filename.
pub(super) fn capture_claude_mcp(root: &Path) -> Result<Captured> {
    let metadata = root.symlink_metadata().map_err(|_| invalid())?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err(invalid());
    }
    let root = root.canonicalize().map_err(|_| invalid())?;
    let directory = open_directory(&root)?;
    let member = file_member(&directory, ".mcp.json", &root.join(".mcp.json"))?;
    same_directory(&root, &directory)?;
    Ok(Captured {
        format: artifacts::FILE_FORMAT,
        bytes: member.bytes,
        file_mode: Some(member.mode),
    })
}

/// A declared native Markdown directory is defined by its executable entries.
/// The caller must validate those names before storing the bounded capture.
pub(super) fn capture_native_entries(root: &Path, relative: &str) -> Result<Captured> {
    capture_scoped_with(root, relative, false, true)
}

/// Namespace manifests above the selected component are context, not payload.
/// Inspect only their presence within the explicit root, without following links.
pub(super) fn reject_plugin_ancestors(root: &Path, relative: &str, markers: &[&str]) -> Result<()> {
    check_name(relative)?;
    let mut directory = open_directory(root)?;
    let mut parts = relative.split('/');
    loop {
        for marker in markers {
            match directory.symlink_metadata(marker) {
                Ok(_) => {
                    let plugin = directory.open_dir_nofollow(marker).map_err(|_| invalid())?;
                    match plugin.symlink_metadata("plugin.json") {
                        Ok(_) => {
                            return Err(Failure::precondition(
                                "namespaced skills require a plugin adaptation",
                            ));
                        }
                        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                        Err(_) => return Err(invalid()),
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(_) => return Err(invalid()),
            }
        }
        let Some(part) = parts.next() else {
            break;
        };
        let metadata = directory.symlink_metadata(part).map_err(|_| invalid())?;
        if metadata.is_file() && !metadata.file_type().is_symlink() {
            break;
        }
        directory = directory.open_dir_nofollow(part).map_err(|_| invalid())?;
    }
    Ok(())
}

fn capture_scoped_with(
    root: &Path,
    relative: &str,
    require_manifest: bool,
    include_hook_siblings: bool,
) -> Result<Captured> {
    check_name(relative)?;
    let root_metadata = root.symlink_metadata().map_err(|_| invalid())?;
    if !root_metadata.is_dir() || root_metadata.file_type().is_symlink() {
        return Err(invalid());
    }
    let root = root.canonicalize().map_err(|_| invalid())?;
    let mut directory = open_directory(&root)?;
    let mut parts = relative.split('/').peekable();
    while let Some(part) = parts.next() {
        if parts.peek().is_none() {
            return capture_open(
                &directory,
                part,
                &root.join(relative),
                require_manifest,
                include_hook_siblings,
            );
        }
        directory = directory.open_dir_nofollow(part).map_err(|_| invalid())?;
    }
    Err(invalid())
}

fn capture_open(
    directory: &Dir,
    name: &str,
    absolute: &Path,
    require_manifest: bool,
    include_hook_siblings: bool,
) -> Result<Captured> {
    check_name(name)?;
    let metadata = directory.symlink_metadata(name).map_err(|_| invalid())?;
    if metadata.file_type().is_symlink() {
        return Err(invalid());
    }
    if metadata.is_dir() {
        if files::home()
            .and_then(|home| home.canonicalize().ok())
            .is_some_and(|home| home == absolute)
        {
            return Err(invalid());
        }
        let child = directory.open_dir_nofollow(name).map_err(|_| invalid())?;
        let members = tree(absolute, &child, require_manifest)?;
        return Ok(Captured {
            format: artifacts::TREE_FORMAT,
            bytes: artifacts::encode_tree(&members)?,
            file_mode: None,
        });
    }
    if !metadata.is_file() {
        return Err(invalid());
    }
    let member = file_member(directory, name, absolute)?;
    if include_hook_siblings && name == "hooks.json" {
        match directory.symlink_metadata("hooks") {
            Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {
                let child = directory
                    .open_dir_nofollow("hooks")
                    .map_err(|_| invalid())?;
                let siblings = absolute.parent().ok_or_else(invalid)?.join("hooks");
                let mut members = vec![member];
                members.extend(
                    tree(&siblings, &child, false)?
                        .into_iter()
                        .map(|mut member| {
                            member.path = format!("hooks/{}", member.path);
                            member
                        }),
                );
                return Ok(Captured {
                    format: artifacts::TREE_FORMAT,
                    bytes: artifacts::encode_tree(&members)?,
                    file_mode: None,
                });
            }
            Ok(_) => return Err(invalid()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err(invalid()),
        }
    }
    Ok(Captured {
        format: artifacts::FILE_FORMAT,
        bytes: member.bytes,
        file_mode: Some(member.mode),
    })
}

fn file_member(directory: &Dir, name: &str, absolute: &Path) -> Result<Member> {
    let mut member = read_member(directory, name)?;
    if cfg!(windows)
        && let Some(mode) = git_members(absolute.parent().ok_or_else(invalid)?, Some(name))?
            .into_iter()
            .flatten()
            .find(|(path, _)| path == name)
            .and_then(|(_, mode)| mode)
    {
        member.mode = mode;
    }
    Ok(member)
}
