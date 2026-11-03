//! Exact captured-release compatibility for legacy authoring callers.

use crate::{
    error::{Failure, Result},
    projection::{self, Route, Scope},
};
use serde_json::Value;

fn require_release() -> Result<()> {
    if projection::surfaces::captured_release()? != super::managed::RELEASE {
        return Err(Failure::precondition(
            "the bundled authoring surfaces do not match the managed component release",
        ));
    }
    Ok(())
}

pub(crate) fn profile(harness: &str, scope: Scope) -> Result<&'static Value> {
    require_release()?;
    projection::surfaces::profile(harness, scope)
}

pub(crate) fn supports_route(route: &Route) -> Result<bool> {
    require_release()?;
    projection::surfaces::supports_route(route)
}
