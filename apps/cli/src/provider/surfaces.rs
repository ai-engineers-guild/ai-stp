//! Offline authoring surfaces captured from the authenticated managed release.
//! The shared catalog retains historical profile anchors. Managed release
//! surfaces own the current authoring digests rather than rewriting anchors.

use std::{collections::BTreeSet, sync::OnceLock};

use serde::Deserialize;
use serde_json::Value;

use crate::{
    error::{Failure, Result},
    projection::{self, Route, Scope},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Surface {
    harness_id: String,
    target_scope: Scope,
    profile: Value,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    schema_version: u32,
    provider_version: String,
    profiles: Vec<Surface>,
}

fn invalid() -> Failure {
    Failure::precondition(
        "the bundled authoring surfaces do not match the managed component release",
    )
}

fn load() -> Result<Catalog> {
    let catalog: Catalog =
        serde_json::from_str(include_str!("surfaces.json")).map_err(|_| invalid())?;
    if catalog.schema_version != 1 || catalog.provider_version != super::managed::RELEASE {
        return Err(invalid());
    }
    let mut scopes = BTreeSet::new();
    for surface in &catalog.profiles {
        projection::profile(&surface.harness_id, surface.target_scope)?;
        super::profile(&surface.profile)?;
        if !scopes.insert((surface.harness_id.as_str(), surface.target_scope.as_str()))
            || !super::contains(&surface.profile["bundle_formats"], "ai-stp-bundle/2")
            || surface.profile["max_files"].as_u64().is_none_or(|n| n == 0)
            || surface.profile["max_bytes"].as_u64().is_none_or(|n| n == 0)
        {
            return Err(invalid());
        }
    }
    if scopes.len() != projection::profiles()?.len() {
        return Err(invalid());
    }
    Ok(catalog)
}

pub(crate) fn profile(harness: &str, scope: Scope) -> Result<&'static Value> {
    static CATALOG: OnceLock<Result<Catalog>> = OnceLock::new();
    CATALOG
        .get_or_init(load)
        .as_ref()
        .map_err(|_| invalid())?
        .profiles
        .iter()
        .find(|surface| surface.harness_id == harness && surface.target_scope == scope)
        .map(|surface| &surface.profile)
        .ok_or_else(invalid)
}

pub(crate) fn supports_route(route: &Route) -> Result<bool> {
    let profile = profile(&route.harness_id, route.target_scope)?;
    let kind = if route.provider_kind.is_empty() {
        &route.component_type
    } else {
        &route.provider_kind
    };
    Ok(super::contains(&profile["component_kinds"], kind)
        && super::contains(&profile["projection_kinds"], &route.projection_kind)
        && super::covers_path(profile, &route.relative))
}
