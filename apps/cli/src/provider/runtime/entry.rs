//! Verify the actual mounted target before any provider code can observe it.

use std::{ffi::OsString, os::unix::process::CommandExt, path::Path, process::Command};

use super::{target::Target, unavailable};
use crate::error::Result;

pub const FLAG: &str = "--ai-stp-target-entry";
pub(super) const WRITABLE_TARGET: &str = "--ai-stp-writable-target";

pub fn run(arguments: &[OsString]) -> Result<()> {
    let configuration = arguments
        .first()
        .is_some_and(|value| value == WRITABLE_TARGET);
    let arguments = if configuration {
        &arguments[1..]
    } else {
        arguments
    };
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
    if !(1..=2).contains(&count)
        || configuration && count != 1
        || arguments.len() <= 1 + count as usize * 3
    {
        return Err(unavailable());
    }
    let end = 1 + count as usize * 3;
    for index in (1..end).step_by(3) {
        let target = Target::open(Path::new(&arguments[index + 2]))?;
        if configuration {
            target.verify_writable_mount((number(index)?, number(index + 1)?))?;
        } else {
            target.verify_mount((number(index)?, number(index + 1)?))?;
        }
    }
    if configuration {
        if arguments
            .get(end)
            .is_none_or(|value| value != "apply-operation")
        {
            return Err(unavailable());
        }
        rustix::process::umask(rustix::fs::Mode::from_raw_mode(0o022));
    }
    // The sealed provider was mounted by the launcher. There is no caller-chosen
    // executable path or interpreter, and the existing explicit environment stays.
    let _ = Command::new("/run/provider")
        .args(&arguments[end..])
        .stdin(std::process::Stdio::null())
        .exec();
    Err(unavailable())
}
