//! The exact setup-component release selected by this ai-stp build.

use crate::error::{Failure, Result};
use serde_json::Value;

/// Updating this pin requires all seven authenticated component journeys.
/// It is a selection default, never publisher authority or an apply-time upgrade.
pub const RELEASE: &str = "0.0.88";

pub fn version(explicit: Option<&str>) -> Result<&str> {
    let version = explicit.unwrap_or(RELEASE);
    sequence(version)?;
    Ok(version)
}

/// One canonical version and rollback sequence for all request boundaries.
pub(crate) fn sequence(version: &str) -> Result<u64> {
    let invalid = || {
        Failure::input(
            "a setup-component release requires canonical X.Y.Z with minor and patch below 1000",
        )
    };
    if version.len() > 32 {
        return Err(invalid());
    }
    let numbers = version
        .split('.')
        .map(|part| {
            part.parse::<u32>()
                .ok()
                .filter(|n| n.to_string() == part)
                .ok_or_else(invalid)
        })
        .collect::<Result<Vec<_>>>()?;
    let [major, minor, patch] = numbers.as_slice() else {
        return Err(invalid());
    };
    if *minor >= 1000 || *patch >= 1000 {
        return Err(invalid());
    }
    Ok(u64::from(*major) * 1_000_000 + u64::from(*minor) * 1000 + u64::from(*patch))
}

/// Resolve only a new request. Stored plans and receipts must carry their
/// original exact release and must never acquire a default during replay.
pub(crate) fn resolve_request(value: &mut Value) {
    if let Some(fields) = value.as_object_mut() {
        fields
            .entry("provider_version")
            .or_insert_with(|| RELEASE.into());
    }
}
