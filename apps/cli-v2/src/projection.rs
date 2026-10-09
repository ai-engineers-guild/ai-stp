//! Exact provider surfaces and target-relative ownership, independent of discovery.

pub mod artifact;

use std::{collections::BTreeSet, sync::OnceLock};

use serde::{Deserialize, Serialize};

use crate::{
    artifacts,
    error::{ErrorKind, Failure, Result},
    harnesses::{self, Root, Shape},
};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Scope {
    Global,
    UserRoot,
    Project,
}

impl Scope {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Global => "global",
            Self::UserRoot => "user_root",
            Self::Project => "project",
        }
    }
}

/// Select only the explicitly declared harness and scope, with no fallback.
pub fn adaptation<'a>(
    document: &'a serde_json::Value,
    harness: &str,
    scope: Scope,
) -> Option<(&'a serde_json::Value, &'a serde_json::Value)> {
    let adaptation = document["adaptations"]
        .as_array()?
        .iter()
        .find(|value| value["harness_id"] == harness)?;
    let selected = adaptation["scope_adaptations"]
        .as_array()?
        .iter()
        .find(|value| value["scope"] == scope.as_str())?;
    Some((adaptation, selected))
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Profile {
    pub harness_id: String,
    pub target_scope: Scope,
    pub profile_id: String,
    pub profile_digest: String,
    pub bundle_format: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Route {
    pub component_type: String,
    pub relative: String,
    pub shape: Shape,
    pub harness_id: String,
    pub source: String,
    pub root: Root,
    pub target_scope: Scope,
    pub excluded_names: BTreeSet<String>,
    pub projection_kind: String,
    pub declared_key: String,
    pub provider_kind: String,
    pub excludes_plugin_manifest: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    schema_version: u32,
    profiles: Vec<Profile>,
    routes: Vec<Route>,
}

fn catalog() -> Result<&'static Catalog> {
    static CATALOG: OnceLock<std::result::Result<Catalog, serde_json::Error>> = OnceLock::new();
    let catalog = CATALOG
        .get_or_init(|| {
            serde_json::from_str(include_str!(
                "../../../packages/foundation/src/ai_stp_foundation/provider_catalog.json"
            ))
        })
        .as_ref()
        .map_err(|_| {
            Failure::new(
                ErrorKind::Internal,
                "the bundled provider catalog is invalid",
            )
        })?;
    if catalog.schema_version != 1 {
        return Err(Failure::new(
            ErrorKind::Internal,
            "the bundled provider catalog version is unsupported",
        ));
    }
    Ok(catalog)
}

pub fn profiles() -> Result<&'static [Profile]> {
    Ok(&catalog()?.profiles)
}

pub fn routes() -> Result<&'static [Route]> {
    Ok(&catalog()?.routes)
}

pub fn profile(harness: &str, scope: Scope) -> Result<&'static Profile> {
    harnesses::definition(harness)?;
    profiles()?
        .iter()
        .find(|profile| profile.harness_id == harness && profile.target_scope == scope)
        .ok_or_else(|| {
            Failure::precondition("the harness has no provider profile for this target scope")
        })
}

pub fn route(kind: &str, harness: &str, scope: Scope) -> Result<Option<&'static Route>> {
    harnesses::definition(harness)?;
    let mut fallback = None;
    for route in routes()? {
        if route.harness_id != harness || route.component_type != kind {
            continue;
        }
        if route.target_scope == scope {
            return Ok(Some(route));
        }
        if scope == Scope::Global && route.target_scope == Scope::UserRoot && fallback.is_none() {
            fallback = Some(route);
        }
    }
    Ok(fallback)
}

pub fn claimed_paths(path: &str, hook: bool) -> Result<Vec<String>> {
    if !artifacts::safe_path(path) {
        return Err(Failure::input("the projection ownership path is invalid"));
    }
    let mut paths = vec![path.to_owned()];
    if hook && (path == "hooks.json" || path.ends_with("/hooks.json")) {
        paths.push(
            path.strip_suffix(".json")
                .ok_or_else(|| Failure::input("the hook manifest path is invalid"))?
                .to_owned(),
        );
    }
    Ok(paths)
}

pub fn covers(kind: &str, harness: &str, name: &str, scope: Scope) -> Result<Vec<String>> {
    if !name.is_empty() && (!artifacts::safe_path(name) || name.contains('/')) {
        return Err(Failure::input("the component source name is not portable"));
    }
    let Some(route) = route(kind, harness, scope)? else {
        return Ok(match (kind, name.is_empty()) {
            ("skill", false) => vec![format!("skills/{name}")],
            ("cli", false) => vec![format!("bin/{name}")],
            _ => Vec::new(),
        });
    };
    match route.shape {
        Shape::File => claimed_paths(&route.relative, kind == "hook"),
        Shape::Directory => {
            let path = if name.is_empty() {
                route.relative.clone()
            } else {
                format!("{}/{name}", route.relative)
            };
            claimed_paths(&path, false)
        }
    }
}
