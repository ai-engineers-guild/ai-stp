//! Independent extraction of the bytes and ownership to verify after component apply.

use std::collections::BTreeMap;

use serde_json::{Value, json};

use super::invalid;
use crate::{archive, digest, error::Result, passport, provider::plan::Binding, wire};

pub(super) struct File {
    pub bytes: Vec<u8>,
    pub mode: u32,
    pub contribution: Option<Value>,
}

pub(super) struct Bundle {
    pub binding: Binding,
    pub setup: Value,
    pub adaptations: Vec<Value>,
    pub files: BTreeMap<String, File>,
}

impl Bundle {
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
            if !super::effects::valid_path(path)
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
                    contribution: file.get("contribution").cloned(),
                },
            );
        }
        if files.len() != members.len() || files.len() > 2000 {
            return Err(invalid());
        }
        Ok(Self {
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
