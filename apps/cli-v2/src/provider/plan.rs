//! Closed read-only provider plan requests and exact response verification.
//! These values describe evidence; none grants permission to write a target.

use std::path::Path;

use jiff::Timestamp;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::Info;
use crate::{
    digest,
    error::{Failure, Result},
    passport,
    projection::Scope,
    wire,
};

pub const MAX_BUNDLE_BYTES: usize = 64 * 1024 * 1024;

fn invalid() -> Failure {
    Failure::precondition("the provider plan does not match its exact request and observations")
}

fn hash(value: &str) -> bool {
    value.strip_prefix("sha256:").is_some_and(|value| {
        value.len() == 64
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    })
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Binding {
    pub(crate) bundle_format: String,
    pub(crate) bundle_digest: String,
    pub(crate) artifact_digest: String,
    pub(crate) bundle_size: usize,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub(crate) operation: String,
    pub(crate) operation_id: String,
    pub(crate) expires_at: String,
    pub(crate) bundle: Binding,
}

/// Exact external observations expected in the provider's plan artifact.
pub struct Observed<'a> {
    pub provider: &'a Info,
    pub release_digest: &'a str,
    pub target: &'a Path,
    pub scope: Scope,
    pub target_digest: &'a str,
}

impl Request {
    pub fn parse(bytes: &[u8], now: Timestamp) -> Result<Self> {
        if bytes.len() > 8192 {
            return Err(invalid());
        }
        let document = wire::parse(bytes)?;
        let request: Self = serde_json::from_value(document).map_err(|_| invalid())?;
        request.check_time(now)?;
        Ok(request)
    }

    /// Recheck the closed request and its short absolute expiry before use.
    pub fn check_time(&self, now: Timestamp) -> Result<()> {
        let expires = self
            .expires_at
            .parse::<Timestamp>()
            .map_err(|_| invalid())?;
        if !matches!(self.operation.as_str(), "install" | "replace")
            || !passport::stable_id(&self.operation_id, "operation")
            || !passport::timestamp(&self.expires_at)
            || expires <= now
            || expires
                > now
                    .checked_add(std::time::Duration::from_secs(900))
                    .map_err(|_| invalid())?
            || self.bundle.bundle_format != "ai-stp-bundle/2"
            || !hash(&self.bundle.bundle_digest)
            || !hash(&self.bundle.artifact_digest)
            || self.bundle.bundle_size == 0
            || self.bundle.bundle_size > MAX_BUNDLE_BYTES
        {
            return Err(invalid());
        }
        Ok(())
    }

    pub fn check_bundle(&self, bytes: &[u8], now: Timestamp) -> Result<()> {
        self.check_time(now)?;
        if bytes.len() != self.bundle.bundle_size
            || digest::sha256(bytes) != self.bundle.artifact_digest
        {
            return Err(invalid());
        }
        Ok(())
    }

    /// Verify every redundant echo, without deriving trust from the response.
    pub fn validation(&self, bytes: &[u8]) -> Result<Value> {
        let response = response(bytes)?;
        let mut expected = serde_json::to_value(&self.bundle).map_err(|_| invalid())?;
        expected["valid"] = true.into();
        if response != expected {
            return Err(invalid());
        }
        Ok(response)
    }

    pub fn planned(&self, bytes: &[u8], observed: &Observed<'_>, now: Timestamp) -> Result<Value> {
        self.check_time(now)?;
        let response = response(bytes)?;
        let effects = response["effects"].as_array().ok_or_else(invalid)?;
        if effects.is_empty()
            || effects.len() > 8200
            || effects.iter().any(|effect| {
                effect.as_str().is_none_or(|text| {
                    text.is_empty() || text.len() > 4096 || text.chars().any(char::is_control)
                })
            })
            || !hash(observed.release_digest)
            || !hash(observed.target_digest)
            || !observed.provider.supports_target(observed.scope)
            || !observed.target.is_absolute()
            || observed.target.to_str().is_none()
        {
            return Err(invalid());
        }
        let provider = observed.provider.document();
        let platform = super::runtime::platform()?;
        let (os, arch) = platform.split_once('/').ok_or_else(invalid)?;
        let mut plan = json!({
            "format":"ai-stp-provider-plan/3", "protocol_version":3,
            "provider_id":provider["provider_id"], "provider_version":provider["provider_version"],
            "provider_build_digest":provider["provider_build_digest"], "provider_release_digest":observed.release_digest,
            "operation_id":self.operation_id, "operation":self.operation,
            "canonical_target":observed.target, "expected_target_digest":observed.target_digest,
            "projection_profile_digest":observed.provider.profile(observed.scope).ok_or_else(invalid)?["digest"],
            "bundle":self.bundle, "backup_ref":null, "restore_target_digest":null, "permission_profile":null,
            "platform":{"os":os,"arch":arch}, "expires_at":self.expires_at, "effects":effects
        });
        if observed.scope != Scope::Global {
            plan["target_scope"] = observed.scope.as_str().into();
        }
        let mut expected = serde_json::to_value(&self.bundle).map_err(|_| invalid())?;
        expected["valid"] = true.into();
        expected["state"] = "planned".into();
        expected["expected_target_digest"] = observed.target_digest.into();
        expected["effects"] = effects.clone().into();
        // The external v3 protocol binds RFC 8785 wire strings, including NFD paths.
        // Project NFC normalization would bind a different filesystem name.
        expected["plan_digest"] = digest::bytes(
            "ai-stp:provider-plan:v3",
            &serde_json_canonicalizer::to_vec(&plan).map_err(|_| invalid())?,
        )?
        .into();
        expected["plan"] = plan;
        if response != expected {
            return Err(invalid());
        }
        Ok(response)
    }
}

fn response(bytes: &[u8]) -> Result<Value> {
    if bytes.len() > 1024 * 1024 {
        return Err(invalid());
    }
    let response = wire::parse(bytes)?;
    if response["state"] == "refused" || response["rejected"] == true || response["valid"] == false
    {
        let reason = response["reason"]
            .as_str()
            .filter(|text| {
                !text.is_empty()
                    && text.len() <= 64
                    && text
                        .bytes()
                        .all(|byte| byte.is_ascii_lowercase() || byte == b'_')
            })
            .unwrap_or("unspecified");
        return Err(
            Failure::precondition("the provider refused the requested plan or bundle")
                .with_details([("reason".into(), reason.into())]),
        );
    }
    Ok(response)
}
