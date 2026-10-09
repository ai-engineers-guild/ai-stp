//! Observe exact npm bytes and declared metadata, without resolving or running packages.

use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha512};
use url::Url;

use super::tarfiles;
use crate::{
    canonical, digest,
    error::{Failure, Result},
    sources::{
        snapshot,
        transport::{Client, Service, allowed},
    },
    wire,
};

const SCRIPT_KEYS: &[&str] = &[
    "preinstall",
    "install",
    "postinstall",
    "prepare",
    "prepublish",
    "prepublishOnly",
    "preuninstall",
    "uninstall",
    "postuninstall",
];

fn invalid() -> Failure {
    Failure::precondition("the npm identity, archive or integrity observation was refused")
}

fn coordinate(name: &str, version: &str) -> Result<()> {
    if name.len() > 214 || version.len() > 256 {
        return Err(Failure::input(
            "npm package coordinates exceed their bounds",
        ));
    }
    let part = |s: &str| {
        !s.is_empty()
            && !s.starts_with(['.', '_'])
            && s.bytes().all(|b| {
                b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'-' | b'_' | b'.')
            })
    };
    let name_ok = if let Some(scoped) = name.strip_prefix('@') {
        scoped
            .split_once('/')
            .is_some_and(|(scope, name)| part(scope) && part(name))
    } else {
        part(name)
    };
    let valid_version = version.len() <= 256 && regex::Regex::new(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$")
        .map_err(|_| invalid())?.is_match(version);
    if name.len() > 214 || !name_ok || !valid_version {
        return Err(Failure::input(
            "npm requires a bounded package name and exact semantic version",
        ));
    }
    Ok(())
}

fn text(value: &Value) -> Result<&str> {
    value
        .as_str()
        .filter(|text| {
            !text.is_empty() && text.len() <= 4096 && !text.chars().any(char::is_control)
        })
        .ok_or_else(invalid)
}

fn strings(value: Option<&Value>) -> Result<Map<String, Value>> {
    let Some(value) = value else {
        return Ok(Map::new());
    };
    let object = value
        .as_object()
        .filter(|object| object.len() <= 1000)
        .ok_or_else(invalid)?;
    object
        .iter()
        .map(|(key, value)| {
            if key.is_empty() || key.len() > 256 || key.chars().any(char::is_control) {
                return Err(invalid());
            }
            let value = value
                .as_str()
                .filter(|value| {
                    value.len() <= 4096
                        && !value
                            .chars()
                            .any(|c| c.is_control() && !matches!(c, '\n' | '\r' | '\t'))
                })
                .ok_or_else(invalid)?;
            Ok((key.clone(), Value::from(value)))
        })
        .collect()
}

fn selected(metadata: &Value, name: &str, version: &str) -> Result<(Url, String)> {
    if metadata["name"] != name || metadata["version"] != version {
        return Err(invalid());
    }
    let dist = &metadata["dist"];
    let integrity = text(&dist["integrity"])?;
    let expected = integrity.strip_prefix("sha512-").ok_or_else(invalid)?;
    let decoded = STANDARD.decode(expected).map_err(|_| invalid())?;
    if decoded.len() != 64 || STANDARD.encode(&decoded) != expected {
        return Err(invalid());
    }
    let url = Url::parse(text(&dist["tarball"])?).map_err(|_| invalid())?;
    let base = name.rsplit('/').next().ok_or_else(invalid)?;
    if !allowed(Service::Npm, &url)
        || url.query().is_some()
        || url.path() != format!("/{name}/-/{base}-{version}.tgz")
    {
        return Err(invalid());
    }
    Ok((url, integrity.to_owned()))
}

