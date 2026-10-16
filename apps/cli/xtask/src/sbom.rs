//! Locked, reachable Cargo normal/build dependency inventory (CycloneDX 1.6).
use crate::{Result, encoded, hash, require, root, text};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    process::Command,
};

pub const LIMIT: usize = 4 * 1024 * 1024;
const REGISTRY: &str = "registry+https://github.com/rust-lang/crates.io-index";

fn string<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .ok_or_else(|| format!("Cargo metadata has no {key}").into())
}
fn array<'a>(value: &'a Value, key: &str) -> Result<&'a Vec<Value>> {
    value[key]
        .as_array()
        .ok_or_else(|| format!("Cargo metadata has no {key}").into())
}

pub fn inventory(
    metadata: &Value,
    lock: &str,
    version: &str,
    revision: &str,
    target: &str,
    binary_digest: &str,
) -> Result<Vec<u8>> {
    let packages = array(metadata, "packages")?
        .iter()
        .map(|p| Ok((string(p, "id")?, p)))
        .collect::<Result<BTreeMap<_, _>>>()?;
    let graph = array(&metadata["resolve"], "nodes")?
        .iter()
        .map(|p| Ok((string(p, "id")?, p)))
        .collect::<Result<BTreeMap<_, _>>>()?;
    let root = string(&metadata["resolve"], "root")?;
    let application = packages.get(root).ok_or("SBOM root is absent")?;
    require(
        application["name"] == "ai-stp-cli" && application["version"] == version,
        "SBOM root differs from release package",
    )?;
    let lock_digest = hash(lock.as_bytes());
    let lock: toml_edit::DocumentMut = lock.parse()?;
    let locked = lock["package"]
        .as_array_of_tables()
        .ok_or("Cargo lock packages missing")?;
    let mut edges = BTreeMap::new();
    let mut pending = vec![root];
    while let Some(id) = pending.pop() {
        if edges.contains_key(id) {
            continue;
        }
        let mut dependencies = BTreeSet::new();
        for dependency in array(
            graph.get(id).ok_or("dependency graph node missing")?,
            "deps",
        )? {
            if array(dependency, "dep_kinds")?
                .iter()
                .any(|kind| kind["kind"].is_null() || kind["kind"] == "build")
            {
                dependencies.insert(string(dependency, "pkg")?);
            }
        }
        pending.extend(dependencies.iter().copied());
        edges.insert(id, dependencies);
    }
    let mut references = BTreeMap::new();
    let mut components = Vec::new();
    for id in edges.keys() {
        let package = packages.get(id).ok_or("SBOM dependency missing")?;
        let name = string(package, "name")?;
        let resolved_version = string(package, "version")?;
        require(
            !name.is_empty()
                && name
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_'),
            "invalid Cargo package name",
        )?;
        let reference = format!("pkg:cargo/{name}@{resolved_version}");
        references.insert(*id, reference.clone());
        if *id == root {
            continue;
        }
        require(
            package["source"] == REGISTRY,
            "native SBOM supports only locked crates.io dependencies",
        )?;
        let locked = locked
            .iter()
            .find(|row| {
                row.get("name").and_then(toml_edit::Item::as_str) == Some(name)
                    && row.get("version").and_then(toml_edit::Item::as_str)
                        == Some(resolved_version)
                    && row.get("source").and_then(toml_edit::Item::as_str) == Some(REGISTRY)
            })
            .ok_or("SBOM dependency not locked")?;
        let checksum = locked
            .get("checksum")
            .and_then(toml_edit::Item::as_str)
            .unwrap_or("");
        require(
            checksum.len() == 64
                && checksum
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "registry package has no exact source checksum",
        )?;
        let mut component = json!({"type":"library","bom-ref":reference,"purl":reference,"name":name,"version":resolved_version,"hashes":[{"alg":"SHA-256","content":checksum}]});
        if let Some(license) = package["license"].as_str().filter(|s| !s.is_empty()) {
            component["licenses"] = json!([{"license":{"name":license}}]);
        }
        components.push(component);
    }
    require(
        references.values().collect::<BTreeSet<_>>().len() == references.len(),
        "ambiguous SBOM package identity",
    )?;
    components.sort_by_key(|v| v["bom-ref"].as_str().unwrap_or("").to_owned());
    let mut dependencies = edges
        .iter()
        .map(|(id, deps)| {
            let mut refs = deps
                .iter()
                .map(|dep| references[*dep].clone())
                .collect::<Vec<_>>();
            refs.sort();
            json!({"ref":references[id],"dependsOn":refs})
        })
        .collect::<Vec<_>>();
    dependencies.sort_by_key(|v| v["ref"].as_str().unwrap_or("").to_owned());
    let result = encoded(&json!({
        "bomFormat":"CycloneDX", "specVersion":"1.6", "version":1,
        "metadata":{"component":{"type":"application","bom-ref":references[root],"name":"ai-stp-cli","version":version,
            "hashes":[{"alg":"SHA-256","content":binary_digest}],"licenses":[{"license":{"name":application["license"]}}]},
            "properties":[{"name":"ai-stp:source-commit","value":revision},{"name":"ai-stp:target","value":target},
                {"name":"ai-stp:cargo-lock-sha256","value":lock_digest},{"name":"ai-stp:inventory","value":"cargo-resolved-normal-and-build"}]},
        "components":components,"dependencies":dependencies,"compositions":[{"aggregate":"incomplete","assemblies":[references[root]]}]
    }))?;
    require(result.len() <= LIMIT, "native SBOM exceeds its bound")?;
    Ok(result)
}

pub fn build(version: &str, revision: &str, target: &str, binary_digest: &str) -> Result<Vec<u8>> {
    let cli = root().join("apps/cli");
    let metadata: Value = serde_json::from_str(&text(
        Command::new("cargo")
            .args([
                "metadata",
                "--format-version",
                "1",
                "--locked",
                "--offline",
                "--filter-platform",
                target,
            ])
            .current_dir(&cli),
    )?)?;
    inventory(
        &metadata,
        &fs::read_to_string(cli.join("Cargo.lock"))?,
        version,
        revision,
        target,
        binary_digest,
    )
}
