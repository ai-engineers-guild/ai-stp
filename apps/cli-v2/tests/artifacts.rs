use ai_stp_cli_v2::artifacts::{self, Member};
use ai_stp_cli_v2::{digest, projection::artifact};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde::Deserialize;
use std::{
    error::Error,
    io::{Cursor, Write},
};

#[derive(Deserialize)]
struct Case {
    name: String,
    files: Vec<File>,
    artifact_base64: String,
}
#[derive(Deserialize)]
struct File {
    path: String,
    content_base64: String,
    mode: u32,
}

#[derive(Deserialize)]
struct Projection {
    name: String,
    scope: serde_json::Value,
    files: Vec<File>,
    artifact_base64: String,
}

#[test]
fn artifact_wire_identity_and_unsafe_archive_refusals() -> Result<(), Box<dyn Error>> {
    // Bytes produced by the existing canonical encoder, independent of Rust's
    // ZIP library, include Unicode flags and executable file metadata.
    let cases: Vec<Case> = serde_json::from_str(include_str!("fixtures/component-artifacts.json"))?;
    for case in cases {
        let files = case
            .files
            .into_iter()
            .map(|file| {
                Ok(Member {
                    path: file.path,
                    bytes: STANDARD.decode(file.content_base64)?,
                    mode: file.mode,
                })
            })
            .collect::<Result<Vec<_>, base64::DecodeError>>()?;
        let expected = STANDARD.decode(case.artifact_base64)?;
        let archive = artifacts::encode_tree(&files)?;
        assert_eq!(
            archive, expected,
            "{} changed its persisted identity",
            case.name
        );
        let mut decoded = artifacts::decode_tree(&archive)?;
        decoded.sort_by(|a, b| a.path.cmp(&b.path));
        let mut ordered = files.clone();
        ordered.sort_by(|a, b| a.path.cmp(&b.path));
        assert_eq!(decoded, ordered);
        let mut corrupt = archive.clone();
        let offset = 30 + "component.json".len();
        corrupt[offset] ^= 1;
        assert!(artifacts::decode_tree(&corrupt).is_err());
        let mut mismatched = archive.clone();
        mismatched[30] = b'X';
        assert!(
            artifacts::decode_tree(&mismatched).is_err(),
            "local and central names disagreed"
        );
        if case.name == "empty" {
            let end = archive.len() - 22;
            let start = u32::from_le_bytes(archive[end + 16..end + 20].try_into()?) as usize;
            let central = &archive[start..end];
            let mut duplicate = archive[..end].to_vec();
            duplicate.extend(central);
            let mut footer = archive[end..].to_vec();
            footer[8..10].copy_from_slice(&2_u16.to_le_bytes());
            footer[10..12].copy_from_slice(&2_u16.to_le_bytes());
            footer[12..16].copy_from_slice(&(2 * central.len() as u32).to_le_bytes());
            duplicate.extend(footer);
            assert!(
                artifacts::decode_tree(&duplicate).is_err(),
                "duplicate central entries were hidden by the decoder"
            );
        }
    }
    for path in [
        "../escape",
        "a/../../b",
        "/absolute",
        "C:/drive",
        "file:stream",
        "back\\slash",
        "a//b",
        "a/./b",
        "trailing.",
        "control\0",
        "cafe\u{301}.md",
        "assets/NUL.txt",
        "com¹.log",
        "lpt9",
        "a?b",
        "a|b",
    ] {
        assert!(
            !artifacts::safe_path(path),
            "unsafe path accepted: {path:?}"
        );
    }
    let file = Member {
        path: "SKILL.md".into(),
        bytes: vec![],
        mode: 0o644,
    };
    let mut alias = file.clone();
    alias.path = "skill.md".into();
    assert!(artifacts::encode_tree(&[file.clone(), alias]).is_err());
    let mut descendant = file.clone();
    descendant.path = "skill.md/child".into();
    assert!(artifacts::encode_tree(&[file.clone(), descendant]).is_err());
    let mut first_directory = file.clone();
    first_directory.path = "Assets/first".into();
    let mut second_directory = file.clone();
    second_directory.path = "assets/second".into();
    assert!(
        artifacts::encode_tree(&[first_directory, second_directory]).is_err(),
        "one portable directory has conflicting case spellings"
    );
    let mut oversized = file.clone();
    oversized.bytes.resize(artifacts::MAX_FILE_BYTES + 1, 0);
    assert!(artifacts::encode_tree(&[oversized]).is_err());
    // A valid ZIP can still violate the component's closed manifest boundary.
    let mut archive = zip::ZipWriter::new(Cursor::new(Vec::new()));
    let options = zip::write::SimpleFileOptions::default()
        .unix_permissions(0o644)
        .system(zip::System::Unix);
    archive.start_file("component.json", options)?;
    archive.write_all(br#"{"files":[],"format":"ai-stp-component-tree/1"}"#)?;
    archive.start_file("files/undeclared", options)?;
    archive.write_all(b"unexpected")?;
    assert!(artifacts::decode_tree(&archive.finish()?.into_inner()).is_err());

    // The existing projection builder supplies an independent byte oracle,
    // including explicit empty directories, non-default modes and ownership.
    let cases: Vec<Projection> =
        serde_json::from_str(include_str!("fixtures/projection-artifacts.json"))?;
    for case in cases {
        let mut files = case
            .files
            .into_iter()
            .map(|file| {
                Ok(Member {
                    path: file.path,
                    bytes: STANDARD.decode(file.content_base64)?,
                    mode: file.mode,
                })
            })
            .collect::<Result<Vec<_>, base64::DecodeError>>()?;
        let expected = STANDARD.decode(case.artifact_base64)?;
        assert_eq!(
            artifact::build(&case.scope, &files)?,
            expected,
            "{} changed its projection identity",
            case.name
        );
        files.sort_by(|a, b| a.path.cmp(&b.path));
        assert_eq!(artifact::verify(&case.scope, &expected)?, files);
        let mut wrong = case.scope.clone();
        wrong["members"][0]["mode"] = 0.into();
        assert!(artifact::verify(&wrong, &expected).is_err());
        let mut corrupt = expected.clone();
        corrupt[30] ^= 1;
        wrong = case.scope.clone();
        wrong["projection_artifact"]["digest"] =
            digest::bytes("ai-stp:artifact:v1", &corrupt)?.into();
        assert!(artifact::verify(&wrong, &corrupt).is_err());
        let extra = Member {
            path: "undeclared".into(),
            bytes: b"unexpected".to_vec(),
            mode: 0o644,
        };
        files.push(extra);
        assert!(artifact::build(&case.scope, &files).is_err());
    }
    Ok(())
}
