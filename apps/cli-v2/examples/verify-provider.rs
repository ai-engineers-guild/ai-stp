//! Evidence runner, not an installation command. All inputs are explicit.
use std::{error::Error, fs::File, io::Read, path::PathBuf};

use ai_stp_cli_v2::provenance::{self, Publisher};
use sha2::{Digest, Sha256};
use sigstore_verify::trust_root::{SIGSTORE_PRODUCTION_TRUSTED_ROOT, TrustedRoot};

fn main() -> Result<(), Box<dyn Error>> {
    let arguments: Vec<_> = std::env::args_os().skip(1).collect();
    if arguments.len() != 3 {
        return Err("usage: verify-provider ARTIFACT PROVENANCE PUBLISHER_JSON".into());
    }
    let artifact = PathBuf::from(&arguments[0]);
    let mut reader = File::open(&artifact)?;
    let mut digest = Sha256::new();
    let mut buffer = [0; 65_536];
    loop {
        let size = reader.read(&mut buffer)?;
        if size == 0 {
            break;
        }
        digest.update(&buffer[..size]);
    }
    let publisher: Publisher = serde_json::from_slice(&std::fs::read(&arguments[2])?)?;
    let root = TrustedRoot::from_json(SIGSTORE_PRODUCTION_TRUSTED_ROOT)?;
    let verified = provenance::verify(
        artifact
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or("invalid artifact name")?,
        digest.finalize().into(),
        &std::fs::read(&arguments[1])?,
        &publisher,
        &root,
    )?;
    println!(
        "Verified {} at {}",
        verified.publisher.repository, verified.source_commit
    );
    Ok(())
}