fn report(
    metadata: &Value,
    name: &str,
    version: &str,
    integrity: &str,
    archive: &[u8],
) -> Result<Value> {
    if format!("sha512-{}", STANDARD.encode(Sha512::digest(archive))) != integrity {
        return Err(invalid());
    }
    let files = tarfiles::read(
        archive,
        "package/",
        &["package.json", "package-lock.json", "npm-shrinkwrap.json"],
    )?;
    let manifest = wire::parse(
        &files
            .iter()
            .find(|file| file.path == "package.json")
            .ok_or_else(invalid)?
            .bytes,
    )?;
    if manifest["name"] != name || manifest["version"] != version {
        return Err(invalid());
    }
    let mut scripts = strings(manifest.get("scripts"))?;
    scripts.retain(|key, _| SCRIPT_KEYS.contains(&key.as_str()));
    let dependencies = strings(manifest.get("dependencies"))?;
    let entry = manifest.get("main").map(text).transpose()?;
    // npm shrinkwrap takes precedence when both lockfiles are present.
    let lock = ["npm-shrinkwrap.json", "package-lock.json"]
        .into_iter()
        .find(|name| files.iter().any(|file| file.path == *name));
    let repository = metadata
        .get("repository")
        .or_else(|| manifest.get("repository"))
        .and_then(|value| value.as_str().or_else(|| value["url"].as_str()))
        .filter(|value| value.len() <= 512)
        .and_then(|value| {
            Url::parse(
                value
                    .strip_prefix("git+")
                    .unwrap_or(value)
                    .trim_end_matches(".git"),
            )
            .ok()
        })
        .filter(|url| {
            url.scheme() == "https"
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none()
        })
        .map(|url| url.to_string());
    let snapshot = snapshot::encode(files)?;
    let value = json!({"schema_version":1,"snapshot":{
        "kind":"package","canonical_coordinate":format!("package:npm:{name}@{version}"),
        "exact_identity":version,"archive_digest":digest::bytes("ai-stp:artifact:v1",archive)?,
        "component_digest":snapshot.digest,"file_paths":snapshot.paths,
        "package_evidence":{"ecosystem":"npm","integrity":integrity,"entry_point":entry,
            "lifecycle_scripts":scripts,"repository":repository,"lockfile_name":lock,"declared_dependencies":dependencies},
        "fetched_at":format!("{:.3}",jiff::Timestamp::now()),"author_verified":false,"component_verified":false,"target_write":false},
        "artifact":snapshot.artifact,"provenance":"package_registry_observed","network_accessed":true,"filesystem_accessed":false});
    canonical::bytes(&value)?;
    Ok(value)
}

pub(super) fn fetch(name: &str, version: &str) -> Result<Value> {
    coordinate(name, version)?;
    let client = Client::new(Service::Npm);
    let endpoint = Url::parse(&format!("https://registry.npmjs.org/{name}/{version}"))
        .map_err(|_| invalid())?;
    let metadata = wire::parse(&client.get(endpoint, 2 * 1024 * 1024)?)?;
    let (url, integrity) = selected(&metadata, name, version)?;
    let archive = client.get(url, tarfiles::MAX_ARCHIVE)?;
    report(&metadata, name, version, &integrity, &archive)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::error::Error;

    #[test]
    fn exact_integrity_and_root_identity_precede_metadata_observation()
    -> std::result::Result<(), Box<dyn Error>> {
        let manifest = br#"{"name":"@scope/demo","version":"1.2.3","main":"index.js","scripts":{"install":"node setup.js","test":"test"},"dependencies":{"dependency":"^2"}}"#;
        let archive = tarfiles::fixture(&[
            ("package/test/package.json", b"{}", tar::EntryType::Regular),
            ("package/package.json", manifest, tar::EntryType::Regular),
            ("package/package-lock.json", b"{}", tar::EntryType::Regular),
            (
                "package/npm-shrinkwrap.json",
                b"{}",
                tar::EntryType::Regular,
            ),
        ])?;
        let integrity = format!("sha512-{}", STANDARD.encode(Sha512::digest(&archive)));
        let metadata = json!({"name":"@scope/demo","version":"1.2.3","dist":{"integrity":integrity,"tarball":"https://registry.npmjs.org/@scope/demo/-/demo-1.2.3.tgz"}});
        coordinate("@scope/demo", "1.2.3")?;
        selected(&metadata, "@scope/demo", "1.2.3")?;
        let value = report(&metadata, "@scope/demo", "1.2.3", &integrity, &archive)?;
        let evidence = &value["snapshot"]["package_evidence"];
        assert_eq!(evidence["lockfile_name"], "npm-shrinkwrap.json");
        assert_eq!(
            evidence["lifecycle_scripts"],
            json!({"install":"node setup.js"})
        );
        assert_eq!(
            evidence["declared_dependencies"],
            json!({"dependency":"^2"})
        );
        assert_eq!(value["snapshot"]["author_verified"], false);
        assert!(report(&metadata, "other", "1.2.3", &integrity, &archive).is_err());
        assert!(report(&metadata, "@scope/demo", "1.2.3", &integrity, b"changed").is_err());
        assert!(selected(&metadata, "@scope/demo", "1.2.4").is_err());
        for integrity in ["sha1-old", "sha512-invalid", ""] {
            let mut metadata = metadata.clone();
            metadata["dist"]["integrity"] = integrity.into();
            assert!(selected(&metadata, "@scope/demo", "1.2.3").is_err());
        }
        for url in [
            "https://evil.example/file",
            "https://registry.npmjs.org/other/-/other-1.2.3.tgz",
            "http://registry.npmjs.org/@scope/demo/-/demo-1.2.3.tgz",
        ] {
            let mut metadata = metadata.clone();
            metadata["dist"]["tarball"] = url.into();
            assert!(selected(&metadata, "@scope/demo", "1.2.3").is_err());
        }
        for (name, version) in [
            ("../escape", "1.2.3"),
            ("demo", "latest"),
            ("demo", "^1.2.3"),
            ("demo", "1.2.3/other"),
            ("@scope/name/extra", "1.2.3"),
        ] {
            assert!(coordinate(name, version).is_err());
        }
        Ok(())
    }
}
