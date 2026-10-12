//! User-installed executables are observations, never caller-supplied versions.

use std::path::{Path, PathBuf};

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{Identity, Selector, Target, invalid};
use crate::{
    error::{Failure, Result},
    files,
};

#[derive(Clone, Serialize)]
#[serde(transparent)]
pub(super) struct Executable(#[serde(serialize_with = "files::serialize_path")] pub PathBuf);

impl<'de> Deserialize<'de> for Executable {
    fn deserialize<D: serde::Deserializer<'de>>(
        deserializer: D,
    ) -> std::result::Result<Self, D::Error> {
        let value = Value::deserialize(deserializer)?;
        if let Value::String(path) = value {
            Ok(Self(path.into()))
        } else {
            files::deserialize_path(value)
                .map(Self)
                .map_err(serde::de::Error::custom)
        }
    }
}

impl Selector {
    pub(super) fn observe(
        &self,
        connection: &Connection,
        parent: &Path,
        identity: &Identity,
    ) -> Result<(Target, Option<String>)> {
        let mut target = self.target(identity)?;
        let _ = (connection, parent);
        let report = crate::program::observe(
            &self.harness_id,
            self.harness_executable
                .as_ref()
                .map(|executable| executable.0.as_path()),
        )?;
        target.harness_version = report["version"].as_str().unwrap_or("").into();
        target.validate()?;
        let digest = Some(
            report["observation_digest"]
                .as_str()
                .ok_or_else(invalid)?
                .into(),
        );
        Ok((target, digest))
    }
}

pub(super) fn matches(current: &Option<String>, expected: &Option<String>) -> Result<()> {
    if current != expected {
        return Err(Failure::precondition(
            "the installed program changed since planning; create a new plan",
        ));
    }
    Ok(())
}

pub(super) fn unobserved(version_missing: bool) -> Vec<&'static str> {
    let mut fields = vec!["project_capabilities", "cloud_trust", "cloud_grants"];
    if version_missing {
        fields.insert(0, "harness_version");
    }
    fields
}
