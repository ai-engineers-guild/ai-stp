//! Fixed native configuration surfaces, independent of external release selection.

use serde_json::{Value, json};

use crate::{
    error::{Failure, Result},
    harnesses,
    projection::{
        self, Scope,
        surfaces::{self, Surface},
    },
};

/// Configuration data compiled into this native engine. This declaration is
/// neither an authenticated external executable nor installation authority.
pub struct Profiles {
    document: Value,
}

impl Profiles {
    /// Resolve the exact supported scopes of one harness, without discovery,
    /// network access, runtime installation or a separately published component.
    pub fn resolve(harness: &str) -> Result<Self> {
        harnesses::definition(harness)?;
        let profiles = projection::profiles()?
            .iter()
            .filter(|profile| profile.harness_id == harness)
            .map(|profile| {
                Ok(json!({
                    "target_scope": profile.target_scope,
                    "profile": surfaces::profile(harness, profile.target_scope)?,
                }))
            })
            .collect::<Result<Vec<_>>>()?;
        if profiles.is_empty() {
            return Err(Failure::precondition(
                "the harness has no native configuration profiles",
            ));
        }
        let (os, arch) = crate::platform::current()
            .and_then(|platform| platform.split_once('/'))
            .ok_or_else(|| {
                Failure::precondition("native configuration is unavailable on this platform")
            })?;
        Ok(Self {
            document: json!({
                "schema_version": 1,
                "configuration_engine": "ai-stp-native/1",
                "harness_id": harness,
                "native_platform": {
                    "os": os,
                    "arch": arch,
                },
                "profiles": profiles,
            }),
        })
    }

    pub fn document(&self) -> &Value {
        &self.document
    }

    /// There is no global/user/project fallback for a native target.
    pub fn profile(&self, scope: Scope) -> Option<&Value> {
        self.document["profiles"]
            .as_array()?
            .iter()
            .find(|row| row["target_scope"] == scope.as_str())
            .map(|row| &row["profile"])
    }

    /// Native installation plans refer to this host's physical directories.
    /// This is not a declaration of a remote or untested executable artifact.
    pub fn supports_platform(&self, os: &str, arch: &str) -> bool {
        self.document["native_platform"]["os"] == os
            && self.document["native_platform"]["arch"] == arch
    }
}

impl Surface for Profiles {
    fn document(&self) -> &Value {
        self.document()
    }
    fn profile(&self, scope: Scope) -> Option<&Value> {
        self.profile(scope)
    }
    fn supports_platform(&self, os: &str, arch: &str) -> bool {
        self.supports_platform(os, arch)
    }
    fn identity_key(&self) -> &'static str {
        "installation_digest"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_seven_harnesses_keep_their_exact_nineteen_configuration_scopes()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let mut count = 0;
        let mut harnesses = 0;
        for harness in harnesses::definitions()? {
            if harness.harness_id == "undefined" {
                assert!(Profiles::resolve(&harness.harness_id).is_err());
                continue;
            }
            harnesses += 1;
            let native = Profiles::resolve(&harness.harness_id)?;
            for scope in [Scope::Global, Scope::UserRoot, Scope::Project] {
                let expected = projection::profiles()?
                    .iter()
                    .any(|row| row.harness_id == harness.harness_id && row.target_scope == scope);
                assert_eq!(native.supports_target(scope), expected);
                if expected {
                    let actual = native.profile(scope).ok_or("native profile missing")?;
                    assert_eq!(
                        actual,
                        crate::provider::surfaces::profile(&harness.harness_id, scope)?
                    );
                    surfaces::validate_profile(actual)?;
                    count += 1;
                }
            }
        }
        assert_eq!(harnesses, 7);
        assert_eq!(count, 19);
        assert!(Profiles::resolve("unknown-harness").is_err());
        Ok(())
    }

    #[test]
    fn native_data_is_not_an_external_executable_declaration_or_remote_host()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let native = Profiles::resolve("claude-code")?;
        assert!(native.profile(Scope::UserRoot).is_none());
        let arch = if cfg!(target_arch = "aarch64") {
            "arm64"
        } else {
            "x86_64"
        };
        assert!(native.supports_platform(std::env::consts::OS, arch));
        assert!(!native.supports_platform("unknown-os", arch));
        assert!(!native.supports_platform(std::env::consts::OS, "unknown-arch"));
        assert!(
            crate::provider::Info::parse(&crate::canonical::bytes(native.document())?).is_err()
        );
        Ok(())
    }
}
