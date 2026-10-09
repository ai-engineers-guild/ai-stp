//! Exact Go module observations, with upstream file-tree checksums and no execution.

use std::{collections::BTreeMap, io::Read};

use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use url::Url;

use crate::sources::{archive, snapshot, transport};
use crate::{
    artifacts::{self, Member},
    canonical, digest,
    error::{Failure, Result},
    wire,
};

const MAX_ARCHIVE: usize = 20 * 1024 * 1024;
const MAX_EXPANDED: u64 = 50 * 1024 * 1024;

fn invalid() -> Failure {
    Failure::precondition("the Go source identity, archive or checksum evidence was refused")
}

fn number(value: &str) -> bool {
    !value.is_empty()
        && value.bytes().all(|b| b.is_ascii_digit())
        && (value.len() == 1 || !value.starts_with('0'))
}

fn version(value: &str) -> bool {
    let value = value.strip_suffix("+incompatible").unwrap_or(value);
    let Some(value) = value.strip_prefix('v') else {
        return false;
    };
    let (core, pre) = value
        .split_once('-')
        .map_or((value, None), |(a, b)| (a, Some(b)));
    let parts = core.split('.').collect::<Vec<_>>();
    parts.len() == 3
        && parts.iter().all(|part| number(part))
        && pre.is_none_or(|pre| {
            pre.split('.').all(|part| {
                !part.is_empty()
                    && part.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
                    && (!part.bytes().all(|b| b.is_ascii_digit()) || number(part))
            })
        })
}

fn coordinate(name: &str, selected: &str) -> Result<(String, String)> {
    let domain = name.split('/').next().unwrap_or_default();
    if name.is_empty()
        || name.len() > 256
        || selected.len() > 256
        || !version(selected)
        || !domain.contains('.')
        || domain.starts_with(['.', '-'])
        || !domain
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'-' | b'.'))
        || name.split('/').any(|part| {
            part.is_empty()
                || matches!(part, "." | "..")
                || part.ends_with('.')
                || !part
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'-' | b'_' | b'~'))
        })
    {
        return Err(Failure::input(
            "Go sources require a bounded module path and exact canonical vX.Y.Z version",
        ));
    }
    let escape = |value: &str| {
        value
            .chars()
            .map(|c| {
                if c.is_ascii_uppercase() {
                    format!("!{}", c.to_ascii_lowercase())
                } else {
                    c.to_string()
                }
            })
            .collect::<String>()
    };
    Ok((escape(name), escape(selected)))
}

fn module_archive(bytes: &[u8], name: &str, version: &str) -> Result<(String, Vec<Member>)> {
    let mut archive = archive::open(bytes, MAX_ARCHIVE)?;
    let prefix = format!("{name}@{version}/");
    let mut names = BTreeMap::new();
    let mut total = 0u64;
    for index in 0..archive.len() {
        let member = archive.by_index(index).map_err(|_| invalid())?;
        let name = std::str::from_utf8(member.name_raw()).map_err(|_| invalid())?;
        if name != member.name()
            || !name.starts_with(&prefix)
            || name.contains('\\')
            || name.chars().any(char::is_control)
            || name
                .strip_suffix('/')
                .unwrap_or(name)
                .split('/')
                .any(|part| part.is_empty() || matches!(part, "." | ".."))
            || member.encrypted()
            || !matches!(
                member.unix_mode().unwrap_or(0o644) & 0o170000,
                0 | 0o100000 | 0o040000
            )
            || !matches!(
                member.compression(),
                zip::CompressionMethod::Stored | zip::CompressionMethod::Deflated
            )
            || names.insert(name.to_owned(), index).is_some()
        {
            return Err(invalid());
        }
        total = total
            .checked_add(member.size())
            .filter(|size| *size <= MAX_EXPANDED)
            .ok_or_else(invalid)?;
    }
    let mut summary = Sha256::new();
    let mut files = Vec::new();
    for (name, index) in names {
        let mut member = archive.by_index(index).map_err(|_| invalid())?;
        let relative = name.strip_prefix(&prefix).ok_or_else(invalid)?;
        // Only module-root metadata is a source projection. Nested testdata is not.
        let selected = matches!(relative, "go.mod" | "go.sum") && !member.is_dir();
        let size = member.size();
        if selected && size > artifacts::MAX_FILE_BYTES as u64 {
            return Err(invalid());
        }
        let mut payload = Vec::new();
        let mut content_hash = Sha256::new();
        let mut length = 0u64;
        let mut buffer = [0u8; 65536];
        loop {
            let limit = (size - length + 1).min(buffer.len() as u64) as usize;
            let read = member.read(&mut buffer[..limit]).map_err(|_| invalid())?;
            if read == 0 {
                break;
            }
            length += read as u64;
            if length > size {
                return Err(invalid());
            }
            content_hash.update(&buffer[..read]);
            if selected {
                payload.extend_from_slice(&buffer[..read]);
            }
        }
        if length != size {
            return Err(invalid());
        }
        let hex = content_hash
            .finalize()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        summary.update(format!("{hex}  {name}\n").as_bytes());
        if selected {
            files.push(Member {
                path: relative.into(),
                bytes: payload,
                mode: 0o644,
            });
        }
    }
    Ok((format!("h1:{}", STANDARD.encode(summary.finalize())), files))
}

