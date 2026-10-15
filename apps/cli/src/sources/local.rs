//! Exact bounded local source snapshots without native-layout or trust claims.

use std::path::Path;

use serde_json::{Value, json};

use crate::{
    artifacts::{self, Member},
    authoring::source,
    error::{Failure, Result},
};

fn invalid() -> Failure {
    Failure::precondition("a source snapshot requires bounded portable UTF-8 files within its root")
}

pub fn capture(root: &Path, relative: &str) -> Result<Value> {
    if !root.is_absolute() || relative.len() > 512 || !artifacts::safe_path(relative) {
        return Err(Failure::input(
            "source capture requires an absolute root and one safe relative path of at most 512 bytes",
        ));
    }
    let captured = source::capture_external(root, relative)?;
    let files = match captured.format {
        artifacts::TREE_FORMAT => artifacts::decode_tree(&captured.bytes)?,
        artifacts::FILE_FORMAT => vec![Member {
            path: relative.rsplit('/').next().ok_or_else(invalid)?.into(),
            bytes: captured.bytes,
            mode: captured.file_mode.ok_or_else(invalid)?,
        }],
        _ => return Err(invalid()),
    };
    let encoded = super::snapshot::encode(files)?;
    Ok(json!({
        "schema_version":1,
        "snapshot":{
            "kind":"path","canonical_coordinate":format!("path:{relative}"),
            "exact_identity":encoded.digest,"component_digest":encoded.digest,
            "subpath":relative,"file_paths":encoded.paths,
            "author_verified":false,"component_verified":false,"target_write":false,
        },
        "artifact":encoded.artifact,
        "provenance":"local_observed","network_accessed":false,"filesystem_accessed":true,
    }))
}
