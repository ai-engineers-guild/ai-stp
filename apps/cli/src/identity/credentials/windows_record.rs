//! Bounded binary account records in Windows Credential Manager.

use std::io::{Read, Write};

use flate2::{Compression, bufread::GzDecoder, write::GzEncoder};
use zeroize::Zeroizing;

use crate::error::{Failure, Result};

const PREFIX: &[u8] = b"ai-stp:windows-account:gzip:v1\0";
const BLOB_LIMIT: usize = 2560;
const RECORD_LIMIT: usize = 65536;

struct PrivateBuffer(Zeroizing<Vec<u8>>);

impl Write for PrivateBuffer {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.0.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

fn invalid() -> Failure {
    Failure::precondition(
        "the native Windows account record is invalid or exceeds its bounded format",
    )
}

pub(super) fn recognizes(bytes: &[u8]) -> bool {
    bytes.starts_with(PREFIX)
}

pub(super) fn encode(value: &[u8]) -> Result<Zeroizing<Vec<u8>>> {
    if value.is_empty() || value.len() > RECORD_LIMIT {
        return Err(invalid());
    }
    let buffer = PrivateBuffer(Zeroizing::new(PREFIX.to_vec()));
    let mut encoder = GzEncoder::new(buffer, Compression::default());
    encoder.write_all(value).map_err(|_| invalid())?;
    let encoded = encoder.finish().map_err(|_| invalid())?.0;
    if encoded.len() > BLOB_LIMIT {
        return Err(Failure::precondition(
            "the account record exceeds the native Windows credential blob limit",
        )
        .with_details([("native_blob_limit".into(), BLOB_LIMIT.into())]));
    }
    Ok(encoded)
}

pub(super) fn decode(bytes: &[u8]) -> Result<Zeroizing<Vec<u8>>> {
    if !recognizes(bytes) || bytes.len() > BLOB_LIMIT {
        return Err(invalid());
    }
    let mut decoded = Zeroizing::new(Vec::new());
    let mut decoder = GzDecoder::new(&bytes[PREFIX.len()..]);
    (&mut decoder)
        .take(RECORD_LIMIT as u64 + 1)
        .read_to_end(&mut decoded)
        .map_err(|_| invalid())?;
    if decoded.is_empty() || decoded.len() > RECORD_LIMIT || !decoder.get_ref().is_empty() {
        return Err(invalid());
    }
    Ok(decoded)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn account_metadata_fits_without_utf16_expansion_and_roundtrips_exactly() -> Result<()> {
        let record=serde_json::to_vec(&serde_json::json!({
            "plan":{"root":"C:\\Users\\Owner\\AppData\\Local\\ai-stp".repeat(35)},
            "session":{"access_token":"access-canary-0123456789","refresh_token":"refresh-canary-0123456789"}
        })).map_err(|_|invalid())?;
        assert!(record.len() * 2 > BLOB_LIMIT);
        let encoded = encode(&record)?;
        assert!(encoded.len() <= BLOB_LIMIT);
        assert!(recognizes(&encoded));
        assert!(*decode(&encoded)? == record);
        Ok(())
    }

    #[test]
    fn decoding_refuses_corruption_and_oversized_expansion() -> Result<()> {
        let record = vec![b'x'; RECORD_LIMIT];
        let mut encoded = encode(&record)?;
        assert!(*decode(&encoded)? == record);
        let mut trailing = encode(&record)?;
        trailing.extend_from_slice(b"unrecognized trailing bytes");
        assert!(decode(&trailing).is_err());
        let length = encoded.len();
        encoded[length - 8] ^= 1;
        assert!(decode(&encoded).is_err());
        let mut encoder = GzEncoder::new(PREFIX.to_vec(), Compression::default());
        encoder
            .write_all(&vec![b'x'; RECORD_LIMIT + 1])
            .map_err(|_| invalid())?;
        assert!(decode(&encoder.finish().map_err(|_| invalid())?).is_err());
        assert!(decode(b"unrecognized record").is_err());
        Ok(())
    }

    #[test]
    fn incompressible_records_refuse_before_native_credential_publication() {
        let mut value = vec![0; 8192];
        let mut seed = 0x1234_5678u32;
        for byte in &mut value {
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            *byte = seed as u8;
        }
        assert!(encode(&value).is_err());
    }
}
