//! Exact PyPI file observations. Release metadata is not a resolved dependency graph.

use percent_encoding::percent_decode_str;
use serde_json::{Value, json};
use url::Url;

use crate::{
    canonical, digest,
    error::{Failure, Result},
    sources::transport::{Client, Service, allowed},
    wire,
};

const MAX_ARCHIVE: u64 = 20 * 1024 * 1024;

fn invalid() -> Failure {
    Failure::precondition("the PyPI project, file, platform or checksum observation was refused")
}

fn project(value: &str) -> Result<String> {
    if value.is_empty()
        || value.len() > 256
        || !value.as_bytes()[0].is_ascii_alphanumeric()
        || !value.as_bytes()[value.len() - 1].is_ascii_alphanumeric()
        || !value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
    {
        return Err(Failure::input("PyPI requires a bounded ASCII project name"));
    }
    let mut name = String::with_capacity(value.len());
    for byte in value.bytes() {
        if matches!(byte, b'.' | b'_' | b'-') {
            if !name.ends_with('-') {
                name.push('-');
            }
        } else {
            name.push(char::from(byte.to_ascii_lowercase()));
        }
    }
    Ok(name)
}

fn request(name: &str, version: &str, filename: &str, platform: &str) -> Result<String> {
    let name = project(name)?;
    if version.is_empty()
        || version.len() > 256
        || !version.as_bytes()[0].is_ascii_digit()
        || !version
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-' | b'+' | b'!'))
        || filename.is_empty()
        || filename.len() > 256
        || matches!(filename, "." | "..")
        || !filename
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-' | b'+' | b'!'))
        || platform.is_empty()
        || platform.len() > 64
        || !platform
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_')
    {
        return Err(Failure::input(
            "PyPI requires an exact version, distribution filename and platform tag",
        ));
    }
    Ok(name)
}

struct Distribution {
    url: Url,
    checksum: String,
    size: u64,
    evidence: Value,
    yanked: bool,
}

fn select(
    metadata: &Value,
    name: &str,
    version: &str,
    filename: &str,
    platform: &str,
) -> Result<Distribution> {
    let info = &metadata["info"];
    if project(info["name"].as_str().ok_or_else(invalid)?)? != name || info["version"] != version {
        return Err(invalid());
    }
    let files = metadata["urls"]
        .as_array()
        .filter(|files| !files.is_empty() && files.len() <= 1000)
        .ok_or_else(invalid)?;
    let mut matches = files.iter().filter(|file| file["filename"] == filename);
    let file = matches.next().ok_or_else(invalid)?;
    if matches.next().is_some() {
        return Err(invalid());
    }
    match file["packagetype"].as_str() {
        Some("bdist_wheel") => {
            let tags = filename
                .strip_suffix(".whl")
                .and_then(|name| name.rsplit('-').next())
                .ok_or_else(invalid)?;
            if !tags.split('.').any(|tag| tag == platform) {
                return Err(invalid());
            }
        }
        Some("sdist")
            if platform == "source"
                && (filename.ends_with(".tar.gz") || filename.ends_with(".zip")) => {}
        _ => return Err(invalid()),
    }
    let checksum = file["digests"]["sha256"]
        .as_str()
        .filter(|value| {
            value.len() == 64
                && value
                    .bytes()
                    .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
        })
        .ok_or_else(invalid)?
        .to_owned();
    let size = file["size"]
        .as_u64()
        .filter(|size| *size > 0 && *size <= MAX_ARCHIVE)
        .ok_or_else(invalid)?;
    let address = file["url"]
        .as_str()
        .filter(|url| url.len() <= 2048)
        .ok_or_else(invalid)?;
    let url = Url::parse(address).map_err(|_| invalid())?;
    if !allowed(Service::Pypi, &url)
        || url.host_str() != Some("files.pythonhosted.org")
        || !url.path().starts_with("/packages/")
        || url.query().is_some()
        || !url
            .path_segments()
            .and_then(|mut parts| parts.next_back())
            .is_some_and(|part| {
                percent_decode_str(part)
                    .decode_utf8()
                    .is_ok_and(|part| part == filename)
            })
    {
        return Err(invalid());
    }
    let requires = match info.get("requires_dist") {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(values)) if values.len() <= 1000 => values
            .iter()
            .map(|value| {
                value
                    .as_str()
                    .filter(|value| {
                        !value.is_empty()
                            && value.len() <= 4096
                            && !value.chars().any(char::is_control)
                    })
                    .map(str::to_owned)
                    .ok_or_else(invalid)
            })
            .collect::<Result<Vec<_>>>()?,
        _ => return Err(invalid()),
    };
    let repository = ["Source", "Source Code", "Repository", "Homepage"]
        .into_iter()
        .filter_map(|key| info["project_urls"][key].as_str())
        .find_map(|address| {
            let url = Url::parse(address).ok()?;
            (address.len() <= 512
                && url.scheme() == "https"
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none())
            .then(|| url.to_string())
        });
    Ok(Distribution {
        url,
        checksum: checksum.clone(),
        size,
        yanked: file["yanked"].as_bool().ok_or_else(invalid)?,
        evidence: json!({"ecosystem":"pypi","filename":filename,"platform":platform,"registry_sha256":checksum,"requires_dist":requires,"repository":repository}),
    })
}

