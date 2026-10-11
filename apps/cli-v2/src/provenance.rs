//! Offline PEP 740 verification against caller-owned trust material and policy.
//! Authenticated trust refresh is owned by provider::trust; installation is separate.

use base64::{Engine, engine::general_purpose::STANDARD};
use serde::Deserialize;
use serde_json::{Value, json};
use sigstore_verify::{
    VerificationPolicy, Verifier,
    trust_root::TrustedRoot,
    types::{Bundle, Sha256Hash},
};

use crate::{
    canonical,
    error::{Failure, Result},
};

#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
pub struct Publisher {
    pub repository: String,
    pub workflow: String,
    pub environment: String,
}

#[derive(Debug)]
pub struct VerifiedPublisher {
    pub publisher: Publisher,
    pub source_commit: String,
}

#[derive(Deserialize)]
struct Provenance {
    version: u32,
    attestation_bundles: Vec<AttestationBundle>,
}

#[derive(Deserialize)]
struct AttestationBundle {
    publisher: IndexPublisher,
    attestations: Vec<Attestation>,
}

#[derive(Deserialize)]
struct IndexPublisher {
    kind: String,
    #[serde(flatten)]
    identity: Publisher,
}

#[derive(Deserialize)]
struct Attestation {
    version: u32,
    envelope: Envelope,
    verification_material: Material,
}

#[derive(Deserialize)]
struct Envelope {
    statement: String,
    signature: String,
}

#[derive(Deserialize)]
struct Material {
    certificate: String,
    transparency_entries: Vec<Value>,
}

fn refused() -> Failure {
    Failure::precondition(
        "no attestation binds the artifact to the pinned publisher and verified transparency evidence",
    )
}

/// The digest must be computed from the artifact by the caller. This function
/// neither downloads nor executes it. A successful result never comes from
/// unsigned index metadata: policy is checked again against verified claims.
pub fn verify(
    filename: &str,
    sha256: [u8; 32],
    document: &[u8],
    publisher: &Publisher,
    trusted_root: &TrustedRoot,
) -> Result<VerifiedPublisher> {
    let provenance: Provenance =
        serde_json::from_value(canonical::parse(document)?).map_err(|_| refused())?;
    if provenance.version != 1
        || provenance.attestation_bundles.is_empty()
        || provenance.attestation_bundles.len() > 16
    {
        return Err(refused());
    }
    let verifier = Verifier::new(trusted_root).map_err(|_| refused())?;
    for bundle in provenance.attestation_bundles {
        if bundle.publisher.kind != "GitHub" || bundle.publisher.identity != *publisher {
            continue;
        }
        if bundle.attestations.len() > 16 {
            return Err(refused());
        }
        for attestation in bundle.attestations {
            if let Ok(identity) =
                verify_attestation(&verifier, filename, sha256, &attestation, publisher)
            {
                return Ok(identity);
            }
        }
    }
    Err(refused())
}

fn verify_attestation(
    verifier: &Verifier,
    filename: &str,
    sha256: [u8; 32],
    attestation: &Attestation,
    publisher: &Publisher,
) -> Result<VerifiedPublisher> {
    if attestation.version != 1
        || attestation
            .verification_material
            .transparency_entries
            .is_empty()
    {
        return Err(refused());
    }
    let statement_bytes = STANDARD
        .decode(&attestation.envelope.statement)
        .map_err(|_| refused())?;
    let statement = canonical::parse(&statement_bytes)?;
    let subjects = statement["subject"].as_array().ok_or_else(refused)?;
    let expected_hex: String = sha256.iter().map(|byte| format!("{byte:02x}")).collect();
    if statement["_type"] != "https://in-toto.io/Statement/v1"
        || !matches!(
            statement["predicateType"].as_str(),
            Some(
                "https://docs.pypi.org/attestations/publish/v1" | "https://slsa.dev/provenance/v1"
            )
        )
        || subjects.len() != 1
        || subjects[0]["name"] != filename
        || subjects[0]["digest"]["sha256"] != expected_hex
    {
        return Err(refused());
    }
    // PEP 740 stores the DSSE payload/signature separately. Preserve their exact
    // bytes; project canonicalization is never used to reconstruct signed data.
    let converted = json!({
        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "verificationMaterial": {
            "certificate": {"rawBytes": attestation.verification_material.certificate},
            "tlogEntries": attestation.verification_material.transparency_entries,
        },
        "dsseEnvelope": {"payloadType": "application/vnd.in-toto+json",
            "payload": attestation.envelope.statement,
            "signatures": [{"sig": attestation.envelope.signature, "keyid": ""}]},
    });
    let bundle = Bundle::from_json(&converted.to_string()).map_err(|_| refused())?;
    let policy = VerificationPolicy::any_identity()
        .require_issuer("https://token.actions.githubusercontent.com");
    let verified = verifier
        .verify(Sha256Hash::new(sha256), &bundle, &policy)
        .map_err(|_| refused())?;
    if !verified.certificate_verified() || !verified.sct_verified() || !verified.tlog_verified() {
        return Err(refused());
    }
    let claims = &verified.certificate().ok_or_else(refused)?.ci_claims;
    let repository_uri = format!("https://github.com/{}", publisher.repository);
    if claims.source_repository_uri.as_deref() != Some(repository_uri.as_str())
        || claims.deployment_environment.as_deref() != Some(publisher.environment.as_str())
    {
        return Err(refused());
    }
    let workflow_matches = [
        claims.source_repository_ref.as_deref(),
        claims.source_repository_digest.as_deref(),
    ]
    .into_iter()
    .flatten()
    .any(|suffix| {
        !suffix.is_empty()
            && claims.build_config_uri.as_deref()
                == Some(
                    format!(
                        "{repository_uri}/.github/workflows/{}@{suffix}",
                        publisher.workflow
                    )
                    .as_str(),
                )
    });
    if !workflow_matches {
        return Err(refused());
    }
    let commit = claims.source_repository_digest.clone().unwrap_or_default();
    if !commit.is_empty()
        && (commit.len() != 40
            || !commit
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)))
    {
        return Err(refused());
    }
    Ok(VerifiedPublisher {
        publisher: publisher.clone(),
        source_commit: commit,
    })
}