fn checksum(bytes: &[u8], name: &str, version: &str) -> Result<String> {
    let mut found = None;
    for line in std::str::from_utf8(bytes).map_err(|_| invalid())?.lines() {
        let mut parts = line.split_whitespace();
        if parts.next() != Some(name) || parts.next() != Some(version) {
            continue;
        }
        let value = parts.next().ok_or_else(invalid)?;
        if parts.next().is_some() || found.is_some() {
            return Err(invalid());
        }
        let encoded = value.strip_prefix("h1:").ok_or_else(invalid)?;
        let hash = STANDARD.decode(encoded).map_err(|_| invalid())?;
        if hash.len() != 32 || STANDARD.encode(&hash) != encoded {
            return Err(invalid());
        }
        found = Some(value.to_owned());
    }
    found.ok_or_else(invalid)
}

pub(super) fn fetch(name: &str, selected: &str) -> Result<Value> {
    let (module, escaped) = coordinate(name, selected)?;
    let client = transport::Client::new(transport::Service::Go);
    let url = |suffix: &str| {
        Url::parse(&format!(
            "https://proxy.golang.org/{module}/@v/{escaped}.{suffix}"
        ))
        .map_err(|_| invalid())
    };
    let info = wire::parse(&client.get(url("info")?, 2 * 1024 * 1024)?)?;
    if info["Version"] != selected {
        return Err(invalid());
    }
    let bytes = client.get(url("zip")?, MAX_ARCHIVE as u64)?;
    let (zip_hash, files) = module_archive(&bytes, name, selected)?;
    let lookup = client.get(
        Url::parse(&format!("https://sum.golang.org/lookup/{module}@{escaped}"))
            .map_err(|_| invalid())?,
        2 * 1024 * 1024,
    )?;
    let sumdb_hash = checksum(&lookup, name, selected)?;
    if zip_hash != sumdb_hash {
        return Err(invalid());
    }
    let archive_digest = digest::bytes("ai-stp:artifact:v1", &bytes)?;
    // Historical modules can contain no root metadata. Do not synthesize a go.mod.
    let (component_digest, paths, artifact) = if files.is_empty() {
        (archive_digest.clone(), Vec::new(), Value::Null)
    } else {
        let encoded = snapshot::encode(files)?;
        (encoded.digest, encoded.paths, encoded.artifact)
    };
    let report = json!({"schema_version":1,"snapshot":{
        "kind":"package","canonical_coordinate":format!("package:go:{name}@{selected}"),
        "exact_identity":selected,"archive_digest":archive_digest,"component_digest":component_digest,
        "file_paths":paths,"package_evidence":{"ecosystem":"go","module":name,"zip_hash":zip_hash,"sumdb_hash":sumdb_hash},
        "fetched_at":format!("{:.3}",jiff::Timestamp::now()),
        "author_verified":false,"component_verified":false,"target_write":false},
        "artifact":artifact,"provenance":"package_registry_observed","network_accessed":true,"filesystem_accessed":false});
    canonical::bytes(&report)?;
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        error::Error,
        io::{Cursor, Write},
    };

    fn zip(
        entries: &[(&str, &[u8])],
        method: zip::CompressionMethod,
    ) -> std::result::Result<Vec<u8>, Box<dyn Error>> {
        let mut writer = zip::ZipWriter::new(Cursor::new(Vec::new()));
        let options = zip::write::SimpleFileOptions::default()
            .compression_method(method)
            .unix_permissions(0o644);
        for (name, bytes) in entries {
            writer.start_file(*name, options)?;
            writer.write_all(bytes)?;
        }
        Ok(writer.finish()?.into_inner())
    }

    #[test]
    fn upstream_go_goldens_bind_original_names_and_content()
    -> std::result::Result<(), Box<dyn Error>> {
        // Independently executed golang.org/x/mod v0.28.0 HashZip and EscapeVersion.
        for (version, escaped, expected) in [
            (
                "v1.2.3",
                "v1.2.3",
                "h1:fiBHkuZvtmSvjRNZhE5mIC23iwt/yZCPpSvQE/ZV85Q=",
            ),
            (
                "v1.2.3-RC1",
                "v1.2.3-!r!c1",
                "h1:exP8QAcop2iu9+POF17z1MHLGAP4XzJ3xdEdvKWyxYc=",
            ),
        ] {
            let name = "github.com/Azure/mod";
            assert_eq!(
                coordinate(name, version)?,
                ("github.com/!azure/mod".into(), escaped.into())
            );
            let root = format!("{name}@{version}/go.mod");
            let readme = format!("{name}@{version}/README.md");
            for method in [
                zip::CompressionMethod::Stored,
                zip::CompressionMethod::Deflated,
            ] {
                let mut entries: Vec<(&str, &[u8])> = vec![
                    (&root, b"module github.com/Azure/mod\n"),
                    (&readme, b"Module source proof.\n"),
                ];
                if method == zip::CompressionMethod::Deflated {
                    entries.reverse();
                }
                let bytes = zip(&entries, method)?;
                let (hash, files) = module_archive(&bytes, name, version)?;
                assert_eq!(hash, expected);
                assert_eq!(
                    files,
                    vec![Member {
                        path: "go.mod".into(),
                        bytes: b"module github.com/Azure/mod\n".to_vec(),
                        mode: 0o644
                    }]
                );
                assert_eq!(snapshot::encode(files)?.paths, ["go.mod"]);
                let line = format!("{name} {version} {expected}\n");
                assert_eq!(checksum(line.as_bytes(), name, version)?, expected);
                assert!(checksum(line.repeat(2).as_bytes(), name, version).is_err());
                assert!(checksum(line.as_bytes(), name, "v9.0.0").is_err());
                assert!(module_archive(&bytes, name, "v9.0.0").is_err());
                assert!(module_archive(&bytes[..bytes.len() - 1], name, version).is_err());
            }
        }
        Ok(())
    }

    #[test]
    fn module_bounds_refuse_ambiguous_inputs_and_keep_root_metadata()
    -> std::result::Result<(), Box<dyn Error>> {
        for version in [
            "main",
            "latest",
            "v1",
            "v01.2.3",
            "v1.2.3-01",
            "v1.2.3+meta",
            "v1.2.3/../../x",
            "v1.2.3 ",
        ] {
            assert!(fetch("example.com/mod", version).is_err());
        }
        for name in [
            "https://example.com/mod",
            "example.com/../mod",
            "example.com/!m",
            "Example.com/mod",
            ".example.com/mod",
            "example.com/mod?x",
            "example.com/mod\\x",
            "example.com/mód",
        ] {
            assert!(fetch(name, "v1.2.3").is_err());
        }
        assert!(coordinate("example.com/mod", "v2.0.0+incompatible").is_ok());
        let name = "example.com/mod";
        let version = "v1.2.3";
        let root = "example.com/mod@v1.2.3/go.mod";
        let nested = "example.com/mod@v1.2.3/testdata/go.mod";
        let bytes = zip(
            &[
                (nested, b"nested"),
                (root, b"root"),
                ("example.com/mod@v1.2.3/data.bin", b"\0\xff"),
            ],
            zip::CompressionMethod::Deflated,
        )?;
        let (_, files) = module_archive(&bytes, name, version)?;
        assert_eq!(files.len(), 1);
        assert_eq!(files[0].bytes, b"root");
        assert!(
            module_archive(
                &zip(&[(nested, b"nested")], zip::CompressionMethod::Stored)?,
                name,
                version
            )?
            .1
            .is_empty()
        );
        for path in [
            "other/mod@v1.2.3/go.mod",
            "example.com/mod@v1.2.3/../go.mod",
            "example.com/mod@v1.2.3/double//",
            "example.com/mod@v1.2.3/a\nb",
        ] {
            assert!(
                module_archive(
                    &zip(&[(path, b"no")], zip::CompressionMethod::Stored)?,
                    name,
                    version
                )
                .is_err()
            );
        }
        let mut excessive = zip(&[(root, b"root")], zip::CompressionMethod::Stored)?;
        let (_, start) = archive::directory(&excessive, MAX_ARCHIVE)?;
        excessive[start + 24..start + 28]
            .copy_from_slice(&u32::try_from(MAX_EXPANDED + 1)?.to_le_bytes());
        assert!(module_archive(&excessive, name, version).is_err());
        let mut linked = zip::ZipWriter::new(Cursor::new(Vec::new()));
        linked.add_symlink(root, "/outside", zip::write::SimpleFileOptions::default())?;
        assert!(module_archive(&linked.finish()?.into_inner(), name, version).is_err());
        for address in ["https://proxy.golang.org/x", "https://sum.golang.org/x"] {
            assert!(transport::allowed(
                transport::Service::Go,
                &Url::parse(address)?
            ));
        }
        for address in [
            "http://proxy.golang.org/x",
            "https://api.github.com/x",
            "https://token@proxy.golang.org/x",
            "https://proxy.golang.org:8443/x",
        ] {
            assert!(!transport::allowed(
                transport::Service::Go,
                &Url::parse(address)?
            ));
        }
        assert!(checksum(b"example.com/mod v1.2.3 h1:invalid\n", name, version).is_err());
        Ok(())
    }
}
