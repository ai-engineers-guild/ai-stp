//! Exact crate bytes and root Cargo manifests; registry ranges are not a solved graph.

use serde_json::{Value, json};
use url::Url;

use super::{
    metadata::{exact_version, tar_snapshot},
    tarfiles,
};
use crate::{
    digest,
    error::{Failure, Result},
    sources::transport::{Client, Service},
    wire,
};

fn invalid() -> Failure {
    Failure::precondition("the crate identity, archive or checksum observation was refused")
}

fn coordinate(name: &str, version: &str) -> Result<()> {
    if name.is_empty()
        || name.len() > 64
        || !name.as_bytes()[0].is_ascii_alphabetic()
        || !name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'))
        || !exact_version(version)
    {
        return Err(Failure::input(
            "crates.io requires an exact crate name and semantic version",
        ));
    }
    Ok(())
}

struct Release {
    checksum: String,
    size: u64,
    yanked: bool,
}

fn select(metadata: &Value, name: &str, version: &str) -> Result<Release> {
    let release = &metadata["version"];
    if release["crate"] != name || release["num"] != version {
        return Err(invalid());
    }
    let checksum = release["checksum"]
        .as_str()
        .filter(|text| {
            text.len() == 64 && text.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
        })
        .ok_or_else(invalid)?;
    Ok(Release {
        checksum: checksum.into(),
        size: release["crate_size"]
            .as_u64()
            .filter(|size| *size > 0 && *size <= tarfiles::MAX_ARCHIVE)
            .ok_or_else(invalid)?,
        yanked: release["yanked"].as_bool().ok_or_else(invalid)?,
    })
}

fn report(name: &str, version: &str, release: Release, archive: &[u8]) -> Result<Value> {
    if archive.len() as u64 != release.size
        || digest::sha256(archive) != format!("sha256:{}", release.checksum)
    {
        return Err(invalid());
    }
    let files = tarfiles::read(
        archive,
        &format!("{name}-{version}/"),
        &["Cargo.toml", "Cargo.lock"],
    )?;
    let manifest = files
        .iter()
        .find(|file| file.path == "Cargo.toml")
        .ok_or_else(invalid)?;
    let manifest = std::str::from_utf8(&manifest.bytes)
        .map_err(|_| invalid())?
        .parse::<toml_edit::DocumentMut>()
        .map_err(|_| invalid())?;
    if manifest
        .get("package")
        .and_then(|package| package.get("name"))
        .and_then(toml_edit::Item::as_str)
        != Some(name)
        || manifest
            .get("package")
            .and_then(|package| package.get("version"))
            .and_then(toml_edit::Item::as_str)
            != Some(version)
    {
        return Err(invalid());
    }
    let lock = files
        .iter()
        .any(|file| file.path == "Cargo.lock")
        .then_some("Cargo.lock");
    let mut value = tar_snapshot(
        "crates.io",
        name,
        version,
        archive,
        files,
        json!({"ecosystem":"crates.io","registry_checksum":release.checksum,"lockfile_name":lock,"resolved_graph":{}}),
    )?;
    value["distribution_yanked"] = release.yanked.into();
    value["dependency_resolution_performed"] = false.into();
    Ok(value)
}

pub(super) fn fetch(name: &str, version: &str) -> Result<Value> {
    coordinate(name, version)?;
    let client = Client::new(Service::Crates);
    let endpoint = Url::parse(&format!("https://crates.io/api/v1/crates/{name}/{version}"))
        .map_err(|_| invalid())?;
    let metadata = wire::parse(&client.get(endpoint, 2 * 1024 * 1024)?)?;
    let release = select(&metadata, name, version)?;
    let url = Url::parse(&format!(
        "https://static.crates.io/crates/{name}/{name}-{version}.crate"
    ))
    .map_err(|_| invalid())?;
    let bytes = client.get(url, release.size)?;
    report(name, version, release, &bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::error::Error;

    #[test]
    fn archived_identity_checksum_and_lock_presence_bind_the_observation()
    -> std::result::Result<(), Box<dyn Error>> {
        let archive = tarfiles::fixture(&[
            (
                "demo-1.2.3/tests/Cargo.toml",
                b"invalid nested fixture",
                tar::EntryType::Regular,
            ),
            (
                "demo-1.2.3/Cargo.toml",
                b"[package]\nname='demo'\nversion='1.2.3'\n[dependencies]\nother='^2'\n",
                tar::EntryType::Regular,
            ),
            (
                "demo-1.2.3/Cargo.lock",
                b"version = 4\n",
                tar::EntryType::Regular,
            ),
        ])?;
        let metadata = json!({"version":{"crate":"demo","num":"1.2.3","checksum":digest::sha256(&archive).trim_start_matches("sha256:"),"crate_size":archive.len(),"yanked":true}});
        coordinate("demo", "1.2.3")?;
        for version in ["0.0.0", "1.2.3-RC.1", "1.2.3+001", "1.2.3-beta.0+build.2"] {
            assert!(exact_version(version));
        }
        for version in ["01.2.3", "1.2.3-01", "1.2.3-", "1.2.3+", "1.2.3+a+b", "1.2"] {
            assert!(!exact_version(version));
        }

        let value = report(
            "demo",
            "1.2.3",
            select(&metadata, "demo", "1.2.3")?,
            &archive,
        )?;
        assert_eq!(
            value["snapshot"]["file_paths"],
            json!(["Cargo.lock", "Cargo.toml"])
        );
        assert_eq!(
            value["snapshot"]["package_evidence"]["resolved_graph"],
            json!({})
        );
        assert_eq!(
            value["snapshot"]["package_evidence"]["lockfile_name"],
            "Cargo.lock"
        );
        assert_eq!(value["distribution_yanked"], true);
        assert_eq!(value["dependency_resolution_performed"], false);
        assert!(select(&metadata, "other", "1.2.3").is_err());
        assert!(select(&metadata, "demo", "1.2.4").is_err());
        assert!(
            report(
                "demo",
                "1.2.3",
                select(&metadata, "demo", "1.2.3")?,
                b"changed"
            )
            .is_err()
        );
        let wrong = tarfiles::fixture(&[(
            "demo-1.2.3/Cargo.toml",
            b"[package]\nname='other'\nversion='1.2.3'\n",
            tar::EntryType::Regular,
        )])?;
        let release = Release {
            checksum: digest::sha256(&wrong).trim_start_matches("sha256:").into(),
            size: wrong.len() as u64,
            yanked: false,
        };
        assert!(report("demo", "1.2.3", release, &wrong).is_err());
        for (name, version) in [
            ("../demo", "1.2.3"),
            ("demo", "latest"),
            ("demo", "1.2.3-01"),
        ] {
            assert!(coordinate(name, version).is_err());
        }
        Ok(())
    }
}
