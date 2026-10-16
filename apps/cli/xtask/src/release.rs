//! Deterministic archives of the exact executable, with bounded verification.
use crate::{
    Files, Result, encoded, executable, hash, isolated, options, require, root, sbom, text,
    write_new,
};
use flate2::{Compression, GzBuilder, read::GzDecoder};
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    fs,
    io::{Cursor, Read, Write},
    path::Path,
    process::Command,
};

pub const MAX_ARCHIVE: usize = 256 * 1024 * 1024;
pub const SBOM: &str = "ai-stp-cli.cdx.json";

pub fn version() -> Result<String> {
    let document: toml_edit::DocumentMut =
        fs::read_to_string(root().join("apps/cli/Cargo.toml"))?.parse()?;
    Ok(document["package"]["version"]
        .as_str()
        .ok_or("Cargo version is missing")?
        .into())
}

pub fn binary(target: &str) -> Result<&'static str> {
    match target {
        "x86_64-unknown-linux-gnu" | "aarch64-apple-darwin" => Ok("ai-stp"),
        "x86_64-pc-windows-msvc" => Ok("ai-stp.exe"),
        _ => Err("unsupported native release target".into()),
    }
}

pub fn identity(version: &str, revision: &str, target: &str) -> Result<()> {
    let parts = version.split('.').collect::<Vec<_>>();
    require(
        parts.len() == 3
            && parts
                .iter()
                .all(|s| s.parse::<u32>().is_ok_and(|n| n.to_string() == *s)),
        "canonical stable version required",
    )?;
    require(
        revision.len() == 40
            && revision
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "exact Git revision required",
    )?;
    binary(target)?;
    Ok(())
}

pub fn probe(path: &Path, version: &str) -> Result<()> {
    let result = isolated(path, &["version"])?;
    require(
        result["runtime"] == "rust"
            && result["release_channel"] == "stable"
            && result["cli_version"] == version,
        "executable does not identify the requested stable Rust release",
    )
}

fn native(bytes: &[u8], target: &str) -> Result<()> {
    let valid = match target {
        "x86_64-unknown-linux-gnu" => {
            bytes.len() >= 64 && bytes[..7] == *b"\x7fELF\x02\x01\x01" && bytes[18..20] == [62, 0]
        }
        "aarch64-apple-darwin" => {
            bytes.len() >= 32 && bytes[..8] == [0xcf, 0xfa, 0xed, 0xfe, 12, 0, 0, 1]
        }
        "x86_64-pc-windows-msvc" => {
            let offset = bytes
                .get(60..64)
                .and_then(|b| b.try_into().ok())
                .map(u32::from_le_bytes)
                .map(|n| n as usize);
            bytes.starts_with(b"MZ")
                && offset.and_then(|n| n.checked_add(6).and_then(|end| bytes.get(n..end)))
                    == Some(b"PE\0\0\x64\x86".as_slice())
        }
        _ => false,
    };
    require(
        valid,
        "release executable has the wrong native platform identity",
    )
}

pub fn zip_bytes(files: &Files, executable: &str) -> Result<Vec<u8>> {
    let mut archive = zip::ZipWriter::new(Cursor::new(Vec::new()));
    for (name, bytes) in files {
        let options = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .unix_permissions(if name == executable { 0o755 } else { 0o644 });
        archive.start_file(name, options)?;
        archive.write_all(bytes)?;
    }
    Ok(archive.finish()?.into_inner())
}

pub fn archive_bytes(files: &Files, binary: &str, windows: bool) -> Result<Vec<u8>> {
    if windows {
        return zip_bytes(files, binary);
    }
    let compressed = GzBuilder::new()
        .mtime(0)
        .write(Vec::new(), Compression::default());
    let mut archive = tar::Builder::new(compressed);
    for (name, bytes) in files {
        let mut header = tar::Header::new_ustar();
        header.set_size(bytes.len() as u64);
        header.set_mode(if name == binary { 0o755 } else { 0o644 });
        header.set_entry_type(tar::EntryType::Regular);
        header.set_uid(0);
        header.set_gid(0);
        header.set_mtime(0);
        header.set_cksum();
        archive.append_data(&mut header, name, bytes.as_slice())?;
    }
    Ok(archive.into_inner()?.finish()?)
}

