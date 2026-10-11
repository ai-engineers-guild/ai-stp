//! Setup declarations augment the minimum requirements of exact members.

use serde::{Deserialize, Serialize};

use super::aggregate::Aggregate;
use crate::error::{Failure, Result};

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub struct Requirements {
    required_env: Vec<Environment>,
    requires_credentials: bool,
    requires_authorization: Authorization,
    permissions: Permissions,
    external_endpoints: Vec<String>,
    runtime_requirements: Vec<String>,
    license: Option<License>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Environment {
    name: String,
    purpose: String,
}

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum Authorization {
    #[default]
    None,
    UserAccount,
    ExternalService,
}

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
struct Permissions {
    filesystem: Vec<String>,
    network: Vec<String>,
    process: Vec<String>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct License {
    spdx_id: String,
    redistribution_allowed: bool,
}

impl Requirements {
    pub(super) fn include(&self, aggregate: &mut Aggregate) -> Result<()> {
        let value = serde_json::to_value(self)
            .map_err(|_| Failure::input("setup requirement declarations are invalid"))?;
        aggregate.include_requirements(&value)?;
        if self.license.is_some() {
            aggregate.include_license(&value["license"])?;
        }
        Ok(())
    }
}
