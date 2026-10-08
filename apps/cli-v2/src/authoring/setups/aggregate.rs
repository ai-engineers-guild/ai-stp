//! Conservative summaries of declarations; exact member passports remain authoritative.

use crate::error::{Failure, Result};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

pub(super) struct Aggregate {
    environment: BTreeMap<String, BTreeSet<String>>,
    credentials: bool,
    authorization: usize,
    permissions: BTreeMap<&'static str, BTreeSet<String>>,
    endpoints: BTreeSet<String>,
    runtimes: BTreeSet<String>,
    licenses: BTreeSet<String>,
    redistributable: bool,
}

impl Default for Aggregate {
    fn default() -> Self {
        Self {
            environment: BTreeMap::new(),
            credentials: false,
            authorization: 0,
            permissions: ["filesystem", "network", "process"]
                .into_iter()
                .map(|key| (key, BTreeSet::new()))
                .collect(),
            endpoints: BTreeSet::new(),
            runtimes: BTreeSet::new(),
            licenses: BTreeSet::new(),
            redistributable: true,
        }
    }
}

const AUTHORIZATION: [&str; 3] = ["none", "user_account", "external_service"];
fn invalid() -> Failure {
    Failure::precondition("a component requirement is invalid")
}
fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str> {
    value[field].as_str().ok_or_else(invalid)
}
fn extend(target: &mut BTreeSet<String>, value: &Value) -> Result<()> {
    if value.is_null() {
        return Ok(());
    }
    for item in value.as_array().ok_or_else(invalid)? {
        target.insert(item.as_str().ok_or_else(invalid)?.into());
    }
    Ok(())
}

impl Aggregate {
    pub(super) fn include(&mut self, document: &Value) -> Result<()> {
        if let Some(items) = document["required_env"].as_array() {
            for item in items {
                self.environment
                    .entry(text(item, "name")?.into())
                    .or_default()
                    .insert(text(item, "purpose")?.into());
            }
        }
        self.credentials |= document["requires_credentials"].as_bool().unwrap_or(false);
        let authorization = document["requires_authorization"]
            .as_str()
            .unwrap_or("none");
        self.authorization = self.authorization.max(
            AUTHORIZATION
                .iter()
                .position(|item| *item == authorization)
                .ok_or_else(invalid)?,
        );
        for (key, values) in &mut self.permissions {
            extend(values, &document["permissions"][*key])?;
        }
        extend(&mut self.endpoints, &document["external_endpoints"])?;
        extend(&mut self.runtimes, &document["runtime_requirements"])?;
        let license = text(&document["license"], "spdx_id")?;
        if license.trim().is_empty() {
            return Err(invalid());
        }
        self.licenses.insert(license.into());
        self.redistributable &= document["license"]["redistribution_allowed"]
            .as_bool()
            .ok_or_else(invalid)?;
        Ok(())
    }

    pub(super) fn apply(self, document: &mut Value) {
        document["required_env"] = self.environment.into_iter().map(|(name,purposes)| json!({"name":name,"purpose":purposes.into_iter().collect::<Vec<_>>().join("\n")})).collect();
        document["requires_credentials"] = self.credentials.into();
        document["requires_authorization"] = AUTHORIZATION[self.authorization].into();
        document["permissions"] = json!(self.permissions);
        document["external_endpoints"] = json!(self.endpoints);
        document["runtime_requirements"] = json!(self.runtimes);
        // Group every declaration before conjunction: OR has lower precedence.
        // This preserves declared expressions, not a license-compatibility verdict.
        let license = match self.licenses.len() {
            0 => "LicenseRef-AI-STP-Private-Composite".into(),
            1 => self.licenses.into_iter().next().unwrap_or_default(),
            _ => self
                .licenses
                .into_iter()
                .map(|value| format!("({value})"))
                .collect::<Vec<_>>()
                .join(" AND "),
        };
        document["license"] =
            json!({"spdx_id":license,"redistribution_allowed":self.redistributable});
    }
}
