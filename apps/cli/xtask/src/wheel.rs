//! PyPI delivers the verified archive binary directly through .data/scripts.
use crate::{Files, Result, hash, options, release, require, write_new};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use sha2::{Digest, Sha256};
use std::{ffi::OsString, fs, path::Path};

fn tag(target: &str) -> Result<&'static str> {
    match target {
        "x86_64-unknown-linux-gnu" => Ok("manylinux_2_43_x86_64"),
        "aarch64-apple-darwin" => Ok("macosx_15_0_arm64"),
        "x86_64-pc-windows-msvc" => Ok("win_amd64"),
        _ => Err("unsupported native wheel target".into()),
    }
}

// The wheel tag is a compatibility promise about the embedded ELF, not just
// the runner label. Inspect version requirements without executing the payload.
fn verify_linux_abi(binary: &[u8]) -> Result<()> {
    use std::io::Write;
    let mut file = tempfile::NamedTempFile::new()?;
    file.write_all(binary)?;
    let output = std::process::Command::new("readelf")
        .args(["--version-info", "--wide"])
        .arg(file.path())
        .output()?;
    require(
        output.status.success(),
        "cannot inspect the Linux executable ABI",
    )?;
    verify_glibc_versions(std::str::from_utf8(&output.stdout)?)
}

fn verify_glibc_versions(output: &str) -> Result<()> {
    let mut count = 0;
    let tokens: Vec<_> = output.split_whitespace().collect();
    for pair in tokens.windows(2) {
        if pair[0] != "Name:" || !pair[1].starts_with("GLIBC_") {
            continue;
        }
        let text = pair[1]
            .strip_prefix("GLIBC_")
            .ok_or("missing libc version")?;
        let parts = text
            .split('.')
            .map(str::parse::<u16>)
            .collect::<std::result::Result<Vec<_>, _>>()?;
        require(
            (2..=3).contains(&parts.len()),
            "unknown GNU libc version requirement",
        )?;
        let version = (parts[0], parts[1], *parts.get(2).unwrap_or(&0));
        require(
            version <= (2, 43, 0),
            "Linux executable exceeds the declared glibc 2.43 wheel baseline",
        )?;
        count += 1;
    }
    require(
        count > 0,
        "Linux executable has no inspectable GNU libc requirements",
    )
}

pub fn contents(
    files: &Files,
    version: &str,
    revision: &str,
    target: &str,
) -> Result<(String, Files)> {
    release::validate(files, version, revision, target)?;
    let stem = format!("ai_stp-{version}");
    let info = format!("{stem}.dist-info");
    let binary = format!("{stem}.data/scripts/{}", release::binary(target)?);
    let platform = tag(target)?;
    let description = "# ai-stp Rust CLI\n\nThis package contains the same native Rust executable as the GitHub release.\nThere is no Python launcher, interpreter dependency or legacy CLI fallback.\n\nInstall or upgrade with `uv tool install --upgrade ai-stp`, then run\n`ai-stp version --json`. Package-manager installations remain owned by that\npackage manager; use it for subsequent updates.\n\nNative archives require no Python installation and remain the primary route:\nhttps://github.com/ai-engineers-guild/ai-stp/releases?q=cli-v\n\nExisting Python state needs explicit `ai-stp state migrate plan` and apply.\nThe older ai-stp-cli PyPI project is separate; remove its launcher through its owning package manager before installing ai-stp.\n\nSupported binaries: Linux x86-64 (glibc 2.43+), macOS 15+ Apple Silicon,\nWindows x86-64. First-party native setup configuration is supported on all\nthree platforms; historical external-provider execution remains Linux-only.\n";
    let metadata = format!(
        "Metadata-Version: 2.4\nName: ai-stp\nVersion: {version}\nSummary: Native Rust engine for AI harness configurations\nLicense-Expression: AGPL-3.0-or-later\nLicense-File: LICENSE\nClassifier: Programming Language :: Rust\nProject-URL: Repository, https://github.com/ai-engineers-guild/ai-stp\nDescription-Content-Type: text/markdown\n\n{description}"
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
    if target == "x86_64-unknown-linux-gnu" {
        verify_linux_abi(&files[release::binary(target)?])?;
    }
    let (binary, files) = contents(&files, version, revision, target)?;
    let bytes = release::zip_bytes(&files, &binary)?;
    require(
        bytes.len() <= release::MAX_ARCHIVE,
        "wheel exceeds its size bound",
    )?;
    let name = format!("ai_stp-{version}-py3-none-{}.whl", tag(target)?);
    let output = Path::new(&opts["--output"]);
    fs::create_dir(output)?;
    write_new(&output.join(&name), &bytes)?;
    println!(
        "{}",
        serde_json::json!({"wheel":name,"sha256":hash(&bytes)})
    );
    Ok(())
}

#[cfg(test)]
mod abi_tests {
    use super::*;

    #[test]
    fn wheel_baseline_refuses_newer_private_unknown_or_absent_libc_versions() -> Result<()> {
        verify_glibc_versions("Name: GLIBC_2.3.4 Flags: none\nName: GLIBC_2.43 Flags: none")?;
        for output in [
            "Name: GLIBC_2.44 Flags: none",
            "Name: GLIBC_3.0 Flags: none",
            "Name: GLIBC_PRIVATE Flags: none",
            "Name: GLIBC_2 Flags: none",
            "Name: GLIBC_2.43.1 Flags: none",
            "Name: GLIBC_2.43.0.0 Flags: none",
            "Name: GLIBC_2.x Flags: none",
            "Name: LIBOTHER_1.0 Flags: none",
            "",
        ] {
            assert!(verify_glibc_versions(output).is_err(), "{output}");
        }
        Ok(())
    }
}
