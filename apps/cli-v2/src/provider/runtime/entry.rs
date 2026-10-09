//! Verify the actual mounted target before any provider code can observe it.

use std::{ffi::OsString, os::unix::process::CommandExt, path::Path, process::Command};

use super::{target::Target, unavailable};
use crate::error::Result;

pub const FLAG: &str = "--ai-stp-target-entry";

pub fn run(arguments: &[OsString]) -> Result<()> {
    if arguments.len() < 4 {
        return Err(unavailable());
    }
    let number = |index: usize| {
        arguments[index]
            .to_str()
            .and_then(|s| s.parse::<u64>().ok())
            .ok_or_else(unavailable)
    };
    let target = Target::open(Path::new(&arguments[2]))?;
    target.verify_mount((number(0)?, number(1)?))?;
    drop(target);
    // The sealed provider was mounted by the launcher. There is no caller-chosen
    // executable path or interpreter, and the existing explicit environment stays.
    let _ = Command::new("/run/provider")
        .args(&arguments[3..])
        .stdin(std::process::Stdio::null())
        .exec();
    Err(unavailable())
}
