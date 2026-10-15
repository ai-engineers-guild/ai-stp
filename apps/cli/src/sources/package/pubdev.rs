//! Exact hosted Pub observations; no Dart execution or dependency solving.

use serde_json::{Value, json};
use url::Url;

use super::{
    metadata::{exact_version, tar_snapshot},
    tarfiles,
};
use crate::{
    digest,
    error::{Failure, Result},
    sources::transport::{Client, Service, allowed},
    wire,
};

fn invalid() -> Failure {
    Failure::precondition("the Pub package identity, archive or checksum observation was refused")
}

fn coordinate(name: &str, version: &str) -> Result<()> {
    if name.is_empty()
        || name.len() > 64
        || !name.as_bytes()[0].is_ascii_lowercase()
        || !name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        || !exact_version(version)
    {
        return Err(Failure::input(
            "pub.dev requires an exact package name and semantic version",
        ));
    }
    Ok(())
}

struct Release {
    url: Url,
    checksum: String,
    retracted: bool,
}

fn select(metadata: &Value, name: &str, version: &str) -> Result<Release> {
    if metadata["version"] != version
        || metadata["pubspec"]["name"] != name
        || metadata["pubspec"]["version"] != version
    {
        return Err(invalid());
    }
    let checksum = metadata["archive_sha256"]
        .as_str()
        .filter(|text| {
            text.len() == 64 && text.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
        })
        .ok_or_else(invalid)?;
    let address = metadata["archive_url"]
        .as_str()
        .filter(|text| text.len() <= 2048 && !text.chars().any(char::is_control))
        .ok_or_else(invalid)?;
    let url = Url::parse(address).map_err(|_| invalid())?;
    if !allowed(Service::Pub, &url)
        || url.query().is_some()
        || !match url.host_str() {
            Some("pub.dev") => url.path() == format!("/api/archives/{name}-{version}.tar.gz"),
            Some("storage.googleapis.com") => {
                url.path() == format!("/pub-packages/packages/{name}-{version}.tar.gz")
            }
            _ => false,
        }
    {
        return Err(invalid());
    }
    Ok(Release {
        url,
        checksum: checksum.into(),
        retracted: metadata
            .get("retracted")
            .map(|value| value.as_bool().ok_or_else(invalid))
            .transpose()?
            .unwrap_or(false),
    })
}

fn report(name: &str, version: &str, release: Release, archive: &[u8]) -> Result<Value> {
    if digest::sha256(archive) != format!("sha256:{}", release.checksum) {
        return Err(invalid());
    }
    let files = tarfiles::read(archive, "", &["pubspec.yaml", "pubspec.lock"])?;
    let manifest = files
        .iter()
        .find(|file| file.path == "pubspec.yaml")
        .ok_or_else(invalid)?;
    let text = std::str::from_utf8(&manifest.bytes).map_err(|_| invalid())?;
    let options = serde_saphyr::options! { budget: serde_saphyr::budget! { max_depth:32, max_events:20_000, max_aliases:0, max_documents:1 } };
    let manifest: Value =
        serde_saphyr::from_str_with_options(text, options).map_err(|_| invalid())?;
    if manifest["name"] != name || manifest["version"] != version {
        return Err(invalid());
    }
    let lock = files
        .iter()
        .any(|file| file.path == "pubspec.lock")
        .then_some("pubspec.lock");
    let mut value = tar_snapshot(
        "pub.dev",
        name,
        version,
        archive,
        files,
        json!({"ecosystem":"pub.dev","registry_sha256":release.checksum,"lockfile_name":lock,"resolved_graph":{}}),
    )?;
    value["distribution_retracted"] = release.retracted.into();
    value["dependency_resolution_performed"] = false.into();
    Ok(value)
}

pub(super) fn fetch(name: &str, version: &str) -> Result<Value> {
    coordinate(name, version)?;
    let client = Client::new(Service::Pub);
    let endpoint = Url::parse(&format!(
        "https://pub.dev/api/packages/{name}/versions/{version}"
    ))
    .map_err(|_| invalid())?;
    let metadata = wire::parse(&client.get(endpoint, 2 * 1024 * 1024)?)?;
    let release = select(&metadata, name, version)?;
    let bytes = client.get(release.url.clone(), tarfiles::MAX_ARCHIVE)?;
    report(name, version, release, &bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::error::Error;

    #[test]
    fn archived_pubspec_and_official_checksum_bind_the_observation()
    -> std::result::Result<(), Box<dyn Error>> {
        let archive = tarfiles::fixture(&[
            (
                "test/pubspec.yaml",
                b"invalid nested fixture",
                tar::EntryType::Regular,
            ),
            (
                "pubspec.yaml",
                b"name: demo\nversion: 1.2.3\ndependencies:\n  other: ^2.0.0\n",
                tar::EntryType::Regular,
            ),
        ])?;
        let metadata = json!({"version":"1.2.3","pubspec":{"name":"demo","version":"1.2.3"},"archive_sha256":digest::sha256(&archive).trim_start_matches("sha256:"),"archive_url":"https://pub.dev/api/archives/demo-1.2.3.tar.gz"});
        coordinate("demo", "1.2.3")?;
        assert!(!allowed(
            Service::Pub,
            &Url::parse("https://storage.googleapis.com/other/demo.tar.gz")?
        ));
        let mut retracted = metadata.clone();
        retracted["retracted"] = true.into();
        assert!(select(&retracted, "demo", "1.2.3")?.retracted);

        let value = report(
            "demo",
            "1.2.3",
            select(&metadata, "demo", "1.2.3")?,
            &archive,
        )?;
        assert_eq!(value["snapshot"]["file_paths"], json!(["pubspec.yaml"]));
        assert_eq!(
            value["snapshot"]["package_evidence"]["resolved_graph"],
            json!({})
        );
        assert_eq!(value["distribution_retracted"], false);
        assert_eq!(value["dependency_resolution_performed"], false);
        assert!(value["snapshot"]["package_evidence"]["lockfile_name"].is_null());
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
        for url in [
            "https://evil.example/archive",
            "https://storage.googleapis.com/other/demo-1.2.3.tar.gz",
            "https://pub.dev/api/archives/other-1.2.3.tar.gz",
        ] {
            let mut metadata = metadata.clone();
            metadata["archive_url"] = url.into();
            assert!(select(&metadata, "demo", "1.2.3").is_err());
        }
        let wrong = tarfiles::fixture(&[(
            "pubspec.yaml",
            b"name: other\nversion: 1.2.3\n",
            tar::EntryType::Regular,
        )])?;
        let mut release = select(&metadata, "demo", "1.2.3")?;
        release.checksum = digest::sha256(&wrong).trim_start_matches("sha256:").into();
        assert!(report("demo", "1.2.3", release, &wrong).is_err());
        assert!(coordinate("../demo", "1.2.3").is_err());
        assert!(coordinate("demo", "any").is_err());
        Ok(())
    }
}
