//! Observe consumer processes without retaining arguments, environment or secrets.

use cap_std::fs::Dir;
use std::{
    collections::BTreeMap,
    fs,
    io::{BufRead, BufReader, Read},
    os::unix::{ffi::OsStrExt, fs::MetadataExt},
    path::{Path, PathBuf},
};
use zeroize::Zeroizing;

#[cfg(test)]
#[path = "activation_tests.rs"]
mod tests;

use super::{Plan, roots};
use crate::{
    error::{ErrorKind, Failure, Result},
    harnesses,
    provider::{
        configuration::activation::{Handoff, Moment, Session},
        runtime::target::Target,
    },
};

fn invalid() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the active consumer boundary could not be observed; configuration activation remains pending",
    )
}
fn read(path: &Path, limit: usize) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    let failure = || {
        invalid().with_details([(
            "stage".into(),
            path.file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("process_read")
                .into(),
        )])
    };
    fs::File::open(path)
        .map_err(|_| failure())?
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| failure())?;
    if bytes.len() > limit {
        return Err(invalid());
    }
    Ok(bytes)
}
fn boot() -> Result<String> {
    let bytes = read(Path::new("/proc/sys/kernel/random/boot_id"), 64)?;
    Ok(std::str::from_utf8(&bytes)
        .map_err(|_| invalid())?
        .trim()
        .into())
}

fn entrypoint(path: &Path, count: usize) -> Result<Zeroizing<Vec<u8>>> {
    let file = fs::File::open(path).map_err(|_| invalid())?;
    let mut reader = BufReader::new(file.take(8193));
    let mut value = Zeroizing::new(Vec::new());
    for _ in 0..count {
        reader.read_until(0, &mut value).map_err(|_| invalid())?;
    }
    if value.len() > 8192 {
        return Err(invalid());
    }
    Ok(value)
}

struct Process {
    parent: u32,
    started: u64,
    command: String,
}
fn process(pid: u32) -> Result<Option<Process>> {
    let path = PathBuf::from(format!("/proc/{pid}"));
    match fs::metadata(&path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Ok(metadata) if metadata.uid() != rustix::process::getuid().as_raw() => return Ok(None),
        Err(_) => return Err(invalid()),
        _ => (),
    }
    let bytes = match read(&path.join("stat"), 4096) {
        Ok(bytes) => bytes,
        Err(_) if !path.exists() => return Ok(None),
        Err(error) => return Err(error),
    };
    let value = std::str::from_utf8(&bytes).map_err(|_| invalid())?;
    let (head, fields) = value.rsplit_once(") ").ok_or_else(invalid)?;
    let (_, command) = head.split_once(" (").ok_or_else(invalid)?;
    let fields: Vec<_> = fields.split_ascii_whitespace().collect();
    if matches!(fields.first().copied(), Some("Z" | "X")) {
        return Ok(None);
    }
    Ok(Some(Process {
        command: command.into(),
        parent: fields
            .get(1)
            .ok_or_else(invalid)?
            .parse()
            .map_err(|_| invalid())?,
        started: fields
            .get(19)
            .ok_or_else(invalid)?
            .parse()
            .map_err(|_| invalid())?,
    }))
}

fn matches(
    definition: &harnesses::Definition,
    process: &Process,
    executable: &Path,
    arguments: &[u8],
) -> bool {
    let named = |name: &str| {
        definition.executable.as_deref() == Some(name)
            || definition
                .executable_aliases
                .iter()
                .any(|value| value == name)
    };
    if named(&process.command)
        || executable
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(named)
    {
        return true;
    }
    // Node/Bun launchers retain the declared package entrypoint in their first
    // two arguments. Never inspect prompts or persist arbitrary command lines.
    arguments.split(|byte| *byte == 0).take(2).any(|part| {
        let path = Path::new(std::ffi::OsStr::from_bytes(part));
        path.file_name()
            .and_then(|name| name.to_str())
            .is_some_and(named)
            || definition.npm_packages.iter().any(|package| {
                std::str::from_utf8(part)
                    .is_ok_and(|value| value.contains(&format!("/node_modules/{package}/")))
            })
    })
}

