//! Closed software plan requests; provider observations never authorize execution.

use std::{path::Path, time::Duration};

use jiff::Timestamp;
use serde::Deserialize;
use serde_json::{Value, json};

use super::plan::{self, Observed};
use crate::{
    digest,
    error::{Failure, Result},
    passport,
    projection::Scope,
    wire,
};

fn invalid() -> Failure {
    Failure::precondition("the software plan differs from its exact request or observations")
}

fn label(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value.as_bytes()[0].is_ascii_alphanumeric()
        && !value.ends_with('.')
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-' | b'+'))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub(crate) operation: String,
    pub(crate) operation_id: String,
    pub(crate) expires_at: String,
    pub(crate) software_version: Option<String>,
}

impl Request {
    pub fn parse(bytes: &[u8], now: Timestamp) -> Result<Self> {
        if bytes.len() > 8192 {
            return Err(invalid());
        }
        let request: Self = serde_json::from_value(wire::parse(bytes)?).map_err(|_| invalid())?;
        request.check_time(now)?;
        Ok(request)
    }

    pub fn check_time(&self, now: Timestamp) -> Result<()> {
        let expires = self
            .expires_at
            .parse::<Timestamp>()
            .map_err(|_| invalid())?;
        if !matches!(
            self.operation.as_str(),
            "software_install" | "software_update" | "software_remove"
        ) || !passport::stable_id(&self.operation_id, "operation")
            || !passport::timestamp(&self.expires_at)
            || expires <= now
            || expires
                > now
                    .checked_add(Duration::from_secs(900))
                    .map_err(|_| invalid())?
            || self
                .software_version
                .as_ref()
                .is_some_and(|version| !label(version))
        {
            return Err(invalid());
        }
        Ok(())
    }

    /// Only the runtime may supply authenticated provider observations. Parsing
    /// this value alone establishes consistency, not provenance or permission.
    pub fn planned(
        &self,
        bytes: &[u8],
        observed: &Observed<'_>,
        prefix: &Path,
        now: Timestamp,
    ) -> Result<Value> {
        self.check_time(now)?;
        let response = plan::response(bytes)?;
        let effects = response["effects"].as_array().ok_or_else(invalid)?;
        let info = observed.provider.document();
        let version = response["plan"]["software_version"]
            .as_str()
            .ok_or_else(invalid)?;
        if !label(version)
            || self
                .software_version
                .as_ref()
                .is_some_and(|asked| asked != version)
        {
            return Err(invalid());
        }
        if effects.is_empty()
            || effects.len() > 128
            || effects.iter().any(|v| {
                v.as_str().is_none_or(|s| {
                    s.is_empty() || s.len() > 8192 || s.chars().any(char::is_control)
                })
            })
            || !plan::hash(observed.release_digest)
            || !plan::hash(observed.target_digest)
            || !observed.provider.supports_target(observed.scope)
            || !info["supported_operations"]
                .as_array()
                .is_some_and(|ops| ops.iter().any(|v| v == &self.operation))
            || !observed.target.is_absolute()
            || observed.target.to_str().is_none()
            || !prefix.is_absolute()
            || prefix.to_str().is_none()
            || prefix == observed.target
        {
            return Err(invalid());
        }
        let platform = super::runtime::platform()?;
        let (os, arch) = platform.split_once('/').ok_or_else(invalid)?;
        let mut artifact = json!({
            "format":"ai-stp-provider-plan/3", "protocol_version":3,
            "provider_id":info["provider_id"], "provider_version":info["provider_version"],
            "provider_build_digest":info["provider_build_digest"], "provider_release_digest":observed.release_digest,
            "operation_id":self.operation_id, "operation":self.operation,
            "canonical_target":observed.target, "expected_target_digest":observed.target_digest,
            "projection_profile_digest":observed.provider.profile(observed.scope).ok_or_else(invalid)?["digest"],
            "bundle":null, "backup_ref":null, "restore_target_digest":null, "permission_profile":null,
            "platform":{"os":os,"arch":arch}, "expires_at":self.expires_at, "effects":effects,
            "software_prefix":prefix, "software_version":version
        });
        if observed.scope != Scope::Global {
            artifact["target_scope"] = observed.scope.as_str().into();
        }
        // This is the authenticated provider's prefix observation, not an
        // independently verified installed-software digest or write authority.
        if let Some(value) = response["plan"].get("expected_software_digest") {
            let value = value
                .as_str()
                .filter(|value| plan::hash(value))
                .ok_or_else(invalid)?;
            artifact["expected_software_digest"] = value.into();
        }
        if self.operation != "software_remove" {
            let files = response["plan"]["software_artifacts"]
                .as_array()
                .ok_or_else(invalid)?;
            if files.is_empty() || files.len() > 16 {
                return Err(invalid());
            }
            let mut total = 0u64;
            let mut seen = std::collections::BTreeSet::new();
            for file in files {
                let record: Download =
                    serde_json::from_value(file.clone()).map_err(|_| invalid())?;
                record.check(platform)?;
                total = total.checked_add(record.byte_length).ok_or_else(invalid)?;
                if total > 2 * 1024 * 1024 * 1024 || !seen.insert((record.url, record.sha256)) {
                    return Err(invalid());
                }
            }
            artifact["software_artifacts"] = files.clone().into();
        }
        let expected = json!({"state":"planned", "expected_target_digest":observed.target_digest,
            "effects":effects, "plan_digest":digest::bytes("ai-stp:provider-plan:v3", &serde_json_canonicalizer::to_vec(&artifact).map_err(|_| invalid())?)?, "plan":artifact});
        if response != expected {
            return Err(invalid());
        }
        Ok(response)
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Download {
    platform: String,
    url: String,
    sha256: String,
    byte_length: u64,
    entry_point: String,
}

impl Download {
    fn check(&self, platform: &str) -> Result<()> {
        let url = url::Url::parse(&self.url).map_err(|_| invalid())?;
        if self.platform != platform
            || !plan::hash(&self.sha256)
            || self.byte_length == 0
            || self.byte_length > 1024 * 1024 * 1024
            || self.url.len() > 4096
            || self.url.chars().any(char::is_whitespace)
            || self.url.chars().any(char::is_control)
            || url.scheme() != "https"
            || !url.username().is_empty()
            || url.password().is_some()
            || url.fragment().is_some()
            || url.query().is_some()
            || url.host_str().is_none()
            || url.port().is_some()
            || !self.entry_point.strip_prefix("bin/").is_some_and(label)
        {
            return Err(invalid());
        }
        Ok(())
    }
}
