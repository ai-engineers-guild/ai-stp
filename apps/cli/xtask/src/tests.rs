use crate::{Files, Result, encoded, hash, release, sbom, wheel};
use serde_json::{Value, json};
use std::fs;

const VERSION: &str = "0.1.3";
const REVISION: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const TARGET: &str = "x86_64-unknown-linux-gnu";

fn inventory() -> (Value, String) {
    let registry = "registry+https://github.com/rust-lang/crates.io-index";
    let mut packages = Vec::new();
    let mut nodes = Vec::new();
    let mut lock = "version = 4\n".to_owned();
    for (name, version, deps) in [
        (
            "ai-stp-cli",
            VERSION,
            vec![
                ("runtime", Value::Null),
                ("builder", json!("build")),
                ("test", json!("dev")),
            ],
        ),
        ("runtime", "1.2.3", vec![("shared", Value::Null)]),
        ("builder", "4.0.0", vec![("shared", Value::Null)]),
        ("shared", "2.0.0", vec![]),
        ("test", "1.0.0", vec![("test-only", Value::Null)]),
        ("test-only", "1.0.0", vec![]),
    ] {
        packages.push(json!({"id":name,"name":name,"version":version,"source":if name == "ai-stp-cli" { Value::Null } else { json!(registry) },"license":"MIT/Apache-2.0","manifest_path":"/private/build/path/Cargo.toml"}));
        nodes.push(json!({"id":name,"deps":deps.iter().map(|(name, kind)| json!({"pkg":name,"dep_kinds":[{"kind":kind}]})).collect::<Vec<_>>()}));
        lock.push_str(&format!(
            "\n[[package]]\nname = \"{name}\"\nversion = \"{version}\"\n"
        ));
        if name != "ai-stp-cli" {
            lock.push_str(&format!(
                "source = \"{registry}\"\nchecksum = \"{}\"\n",
                "b".repeat(64)
            ));
        }
    }
    (
        json!({"packages":packages,"resolve":{"root":"ai-stp-cli","nodes":nodes}}),
        lock,
    )
}

fn payload(target: &str) -> Result<Files> {
    let (metadata, lock) = inventory();
    let mut binary = vec![0; 80];
    if target == TARGET {
        binary[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
        binary[18] = 62;
    } else {
        binary[..2].copy_from_slice(b"MZ");
        binary[60] = 64;
        binary[64..70].copy_from_slice(b"PE\0\0\x64\x86");
    }
    let inventory = sbom::inventory(&metadata, &lock, VERSION, REVISION, target, &hash(&binary))?;
    let name = release::binary(target)?;
    let manifest = json!({"schema_version":2,"package":"ai-stp-cli","version":VERSION,"release_channel":"stable","source_commit":REVISION,"target":target,"binary":name,"binary_sha256":hash(&binary),"license_sha256":hash(b"license"),"sbom":release::SBOM,"sbom_sha256":hash(&inventory)});
    Ok(Files::from([
        (name.into(), binary),
        ("LICENSE".into(), b"license".to_vec()),
        (release::SBOM.into(), inventory),
        ("release.json".into(), encoded(&manifest)?),
    ]))
}

#[test]
fn sbom_retains_normal_and_build_edges_but_excludes_dev_and_local_paths() -> Result<()> {
    let (mut metadata, lock) = inventory();
    let build = |metadata: &Value, lock: &str| {
        sbom::inventory(metadata, lock, VERSION, REVISION, TARGET, &hash(b"binary"))
    };
    let bytes = build(&metadata, &lock)?;
    let value: Value = serde_json::from_slice(&bytes)?;
    assert_eq!(
        value["components"]
            .as_array()
            .ok_or("components missing")?
            .iter()
            .map(|p| p["name"].clone())
            .collect::<Vec<_>>(),
        vec![json!("builder"), json!("runtime"), json!("shared")]
    );
    assert_eq!(
        value["dependencies"][0]["dependsOn"],
        json!(["pkg:cargo/builder@4.0.0", "pkg:cargo/runtime@1.2.3"])
    );
    assert!(!String::from_utf8(bytes.clone())?.contains("/private"));
    metadata["packages"]
        .as_array_mut()
        .ok_or("packages missing")?
        .reverse();
    metadata["resolve"]["nodes"]
        .as_array_mut()
        .ok_or("nodes missing")?
        .reverse();
    assert_eq!(build(&metadata, &lock)?, bytes);
    assert!(build(&metadata, &lock.replace(&"b".repeat(64), "invalid")).is_err());
    metadata["packages"]
        .as_array_mut()
        .ok_or("packages missing")?
        .iter_mut()
        .find(|p| p["name"] == "runtime")
        .ok_or("runtime missing")?["source"] = json!("git+https://example.invalid/unlocked");
    assert!(build(&metadata, &lock).is_err());
    Ok(())
}

#[test]
fn archives_are_deterministic_and_refuse_missing_or_changed_inventory() -> Result<()> {
    let directory = tempfile::tempdir()?;
    for target in [TARGET, "x86_64-pc-windows-msvc"] {
        let files = payload(target)?;
        let binary = release::binary(target)?;
        let windows = target != TARGET;
        let path = directory.path().join(if windows {
            "release.zip"
        } else {
            "release.tar.gz"
        });
        let bytes = release::archive_bytes(&files, binary, windows)?;
        assert_eq!(release::archive_bytes(&files, binary, windows)?, bytes);
        fs::write(&path, &bytes)?;
        assert_eq!(release::read_archive(&path, binary)?, files);
        release::validate(&files, VERSION, REVISION, target)?;
        let mut missing = files.clone();
        missing.remove(release::SBOM);
        fs::write(&path, release::archive_bytes(&missing, binary, windows)?)?;
        assert!(release::read_archive(&path, binary).is_err());
        let mut changed = files.clone();
        changed.insert(release::SBOM.into(), b"{}".to_vec());
        assert!(release::validate(&changed, VERSION, REVISION, target).is_err());
        let mut value: Value = serde_json::from_slice(&files[release::SBOM])?;
        value["metadata"]["component"]["version"] = json!("0.0.0");
        changed.insert(release::SBOM.into(), encoded(&value)?);
        let mut manifest: Value = serde_json::from_slice(&files["release.json"])?;
        manifest["sbom_sha256"] = json!(hash(&changed[release::SBOM]));
        changed.insert("release.json".into(), encoded(&manifest)?);
        assert!(release::validate(&changed, VERSION, REVISION, target).is_err());
    }
    Ok(())
}

#[test]
fn wheel_delivers_the_exact_binary_without_python_or_entrypoint_wrappers() -> Result<()> {
    for target in [TARGET, "x86_64-pc-windows-msvc"] {
        let original = payload(target)?;
        let (executable, files) = wheel::contents(&original, VERSION, REVISION, target)?;
        assert_eq!(files[&executable], original[release::binary(target)?]);
        assert!(executable.contains(".data/scripts/ai-stp"));
        assert!(
            !files
                .keys()
                .any(|name| name.ends_with(".py") || name.ends_with("entry_points.txt"))
        );
        let metadata = files
            .iter()
            .find(|(name, _)| name.ends_with("/METADATA"))
            .ok_or("METADATA missing")?;
        assert!(!String::from_utf8(metadata.1.clone())?.contains("Requires-Dist:"));
        let record = files
            .iter()
            .find(|(name, _)| name.ends_with("/RECORD"))
            .ok_or("RECORD missing")?;
        assert_eq!(
            String::from_utf8(record.1.clone())?.lines().count(),
            files.len()
        );
    }
    Ok(())
}
