use std::error::Error;

use ai_stp_cli_v2::provenance::{self, Publisher};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::Value;
use sigstore_verify::{
    trust_root::{SIGSTORE_PRODUCTION_TRUSTED_ROOT, TrustedRoot},
    types::Sha256Hash,
};

#[test]
fn public_pypi_evidence_and_adversarial_variants() -> Result<(), Box<dyn Error>> {
    let record: Value = serde_json::from_str(include_str!("fixtures/provider.json"))?;
    let original: Value = serde_json::from_str(include_str!("fixtures/provider-provenance.json"))?;
    let expected: Publisher = serde_json::from_value(record["publisher"].clone())?;
    let digest = Sha256Hash::from_hex(record["sha256"].as_str().ok_or("digest")?)?;
    let root = TrustedRoot::from_json(SIGSTORE_PRODUCTION_TRUSTED_ROOT)?;
    let filename = record["filename"].as_str().ok_or("filename")?;
    let sha256 = *digest.as_bytes();
    let accepted = provenance::verify(
        filename,
        sha256,
        &serde_json::to_vec(&original)?,
        &expected,
        &root,
    )?;
    assert_eq!(
        accepted.source_commit,
        record["source_commit"].as_str().ok_or("commit")?
    );

    for case in [
        "digest",
        "filename",
        "repository",
        "workflow",
        "environment",
        "signature",
        "inclusion",
        "promise",
    ] {
        let mut document = original.clone();
        let mut publisher = expected.clone();
        let mut digest = sha256;
        let mut name = filename;
        match case {
            "digest" => digest[0] ^= 1,
            "filename" => name = "other-1.0-py3-none-any.whl",
            "repository" | "workflow" | "environment" => {
                // Also forge the unsigned publisher metadata. A metadata-only
                // comparison would now accept; the signed claims must refuse.
                document["attestation_bundles"][0]["publisher"][case] = "wrong".into();
                match case {
                    "repository" => publisher.repository = "wrong".into(),
                    "workflow" => publisher.workflow = "wrong".into(),
                    _ => publisher.environment = "wrong".into(),
                }
            }
            _ => {
                let attestation = &mut document["attestation_bundles"][0]["attestations"][0];
                let field = match case {
                    "signature" => &mut attestation["envelope"]["signature"],
                    "inclusion" => {
                        &mut attestation["verification_material"]["transparency_entries"][0]["inclusionProof"]
                            ["rootHash"]
                    }
                    _ => {
                        &mut attestation["verification_material"]["transparency_entries"][0]["inclusionPromise"]
                            ["signedEntryTimestamp"]
                    }
                };
                let mut bytes = STANDARD.decode(field.as_str().ok_or("base64")?)?;
                // Keep DER framing intact: this must fail verification, not
                // merely parsing of the signature's sequence tag.
                *bytes.last_mut().ok_or("empty evidence")? ^= 1;
                *field = STANDARD.encode(bytes).into();
            }
        }
        assert!(
            provenance::verify(
                name,
                digest,
                &serde_json::to_vec(&document)?,
                &publisher,
                &root
            )
            .is_err(),
            "accepted {case}"
        );
    }
    Ok(())
}