pub fn read_archive(path: &Path, binary: &str) -> Result<Files> {
    require(
        fs::metadata(path)?.len() <= MAX_ARCHIVE as u64,
        "archive exceeds its bound",
    )?;
    let bytes = fs::read(path)?;
    let limits = [
        (binary, MAX_ARCHIVE),
        ("LICENSE", 64 * 1024),
        ("release.json", 4096),
        (SBOM, sbom::LIMIT),
    ]
    .into_iter()
    .collect::<std::collections::BTreeMap<_, _>>();
    let mut files = Files::new();
    let mut admit =
        |name: String, size: u64, mode: u32, mut stream: Box<dyn Read + '_>| -> Result<()> {
            let limit = *limits
                .get(name.as_str())
                .ok_or("unexpected archive member")?;
            require(
                !files.contains_key(&name)
                    && size <= limit as u64
                    && mode == if name == binary { 0o755 } else { 0o644 },
                "invalid archive member identity or size",
            )?;
            let mut data = Vec::new();
            stream
                .by_ref()
                .take(limit as u64 + 1)
                .read_to_end(&mut data)?;
            require(data.len() as u64 == size, "archive member size differs")?;
            files.insert(name, data);
            Ok(())
        };
    if path.extension().is_some_and(|s| s == "zip") {
        let mut archive = zip::ZipArchive::new(Cursor::new(bytes))?;
        require(
            archive.len() == 4,
            "archive must contain exactly four regular files",
        )?;
        for i in 0..archive.len() {
            let entry = archive.by_index(i)?;
            let mode = entry.unix_mode().ok_or("archive has no file mode")?;
            require(
                mode & 0o170000 == 0o100000 && !entry.encrypted(),
                "archive entry is not a regular unencrypted file",
            )?;
            admit(
                entry.name().into(),
                entry.size(),
                mode & 0o7777,
                Box::new(entry),
            )?;
        }
    } else {
        let mut archive = tar::Archive::new(GzDecoder::new(Cursor::new(bytes)));
        for entry in archive.entries()? {
            let entry = entry?;
            require(
                entry.header().entry_type().is_file(),
                "archive entry is not a regular file",
            )?;
            let path = String::from_utf8(entry.path_bytes().into_owned())?;
            admit(path, entry.size(), entry.header().mode()?, Box::new(entry))?;
        }
    }
    require(files.len() == 4, "archive member inventory differs")?;
    Ok(files)
}

pub fn validate(files: &Files, version: &str, revision: &str, target: &str) -> Result<()> {
    identity(version, revision, target)?;
    let binary = binary(target)?;
    for name in [binary, "LICENSE", "release.json", SBOM] {
        require(files.contains_key(name), "release member is missing")?;
    }
    let manifest: Value = serde_json::from_slice(&files["release.json"])?;
    require(
        manifest == manifest_for(files, version, revision, target)?,
        "archive manifest or payload identity differs",
    )?;
    let sbom: Value = serde_json::from_slice(&files[SBOM])?;
    let application = &sbom["metadata"]["component"];
    let properties = sbom["metadata"]["properties"]
        .as_array()
        .ok_or("SBOM properties missing")?;
    require(
        sbom["bomFormat"] == "CycloneDX"
            && sbom["specVersion"] == "1.6"
            && application["name"] == "ai-stp-cli"
            && application["version"] == version
            && application["hashes"] == json!([{"alg":"SHA-256","content":hash(&files[binary])}])
            && properties.contains(&json!({"name":"ai-stp:source-commit","value":revision}))
            && properties.contains(&json!({"name":"ai-stp:target","value":target})),
        "SBOM differs from the archive identity",
    )?;
    native(&files[binary], target)
}

