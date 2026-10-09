use serde_json::{Value, json};

use super::{File, MAX_BYTES, MAX_FILE_BYTES, MAX_FILES, composition::Composition};
use crate::{
    archive::{self, Entry, Kind, Limits},
    canonical, digest,
    error::Result,
    projection::Scope,
    selection::eligibility::Target,
};

pub(super) fn build(
    passport: &Value,
    target: &Target,
    profile: &Value,
    input_digest: &str,
    bindings: Vec<Value>,
    files: &[File],
    composition: Composition,
) -> Result<(Value, Vec<u8>)> {
    let (composition, conversion) = composition.reports();
    let documents = [
        (
            "setup_passport",
            "setup-passport.json",
            canonical::bytes(passport)?,
        ),
        (
            "composition_report",
            "composition-report.json",
            canonical::bytes(&composition)?,
        ),
        (
            "conversion_report",
            "conversion-report.json",
            canonical::bytes(&conversion)?,
        ),
    ];
    let entries: Vec<_> = files
        .iter()
        .map(|file| {
            json!({"path":file.member.path,"digest":digest::sha256(&file.member.bytes),
        "byte_length":file.member.bytes.len(),"mode":file.member.mode,"owner":file.owner})
        })
        .collect();
    let mut manifest = json!({"schema_version":1,"bundle_format":"ai-stp-bundle/2","protocol_version":1,"builder_version":"1.0",
        "harness_id":target.harness_id,"projection_profile":{"profile_id":profile["profile_id"],"profile_digest":profile["digest"],"target_scope":target.scope},
        "component_adaptations":bindings,"setup":{"stable_id":passport["stable_id"],"version":passport["version"],"passport_digest":digest::canonical("ai-stp:passport:v1", passport)?},
        "input_digest":input_digest,"managed_paths":files.iter().map(|file|&file.member.path).collect::<Vec<_>>(),"files":entries,
        "documents":{},"limits":{"max_files":MAX_FILES,"max_file_bytes":MAX_FILE_BYTES,"max_bundle_bytes":MAX_BYTES},
        "composition_report":composition,"conversion_report":conversion});
    if target.scope != Scope::Global {
        manifest["target_scope"] = json!(target.scope);
    }
    for (key, path, bytes) in &documents {
        manifest["documents"][key] =
            json!({"path":path,"digest":digest::sha256(bytes),"byte_length":bytes.len()});
    }
    manifest["bundle_digest"] = digest::canonical("ai-stp:bundle:v1", &manifest)?.into();
    let manifest_bytes = canonical::bytes(&manifest)?;
    let mut members = vec![Entry {
        path: "bundle.json".into(),
        bytes: manifest_bytes.as_slice().into(),
        mode: 0o644,
        kind: Kind::File,
    }];
    for (_, path, bytes) in &documents {
        members.push(Entry {
            path: (*path).into(),
            bytes: bytes.as_slice().into(),
            mode: 0o644,
            kind: Kind::File,
        });
    }
    members.push(Entry {
        path: "files".into(),
        bytes: (&[][..]).into(),
        mode: 0o755,
        kind: Kind::Directory,
    });
    members.extend(files.iter().map(|file| Entry {
        path: format!("files/{}", file.member.path).into(),
        bytes: file.member.bytes.as_slice().into(),
        mode: file.member.mode,
        kind: Kind::File,
    }));
    members.push(Entry {
        path: "attestations".into(),
        bytes: (&[][..]).into(),
        mode: 0o755,
        kind: Kind::Directory,
    });
    let archive = archive::encode(
        &members,
        Limits {
            entries: MAX_FILES + 6,
            file_bytes: MAX_FILE_BYTES,
            content_bytes: MAX_BYTES,
            archive_bytes: MAX_BYTES,
        },
    )?;
    Ok((manifest, archive))
}
