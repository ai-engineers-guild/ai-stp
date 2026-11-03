//! Bounded package extraction shared by native and historical provider operations.
//!
//! Reading validates data; it never authorizes filesystem or corporate effects.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{
    archive, digest,
    error::{Failure, Result},
    passport,
    projection::Scope,
    store::Store,
    wire,
};

fn invalid() -> Failure {
    Failure::precondition("the configuration package is inconsistent with its exact inputs")
}

use crate::bundle::coverage::File;

/// Exact data identity, shared with historical provider plan serialization.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub bundle_format: String,
    pub bundle_digest: String,
    pub artifact_digest: String,
    pub bundle_size: usize,
}

pub struct Package {
    manifest: Value,
    archive_paths: Vec<String>,
    pub binding: Binding,
    pub setup: Value,
    pub adaptations: Vec<Value>,
    pub files: BTreeMap<String, File>,
}

impl Package {
    pub fn read(bytes: &[u8]) -> Result<Self> {
        let entries = archive::decode(
            bytes,
            archive::Limits {
                entries: 2006,
                file_bytes: 4 * 1024 * 1024,
                content_bytes: 64 * 1024 * 1024,
                archive_bytes: 64 * 1024 * 1024,
            },
        )?;
        let first = entries
            .first()
            .filter(|entry| entry.path == "bundle.json")
            .ok_or_else(invalid)?;
        let manifest = wire::parse(&first.bytes)?;
        let mut unsigned = manifest.clone();
        unsigned
            .as_object_mut()
            .ok_or_else(invalid)?
            .remove("bundle_digest");
        if manifest["bundle_format"] != "ai-stp-bundle/2"
            || manifest["bundle_digest"] != digest::canonical("ai-stp:bundle:v1", &unsigned)?
        {
            return Err(invalid());
        }
        documents(&entries, &manifest)?;
        let members: BTreeMap<_, _> = entries
            .iter()
            .filter_map(|entry| entry.path.strip_prefix("files/").map(|path| (path, entry)))
            .collect();
        let mut files = BTreeMap::new();
        for file in manifest["files"].as_array().ok_or_else(invalid)? {
            let path = file["path"].as_str().ok_or_else(invalid)?;
            let entry = members.get(path).ok_or_else(invalid)?;
            if !(crate::archive::safe_path(path) && path.split('/').count() <= 32)
                || entry.kind != archive::Kind::File
                || file["digest"] != digest::sha256(&entry.bytes)
                || file["byte_length"] != entry.bytes.len()
                || file["mode"] != entry.mode
                || entry.mode & 0o400 == 0
                || files.contains_key(path)
            {
                return Err(invalid());
            }
            files.insert(
                path.into(),
                File {
                    bytes: entry.bytes.to_vec(),
                    mode: entry.mode,
                    owner: file["owner"].as_str().ok_or_else(invalid)?.into(),
                    contribution: file.get("contribution").cloned(),
                },
            );
        }
        if files.len() != members.len() || files.len() > 2000 {
            return Err(invalid());
        }
        Ok(Self {
            archive_paths: entries.iter().map(|entry| entry.path.to_string()).collect(),
            manifest: manifest.clone(),
            binding: Binding {
                bundle_format: "ai-stp-bundle/2".into(),
                bundle_digest: manifest["bundle_digest"]
                    .as_str()
                    .ok_or_else(invalid)?
                    .into(),
                artifact_digest: digest::sha256(bytes),
                bundle_size: bytes.len(),
            },
            setup: manifest["setup"].clone(),
            adaptations: manifest["component_adaptations"]
                .as_array()
                .ok_or_else(invalid)?
                .clone(),
            files,
        })
    }

    /// Read a first-party package against the exact host profile and complete
    /// immutable source graph. Host contributions must include their observed
    /// original bytes (or explicit absence); omitted hosts remain unknown.
    pub fn read_native(
        store: &mut Store,
        bytes: &[u8],
        harness: &str,
        scope: Scope,
        hosts: &super::Hosts,
    ) -> Result<Self> {
        let package = Self::read(bytes)?;
        let native = crate::installation::profiles::Profiles::resolve(harness)?;
        let profile = native.profile(scope).ok_or_else(invalid)?;
        let manifest = &package.manifest;
        let expected_profile = json!({
            "profile_id": profile["profile_id"],
            "profile_digest": profile["digest"],
            "target_scope": scope,
        });
        let paths: Vec<_> = package.files.keys().cloned().collect();
        let mut archive_paths = vec![
            "bundle.json".to_owned(),
            "setup-passport.json".into(),
            "composition-report.json".into(),
            "conversion-report.json".into(),
            "files".into(),
        ];
        archive_paths.extend(paths.iter().map(|path| format!("files/{path}")));
        archive_paths.push("attestations".into());
        let bytes_total: usize = package.files.values().map(|file| file.bytes.len()).sum();
        if manifest["schema_version"] != 1
            || manifest["protocol_version"] != 1
            || manifest["builder_version"] != "1.0"
            || manifest["harness_id"] != harness
            || manifest["projection_profile"] != expected_profile
            || manifest
                .get("target_scope")
                .cloned()
                .unwrap_or(json!("global"))
                != json!(scope)
            || manifest["managed_paths"] != json!(paths)
            || manifest["limits"]
                != json!({
                    "max_files": super::MAX_FILES,
                    "max_file_bytes": super::MAX_FILE_BYTES,
                    "max_bundle_bytes": super::MAX_BYTES,
                })
            || !manifest["input_digest"]
                .as_str()
                .is_some_and(crate::provider::plan::hash)
            || package.archive_paths != archive_paths
            || package.files.len() as u64 > profile["max_files"].as_u64().unwrap_or(0)
            || bytes_total as u64 > profile["max_bytes"].as_u64().unwrap_or(0)
            || package
                .files
                .keys()
                .any(|path| !crate::projection::surfaces::covers_path(profile, path))
        {
            return Err(invalid());
        }
        super::coverage::verify_payload(
            store,
            &package.setup,
            harness,
            scope,
            &package.adaptations,
            &package.files,
            hosts,
        )?;
        Ok(package)
    }

