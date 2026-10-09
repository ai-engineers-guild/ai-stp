//! Validated provider declarations; parsing does not attest a provider executable.

pub mod wheel;

use crate::{
    artifacts, digest,
    error::{Failure, Result},
    projection::Scope,
    wire::{self, Schema},
};
use serde_json::Value;
use std::collections::BTreeSet;

static INFO: Schema = Schema::new(include_str!(
    "../../../provider-kit/v3/provider-info.schema.json"
));

pub struct Info(Value);
fn invalid() -> Failure {
    Failure::precondition(
        "the provider declaration has inconsistent capabilities or profile identities",
    )
}
fn contains(value: &Value, item: &str) -> bool {
    value
        .as_array()
        .is_some_and(|items| items.iter().any(|value| value == item))
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
        let required = &adaptation["required_surface"];
        if required["profile_id"] != profile["profile_id"]
            || required["profile_digest"] != profile["digest"]
            || !required["bundle_format"]
                .as_str()
                .is_some_and(|name| contains(&profile["bundle_formats"], name))
            || !adaptation["provider_component_kind"]
                .as_str()
                .is_some_and(|name| contains(&profile["component_kinds"], name))
            || !adaptation["projection_kind"]
                .as_str()
                .is_some_and(|name| contains(&profile["projection_kinds"], name))
        {
            return false;
        }
        let Some(members) = adaptation["members"].as_array() else {
            return false;
        };
        let Some(namespaces) = profile["native_namespaces"].as_array() else {
            return false;
        };
        let mut count = 0u64;
        let mut size = 0u64;
        for member in members {
            let Some(path) = member["path"].as_str() else {
                return false;
            };
            if !artifacts::safe_path(path)
                || !namespaces
                    .iter()
                    .filter_map(Value::as_str)
                    .any(|namespace| {
                        path == namespace
                            || path
                                .strip_prefix(namespace)
                                .is_some_and(|tail| tail.starts_with('/'))
                    })
            {
                return false;
            }
            if member["object_type"] == "file" {
                count += 1;
                let Some(next) = member["content_artifact"]["size_bytes"]
                    .as_u64()
                    .and_then(|value| size.checked_add(value))
                else {
                    return false;
                };
                size = next;
            }
        }
        count <= profile["max_files"].as_u64().unwrap_or(0)
            && size <= profile["max_bytes"].as_u64().unwrap_or(0)
    }
}

fn profile(value: &Value) -> Result<()> {
    let mut payload = value.clone();
    payload
        .as_object_mut()
        .ok_or_else(invalid)?
        .remove("digest");
    if value["digest"] != digest::canonical("ai-stp:provider-projection:v3", &payload)? {
        return Err(invalid());
    }
    for namespace in value["native_namespaces"].as_array().ok_or_else(invalid)? {
        if !namespace.as_str().is_some_and(artifacts::safe_path) {
            return Err(invalid());
        }
    }
    Ok(())
}