fn context(pid: u32, definition: &harnesses::Definition) -> Result<Vec<PathBuf>> {
    let root = PathBuf::from(format!("/proc/{pid}"));
    let environment = Zeroizing::new(read(&root.join("environ"), 1024 * 1024)?);
    let allowed = [
        Some("HOME"),
        Some("XDG_CONFIG_HOME"),
        definition.root_override.as_deref(),
    ];
    let mut values = BTreeMap::new();
    for entry in environment.split(|byte| *byte == 0) {
        let Some(index) = entry.iter().position(|byte| *byte == b'=') else {
            continue;
        };
        if let Ok(name) = std::str::from_utf8(&entry[..index])
            && allowed.contains(&Some(name))
        {
            let path = PathBuf::from(std::ffi::OsStr::from_bytes(&entry[index + 1..]));
            if !path.as_os_str().is_empty() {
                if !path.is_absolute() || path.as_os_str().len() > 4096 {
                    return Err(invalid());
                }
                values.insert(name.to_owned(), path);
            }
        }
    }
    let home = values
        .get("HOME")
        .ok_or_else(|| invalid().with_details([("stage".into(), "consumer_home".into())]))?;
    let xdg = values
        .get("XDG_CONFIG_HOME")
        .cloned()
        .unwrap_or_else(|| home.join(".config"));
    let mut paths = vec![
        home.join(".agents"),
        fs::read_link(root.join("cwd")).map_err(|_| invalid())?,
    ];
    if let Some(path) = definition
        .root_override
        .as_ref()
        .and_then(|key| values.get(key))
    {
        paths.push(path.clone());
    } else if let Some(path) = &definition.config_root {
        paths.push(if definition.xdg_config {
            xdg.join(path)
        } else {
            home.join(path)
        });
    }
    if let Some(path) = &definition.xdg_config_root {
        paths.push(xdg.join(path));
    }
    Ok(paths)
}

fn overlaps(paths: &[PathBuf], targets: &[Target]) -> Result<bool> {
    for path in paths {
        match Dir::open_ambient_dir(path, cap_std::ambient_authority()) {
            Ok(directory)
                if targets
                    .iter()
                    .any(|target| target.disjoint(&directory).is_err()) =>
            {
                return Ok(true);
            }
            Ok(_) => (),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
            Err(_) => return Err(invalid()),
        }
    }
    Ok(false)
}

fn observe(plan: &Plan) -> Result<Vec<Session>> {
    let targets = roots(plan, false)?;
    let boot_id = boot()?;
    let mut sessions = Vec::new();
    for entry in fs::read_dir("/proc").map_err(|_| invalid())? {
        let entry = entry.map_err(|_| invalid())?;
        let Some(pid) = entry
            .file_name()
            .to_str()
            .and_then(|name| name.parse::<u32>().ok())
        else {
            continue;
        };
        if pid <= 1 {
            continue;
        }
        let Some(before) = process(pid)? else {
            continue;
        };
        if !matches!(before.command.as_str(), "node" | "bun" | "deno")
            && !harnesses::definitions()?.iter().any(|definition| {
                definition.executable.as_deref() == Some(before.command.as_str())
                    || definition.executable_aliases.contains(&before.command)
            })
        {
            continue;
        }
        let root = entry.path();
        let observed = (|| {
            let executable = fs::read_link(root.join("exe")).map_err(|_| invalid())?;
            let wrapper = matches!(
                executable.file_name().and_then(|name| name.to_str()),
                Some("node" | "bun" | "deno")
            );
            let arguments = entrypoint(&root.join("cmdline"), if wrapper { 3 } else { 2 })?;
            for definition in harnesses::definitions()? {
                // The catalog's short version query never creates an agent
                // session and intentionally inherits no harness root settings.
                if definition.version_arguments.len() == 1
                    && arguments
                        .split(|byte| *byte == 0)
                        .nth(if wrapper { 2 } else { 1 })
                        == Some(definition.version_arguments[0].as_bytes())
                {
                    continue;
                }
                if matches(definition, &before, &executable, &arguments)
                    && overlaps(&context(pid, definition)?, &targets)?
                {
                    return Ok(Some(Session {
                        pid,
                        started: before.started,
                        harness_id: definition.harness_id.clone(),
                        boot_id: boot_id.clone(),
                    }));
                }
            }
            Ok(None)
        })();
        let Some(after) = process(pid)? else {
            continue;
        };
        if before.started != after.started {
            return Err(invalid());
        }
        if let Some(session) = observed? {
            sessions.push(session);
        }
        if sessions.len() > 256 {
            return Err(invalid());
        }
    }
    sessions.sort_by_key(|session| session.pid);
    Ok(sessions)
}

