//! Validated provider declarations; parsing does not attest a provider executable.

pub mod artifact;
pub(crate) mod configuration;
pub mod managed;
pub mod plan;
pub mod runtime;
pub mod status;
pub(crate) mod surfaces;
pub mod trust;
pub mod wheel;

pub(crate) use crate::projection::surfaces::supports_profile;
use crate::projection::surfaces::{Surface, contains};
use crate::{
    error::{Failure, Result},
    projection::Scope,
    wire::{self, Schema},
};
use serde_json::Value;
use std::collections::BTreeSet;

static INFO: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/provider-kit/v3/provider-info.schema.json"
)));

pub struct Info(Value);
fn invalid() -> Failure {
    Failure::precondition(
        "the provider declaration has inconsistent capabilities or profile identities",
    )
}
impl Info {
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        if bytes.len() > 1024 * 1024 {
            return Err(invalid());
        }
        let document = wire::parse(bytes)?;
        INFO.validate(&document)?;
        for command in [
            "provider-info",
            "validate-bundle",
            "plan-operation",
            "apply-operation",
            "recover-operation",
            "status",
        ] {
            if !contains(&document["supported_commands"], command) {
                return Err(invalid());
            }
        }
        for operation in ["install", "replace", "backup", "restore", "remove"] {
            if !contains(&document["supported_operations"], operation) {
                return Err(invalid());
            }
        }
        if contains(&document["supported_commands"], "launch")
            != contains(&document["supported_operations"], "launch")
        {
            return Err(invalid());
        }
        profile(&document["projection_profile"])?;
        let mut scopes = BTreeSet::new();
        if let Some(profiles) = document["scoped_projection_profiles"].as_array() {
            for item in profiles {
                if !scopes.insert(item["target_scope"].as_str().ok_or_else(invalid)?) {
                    return Err(invalid());
                }
                profile(item)?;
            }
        }
        Ok(Self(document))
    }

    pub fn document(&self) -> &Value {
        &self.0
    }

    pub fn profile(&self, scope: Scope) -> Option<&Value> {
        if scope == Scope::Global {
            return Some(&self.0["projection_profile"]);
        }
        let name = match scope {
            Scope::Global => "global",
            Scope::Project => "project",
            Scope::UserRoot => "user_root",
        };
        self.0["scoped_projection_profiles"]
            .as_array()?
            .iter()
            .find(|item| item["target_scope"] == name)
    }

    pub fn supports_platform(&self, os: &str, arch: &str) -> bool {
        contains(&self.0["supported_os"], os) && contains(&self.0["supported_arch"], arch)
    }

    pub fn supports_target(&self, scope: Scope) -> bool {
        self.profile(scope).is_some()
            && (scope == Scope::Global
                || (contains(&self.0["plan_request_fields"], "target_scope")
                    && contains(&self.0["status_request_fields"], "target_scope")))
    }

    pub fn supports_scope(&self, scope: Scope, adaptation: &Value) -> bool {
        let name = match scope {
            Scope::Global => "global",
            Scope::Project => "project",
            Scope::UserRoot => "user_root",
        };
        if !self.supports_target(scope) || adaptation["scope"] != name {
            return false;
        }
        let Some(profile) = self.profile(scope) else {
            return false;
        };
        supports_profile(profile, adaptation)
    }
}

pub(crate) fn profile(value: &Value) -> Result<()> {
    crate::projection::surfaces::validate_profile(value).map_err(|_| invalid())
}

impl Surface for Info {
    fn document(&self) -> &Value {
        Info::document(self)
    }
    fn profile(&self, scope: Scope) -> Option<&Value> {
        Info::profile(self, scope)
    }
    fn supports_platform(&self, os: &str, arch: &str) -> bool {
        Info::supports_platform(self, os, arch)
    }
    fn supports_target(&self, scope: Scope) -> bool {
        Info::supports_target(self, scope)
    }
    fn supports_scope(&self, scope: Scope, adaptation: &Value) -> bool {
        Info::supports_scope(self, scope, adaptation)
    }
    fn identity_key(&self) -> &'static str {
        "provider_digest"
    }
}
