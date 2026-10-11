//! Closed wire domains and SHA-256 content identities.

use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::{
    canonical,
    error::{Failure, Result},
};

pub fn sha256(bytes: &[u8]) -> String {
    representation(&Sha256::digest(bytes))
}

pub(crate) fn representation(bytes: &[u8]) -> String {
    let hex: String = bytes.iter().map(|byte| format!("{byte:02x}")).collect();
    format!("sha256:{hex}")
}

pub fn canonical(domain: &str, value: &Value) -> Result<String> {
    bytes(domain, &canonical::bytes(value)?)
}

pub fn bytes(domain: &str, payload: &[u8]) -> Result<String> {
    if !DOMAINS.contains(&domain) {
        return Err(Failure::input("unknown digest domain"));
    }
    let mut hash = Sha256::new();
    hash.update(domain.as_bytes());
    hash.update([0]);
    hash.update(payload);
    Ok(representation(&hash.finalize()))
}

pub const DOMAINS: &[&str] = &[
    "ai-stp:article-active:v1",
    "ai-stp:article-body:v1",
    "ai-stp:article-revision:v1",
    "ai-stp:article-snapshot:v1",
    "ai-stp:artifact:v1",
    "ai-stp:attestation:v1",
    "ai-stp:bundle:v1",
    "ai-stp:cli-registry:v1",
    "ai-stp:component-adaptation:v1",
    "ai-stp:component-eval-plan:v1",
    "ai-stp:component-eval-result:v1",
    "ai-stp:component-logical:v1",
    "ai-stp:component-source-binding:v1",
    "ai-stp:corporate-inventory-location:v1",
    "ai-stp:github-request:v1",
    "ai-stp:gitlab-request:v1",
    "ai-stp:installation-inventory:v1",
    "ai-stp:installation-operation:v1",
    "ai-stp:mapping-apply:v1",
    "ai-stp:multi-root-transaction:v1",
    "ai-stp:native-discovery:v1",
    "ai-stp:official-manifest:v1",
    "ai-stp:passport:v1",
    "ai-stp:path-inventory:v1",
    "ai-stp:plan:v1",
    "ai-stp:portability-claim:v1",
    "ai-stp:profile-publish:v1",
    "ai-stp:project-configuration:v1",
    "ai-stp:project-index:v1",
    "ai-stp:project-toolchain:v1",
    "ai-stp:provider-plan:v3",
    "ai-stp:provider-projection:v3",
    "ai-stp:publication-set:v1",
    "ai-stp:revision:v1",
    "ai-stp:runtime-usage-export:v1",
    "ai-stp:scaffold-plan:v1",
    "ai-stp:schema-body:v1",
    "ai-stp:selection-snapshot:v1",
    "ai-stp:seo-profile:v1",
    "ai-stp:seo-snapshot:v1",
    "ai-stp:setup-eval-plan:v1",
    "ai-stp:setup-eval-result:v1",
    "ai-stp:setup-export:v1",
    "ai-stp:setup-harness-invariant:v1",
    "ai-stp:setup-scaffold-plan:v1",
    "ai-stp:skill-package:v1",
    "ai-stp:standard-inventory:v1",
    "ai-stp:store-port-plan:v1",
    "ai-stp:target-assessment-key:v1",
];
