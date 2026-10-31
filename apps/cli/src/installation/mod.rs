//! First-party harness configuration transactions owned by ai-stp.
//!
//! Configuration code is part of the native engine. This module carries no
//! vendor executables, version tables, downloaders or updater controls.
//! Its forward writer retains desired bytes, original physical bindings and
//! immutable outcomes; it never captures previous user content.

pub mod error;
pub mod forward;
mod identity;
pub mod journal;
pub mod lock;
pub(crate) mod sqlite;
pub mod target;

pub use error::{Error, ReasonCode, Result};

mod canonical {
    use super::{Error, ReasonCode, Result};

    // Filesystem spellings and retained user bytes are not project NFC data.
    pub(crate) fn to_canonical_bytes(value: &serde_json::Value) -> Result<Vec<u8>> {
        serde_json_canonicalizer::to_vec(value).map_err(|source| {
            Error::new(
                ReasonCode::StateUnavailable,
                "installation state cannot be encoded",
            )
            .with_source(source)
        })
    }
}
