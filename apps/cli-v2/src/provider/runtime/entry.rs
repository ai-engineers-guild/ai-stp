//! Verify the actual mounted target before any provider code can observe it.

use std::{ffi::OsString, os::unix::process::CommandExt, path::Path, process::Command};

use super::{prefix::Prefix, target::Target, unavailable};
use crate::error::Result;

pub const FLAG: &str = "--ai-stp-target-entry";
pub(super) const MISSING_PREFIX: &str = "--ai-stp-missing-prefix";
pub(super) const EMPTY_PREFIX: &str = "--ai-stp-empty-prefix";
pub(super) const WRITABLE_PREFIX: &str = "--ai-stp-writable-prefix";

pub fn run(arguments: &[OsString]) -> Result<()> {
    if arguments.len() < 5 {
        return Err(unavailable());
    }
    let number = |index: usize| {
        arguments[index]
            .to_str()
            .and_then(|s| s.parse::<u64>().ok())
            .ok_or_else(unavailable)
    };
    let count = number(0)?;
    if !(1..=2).contains(&count) || arguments.len() <= 1 + count as usize * 3 {
        return Err(unavailable());
    }
    let mut end = 1 + count as usize * 3;
    for index in (1..end).step_by(3) {
        let target = Target::open(Path::new(&arguments[index + 2]))?;
        target.verify_mount((number(index)?, number(index + 1)?))?;
    }
    if arguments.get(end).is_some_and(|arg| arg == WRITABLE_PREFIX) {
        if arguments.len() <= end + 4 {
            return Err(unavailable());
        }
        let root = Target::open(Path::new(&arguments[end + 3]))?;
        root.verify_writable_mount((number(end + 1)?, number(end + 2)?))?;
        let parent = Target::open(root.path().parent().ok_or_else(unavailable)?)?;
        parent.verify_mount(parent.identity()?)?;
        // This is the dedicated entry process, immediately before exec. Give
        // public vendor payloads deterministic directory modes; the component
        // explicitly creates its private metadata with stricter permissions.
        rustix::process::umask(rustix::fs::Mode::from_raw_mode(0o022));
        end += 4;
    } else if arguments
        .get(end)
        .is_some_and(|arg| arg == MISSING_PREFIX || arg == EMPTY_PREFIX)
    {
        if arguments.len() <= end + 2 {
            return Err(unavailable());
        }
        if arguments[end] == EMPTY_PREFIX {
            Prefix::verify_empty_mount(Path::new(&arguments[end + 1]))?;
        } else {
            Prefix::verify_missing_mount(Path::new(&arguments[end + 1]))?;
        }
        end += 2;
    }
    // The sealed provider was mounted by the launcher. There is no caller-chosen
    // executable path or interpreter, and the existing explicit environment stays.
    let _ = Command::new("/run/provider")
        .args(&arguments[end..])
        .stdin(std::process::Stdio::null())
        .exec();
    Err(unavailable())
}
