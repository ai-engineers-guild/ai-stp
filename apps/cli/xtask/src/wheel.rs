//! PyPI delivers the verified archive binary directly through .data/scripts.
use crate::{Files, Result, hash, options, release, require, write_new};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use sha2::{Digest, Sha256};
use std::{ffi::OsString, fs, path::Path};

fn tag(target: &str) -> Result<&'static str> {
    match target {
        "x86_64-unknown-linux-gnu" => Ok("manylinux_2_39_x86_64"),
        "aarch64-apple-darwin" => Ok("macosx_15_0_arm64"),
        "x86_64-pc-windows-msvc" => Ok("win_amd64"),
        _ => Err("unsupported native wheel target".into()),
    }
}

pub fn contents(
    files: &Files,
    version: &str,
    revision: &str,
    target: &str,
) -> Result<(String, Files)> {
    release::validate(files, version, revision, target)?;
    let stem = format!("ai_stp_cli-{version}");
    let info = format!("{stem}.dist-info");
    let binary = format!("{stem}.data/scripts/{}", release::binary(target)?);
    let platform = tag(target)?;
    let description = "# ai-stp Rust CLI\n\nThis package contains the same native Rust executable as the GitHub release.\nThere is no Python launcher, interpreter dependency or legacy CLI fallback.\n\nInstall or upgrade with `uv tool install --upgrade ai-stp-cli`, then run\n`ai-stp version --json`. Package-manager installations remain owned by that\npackage manager; use it for subsequent updates.\n\nNative archives require no Python installation and remain the primary route:\nhttps://github.com/ai-engineers-guild/ai-stp/releases?q=cli-v\n\nExisting Python state needs explicit `ai-stp state migrate plan` and apply.\nVersions before 0.1.0 are the retired Python implementation.\n\nSupported binaries: Linux x86-64 (glibc 2.39+), macOS 15+ Apple Silicon,\nWindows x86-64. Isolated setup installation is currently Linux-only.\n";
    let metadata = format!(
        "Metadata-Version: 2.4\nName: ai-stp-cli\nVersion: {version}\nSummary: Native Rust engine for AI harness configurations\nLicense-Expression: AGPL-3.0-or-later\nLicense-File: LICENSE\nClassifier: Programming Language :: Rust\nProject-URL: Repository, https://github.com/ai-engineers-guild/ai-stp\nDescription-Content-Type: text/markdown\n\n{description}"
    );
    let mut wheel = Files::from([
        (binary.clone(), files[release::binary(target)?].clone()),
        (format!("{info}/METADATA"), metadata.into_bytes()),
        (format!("{info}/WHEEL"), format!("Wheel-Version: 1.0\nGenerator: ai-stp-native-tools\nRoot-Is-Purelib: false\nTag: py3-none-{platform}\n").into_bytes()),
        (format!("{info}/licenses/LICENSE"), files["LICENSE"].clone()),
        (format!("{info}/release.json"), files["release.json"].clone()),
        (format!("{info}/{}", release::SBOM), files[release::SBOM].clone()),
    ]);
    let record = format!("{info}/RECORD");
    let mut rows = wheel
        .iter()
        .map(|(name, bytes)| {
            format!(
                "{name},sha256={},{}\n",
                URL_SAFE_NO_PAD.encode(Sha256::digest(bytes)),
                bytes.len()
            )
        })
        .collect::<String>();
    rows.push_str(&format!("{record},,\n"));
    wheel.insert(record, rows.into_bytes());
    Ok((binary, wheel))
}

pub fn package(args: &[OsString]) -> Result<()> {
    let opts = options(
        args,
        &[
            "--archive",
            "--target",
            "--version",
            "--revision",
            "--output",
        ],
    )?;
    let (version, revision, target) = (&opts["--version"], &opts["--revision"], &opts["--target"]);
    let files = release::read_archive(Path::new(&opts["--archive"]), release::binary(target)?)?;
    let (binary, files) = contents(&files, version, revision, target)?;
    let bytes = release::zip_bytes(&files, &binary)?;
    require(
        bytes.len() <= release::MAX_ARCHIVE,
        "wheel exceeds its size bound",
    )?;
    let name = format!("ai_stp_cli-{version}-py3-none-{}.whl", tag(target)?);
    let output = Path::new(&opts["--output"]);
    fs::create_dir(output)?;
    write_new(&output.join(&name), &bytes)?;
    println!(
        "{}",
        serde_json::json!({"wheel":name,"sha256":hash(&bytes)})
    );
    Ok(())
}