fn report(
    name: &str,
    version: &str,
    filename: &str,
    selected: Distribution,
    bytes: &[u8],
) -> Result<Value> {
    if bytes.len() as u64 != selected.size
        || digest::sha256(bytes) != format!("sha256:{}", selected.checksum)
    {
        return Err(invalid());
    }
    let digest = digest::bytes("ai-stp:artifact:v1", bytes)?;
    let value = json!({"schema_version":1,"snapshot":{
        "kind":"package","canonical_coordinate":format!("package:pypi:{name}@{version}:{filename}"),
        "exact_identity":version,"archive_digest":digest,"component_digest":digest,"file_paths":[],
        "package_evidence":selected.evidence,"fetched_at":format!("{:.3}",jiff::Timestamp::now()),
        "author_verified":false,"component_verified":false,"target_write":false},
        "artifact":null,"provenance":"package_registry_observed","metadata_scope":"release",
        "distribution_yanked":selected.yanked,"network_accessed":true,"filesystem_accessed":false});
    canonical::bytes(&value)?;
    Ok(value)
}

pub(super) fn fetch(name: &str, version: &str, filename: &str, platform: &str) -> Result<Value> {
    let name = request(name, version, filename, platform)?;
    let client = Client::new(Service::Pypi);
    let endpoint = Url::parse(&format!("https://pypi.org/pypi/{name}/{version}/json"))
        .map_err(|_| invalid())?;
    let metadata = wire::parse(&client.get(endpoint, 2 * 1024 * 1024)?)?;
    let selected = select(&metadata, &name, version, filename, platform)?;
    let bytes = client.get(selected.url.clone(), selected.size)?;
    report(&name, version, filename, selected, &bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::error::Error;

    fn metadata(filename: &str, kind: &str, bytes: &[u8]) -> Value {
        json!({"info":{"name":"Example_Package","version":"1.2.3","requires_dist":["dependency>=2; python_version < '3.13'"],"project_urls":{"Source":"https://github.com/example/project"}},
            "urls":[{"filename":filename,"packagetype":kind,"size":bytes.len(),"yanked":true,
            "digests":{"sha256":digest::sha256(bytes).trim_start_matches("sha256:")},
            "url":format!("https://files.pythonhosted.org/packages/ab/cd/{filename}")}]})
    }

    #[test]
    fn exact_file_platform_digest_and_registry_metadata_are_distinct()
    -> std::result::Result<(), Box<dyn Error>> {
        let bytes = b"opaque distribution bytes; observation never extracts or executes them";
        for (filename, kind, platform) in [
            (
                "example_package-1.2.3-py3-none-any.whl",
                "bdist_wheel",
                "any",
            ),
            (
                "example_package-1.2.3-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
                "bdist_wheel",
                "manylinux2014_x86_64",
            ),
            ("example_package-1.2.3.tar.gz", "sdist", "source"),
        ] {
            let name = request("Example.__Package", "1.2.3", filename, platform)?;
            assert_eq!(name, "example-package");
            let metadata = metadata(filename, kind, bytes);
            let selected = select(&metadata, &name, "1.2.3", filename, platform)?;
            let value = report(&name, "1.2.3", filename, selected, bytes)?;
            assert_eq!(value["metadata_scope"], "release");
            assert_eq!(value["distribution_yanked"], true);
            assert_eq!(value["snapshot"]["package_evidence"]["platform"], platform);
            assert_eq!(
                value["snapshot"]["package_evidence"]["requires_dist"],
                metadata["info"]["requires_dist"]
            );
            assert!(value["artifact"].is_null());
            assert_eq!(
                value["snapshot"]["archive_digest"],
                value["snapshot"]["component_digest"]
            );
            for field in ["author_verified", "component_verified", "target_write"] {
                assert_eq!(value["snapshot"][field], false);
            }
            assert!(select(&metadata, &name, "1.2.4", filename, platform).is_err());
            assert!(select(&metadata, "other-package", "1.2.3", filename, platform).is_err());
            assert!(select(&metadata, &name, "1.2.3", filename, "linux").is_err());
            let selected = select(&metadata, &name, "1.2.3", filename, platform)?;
            assert!(report(&name, "1.2.3", filename, selected, b"changed bytes").is_err());
            let mut duplicate = metadata.clone();
            duplicate["urls"] = json!([metadata["urls"][0], metadata["urls"][0]]);
            assert!(select(&duplicate, &name, "1.2.3", filename, platform).is_err());
        }
        Ok(())
    }

    #[test]
    fn input_bounds_and_remote_metadata_fail_closed() -> std::result::Result<(), Box<dyn Error>> {
        for name in [
            "",
            ".hidden",
            "trailing-",
            "../escape",
            "https://pypi.org/pypi/demo",
            "café",
        ] {
            assert!(project(name).is_err());
        }
        for version in ["latest", "1.*", "^1.2", "1/../../other", "1.0?x", " 1.0"] {
            assert!(request("demo", version, "demo.whl", "any").is_err());
        }
        assert!(request("demo", "1.0", "../demo.whl", "any").is_err());
        assert!(
            super::super::fetch("go", "example.com/mod", "v1.0.0", Some("ignored"), None).is_err()
        );
        assert!(super::super::fetch("pypi", "demo", "1.0", None, None).is_err());
        let filename = "example_package-1.2.3-py3-none-any.whl";
        for url in [
            "https://evil.example/file",
            "http://files.pythonhosted.org/packages/demo.whl",
            "https://user:secret@files.pythonhosted.org/packages/demo.whl",
            "https://files.pythonhosted.org/other/demo.whl",
            "https://files.pythonhosted.org/packages/other.whl",
        ] {
            let mut metadata = metadata(filename, "bdist_wheel", b"bytes");
            metadata["urls"][0]["url"] = url.into();
            assert!(select(&metadata, "example-package", "1.2.3", filename, "any").is_err());
        }
        for field in ["size", "yanked", "digests"] {
            let mut metadata = metadata(filename, "bdist_wheel", b"bytes");
            metadata["urls"][0][field] = Value::Null;
            assert!(select(&metadata, "example-package", "1.2.3", filename, "any").is_err());
        }
        let mut excessive = metadata(filename, "bdist_wheel", b"bytes");
        excessive["urls"][0]["size"] = (MAX_ARCHIVE + 1).into();
        assert!(select(&excessive, "example-package", "1.2.3", filename, "any").is_err());
        excessive["urls"][0]["size"] = 5.into();
        excessive["info"]["requires_dist"] = json!([false]);
        assert!(select(&excessive, "example-package", "1.2.3", filename, "any").is_err());
        Ok(())
    }
}
