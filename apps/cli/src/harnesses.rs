//! Shared declarative harness facts; discovery does not grant provider authority.

use std::{collections::BTreeSet, sync::OnceLock};

use serde::{Deserialize, Serialize};

use crate::error::{ErrorKind, Failure, Result};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Scope {
    Global,
    Project,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Root {
    Config,
    Home,
    CursorConfig,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Shape {
    File,
    Directory,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Layout {
    pub component_type: String,
    pub relative: String,
    pub shape: Shape,
    pub source: String,
    pub scope: Scope,
    pub root: Root,
    pub evidence: String,
    pub excluded_names: BTreeSet<String>,
    pub projection_kind: String,
    pub declared_key: String,
    pub excludes_plugin_manifest: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Definition {
    pub harness_id: String,
    pub title: String,
    pub executable: Option<String>,
    pub version_arguments: Vec<String>,
    pub config_root: Option<String>,
    pub source: String,
    pub layouts: Vec<Layout>,
    pub native_authoring: BTreeSet<String>,
    pub gaps: Vec<String>,
    pub xdg_config: bool,
    pub xdg_config_root: Option<String>,
    pub root_override: Option<String>,
    pub npm_packages: Vec<String>,
    pub scoop_app: Option<String>,
    pub executable_aliases: Vec<String>,
    pub state_paths: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    schema_version: u32,
    harnesses: Vec<Definition>,
}

pub fn definitions() -> Result<&'static [Definition]> {
    static CATALOG: OnceLock<std::result::Result<Catalog, serde_json::Error>> = OnceLock::new();
    let catalog = CATALOG
        .get_or_init(|| {
            serde_json::from_str(include_str!(
                "../../../packages/foundation/src/ai_stp_foundation/harness_catalog.json"
            ))
        })
        .as_ref()
        .map_err(|_| {
            Failure::new(
                ErrorKind::Internal,
                "the bundled harness catalog is invalid",
            )
        })?;
    if catalog.schema_version != 1 {
        return Err(Failure::new(
            ErrorKind::Internal,
            "the bundled harness catalog version is unsupported",
        ));
    }
    Ok(&catalog.harnesses)
}

pub fn definition(id: &str) -> Result<&'static Definition> {
    definitions()?
        .iter()
        .find(|item| item.harness_id == id)
        .ok_or_else(|| Failure::input("the harness identifier is not supported"))
}
