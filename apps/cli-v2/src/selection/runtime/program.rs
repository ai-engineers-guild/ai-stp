//! Explicit program prefixes are observations, never caller-supplied versions.

use std::path::{Path, PathBuf};

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{Identity, Selector, Target, invalid};
use crate::{
    error::{Failure, Result},
    files,
    provider::runtime,
};

#[derive(Clone, Serialize)]
#[serde(transparent)]
pub(super) struct Prefix(#[serde(serialize_with = "files::serialize_path")] pub PathBuf);

impl<'de> Deserialize<'de> for Prefix {
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
        let digest = if let Some(prefix) = &self.program_prefix {
            let report =
                runtime::program_observe_in(connection, parent, &self.harness_id, &prefix.0)?;
            if report["state"] != "verified" || report["program_observed"] != true {
                return Err(Failure::precondition(
                    "the explicit program prefix has no current verified installation",
                )
                .with_details([("program".into(), report)]));
            }
            target.harness_version = report["observation"]["software_version"]
                .as_str()
                .ok_or_else(invalid)?
                .into();
            target.validate()?;
            Some(
                report["observation_digest"]
                    .as_str()
                    .ok_or_else(invalid)?
                    .into(),
            )
        } else {
            None
        };
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