pub(super) fn sessions(plan: &Plan) -> Result<Vec<Session>> {
    for attempt in 0..3 {
        match observe(plan) {
            Err(error) if matches!(error.kind, ErrorKind::Unavailable) && attempt < 2 => {
                // A process can disappear between stat, exe and environ reads.
                // Retry the entire read-only observation; never infer quiescence
                // from an unreadable process that remains present.
                std::thread::sleep(std::time::Duration::from_millis(20));
            }
            result => return result,
        }
    }
    Err(invalid())
}

pub(super) fn prepare(plan: &Plan) -> Result<Handoff> {
    let handoff = Handoff {
        sessions: sessions(plan)?,
        published: None,
        confirmed: None,
    };
    handoff.validate()?;
    Ok(handoff)
}

pub(super) fn idle(plan: &Plan, handoff: &Handoff) -> Result<()> {
    handoff.validate()?;
    let current_boot = boot()?;
    for session in &handoff.sessions {
        if session.boot_id == current_boot
            && process(session.pid)?.is_some_and(|held| held.started == session.started)
        {
            return Err(Failure::precondition(
                "configuration is staged; finish the original harness session before activation",
            ));
        }
    }
    if !sessions(plan)?.is_empty() {
        return Err(Failure::precondition(
            "a harness is using an activation root; finish that session before continuing",
        ));
    }
    Ok(())
}

pub(super) fn published() -> Result<Moment> {
    let bytes = read(Path::new("/proc/uptime"), 128)?;
    let value = std::str::from_utf8(&bytes)
        .map_err(|_| invalid())?
        .split_ascii_whitespace()
        .next()
        .ok_or_else(invalid)?;
    let (seconds, fraction) = value.split_once('.').ok_or_else(invalid)?;
    let hz = rustix::param::clock_ticks_per_second();
    let seconds: u64 = seconds.parse().map_err(|_| invalid())?;
    let scale = 10u64
        .checked_pow(fraction.len().try_into().map_err(|_| invalid())?)
        .ok_or_else(invalid)?;
    let fraction: u64 = fraction.parse().map_err(|_| invalid())?;
    let ticks = seconds
        .checked_mul(hz)
        .and_then(|whole| {
            fraction
                .checked_mul(hz)
                .and_then(|part| whole.checked_add(part.div_ceil(scale)))
        })
        .ok_or_else(invalid)?;
    Ok(Moment {
        boot_id: boot()?,
        ticks,
    })
}

pub(super) fn confirm(plan: &Plan, handoff: &Handoff) -> Result<Session> {
    let publication = handoff.published.as_ref().ok_or_else(invalid)?;
    let current = sessions(plan)?;
    let first = plan.first()?;
    let targets = roots(plan, false)?;
    let mut pid = std::process::id();
    for _ in 0..128 {
        let Some(process) = process(pid)? else {
            break;
        };
        if let Some(session) = current.iter().find(|session| {
            session.pid == pid
                && session.started == process.started
                && session.harness_id == first.harness_id
        }) && !handoff.sessions.contains(session)
            && (session.boot_id != publication.boot_id || session.started > publication.ticks)
        {
            let paths = context(pid, harnesses::definition(&session.harness_id)?)?;
            for target in &targets {
                if !overlaps(&paths, std::slice::from_ref(target))? {
                    return Err(invalid());
                }
            }
            return Ok(session.clone());
        }
        if process.parent <= 1 {
            break;
        }
        pid = process.parent;
    }
    Err(Failure::precondition(
        "confirmation must be called by a new harness session after verified configuration publication",
    ))
}
