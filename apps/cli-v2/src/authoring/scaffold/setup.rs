//! One editable composition request. Component authoring has its own source trees.

use std::{collections::BTreeMap, path::Path};

use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{DRAFT, apply_exact, encoded, invalid, planned, read_plan, valid_name};
use crate::{authoring::setups, error::Result, harnesses};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub name: String,
    pub harness_id: String,
}

pub type Plan = super::Plan<Request>;

fn render(request: &Request) -> Result<BTreeMap<String, String>> {
    if !valid_name(&request.name) || request.harness_id == "undefined" {
        return Err(invalid());
    }
    harnesses::definition(&request.harness_id)?;
    let document = setups::Request {
        harness_id: request.harness_id.clone(),
        name: request.name.clone(),
        description: format!("{DRAFT} describe this complete setup."),
        purpose: format!("{DRAFT} define its purpose and select exact component versions."),
        members: Vec::new(),
    };
    // Keep the starter directly consumable by compose; it is not a passport.
    Ok(BTreeMap::from([(
        "setup-request.json".into(),
        encoded(serde_json::to_value(document).map_err(|_| invalid())?)?,
    )]))
}

pub fn plan(output: &Path, request: Request) -> Result<Plan> {
    let files = render(&request)?;
    planned(output, "setup.scaffold", request, files)
}

pub fn read(path: &Path) -> Result<Plan> {
    read_plan(path)
}

pub fn apply(plan: &Plan, expected_digest: &str) -> Result<Value> {
    apply_exact(
        plan,
        expected_digest,
        "setup.scaffold",
        render(&plan.request)?,
    )
}
