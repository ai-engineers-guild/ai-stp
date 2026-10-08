//! Capture one explicit component without links, hidden partial reads or writes.

use std::{
    collections::BTreeSet,
    env,
    ffi::OsString,
    io::Read,
    path::{Path, PathBuf},
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
}

fn invalid() -> Failure {
    Failure::precondition("component source is unsafe, changed or exceeds its capture limits")
}

type SourceMember = (String, Option<u32>);

fn git_members(root: &Path) -> Result<Option<Vec<SourceMember>>> {
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
        ".",
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

fn tree(root: &Path, require_manifest: bool) -> Result<Vec<Member>> {
    let directory = open_directory(root)?;
    let names = match git_members(root)? {
        Some(names) => names,
        None => {
            let mut names = Vec::new();
            walk(&directory, "", &mut names, &mut 0, Instant::now())?;
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
        let mut member = read(&directory, &name)?;
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
    check_name(
        absolute
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(invalid)?,
    )?;
    if metadata.is_dir() {
        if files::home()
            .and_then(|home| home.canonicalize().ok())
            .is_some_and(|home| home == absolute)
        {
            return Err(invalid());
        }
        let members = tree(&absolute, true)?;
        return Ok(Captured {
            format: artifacts::TREE_FORMAT,
            bytes: artifacts::encode_tree(&members)?,
        });
    }
    if !metadata.is_file() {
        return Err(invalid());
    }
    let parent = absolute.parent().ok_or_else(invalid)?;
    let name = absolute
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(invalid)?;
    let directory =
        Dir::open_ambient_dir(parent, cap_std::ambient_authority()).map_err(|_| invalid())?;
    let member = read(&directory, name)?;
    let siblings: PathBuf = parent.join("hooks");
    if name == "hooks.json" {
        match siblings.symlink_metadata() {
            Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {
                let mut members = vec![member];
                members.extend(tree(&siblings, false)?.into_iter().map(|mut member| {
                    member.path = format!("hooks/{}", member.path);
                    member
                }));
                return Ok(Captured {
                    format: artifacts::TREE_FORMAT,
                    bytes: artifacts::encode_tree(&members)?,
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
    })
}