fn manifest_for(files: &Files, version: &str, revision: &str, target: &str) -> Result<Value> {
    let binary = binary(target)?;
    Ok(
        json!({"schema_version":2,"package":"ai-stp-cli","version":version,"release_channel":"stable","source_commit":revision,"target":target,"binary":binary,"binary_sha256":hash(&files[binary]),"license_sha256":hash(&files["LICENSE"]),"sbom":SBOM,"sbom_sha256":hash(&files[SBOM])}),
    )
}

pub fn package(args: &[OsString]) -> Result<()> {
    let opts = options(
        args,
        &[
            "--binary",
            "--target",
            "--version",
            "--revision",
            "--output",
        ],
    )?;
    let (version, revision, target) = (&opts["--version"], &opts["--revision"], &opts["--target"]);
    identity(version, revision, target)?;
    require(
        self::version()? == *version
            && text(Command::new("git").args(["rev-parse", "HEAD"]))? == *revision,
        "checkout version or revision differs",
    )?;
    require(
        text(Command::new("git").args(["status", "--porcelain", "--untracked-files=no"]))?
            .is_empty(),
        "release packaging requires a clean tracked checkout",
    )?;
    let compiler = text(
        Command::new("rustc")
            .arg("-vV")
            .current_dir(root().join("apps/cli")),
    )?;
    require(
        compiler.lines().any(|l| l == format!("host: {target}")),
        "compiler host differs from target",
    )?;
    let path = Path::new(&opts["--binary"]);
    require(
        fs::symlink_metadata(path)?.is_file(),
        "binary must be a regular file",
    )?;
    require(
        fs::metadata(path)?.len() <= MAX_ARCHIVE as u64,
        "binary exceeds its bound",
    )?;
    probe(path, version)?;
    let bytes = fs::read(path)?;
    native(&bytes, target)?;
    let inventory = sbom::build(version, revision, target, &hash(&bytes))?;
    let binary = binary(target)?;
    let mut files = Files::from([
        (binary.into(), bytes),
        ("LICENSE".into(), fs::read(root().join("LICENSE"))?),
        (SBOM.into(), inventory),
    ]);
    files.insert(
        "release.json".into(),
        encoded(&manifest_for(&files, version, revision, target)?)?,
    );
    let windows = target.ends_with("windows-msvc");
    let extension = if windows { "zip" } else { "tar.gz" };
    let name = format!("ai-stp-cli-{version}-{target}.{extension}");
    let bytes = archive_bytes(&files, binary, windows)?;
    require(bytes.len() <= MAX_ARCHIVE, "archive exceeds its bound")?;
    let output = Path::new(&opts["--output"]);
    fs::create_dir(output)?;
    write_new(&output.join(&name), &bytes)?;
    write_new(
        &output.join(format!("{name}.sha256")),
        format!("{}  {name}\n", hash(&bytes)).as_bytes(),
    )?;
    println!(
        "{}",
        json!({"archive":name,"sha256":hash(&bytes),"source_commit":revision})
    );
    Ok(())
}

pub fn verify(args: &[OsString]) -> Result<()> {
    let opts = options(
        args,
        &[
            "--archive",
            "--target",
            "--version",
            "--revision",
            "--install-directory",
        ],
    )?;
    let (version, revision, target) = (&opts["--version"], &opts["--revision"], &opts["--target"]);
    let binary = binary(target)?;
    let files = read_archive(Path::new(&opts["--archive"]), binary)?;
    validate(&files, version, revision, target)?;
    let directory = Path::new(&opts["--install-directory"]);
    fs::create_dir(directory)?;
    for (name, bytes) in files {
        write_new(&directory.join(&name), &bytes)?;
    }
    executable(&directory.join(binary))?;
    probe(&directory.join(binary), version)?;
    println!(
        "{}",
        json!({"verified":opts["--archive"],"source_commit":revision})
    );
    Ok(())
}