    pub fn ownership(&self) -> Result<Value> {
        self.files.iter().map(|(path, file)| {
            Ok(if let Some(claim) = &file.contribution {
                let key = claim["ownership_key"].as_str().ok_or_else(invalid)?;
                let parser = claim["parser_id"].as_str().ok_or_else(invalid)?;
                json!({"path":path,"ownership":"contribution","parser_id":parser,"ownership_keys":[key]})
            } else {
                json!({"path":path,"ownership":"whole","parser_id":null,"ownership_keys":[]})
            })
        }).collect::<Result<Vec<_>>>().map(Value::from)
    }
}

fn documents(entries: &[archive::Entry<'_>], manifest: &Value) -> Result<()> {
    if manifest["documents"]
        .as_object()
        .is_none_or(|documents| documents.len() != 3)
    {
        return Err(invalid());
    }
    for (index, (key, path)) in [
        ("setup_passport", "setup-passport.json"),
        ("composition_report", "composition-report.json"),
        ("conversion_report", "conversion-report.json"),
    ]
    .into_iter()
    .enumerate()
    {
        let entry = entries.get(index + 1).ok_or_else(invalid)?;
        let descriptor = &manifest["documents"][key];
        if entry.path != path
            || entry.kind != archive::Kind::File
            || descriptor
                != &json!({"path":path,"digest":digest::sha256(&entry.bytes),"byte_length":entry.bytes.len()})
        {
            return Err(invalid());
        }
        let document = wire::parse(&entry.bytes)?;
        if key == "setup_passport" {
            passport::versions::validate_document(&document)?;
            if document["kind"] != "setup"
                || document["harness_id"] != manifest["harness_id"]
                || manifest["setup"]
                    != json!({
                        "stable_id":document["stable_id"],"version":document["version"],
                        "passport_digest":digest::canonical("ai-stp:passport:v1", &document)?,
                    })
            {
                return Err(invalid());
            }
        } else if document != manifest[key] {
            return Err(invalid());
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn setup_identity_and_document_bytes_must_match_before_execution()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        use crate::{
            authoring::{Identity, setups},
            store::Store,
        };
        let root = tempfile::tempdir()?;
        let mut store = Store::open(root.path(), true)?;
        let identity = Identity {
            account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
            device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        };
        let at = "2026-10-11T00:00:00.000Z";
        let plan = setups::plan(
            &mut store,
            setups::Request {
                harness_id: "codex".into(),
                name: "Identity proof".into(),
                description: "Verify native setup identity.".into(),
                purpose: "Refuse inconsistent bundle identities.".into(),
                requirements: None,
                members: vec![],
            },
            identity.clone(),
            at,
        )?;
        let passport = &setups::apply(&mut store, &plan, &plan.digest()?, &identity, at)?;
        let mut manifest = json!({"harness_id":passport["harness_id"],
            "setup":{"stable_id":passport["stable_id"],"version":passport["version"],
                "passport_digest":digest::canonical("ai-stp:passport:v1", passport)?},
            "composition_report":{},"conversion_report":{},"documents":{}});
        let mut entries = vec![archive::Entry {
            path: "bundle.json".into(),
            bytes: (&[][..]).into(),
            mode: 0o644,
            kind: archive::Kind::File,
        }];
        for (key, path, value) in [
            ("setup_passport", "setup-passport.json", passport.clone()),
            ("composition_report", "composition-report.json", json!({})),
            ("conversion_report", "conversion-report.json", json!({})),
        ] {
            let bytes = crate::canonical::bytes(&value)?;
            manifest["documents"][key] =
                json!({"path":path,"digest":digest::sha256(&bytes),"byte_length":bytes.len()});
            entries.push(archive::Entry {
                path: path.into(),
                bytes: bytes.into(),
                mode: 0o644,
                kind: archive::Kind::File,
            });
        }
        documents(&entries, &manifest)?;
        let mut substituted = manifest.clone();
        substituted["setup"]["version"] = "999.0".into();
        assert!(documents(&entries, &substituted).is_err());
        substituted = manifest.clone();
        substituted["setup"]["passport_digest"] = digest::sha256(b"another passport").into();
        assert!(documents(&entries, &substituted).is_err());
        entries[1].bytes = b"{}".to_vec().into();
        assert!(documents(&entries, &manifest).is_err());
        Ok(())
    }
}
