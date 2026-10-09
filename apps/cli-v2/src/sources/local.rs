//! Exact bounded local source snapshots without native-layout or trust claims.

use std::path::Path;

use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use serde_json::{Value, json};

use crate::{
    artifacts::{self, Member},
    authoring::source,
    digest,
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
    let mut files = match captured.format {
        artifacts::TREE_FORMAT => artifacts::decode_tree(&captured.bytes)?,
        artifacts::FILE_FORMAT => vec![Member {
            path: relative.rsplit('/').next().ok_or_else(invalid)?.into(),
            bytes: captured.bytes,
            mode: captured.file_mode.ok_or_else(invalid)?,
        }],
        _ => return Err(invalid()),
    };
    if files.is_empty()
        || files.iter().map(|file| file.bytes.len()).sum::<usize>() > 8 * 1024 * 1024
        || files.iter().any(|file| {
            file.path.split('/').count() > 33
                || file.bytes.contains(&0)
                || std::str::from_utf8(&file.bytes).is_err()
        })
    {
        return Err(invalid());
    }
    files.sort_by(|a, b| a.path.cmp(&b.path));
    let manifest = files
        .iter()
        .map(|file| {
            Ok(
                json!({"path":file.path,"digest":digest::bytes("ai-stp:artifact:v1", &file.bytes)?,
                "byte_length":file.bytes.len()}),
            )
        })
        .collect::<Result<Vec<_>>>()?;
    let component_digest = digest::canonical("ai-stp:artifact:v1", &json!({"files":manifest}))?;
    // The shared source identity excludes modes. The separate native artifact
    // digest binds paths, original bytes and executable bits together.
    let artifact = artifacts::encode_tree(&files)?;
    let paths: Vec<_> = files.iter().map(|file| &file.path).collect();
    Ok(json!({
        "schema_version":1,
        "snapshot":{
            "kind":"path","canonical_coordinate":format!("path:{relative}"),
            "exact_identity":component_digest,"component_digest":component_digest,
            "subpath":relative,"file_paths":paths,
            "author_verified":false,"component_verified":false,"target_write":false,
        },
        "artifact":{
            "format":artifacts::TREE_FORMAT,
            "digest":digest::bytes("ai-stp:artifact:v1", &artifact)?,
            "size_bytes":artifact.len(),"bytes_b64":URL_SAFE_NO_PAD.encode(&artifact),
        },
        "provenance":"local_observed","network_accessed":false,"filesystem_accessed":true,
    }))
}
