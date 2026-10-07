use std::{error::Error, fs, path::Path, process::Command};

use ai_stp_cli_v2::{canonical, digest};
use serde_json::{Value, json};

#[test]
fn shared_canonical_vectors_and_rejections() -> Result<(), Box<dyn Error>> {
    let golden = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/golden");
    for entry in fs::read_dir(golden.join("canonical"))? {
        let vector: Value = serde_json::from_slice(&fs::read(entry?.path())?)?;
        let actual = canonical::bytes(&vector["value"])?;
        assert_eq!(
            std::str::from_utf8(&actual)?,
            vector["canonical"]
                .as_str()
                .ok_or("missing canonical bytes")?
        );
        for (domain, digest) in vector["digests"].as_object().ok_or("missing digests")? {
            assert_eq!(
                digest::canonical(domain, &vector["value"])?,
                digest.as_str().ok_or("invalid digest")?
            );
        }
    }
    for entry in fs::read_dir(golden.join("canonical-invalid"))? {
        let path = entry?.path();
        assert!(
            canonical::parse(&fs::read(&path)?)
                .and_then(|value| canonical::bytes(&value))
                .is_err(),
            "{}",
            path.display()
        );
    }
    for input in [
        r#"{"a":1,"\u0061":2}"#,
        r#""\ud800""#,
        "184467440737095516160",
        "1e999",
    ] {
        assert!(canonical::parse(input.as_bytes()).is_err(), "{input}");
    }
    // RFC 8785 orders UTF-16 code units, not UTF-8 bytes or scalar values.
    assert_eq!(
        canonical::bytes(&json!({"\u{e000}": 1, "\u{10000}": 2}))?,
        "{\"𐀀\":2,\"\u{e000}\":1}".as_bytes()
    );
    assert!(digest::canonical("unknown", &json!({})).is_err());
    let nested = format!("{}0{}", "[".repeat(130), "]".repeat(130));
    assert!(canonical::parse(nested.as_bytes()).is_err());
    Ok(())
}

#[test]
fn executable_metadata_and_refusals() -> Result<(), Box<dyn Error>> {
    let home = tempfile::tempdir()?;
    for (arguments, expected) in [
        (vec!["version", "--json"], 0),
        (vec!["--json", "capabilities"], 0),
        (vec!["help", "--agent", "--json"], 0),
        (vec!["--help", "--json"], 0),
        (vec!["snapshot", "inspect", "--json"], 2),
        (vec!["install", "--json"], 2),
        (vec!["help", "--path", "install", "--json"], 2),
        (vec!["version", "--token=must-not-be-echoed", "--json"], 2),
    ] {
        let output = Command::new(env!("CARGO_BIN_EXE_ai-stp-v2"))
            .args(arguments)
            .env("HOME", home.path())
            .env("XDG_DATA_HOME", home.path())
            .env("PATH", "")
            .output()?;
        assert_eq!(output.status.code(), Some(expected));
        assert!(output.stderr.is_empty());
        let envelope: Value = serde_json::from_slice(&output.stdout)?;
        assert_eq!(envelope["schema_version"], 1);
        assert_eq!(envelope["ok"], expected == 0);
        assert!(
            envelope["request_id"]
                .as_str()
                .ok_or("missing ID")?
                .starts_with("request_")
        );
        assert!(!String::from_utf8_lossy(&output.stdout).contains("must-not-be-echoed"));
    }
    assert_eq!(fs::read_dir(home.path())?.count(), 0);
    Ok(())
}
