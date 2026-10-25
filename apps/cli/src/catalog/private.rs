//! Exact authenticated versions and account-scoped offline observations.

use serde_json::{Value, json};
use std::{path::Path, time::Duration};

use super::{Kind, Reader, cache, invalid, moment};
use crate::{
    account::access::Access,
    digest,
    error::{ErrorKind, Failure, Result},
    http::{Endpoint, MAX_BODY},
    passport, wire,
};

static VERSION: wire::Schema = wire::Schema::reader(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/private-version-response.schema.json"
)));

pub(crate) fn validate(kind: Kind, id: &str, version: &str, document: &Value) -> Result<()> {
    VERSION.validate(document)?;
    let passport = &document["passport"];
    passport::validate(passport)?;
    if document["visibility"] != "private"
        || document["trust"]["trust_lane"] != "local_owner_or_pinned"
        || passport["stable_id"] != id
        || passport["kind"] != kind.name()
        || passport["version"] != version
        || digest::canonical("ai-stp:passport:v1", passport)? != document["passport_digest"]
    {
        return Err(invalid());
    }
    Ok(())
}

pub(crate) fn version(
    config: Option<&Path>,
    cache_root: Option<&Path>,
    state: &Path,
    kind: Kind,
    id: &str,
    version: &str,
    offline: bool,
) -> Result<Value> {
    let endpoint = Endpoint::configured(config)?;
    let access = Access::load(
        state,
        &endpoint.base.origin().ascii_serialization(),
        offline,
    )?;
    version_with_access(config, cache_root, kind, id, version, offline, access)
}

pub(crate) fn version_with_access(
    config: Option<&Path>,
    cache_root: Option<&Path>,
    kind: Kind,
    id: &str,
    version: &str,
    offline: bool,
    mut access: Access,
) -> Result<Value> {
    // Public observations keep their existing cache and validation. An exact
    // private read is the only authenticated fallback; searches stay anonymous.
    let configured = Endpoint::configured(config)?;
    let reader = Reader {
        endpoint: if access.binding().connection.is_some() {
            Endpoint::new(&access.binding().origin)?
        } else {
            configured
        },
        cache: cache_root,
        offline,
    };
    let public_unavailable = match reader.show(kind, id, Some(version)) {
        Ok(value) => return Ok(value),
        Err(failure) if matches!(failure.kind, ErrorKind::NotFound) => false,
        Err(failure) if matches!(failure.kind, ErrorKind::Unavailable) => true,
        Err(failure) => return Err(failure),
    };
    let url = reader
        .endpoint
        .route(&[kind.route(), id, "versions", version, "private"], &[])?;
    let remote = if offline || public_unavailable {
        Err(crate::http::unavailable())
    } else {
        access.verify().and_then(|()| {
            access.read(
                &reader.endpoint,
                &url,
                "application/json",
                MAX_BODY,
                Duration::from_secs(30),
            )
        })
    };
    let (document, source, checked_at) = match remote {
        Ok(bytes) => {
            let document = wire::parse(&bytes)?;
            validate(kind, id, version, &document)?;
            let checked_at = moment();
            cache::Cache::private(&access, true)?
                .ok_or_else(invalid)?
                .store(url.as_str(), &document, &checked_at)?;
            (document, "online", checked_at)
        }
        Err(failure) if matches!(failure.kind, ErrorKind::Unavailable) => {
            let cached = cache::Cache::private(&access, false)?
                .map(|cache| cache.load(url.as_str()))
                .transpose()?
                .flatten()
                .ok_or(failure)?;
            validate(kind, id, version, &cached.document)?;
            (cached.document, "cache", cached.checked_at)
        }
        Err(failure) => return Err(failure),
    };
    access.revalidate()?;
    Ok(
        json!({"schema_version":1,"distribution_visibility":"private","kind":kind.name(),
        "source":source,"checked_at":checked_at,"passport_digest":document["passport_digest"],
        "lifecycle":document["lifecycle"],"trust":document["trust"],"published_at":document["published_at"],
        "passport":document["passport"],"account_id":access.binding().account_id,
        "online_authorized":source == "online"}),
    )
}

pub(super) fn require_binding(
    binding: &Option<crate::account::access::Binding>,
    access: Option<&Access>,
) -> Result<()> {
    match (binding, access) {
        (None, None) => Ok(()),
        (Some(binding), Some(access)) if binding == access.binding() => {
            binding.validate()?;
            access.revalidate()
        }
        _ => Err(Failure::precondition(
            "the acquisition account, device, session or origin changed after planning",
        )),
    }
}
