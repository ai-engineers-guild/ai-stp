//! Fresh exact catalog observations for reuse and terminal publication readback.

use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::{Snapshot, contract::Visibility, text};
use crate::{
    account::access::{Access, Binding},
    catalog::{self, Kind},
    digest,
    error::{ErrorKind, Failure, Result},
    http::{Endpoint, MAX_BODY},
    passport, wire,
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Observation {
    pub origin: String,
    pub account_id: String,
    pub checked_at: String,
    pub distribution_visibility: Visibility,
    pub document: Value,
}

fn invalid() -> Failure {
    Failure::precondition("the readable catalog version differs from the exact publication intent")
}

impl Observation {
    /// This verifies retained evidence, not current authority. New effects need
    /// another online read through the currently held account.
    pub fn validate(
        &self,
        snapshot: &Snapshot,
        requested: Visibility,
        binding: &Binding,
    ) -> Result<()> {
        binding.validate()?;
        let kind = Kind::parse(text(&snapshot.passport, "kind")?)?;
        let id = text(&snapshot.passport, "stable_id")?;
        let version = text(&snapshot.passport, "version")?;
        if self.origin != binding.origin
            || self.account_id != binding.account_id
            || !passport::timestamp(&self.checked_at)
            || requested == Visibility::Public && self.distribution_visibility != Visibility::Public
        {
            return Err(invalid());
        }
        match self.distribution_visibility {
            Visibility::Private => catalog::private::validate(kind, id, version, &self.document)?,
            Visibility::Public => catalog::validate(kind, id, Some(version), &self.document)?,
        }
        passport::validate(&self.document["passport"])?;
        passport::versions::validate_document(&self.document["passport"])?;
        if self.document["passport_digest"] != snapshot.passport_digest
            || self.document["passport"] != snapshot.passport
            || snapshot.passport_digest
                != digest::canonical("ai-stp:passport:v1", &snapshot.passport)?
            || !matches!(
                self.document["lifecycle"].as_str(),
                Some("active" | "deprecated")
            )
        {
            return Err(invalid());
        }
        Ok(())
    }
}

pub(crate) fn read(
    access: &mut Access,
    snapshot: &Snapshot,
    visibility: Visibility,
) -> Result<Option<Observation>> {
    passport::validate(&snapshot.passport)?;
    passport::versions::validate_document(&snapshot.passport)?;
    if snapshot.passport_digest != digest::canonical("ai-stp:passport:v1", &snapshot.passport)? {
        return Err(invalid());
    }
    let kind = Kind::parse(text(&snapshot.passport, "kind")?)?;
    let id = text(&snapshot.passport, "stable_id")?;
    let version = text(&snapshot.passport, "version")?;
    access.verify()?;
    let endpoint = Endpoint::new(&access.binding().origin)?;
    let started = Instant::now();
    let remaining = || {
        Duration::from_secs(30)
            .checked_sub(started.elapsed())
            .filter(|v| !v.is_zero())
            .ok_or_else(|| {
                Failure::new(
                    ErrorKind::Unavailable,
                    "publication readback exceeded thirty seconds",
                )
            })
    };
    let url = endpoint.route(&[kind.route(), id, "versions", version], &[])?;
    let (bytes, distribution_visibility) =
        match endpoint.read(&url, "application/json", MAX_BODY, remaining()?) {
            Ok(bytes) => (bytes, Visibility::Public),
            Err(failure) if matches!(failure.kind, ErrorKind::NotFound) => {
                if visibility == Visibility::Public {
                    access.revalidate()?;
                    return Ok(None);
                }
                let url =
                    endpoint.route(&[kind.route(), id, "versions", version, "private"], &[])?;
                match access.read(&endpoint, &url, "application/json", MAX_BODY, remaining()?) {
                    Ok(bytes) => (bytes, Visibility::Private),
                    Err(failure) if matches!(failure.kind, ErrorKind::NotFound) => {
                        access.revalidate()?;
                        return Ok(None);
                    }
                    Err(failure) => return Err(failure),
                }
            }
            Err(failure) => return Err(failure),
        };
    let observed = Observation {
        origin: access.binding().origin.clone(),
        account_id: access.binding().account_id.clone(),
        checked_at: format!("{:.3}", jiff::Timestamp::now()),
        distribution_visibility,
        document: wire::parse(&bytes)?,
    };
    observed.validate(snapshot, visibility, access.binding())?;
    access.revalidate()?;
    Ok(Some(observed))
}
