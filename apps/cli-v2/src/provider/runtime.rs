//! Read-only provider observations from authenticated bytes and proved network denial.

#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "linux")]
pub mod probe;
#[cfg(target_os = "linux")]
mod target;

use super::artifact::Artifact;
use crate::{
    error::{ErrorKind, Failure, Result},
    projection::Scope,
};
use serde_json::Value;
use std::path::Path;
#[cfg(target_os = "linux")]
use {
    super::Info,
    crate::{digest, wire},
    serde_json::json,
};

fn unavailable() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "native provider network isolation is unavailable on this host",
    )
}

pub fn platform() -> Result<&'static str> {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("linux", "x86_64") => Ok("linux/x86_64"),
        ("linux", "aarch64") => Ok("linux/arm64"),
        ("macos", "x86_64") => Ok("macos/x86_64"),
        ("macos", "aarch64") => Ok("macos/arm64"),
        ("windows", "x86_64") => Ok("windows/x86_64"),
        ("windows", "aarch64") => Ok("windows/arm64"),
        _ => Err(unavailable()),
    }
}

pub struct Runtime {
    #[cfg(target_os = "linux")]
    launcher: linux::Launcher,
}

impl Runtime {
    pub fn observe() -> Result<Self> {
        #[cfg(target_os = "linux")]
        {
            Ok(Self {
                launcher: linux::Launcher::observe()?,
            })
        }
        #[cfg(not(target_os = "linux"))]
        {
            Err(unavailable())
        }
    }

    pub fn report(&self) -> Value {
        #[cfg(target_os = "linux")]
        {
            self.launcher.report()
        }
        #[cfg(not(target_os = "linux"))]
        {
            serde_json::json!({"enforcement":"unavailable"})
        }
    }

    /// The report is evidence of this observation, not a serializable installation permit.
    pub fn inspect(&self, artifact: &Artifact<'_>) -> Result<Value> {
        if artifact.report()["platform"] != platform()? {
            return Err(unavailable());
        }
        #[cfg(target_os = "linux")]
        {
            self.information(artifact).map(|(_, report)| report)
        }
        #[cfg(not(target_os = "linux"))]
        {
            Err(unavailable())
        }
    }

    #[cfg(target_os = "linux")]
    fn information(&self, artifact: &Artifact<'_>) -> Result<(Info, Value)> {
        if artifact.report()["platform"] != platform()? {
            return Err(unavailable());
        }
        let output = self.launcher.inspect(artifact.executable()?)?;
        let info = Info::parse(&output)?;
        let document = info.document();
        if document["harness_id"] != artifact.report()["harness_id"]
            || document["provider_id"] != artifact.report()["project"]
            || document["provider_version"] != artifact.report()["version"]
            || !info.supports_platform(
                "linux",
                if cfg!(target_arch = "aarch64") {
                    "arm64"
                } else {
                    "x86_64"
                },
            )
        {
            return Err(Failure::precondition(
                "the observed provider identity or platform differs from its authenticated artifact",
            ));
        }
        artifact.executable()?;
        let report = json!({"artifact":artifact.report(),"provider_info":document,"provider_info_digest":digest::sha256(&output),"network":self.launcher.report(),"observed_at":jiff::Timestamp::now().to_string(),"harness_written":false,"installed":false});
        wire::parse(&serde_json::to_vec(&report).map_err(|_| unavailable())?)?;
        Ok((info, report))
    }

    /// Observe one explicit existing target without mounting any writable host path.
    pub fn status(
        &self,
        parent: &Path,
        harness: &str,
        version: &str,
        path: &Path,
        scope: Scope,
    ) -> Result<Value> {
        #[cfg(target_os = "linux")]
        {
            let target = target::Target::open(path)?;
            let state = target.state_parent(parent)?;
            let trust = super::trust::refresh_at(&state)?;
            let artifact = super::artifact::fetch(harness, version, platform()?, &trust)?;
            let (info, mut report) = self.information(&artifact)?;
            if !info.supports_target(scope) {
                return Err(Failure::precondition(
                    "the observed provider does not support this target scope",
                ));
            }
            target.revalidate()?;
            let bytes = self
                .launcher
                .status(artifact.executable()?, &target, scope)?;
            let status = target.response(&bytes, &info)?;
            artifact.executable()?;
            report
                .as_object_mut()
                .ok_or_else(unavailable)?
                .remove("installed");
            report["installation_performed"] = false.into();
            report["network"]["filesystem"] = "declared_runtime_and_readonly_target".into();
            report["target"] =
                json!({"path":target.path(),"scope":scope.as_str(),"access":"read_only"});
            report["status"] = status;
            report["status_digest"] = digest::sha256(&bytes).into();
            report["status_observed_at"] = jiff::Timestamp::now().to_string().into();
            Ok(report)
        }
        #[cfg(not(target_os = "linux"))]
        {
            let _ = (parent, harness, version, path, scope);
            Err(unavailable())
        }
    }
}
