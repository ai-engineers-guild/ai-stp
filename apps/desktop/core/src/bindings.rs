//! Compile-derived IPC declarations, checked against their committed projection.
use crate::{CmdResult, Continuation};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use ts_rs::{Config, TS};

#[test]
fn native_bindings_match() {
    let sources = [
        ("core/Cargo.toml", include_str!("../Cargo.toml")),
        ("core/Cargo.lock", include_str!("../Cargo.lock")),
        ("core/src/bridge.rs", include_str!("bridge.rs")),
        ("core/src/envelope.rs", include_str!("envelope.rs")),
        ("core/src/bindings.rs", include_str!("bindings.rs")),
    ];
    let inputs: BTreeMap<_, _> = sources
        .into_iter()
        .map(|(name, source)| {
            let canonical = source.replace("\r\n", "\n");
            let digest: String = Sha256::digest(canonical.as_bytes())
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect();
            (name, digest)
        })
        .collect();
    let configuration = Config::default();
    let expected = serde_json::json!({
        "inputs": inputs,
        "declarations": [Continuation::decl(&configuration), CmdResult::decl(&configuration)],
    });
    let target = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../src/generated/native-bindings.json");
    if std::env::var("AI_STP_WRITE_BINDINGS").as_deref() == Ok("1") {
        std::fs::create_dir_all(target.parent().expect("projection parent")).unwrap();
        std::fs::write(
            target,
            format!("{}\n", serde_json::to_string_pretty(&expected).unwrap()),
        )
        .unwrap();
    } else {
        let committed: serde_json::Value = serde_json::from_slice(
            &std::fs::read(target).expect("run just desktop-native-gen on an execution host"),
        )
        .unwrap();
        assert_eq!(
            expected, committed,
            "native IPC bindings drifted; run just desktop-native-gen on an execution host"
        );
    }
}
