//! Shared exact-version and portable metadata observations for registry TAR sources.

use serde_json::{Value, json};

use crate::{artifacts::Member, canonical, digest, error::Result, sources::snapshot};

pub(super) fn exact_version(version: &str) -> bool {
    if version.is_empty() || version.len() > 256 {
        return false;
    }
    let identifiers = |text: &str, prerelease: bool| {
        text.split('.').all(|part| {
            !part.is_empty()
                && part.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
                && !(prerelease
                    && part.len() > 1
                    && part.starts_with('0')
                    && part.bytes().all(|b| b.is_ascii_digit()))
        })
    };
    let core = if let Some((core, build)) = version.split_once('+') {
        if !identifiers(build, false) {
            return false;
        }
        core
    } else {
        version
    };
    let core = if let Some((core, pre)) = core.split_once('-') {
        if !identifiers(pre, true) {
            return false;
        }
        core
    } else {
        core
    };
    let mut count = 0;
    core.split('.').all(|part| {
        count += 1;
        !part.is_empty()
            && part.bytes().all(|b| b.is_ascii_digit())
            && (part.len() == 1 || !part.starts_with('0'))
    }) && count == 3
}

pub(super) fn tar_snapshot(
    ecosystem: &str,
    name: &str,
    version: &str,
    archive: &[u8],
    files: Vec<Member>,
    evidence: Value,
) -> Result<Value> {
    let snapshot = snapshot::encode(files)?;
    let value = json!({"schema_version":1,"snapshot":{
        "kind":"package","canonical_coordinate":format!("package:{ecosystem}:{name}@{version}"),"exact_identity":version,
        "archive_digest":digest::bytes("ai-stp:artifact:v1",archive)?,"component_digest":snapshot.digest,"file_paths":snapshot.paths,
        "package_evidence":evidence,"fetched_at":format!("{:.3}",jiff::Timestamp::now()),
        "author_verified":false,"component_verified":false,"target_write":false},
        "artifact":snapshot.artifact,"provenance":"package_registry_observed","network_accessed":true,"filesystem_accessed":false});
    canonical::bytes(&value)?;
    Ok(value)
}
