//! Native source capture and authoring services.

pub mod adaptations;
pub mod adoption;
mod bindings;
pub mod contribution;
pub mod discovery;
pub mod forks;
mod freezing;
mod frontmatter;
pub mod native_edit;
pub(crate) mod native_identity;
pub mod passports;
pub mod project_binding;
pub mod releases;
pub mod runtime;
pub mod scaffold;
pub mod setups;
pub mod source;
pub mod source_project;
pub mod templates;

use serde::{Deserialize, Serialize};
use std::time::Duration;

use crate::{
    error::{Failure, Result},
    passport,
};

/// Local authoring context supplied by the owning runtime, not an authentication claim.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Identity {
    pub account_id: String,
    pub device_id: String,
}

impl Identity {
    pub(crate) fn validate(&self) -> Result<()> {
        if !passport::stable_id(&self.account_id, "account")
            || !passport::stable_id(&self.device_id, "device")
        {
            return Err(Failure::input("the local authoring identity is invalid"));
        }
        Ok(())
    }
}

pub(crate) fn expiry(at: &str) -> Result<String> {
    if !passport::timestamp(at) {
        return Err(Failure::input("the authoring timestamp is invalid"));
    }
    let expires = at
        .parse::<jiff::Timestamp>()
        .map_err(|_| Failure::input("the authoring timestamp is invalid"))?
        .checked_add(Duration::from_secs(900))
        .map_err(|_| Failure::input("the authoring expiry exceeds its range"))?;
    Ok(format!("{expires:.3}"))
}
