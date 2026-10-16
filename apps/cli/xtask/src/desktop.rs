//! Build and qualify the desktop's sole native CLI resource on each host OS.
use crate::{
    Result, build, encoded, executable, hash, isolated, release, require, root, run, text,
    write_new,
};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

fn name() -> &'static str {
    if cfg!(windows) {
        "ai-stp-desktop-cli.exe"
    } else {
        "ai-stp-desktop-cli"
    }
}
fn resources() -> PathBuf {
    root().join("apps/desktop/src-tauri/sidecar/cli")
}

pub fn stub() -> Result<()> {
    let resource = resources();
    if resource.join(name()).exists() {
        return Ok(());
    }
    fs::create_dir_all(&resource)?;
    // Only compilation consumes this placeholder. It cannot be mistaken for
    // the stable native binary by any build or packaged-resource probe.
    write_new(
        &resource.join(name()),
        b"Compile-time placeholder; run just desktop-regress for the native engine.\n",
    )?;
    Ok(())
}

pub fn build() -> Result<()> {
    build::invoke(
        &[
            "cargo",
            "build",
            "--locked",
            "--release",
            "--target-dir",
            "target",
            "--bin",
            "ai-stp",
        ]
        .map(Into::into),
    )?;
    let compiler = text(
        Command::new("rustc")
            .arg("-vV")
            .current_dir(root().join("apps/cli")),
    )?;
    let host = compiler
        .lines()
        .find_map(|line| line.strip_prefix("host: "))
        .ok_or("compiler host unavailable")?;
    let source = root()
        .join("apps/cli/target/release")
        .join(release::binary(host)?);
    let resource = resources();
    let parent = resource.parent().ok_or("resource parent missing")?;
    fs::create_dir_all(parent)?;
    let staged = tempfile::tempdir_in(parent)?;
    let binary = staged.path().join(name());
    fs::copy(source, &binary)?;
    executable(&binary)?;
    release::probe(&binary, &release::version()?)?;
    let version = isolated(&binary, &["version"])?;
    let capabilities = isolated(&binary, &["capabilities"])?;
    let help = isolated(&binary, &["help", "--agent"])?;
    require(
        capabilities["registry_digest"] == help["registry_digest"],
        "native registry changed during packaging",
    )?;
    let manifest = json!({"schema_version":1,"runtime":"rust","target":host,"cli_version":version["cli_version"],"registry_digest":capabilities["registry_digest"],"executable":name(),"sha256":hash(&fs::read(&binary)?)});
    write_new(&staged.path().join("sidecar.json"), &encoded(&manifest)?)?;
    if let Ok(metadata) = fs::symlink_metadata(&resource) {
        require(
            metadata.is_dir() && !metadata.is_symlink(),
            "generated resource directory must not be a link",
        )?;
        fs::remove_dir_all(&resource)?;
    }
    fs::rename(staged.path(), &resource)?;
    println!("Rust sidecar ready: {}", resource.join(name()).display());
    Ok(())
}

fn validate(binary: &Path) -> Result<()> {
    require(
        fs::symlink_metadata(binary)?.is_file(),
        "sidecar must be a regular file",
    )?;
    let parent = binary.parent().ok_or("sidecar parent missing")?;
    let manifest: Value = serde_json::from_slice(&fs::read(parent.join("sidecar.json"))?)?;
    let names = fs::read_dir(parent)?
        .map(|entry| entry.map(|e| e.file_name()))
        .collect::<std::io::Result<std::collections::BTreeSet<_>>>()?;
    require(
        names == [name().into(), "sidecar.json".into()].into_iter().collect()
            && manifest["schema_version"] == 1
            && manifest["runtime"] == "rust"
            && manifest["executable"] == name()
            && manifest["sha256"] == hash(&fs::read(binary)?),
        "packaged resource inventory or digest differs",
    )?;
    release::probe(binary, &release::version()?)?;
    let help = isolated(binary, &["help", "--agent"])?;
    require(
        manifest["registry_digest"] == help["registry_digest"]
            && manifest["cli_version"] == help["cli_version"],
        "resource manifest differs from executable",
    )
}

pub fn probe(path: Option<&Path>) -> Result<()> {
    let binary = match path {
        Some(path) => path.to_path_buf(),
        None => std::env::var_os("AI_STP_SIDECAR_EXE")
            .map(PathBuf::from)
            .unwrap_or_else(|| resources().join(name())),
    }
    .canonicalize()?;
    validate(&binary)?;
    run(Command::new("cargo")
        .current_dir(root().join("apps/desktop/core"))
        .env("AI_STP_SIDECAR_EXE", &binary)
        .args([
            "test",
            "--locked",
            "--test",
            "integration",
            "--",
            "--exact",
            "bundled_sidecar_spawns_under_runner_env",
            "--nocapture",
        ]))
}

fn matching(root: &Path, suffix: &str, recursive: bool) -> Result<Vec<PathBuf>> {
    let mut found = Vec::new();
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        let kind = entry.file_type()?;
        if entry.file_name().to_string_lossy().ends_with(suffix) {
            found.push(entry.path());
        }
        if recursive && kind.is_dir() {
            found.extend(matching(&entry.path(), suffix, true)?);
        }
        require(found.len() < 10_000, "bundle inventory exceeds its bound")?;
    }
    Ok(found)
}

fn only(mut paths: Vec<PathBuf>) -> Result<PathBuf> {
    require(
        paths.len() == 1,
        "expected exactly one OS package or native resource",
    )?;
    paths.pop().ok_or_else(|| "OS package missing".into())
}

pub fn packaged() -> Result<()> {
    let bundles = root().join("apps/desktop/src-tauri/target/release/bundle");
    let temporary = tempfile::tempdir()?;
    let binary = if cfg!(target_os = "macos") {
        only(matching(&bundles.join("macos"), ".app", false)?)?
            .join("Contents/Resources/cli")
            .join(name())
    } else if cfg!(windows) {
        let msi = only(matching(&bundles.join("msi"), ".msi", false)?)?;
        // Windows Installer rejects forward slashes accepted by filesystem APIs.
        let msi = msi.components().collect::<PathBuf>();
        // Administrative extraction writes files without installing/registering.
        run(Command::new("msiexec.exe")
            .arg("/a")
            .arg(msi)
            .arg("/qn")
            .arg(format!("TARGETDIR={}", temporary.path().display())))?;
        only(matching(temporary.path(), name(), true)?)?
    } else {
        let deb = only(matching(&bundles.join("deb"), ".deb", false)?)?;
        run(Command::new("dpkg-deb")
            .arg("-x")
            .arg(deb)
            .arg(temporary.path()))?;
        temporary
            .path()
            .join("usr/lib/ai-stp-desktop/cli")
            .join(name())
    };
    probe(Some(&binary))?;
    println!("Packaged native CLI resource probe passed");
    Ok(())
}
