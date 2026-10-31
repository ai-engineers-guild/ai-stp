//! Shared configuration surfaces; declarations alone confer no execution authority.

use crate::{
    artifacts, digest,
    error::{Failure, Result},
    projection::{self, Route, Scope},
};
use serde::Deserialize;
use serde_json::Value;
use std::{collections::BTreeSet, sync::OnceLock};

pub(crate) fn contains(value: &Value, item: &str) -> bool {
    value
        .as_array()
        .is_some_and(|items| items.iter().any(|value| value == item))
}

pub(crate) fn supports_profile(profile: &Value, adaptation: &Value) -> bool {
    let required = &adaptation["required_surface"];
    if required["profile_id"] != profile["profile_id"]
        || required["profile_digest"] != profile["digest"]
        || !required["bundle_format"]
            .as_str()
            .is_some_and(|name| contains(&profile["bundle_formats"], name))
        || !adaptation["provider_component_kind"]
            .as_str()
            .is_some_and(|name| contains(&profile["component_kinds"], name))
        || !adaptation["projection_kind"]
            .as_str()
            .is_some_and(|name| contains(&profile["projection_kinds"], name))
    {
        return false;
    }
    let Some(members) = adaptation["members"].as_array() else {
        return false;
    };
    let mut count = 0u64;
    let mut size = 0u64;
    for member in members {
        let Some(path) = member["path"].as_str() else {
            return false;
        };
        if !covers_path(profile, path) {
            return false;
        }
        if member["object_type"] == "file" {
            count += 1;
            let Some(next) = member["content_artifact"]["size_bytes"]
                .as_u64()
                .and_then(|value| size.checked_add(value))
            else {
                return false;
            };
            size = next;
        }
    }
    count <= profile["max_files"].as_u64().unwrap_or(0)
        && size <= profile["max_bytes"].as_u64().unwrap_or(0)
}

pub(crate) fn covers_path(profile: &Value, path: &str) -> bool {
    artifacts::safe_path(path)
        && profile["native_namespaces"]
            .as_array()
            .is_some_and(|namespaces| {
                namespaces
                    .iter()
                    .filter_map(Value::as_str)
                    .any(|namespace| {
                        path == namespace
                            || path
                                .strip_prefix(namespace)
                                .is_some_and(|tail| tail.starts_with('/'))
                    })
            })
}

pub(crate) fn validate_profile(value: &Value) -> Result<()> {
    let mut payload = value.clone();
    payload
        .as_object_mut()
        .ok_or_else(invalid)?
        .remove("digest");
    if value["digest"] != digest::canonical("ai-stp:provider-projection:v3", &payload)? {
        return Err(invalid());
    }
    for namespace in value["native_namespaces"].as_array().ok_or_else(invalid)? {
        if !namespace.as_str().is_some_and(artifacts::safe_path) {
            return Err(invalid());
        }
    }
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CapturedSurface {
    harness_id: String,
    target_scope: Scope,
    profile: Value,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    schema_version: u32,
    provider_version: String,
    profiles: Vec<CapturedSurface>,
}

fn invalid() -> Failure {
    Failure::precondition("the bundled configuration surface catalog is inconsistent")
}

fn load() -> Result<Catalog> {
    let catalog: Catalog =
        serde_json::from_str(include_str!("surfaces.json")).map_err(|_| invalid())?;
    if catalog.schema_version != 1 {
        return Err(invalid());
    }
    let mut scopes = BTreeSet::new();
    for surface in &catalog.profiles {
        projection::profile(&surface.harness_id, surface.target_scope)?;
        validate_profile(&surface.profile)?;
        if !scopes.insert((surface.harness_id.as_str(), surface.target_scope.as_str()))
            || !contains(&surface.profile["bundle_formats"], "ai-stp-bundle/2")
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

fn catalog() -> Result<&'static Catalog> {
    static CATALOG: OnceLock<Result<Catalog>> = OnceLock::new();
    CATALOG.get_or_init(load).as_ref().map_err(|_| invalid())
}

pub(crate) fn captured_release() -> Result<&'static str> {
    Ok(&catalog()?.provider_version)
}

pub(crate) fn profile(harness: &str, scope: Scope) -> Result<&'static Value> {
    catalog()?
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
    Ok(contains(&profile["component_kinds"], kind)
        && contains(&profile["projection_kinds"], &route.projection_kind)
        && covers_path(profile, &route.relative))
}

/// The common compiler sees a configuration surface, never an executable grant.
/// Legacy declarations and the fixed native engine share this one evaluator.
pub(crate) trait Surface {
    fn document(&self) -> &Value;
    fn profile(&self, scope: Scope) -> Option<&Value>;
    fn supports_platform(&self, os: &str, arch: &str) -> bool;
    fn identity_key(&self) -> &'static str;

    fn supports_target(&self, scope: Scope) -> bool {
        self.profile(scope).is_some()
    }

    fn supports_scope(&self, scope: Scope, adaptation: &Value) -> bool {
        if adaptation["scope"] != scope.as_str() {
            return false;
        }
        self.profile(scope)
            .is_some_and(|profile| supports_profile(profile, adaptation))
    }
}
