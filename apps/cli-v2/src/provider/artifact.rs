//! Exact provider bytes authenticated against compiled publisher policy.

use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use super::{trust::Material, wheel};
use crate::{
    digest,
    error::{Failure, Result},
    provenance,
    sources::package::pypi,
};

mod policy;

/// Construction requires current authenticated trust and verified artifact bytes.
/// Persisting the report does not persist this authority: reopening must verify again.
pub struct Artifact<'a> {
    trust: &'a Material,
    payload: wheel::Payload,
    report: Value,
}

impl Artifact<'_> {
    pub fn executable(&self) -> Result<&[u8]> {
        self.trust.root()?;
        Ok(&self.payload.executable)
    }

    pub fn executable_name(&self) -> &str {
        &self.payload.executable_name
    }

    pub fn report(&self) -> &Value {
        &self.report
    }
}

fn refused() -> Failure {
    Failure::precondition("the exact provider artifact or compiled publisher policy was refused")
}

/// Verify explicit bytes without executing package code or writing a harness.
pub fn verify<'a>(
    harness: &str,
    version: &str,
    platform: &str,
    archive: &[u8],
    document: &[u8],
    trust: &'a Material,
) -> Result<Artifact<'a>> {
    let policy::Request {
        project,
        filename,
        publisher,
        sequence,
        policy_id,
    } = policy::request(harness, version, platform)?;
    if archive.is_empty() || archive.len() > 64 * 1024 * 1024 || document.len() > 1024 * 1024 {
        return Err(refused());
    }
    let identity = provenance::verify(
        &filename,
        Sha256::digest(archive).into(),
        document,
        &publisher,
        trust.root()?,
    )?;
    if identity.source_commit.len() != 40 {
        return Err(refused());
    }
    let payload = wheel::inspect(archive, &project, version, platform)?;
    trust.root()?;
    let report = json!({"harness_id":harness,"project":project,"version":version,"platform":platform,
        "filename":filename,"archive_digest":digest::sha256(archive),"archive_bytes":archive.len(),
        "executable_name":payload.executable_name,"executable_digest":digest::sha256(&payload.executable),"executable_bytes":payload.executable.len(),"license":payload.license,
        "publisher":{"repository":publisher.repository,"workflow":publisher.workflow,"environment":publisher.environment},
        "source_commit":identity.source_commit,"policy_digest":digest::sha256(policy::POLICY.as_bytes()),"policy_id":policy_id,"release_sequence":sequence,"trust_level":"verified_publisher","trust":trust.report()});
    Ok(Artifact {
        trust,
        payload,
        report,
    })
}

/// Fetch exactly one non-yanked wheel and its PEP 740 provenance from PyPI.
pub fn fetch<'a>(
    harness: &str,
    version: &str,
    platform: &str,
    trust: &'a Material,
) -> Result<Artifact<'a>> {
    trust.root()?;
    let policy::Request {
        project, filename, ..
    } = policy::request(harness, version, platform)?;
    let (held, document) =
        pypi::attested_file(&project, version, &filename, wheel::platform_tag(platform)?)?;
    let mut artifact = verify(harness, version, platform, &held.bytes, &document, trust)?;
    artifact.report["registry_observation"] = held.observation;
    Ok(artifact)
}
