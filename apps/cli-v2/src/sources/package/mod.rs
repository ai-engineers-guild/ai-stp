//! Explicit registry/file selection. Source observations do not grant install authority.

mod crates;
mod go;
mod metadata;
mod npm;
mod pubdev;
mod pypi;
mod tarfiles;

use crate::error::{Failure, Result};
use serde_json::Value;

pub fn fetch(
    ecosystem: &str,
    name: &str,
    version: &str,
    filename: Option<&str>,
    platform: Option<&str>,
) -> Result<Value> {
    match ecosystem {
        "go" if filename.is_none() && platform.is_none() => go::fetch(name, version),
        "npm" if filename.is_none() && platform.is_none() => npm::fetch(name, version),
        "crates.io" if filename.is_none() && platform.is_none() => crates::fetch(name, version),
        "pub.dev" if filename.is_none() && platform.is_none() => pubdev::fetch(name, version),
        "pypi" => pypi::fetch(
            name,
            version,
            filename.ok_or_else(|| {
                Failure::input("PyPI source observation requires an exact filename")
            })?,
            platform.ok_or_else(|| {
                Failure::input("PyPI source observation requires an explicit platform")
            })?,
        ),
        _ => Err(Failure::input(
            "package source options do not match the selected ecosystem",
        )),
    }
}
