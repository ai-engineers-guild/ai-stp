//! Native macOS/Windows process reads. Only selected paths reach the observer;
//! arguments and environment values are never returned or retained in history.

use super::{Session, Stamp, Target, unavailable};
use crate::{error::Result, harnesses};
use std::{
    collections::BTreeMap,
    ffi::OsStr,
    path::{Path, PathBuf},
};
use sysinfo::{Pid, Process, ProcessRefreshKind, ProcessesToUpdate, System, UpdateKind};

fn system() -> Result<System> {
    let mut system = System::new().map_err(|_| unavailable())?;
    let refreshed = system.refresh_processes_specifics(
        ProcessesToUpdate::All,
        true,
        ProcessRefreshKind::nothing()
            .without_tasks()
            .with_user(UpdateKind::Always)
            .with_exe(UpdateKind::Always),
    );
    if refreshed == 0
        || system
            .process(Pid::from_u32(std::process::id()))
            .and_then(Process::user_id)
            .is_none()
    {
        return Err(unavailable());
    }
    Ok(system)
}
#[cfg(target_os = "macos")]
fn present(pid: u32) -> Result<bool> {
    let pid = rustix::process::Pid::from_raw(i32::try_from(pid).map_err(|_| unavailable())?)
        .ok_or_else(unavailable)?;
    match rustix::process::test_kill_process(pid) {
        Ok(()) | Err(rustix::io::Errno::PERM) => Ok(true),
        Err(rustix::io::Errno::SRCH) => Ok(false),
        Err(_) => Err(unavailable()),
    }
}
#[cfg(target_os = "macos")]
pub(super) fn parent(pid: u32) -> Result<Option<(u32, Stamp)>> {
    let id = i32::try_from(pid).map_err(|_| unavailable())?;
    match libproc::proc_pid::pidinfo::<libproc::bsd_info::BSDInfo>(id, 0) {
        Ok(info) => {
            // Darwin SZOMB: the consumer has exited, even before its parent reaps it.
            if info.pbi_status == 5 {
                return Ok(None);
            }
            if info.pbi_uid != rustix::process::geteuid().as_raw() {
                return Err(unavailable());
            }
            let micros = u32::try_from(info.pbi_start_tvusec).map_err(|_| unavailable())?;
            let stamp = Stamp::Macos {
                seconds: info.pbi_start_tvsec.to_string(),
                microseconds: micros,
            };
            stamp.validate()?;
            Ok(Some((info.pbi_ppid, stamp)))
        }
        Err(_) if !present(pid)? => Ok(None),
        Err(_) => Err(unavailable()),
    }
}
#[cfg(windows)]
fn windows_stamp(pid: u32) -> Result<Option<Stamp>> {
    let process = match winsafe::HPROCESS::OpenProcess(
        winsafe::co::PROCESS::QUERY_LIMITED_INFORMATION,
        false,
        pid,
    ) {
        Ok(process) => process,
        Err(winsafe::co::ERROR::INVALID_PARAMETER) => return Ok(None),
        Err(_) => return Err(unavailable()),
    };
    let (created, exited, _, _) = process.GetProcessTimes().map_err(|_| unavailable())?;
    if u64::from(exited) != 0 {
        return Ok(None);
    }
    let stamp = Stamp::Windows {
        filetime: u64::from(created).to_string(),
    };
    stamp.validate()?;
    Ok(Some(stamp))
}
#[cfg(windows)]
pub(super) fn parent(pid: u32) -> Result<Option<(u32, Stamp)>> {
    let Some(stamp) = windows_stamp(pid)? else {
        return Ok(None);
    };
    let system = system()?;
    let own = system
        .process(Pid::from_u32(std::process::id()))
        .and_then(Process::user_id)
        .ok_or_else(unavailable)?;
    let process = system.process(Pid::from_u32(pid)).ok_or_else(unavailable)?;
    if process.user_id() != Some(own) {
        return Err(unavailable());
    }
    Ok(Some((process.parent().map_or(0, Pid::as_u32), stamp)))
}
fn stem(path: &Path) -> Option<&str> {
    path.file_stem()?.to_str()
}
fn named(definition: &harnesses::Definition, name: &str) -> bool {
    definition
        .executable
        .as_deref()
        .is_some_and(|v| v.eq_ignore_ascii_case(name))
        || definition
            .executable_aliases
            .iter()
            .any(|v| v.eq_ignore_ascii_case(name))
}
fn wrapper(process: &Process) -> bool {
    process
        .exe()
        .and_then(stem)
        .or_else(|| process.name().to_str())
        .is_some_and(|v| {
            ["node", "bun", "deno"]
                .iter()
                .any(|name| v.eq_ignore_ascii_case(name))
        })
}
fn matches(definition: &harnesses::Definition, process: &Process) -> bool {
    if process
        .exe()
        .and_then(stem)
        .is_some_and(|n| named(definition, n))
        || Path::new(process.name())
            .file_stem()
            .and_then(OsStr::to_str)
            .is_some_and(|n| named(definition, n))
    {
        return true;
    }
    process.cmd().iter().take(2).any(|argument| {
        let path = Path::new(argument);
        path.file_stem()
            .and_then(OsStr::to_str)
            .is_some_and(|n| named(definition, n))
            || argument.to_str().is_some_and(|value| {
                let value = value.replace('\\', "/");
                definition
                    .npm_packages
                    .iter()
                    .any(|package| value.contains(&format!("/node_modules/{package}/")))
            })
    })
}
fn contexts(process: &Process, definition: &harnesses::Definition) -> Result<Option<Vec<PathBuf>>> {
    let allowed = [
        Some("HOME"),
        if cfg!(windows) {
            Some("USERPROFILE")
        } else {
            None
        },
        Some("XDG_CONFIG_HOME"),
        definition.root_override.as_deref(),
    ];
    let mut values = BTreeMap::new();
    for entry in process.environ() {
        let Some(entry) = entry.to_str() else {
            return Err(unavailable());
        };
        let Some((name, value)) = entry.split_once('=') else {
            continue;
        };
        if allowed.contains(&Some(name)) && !value.is_empty() {
            let path = PathBuf::from(value);
            if !path.is_absolute() || value.len() > 8192 || values.insert(name, path).is_some() {
                return Err(unavailable());
            }
        }
    }
    // Unknown process roots cannot imply quiescence. Keep the identified live
    // consumer conservatively active until that session is finished.
    let Some(home) = values.get("USERPROFILE").or_else(|| values.get("HOME")) else {
        return Ok(None);
    };
    let mut paths = vec![home.join(".agents")];
    if let Some(cwd) = process.cwd() {
        paths.push(cwd.to_owned());
    } else {
        return Ok(None);
    }
    if let Some(root) = definition
        .root_override
        .as_ref()
        .and_then(|key| values.get(key.as_str()))
    {
        paths.push(root.clone());
    } else if let Some(root) = &definition.config_root {
        paths.push(if definition.xdg_config {
            values
                .get("XDG_CONFIG_HOME")
                .cloned()
                .unwrap_or_else(|| home.join(".config"))
                .join(root)
        } else {
            home.join(root)
        });
        #[cfg(windows)]
        if definition.xdg_config {
            paths.push(home.join("AppData/Roaming").join(root));
        }
    }
    if let Some(root) = &definition.xdg_config_root {
        paths.push(
            values
                .get("XDG_CONFIG_HOME")
                .cloned()
                .unwrap_or_else(|| home.join(".config"))
                .join(root),
        );
    }
    // Unresolved command-line configuration overrides are a reason to stage,
    // never proof that a candidate target is unused.
    if process
        .cmd()
        .iter()
        .skip(1)
        .filter_map(|a| a.to_str())
        .any(|a| {
            [
                "--config",
                "--settings",
                "--mcp-config",
                "--config-dir",
                "--cwd",
                "--directory",
                "-C",
            ]
            .iter()
            .any(|flag| a == *flag || a.starts_with(&format!("{flag}=")))
        })
    {
        return Ok(None);
    }
    Ok(Some(paths))
}
fn overlaps(paths: &[PathBuf], targets: &[&Target]) -> Result<bool> {
    for path in paths {
        match cap_std::fs::Dir::open_ambient_dir(path, cap_std::ambient_authority()) {
            Ok(directory) => {
                for target in targets {
                    let held = target.directory().map_err(|_| unavailable())?;
                    if crate::files::physical::require_disjoint(&held, &directory).is_err() {
                        return Ok(true);
                    }
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
            Err(_) => return Err(unavailable()),
        }
    }
    Ok(false)
}
fn attempt(targets: &[&Target]) -> Result<Vec<Session>> {
    let mut system = system()?;
    let own = system
        .process(Pid::from_u32(std::process::id()))
        .and_then(Process::user_id)
        .ok_or_else(unavailable)?
        .clone();
    let definitions = harnesses::definitions()?;
    let candidates = system
        .processes()
        .iter()
        .filter_map(|(pid, process)| {
            if pid.as_u32() <= 1 {
                return None;
            }
            let candidate = wrapper(process)
                || definitions.iter().any(|d| {
                    process.exe().and_then(stem).is_some_and(|n| named(d, n))
                        || Path::new(process.name())
                            .file_stem()
                            .and_then(OsStr::to_str)
                            .is_some_and(|n| named(d, n))
                });
            if candidate {
                Some((*pid, process.user_id().cloned()))
            } else {
                None
            }
        })
        .collect::<Vec<_>>();
    if candidates.len() > 4096 {
        return Err(unavailable());
    }
    let mut sessions = Vec::new();
    for (pid, user) in candidates {
        let user = user.ok_or_else(unavailable)?;
        if user != own {
            continue;
        }
        let Some((_, before)) = parent(pid.as_u32())? else {
            continue;
        };
        system.refresh_processes_specifics(
            ProcessesToUpdate::Some(&[pid]),
            true,
            ProcessRefreshKind::nothing()
                .without_tasks()
                .with_cmd(UpdateKind::Always)
                .with_cwd(UpdateKind::Always)
                .with_environ(UpdateKind::Always)
                .with_exe(UpdateKind::Always),
        );
        let observed = (|| {
            let process = system.process(pid).ok_or_else(unavailable)?;
            if process.cmd().is_empty() {
                return Err(unavailable());
            }
            for definition in definitions {
                if !matches(definition, process) {
                    continue;
                }
                let version_index = if wrapper(process) { 2 } else { 1 };
                if definition.version_arguments.len() == 1
                    && process.cmd().len() == version_index + 1
                    && process.cmd()[version_index].as_os_str()
                        == OsStr::new(&definition.version_arguments[0])
                {
                    continue;
                }
                let paths = contexts(process, definition)?;
                if paths
                    .as_ref()
                    .map(|paths| overlaps(paths, targets))
                    .transpose()?
                    .unwrap_or(true)
                {
                    return Ok(Some(Session {
                        pid: pid.as_u32(),
                        harness_id: definition.harness_id.clone(),
                        stamp: before.clone(),
                    }));
                }
            }
            Ok(None)
        })();
        let Some((_, after)) = parent(pid.as_u32())? else {
            continue;
        };
        if before != after {
            return Err(unavailable());
        }
        if let Some(session) = observed? {
            sessions.push(session);
        }
        if sessions.len() > 256 {
            return Err(unavailable());
        }
    }
    sessions.sort_by_key(|s| s.pid);
    Ok(sessions)
}
pub(super) fn observe(targets: &[&Target]) -> Result<Vec<Session>> {
    for retry in 0..3 {
        match attempt(targets) {
            Err(error)
                if matches!(error.kind, crate::error::ErrorKind::Unavailable) && retry < 2 =>
            {
                std::thread::sleep(std::time::Duration::from_millis(20))
            }
            result => return result,
        }
    }
    Err(unavailable())
}
pub(super) fn moment() -> Result<Stamp> {
    #[cfg(target_os = "macos")]
    {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|_| unavailable())?;
        Ok(Stamp::Macos {
            seconds: now.as_secs().to_string(),
            microseconds: now.subsec_micros(),
        })
    }
    #[cfg(windows)]
    {
        Ok(Stamp::Windows {
            filetime: u64::from(winsafe::GetSystemTimeAsFileTime()).to_string(),
        })
    }
}
