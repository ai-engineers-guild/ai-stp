//! Shared portable source bytes; local and remote observations keep their own provenance.

use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use serde_json::{Value, json};

use crate::{
    artifacts::{self, Member},
    digest,
    error::{Failure, Result},
};

pub(super) const MAX_BYTES: usize = 8 * 1024 * 1024;

pub(super) struct Encoded {
    pub digest: String,
    pub paths: Vec<String>,
    pub artifact: Value,
}

pub(super) fn encode(mut files: Vec<Member>) -> Result<Encoded> {
    if files.is_empty()
        || files.iter().map(|file| file.bytes.len()).sum::<usize>() > MAX_BYTES
        || files.iter().any(|file| {
            file.path.split('/').count() > 33
                || file.bytes.contains(&0)
                || std::str::from_utf8(&file.bytes).is_err()
        })
    {
        return Err(Failure::precondition(
            "a source snapshot requires bounded portable UTF-8 files",
        ));
    }
    files.sort_by(|a, b| a.path.cmp(&b.path));
    let manifest = files
        .iter()
        .map(|file| {
            Ok(json!({"path":file.path,
        "digest":digest::bytes("ai-stp:artifact:v1", &file.bytes)?,"byte_length":file.bytes.len()}))
        })
        .collect::<Result<Vec<_>>>()?;
    let digest = digest::canonical("ai-stp:artifact:v1", &json!({"files":manifest}))?;
    // Source identity excludes modes; the canonical artifact binds them too.
    let archive = artifacts::encode_tree(&files)?;
    Ok(Encoded {
        digest,
        paths: files.into_iter().map(|file| file.path).collect(),
        artifact: json!({"format":artifacts::TREE_FORMAT,
            "digest":digest::bytes("ai-stp:artifact:v1", &archive)?,
            "size_bytes":archive.len(),"bytes_b64":URL_SAFE_NO_PAD.encode(&archive)}),
    })
}
