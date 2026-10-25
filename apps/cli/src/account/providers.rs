//! Sign-in availability belongs to the selected deployment, not machine help.

use serde::Deserialize;
use serde_json::{Value, json};

use crate::error::{Failure, Result};

#[cfg(test)]
#[path = "providers_tests.rs"]
mod tests;

pub const IDS: &[&str] = &[
    "google",
    "github",
    "authentik",
    "keycloak",
    "gitlab",
    "saml",
];

#[derive(Deserialize)]
pub(super) struct Providers {
    pub schema_version: u32,
    pub providers: Vec<String>,
}

pub fn read(origin: Option<&str>) -> Result<Value> {
    let origin = super::transport::origin(origin.unwrap_or(crate::config::CATALOG_URL))?;
    let providers = match super::transport::Api::new(&origin)?.providers()? {
        super::transport::Reply::Resource(value) => value,
        super::transport::Reply::Refused(_) => {
            return Err(Failure::precondition(
                "the selected server does not provide sign-in availability",
            ));
        }
    };
    if providers.schema_version != 1
        || providers.providers.len() > IDS.len()
        || providers
            .providers
            .iter()
            .enumerate()
            .any(|(index, value)| {
                !IDS.contains(&value.as_str()) || providers.providers[..index].contains(value)
            })
    {
        return Err(super::invalid());
    }
    Ok(
        json!({"schema_version":1,"origin":origin,"providers":providers.providers,"online_verified":true}),
    )
}
