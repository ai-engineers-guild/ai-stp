use std::{
    collections::BTreeMap,
    error::Error,
    io::{Cursor, Write},
};

use ai_stp_cli_v2::provider::wheel;
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use sha2::{Digest, Sha256};
use zip::{CompressionMethod, ZipWriter, write::SimpleFileOptions};

const INFO: &str = "sample_provider-1.0.0.dist-info";
const BINARY: &str = "sample_provider/bin/sample-provider";

fn contents() -> BTreeMap<String, Vec<u8>> {
    let mut binary = vec![0; 64];
    binary[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
    binary[16..18].copy_from_slice(&2_u16.to_le_bytes());
    binary[18..20].copy_from_slice(&62_u16.to_le_bytes());
    BTreeMap::from([
        (BINARY.into(), binary),
        ("sample_provider/data,quoted.txt".into(), b"comma requires CSV quoting".to_vec()),
        (format!("{INFO}/METADATA"), b"Metadata-Version: 2.6\r\nName: Sample.Provider\r\nVersion: 1.0.0\r\nLicense-Expression: MIT OR\r\n Apache-2.0\r\n\r\nName: ignored body\r\n".to_vec()),
        (format!("{INFO}/WHEEL"), b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: py3-none-manylinux_2_34_x86_64\n".to_vec()),
    ])
}

fn record(files: &mut BTreeMap<String, Vec<u8>>) -> Result<(), Box<dyn Error>> {
    let mut writer = csv::Writer::from_writer(Vec::new());
    for (name, bytes) in files.iter() {
        writer.write_record([
            name,
            &format!("sha256={}", URL_SAFE_NO_PAD.encode(Sha256::digest(bytes))),
            &bytes.len().to_string(),
        ])?;
    }
    writer.write_record([format!("{INFO}/RECORD"), String::new(), String::new()])?;
    files.insert(format!("{INFO}/RECORD"), writer.into_inner()?);
    Ok(())
}

fn archive(files: &BTreeMap<String, Vec<u8>>, deflated: bool) -> Result<Vec<u8>, Box<dyn Error>> {
    let mut writer = ZipWriter::new(Cursor::new(Vec::new()));
    for (name, bytes) in files {
        writer.start_file(
            name,
            SimpleFileOptions::default()
                .unix_permissions(0o644)
                .compression_method(if deflated {
                    CompressionMethod::Deflated
                } else {
                    CompressionMethod::Stored
                }),
        )?;
        writer.write_all(bytes)?;
    }
    Ok(writer.finish()?.into_inner())
}

fn inspect(bytes: &[u8]) -> ai_stp_cli_v2::error::Result<wheel::Payload> {
    wheel::inspect(bytes, "sample-provider", "1.0.0", "linux/x86_64")
}

#[test]
fn provider_wheel_checks_every_member_before_returning_one_native_payload()
-> Result<(), Box<dyn Error>> {
    let mut files = contents();
    record(&mut files)?;
    for compressed in [false, true] {
        let bytes = archive(&files, compressed)?;
        let found = inspect(&bytes)?;
        assert_eq!(found.executable_name, "sample-provider");
        assert_eq!(found.executable, files[BINARY]);
        assert_eq!(found.license, "MIT OR Apache-2.0");
        assert_eq!(found.version, "1.0.0");
        assert!(wheel::inspect(&bytes, "another-provider", "1.0.0", "linux/x86_64").is_err());
        assert!(wheel::inspect(&bytes, "sample-provider", "1.0.1", "linux/x86_64").is_err());
        assert!(wheel::inspect(&bytes, "sample-provider", "1.0.0", "windows/x86_64").is_err());
        let mut prefixed = b"executable-stub".to_vec();
        prefixed.extend(&bytes);
        assert!(inspect(&prefixed).is_err());
    }
    for (name, bytes) in [
        (BINARY.to_owned(), Vec::new()),
        (BINARY.to_owned(), b"#!/usr/bin/python\nprint('not a native binary')\n".to_vec()),
        ("../escape".into(), b"x".to_vec()),
        ("sample_provider/bin/extra".into(), b"x".to_vec()),
        ("Sample_Provider/other".into(), b"x".to_vec()),
        ("unrelated-1.0.dist-info/METADATA".into(), b"x".to_vec()),
        ("sample_provider".into(), b"file hides a directory".to_vec()),
        (format!("{INFO}/METADATA"), b"Metadata-Version: 2.6\nName: sample-provider\nName: other\nVersion: 1.0.0\nLicense: MIT\n".to_vec()),
        (format!("{INFO}/WHEEL"), b"Wheel-Version: 2.0\nRoot-Is-Purelib: false\nTag: py3-none-manylinux_2_34_x86_64\n".to_vec()),
        (format!("{INFO}/METADATA"), vec![b'x'; 1024 * 1024 + 1]),
    ] {
        let mut changed = contents();
        changed.insert(name.clone(), bytes);
        record(&mut changed)?;
        assert!(inspect(&archive(&changed, true)?).is_err(), "{name}");
    }
    let record_path = format!("{INFO}/RECORD");
    let original = String::from_utf8(files[&record_path].clone())?;
    for changed in [
        original.replace("sha256=", "md5="),
        original.replace("sha256=", ""),
        original.replace("sha256=", "sha256=A"),
        original.replace(",64\n", ",63\n"),
        format!("{original}{BINARY},sha256=bad,32\n"),
        format!("{original}missing,sha256=bad,1\n"),
        original.lines().skip(1).collect::<Vec<_>>().join("\n"),
        original.replace(
            &format!("{INFO}/RECORD,,"),
            &format!("{INFO}/RECORD,sha256=bad,3"),
        ),
    ] {
        assert_ne!(changed, original);
        let mut bad = files.clone();
        bad.insert(record_path.clone(), changed.into_bytes());
        assert!(inspect(&archive(&bad, false)?).is_err());
    }
    let mut tampered = files.clone();
    tampered.insert(BINARY.into(), b"different same-sized native bytes".to_vec());
    assert!(inspect(&archive(&tampered, false)?).is_err());
    let mut writer = ZipWriter::new(Cursor::new(Vec::new()));
    writer.add_symlink(BINARY, "../../outside", SimpleFileOptions::default())?;
    assert!(inspect(&writer.finish()?.into_inner()).is_err());
    assert!(inspect(&vec![0; 64 * 1024 * 1024 + 1]).is_err());
    for (platform, tag, arm) in [
        ("linux/arm64", "manylinux_2_34_aarch64", true),
        ("macos/x86_64", "macosx_10_12_x86_64", false),
        ("macos/arm64", "macosx_11_0_arm64", true),
        ("windows/x86_64", "win_amd64", false),
        ("windows/arm64", "win_arm64", true),
    ] {
        let mut files = contents();
        let mut binary = vec![0; 128];
        if platform.starts_with("linux/") {
            binary[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
            binary[16..18].copy_from_slice(&3_u16.to_le_bytes());
            binary[18..20].copy_from_slice(&183_u16.to_le_bytes());
        } else if platform.starts_with("macos/") {
            binary[..4].copy_from_slice(&[0xcf, 0xfa, 0xed, 0xfe]);
            binary[4..8].copy_from_slice(
                &(if arm {
                    0x0100_000c_u32
                } else {
                    0x0100_0007_u32
                })
                .to_le_bytes(),
            );
            binary[12..16].copy_from_slice(&2_u32.to_le_bytes());
        } else {
            binary[..2].copy_from_slice(b"MZ");
            binary[60..64].copy_from_slice(&64_u32.to_le_bytes());
            binary[64..68].copy_from_slice(b"PE\0\0");
            binary[68..70]
                .copy_from_slice(&(if arm { 0xaa64_u16 } else { 0x8664_u16 }).to_le_bytes());
            binary[88..90].copy_from_slice(&0x020b_u16.to_le_bytes());
        }
        files.remove(BINARY);
        let path = if platform.starts_with("windows/") {
            format!("{BINARY}.exe")
        } else {
            BINARY.into()
        };
        files.insert(path.clone(), binary);
        files.insert(
            format!("{INFO}/WHEEL"),
            format!("Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: py3-none-{tag}\n")
                .into_bytes(),
        );
        record(&mut files)?;
        assert_eq!(
            wheel::inspect(
                &archive(&files, true)?,
                "sample-provider",
                "1.0.0",
                platform
            )?
            .executable,
            files[&path]
        );
        files.remove(&record_path);
        files.insert(path, b"#!/bin/sh\nexit 0\n".to_vec());
        record(&mut files)?;
        assert!(
            wheel::inspect(
                &archive(&files, true)?,
                "sample-provider",
                "1.0.0",
                platform
            )
            .is_err()
        );
    }
    Ok(())
}
