use std::{collections::BTreeMap, error::Error, fs, path::PathBuf};

use ed25519_dalek::{Signer, SigningKey};
use sigstore_verify::trust_root::SIGSTORE_PRODUCTION_TRUSTED_ROOT;

use super::*;

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn signed(mut value: Value, key: &SigningKey) -> std::result::Result<Vec<u8>, Box<dyn Error>> {
    value["spec_version"] = "1.0.37".into();
    if value.get("expires").is_none() {
        value["expires"] = "2030-01-01T00:00:00Z".into();
    }
    let bytes = sigstore_tuf::canonical_json::to_canonical_bytes(&value)?;
    Ok(serde_json::to_vec(
        &json!({"signed":value,"signatures":[{"keyid":"synthetic","sig":hex(&key.sign(&bytes).to_bytes())}]}),
    )?)
}

fn root(version: u64, key: &SigningKey) -> std::result::Result<Vec<u8>, Box<dyn Error>> {
    let role = json!({"keyids":["synthetic"],"threshold":1});
    signed(
        json!({"_type":"root","version":version,"consistent_snapshot":false,
        "keys":{"synthetic":{"keytype":"ed25519","scheme":"ed25519","keyval":{"public":hex(key.verifying_key().as_bytes())}}},
        "roles":{"root":role,"timestamp":role,"snapshot":role,"targets":role}}),
        key,
    )
}

fn pin(version: u64, bytes: &[u8]) -> Value {
    json!({"version":version,"length":bytes.len(),"hashes":{"sha256":hex(&Sha256::digest(bytes))}})
}

struct Repo {
    files: BTreeMap<String, Vec<u8>>,
    requested: Vec<String>,
    break_storage: Option<PathBuf>,
}

impl Repository for Repo {
    fn get(&mut self, name: &str, target: bool, limit: usize) -> Result<Option<Vec<u8>>> {
        self.requested.push(name.into());
        if name == "snapshot.json"
            && let Some(path) = self.break_storage.take()
        {
            fs::remove_file(&path).map_err(|_| invalid())?;
            fs::create_dir(path).map_err(|_| invalid())?;
        }
        assert_eq!(target, name == TARGET);
        let found = self.files.get(name).cloned();
        if found.as_ref().is_some_and(|bytes| bytes.len() > limit) {
            return Err(invalid());
        }
        Ok(found)
    }
}

fn repository(
    version: u64,
    targets_version: u64,
    key: &SigningKey,
) -> std::result::Result<Repo, Box<dyn Error>> {
    let target = SIGSTORE_PRODUCTION_TRUSTED_ROOT.as_bytes().to_vec();
    let targets = signed(
        json!({"_type":"targets","version":targets_version,"targets":{TARGET:{"length":target.len(),"hashes":{"sha256":hex(&Sha256::digest(&target))}}}}),
        key,
    )?;
    let snapshot = signed(
        json!({"_type":"snapshot","version":version,"meta":{"targets.json":pin(targets_version,&targets)}}),
        key,
    )?;
    let timestamp = signed(
        json!({"_type":"timestamp","version":version,"meta":{"snapshot.json":pin(version,&snapshot)}}),
        key,
    )?;
    Ok(Repo {
        files: BTreeMap::from([
            ("timestamp.json".into(), timestamp),
            ("snapshot.json".into(), snapshot),
            ("targets.json".into(), targets),
            (TARGET.into(), target),
        ]),
        requested: Vec::new(),
        break_storage: None,
    })
}

#[test]
fn durable_trust_preserves_authenticated_floors_roots_and_storage_errors()
-> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let path = temporary.path();
    let state_path = path.join("sigstore-tuf/state.json");
    let marker = path.join("sigstore-tuf/initialized");
    let now: jiff::Timestamp = "2026-10-09T00:00:00Z".parse()?;
    // Synthetic signing material, unrelated to any real publishing identity.
    let key = SigningKey::from_bytes(&[42; 32]);
    let bootstrap = root(1, &key)?;
    let material = run(path, &bootstrap, &mut repository(1, 10, &key)?, now)?;
    assert_eq!(material.report()["targets_version"], 10);
    assert_eq!(fs::read(&marker)?, b"1\n");
    let mut interrupted = repository(2, 9, &key)?;
    let snapshot = interrupted
        .files
        .remove("snapshot.json")
        .ok_or("snapshot missing")?;
    assert!(run(path, &bootstrap, &mut interrupted, now).is_err());
    let state: State = serde_json::from_slice(&fs::read(&state_path)?)?;
    assert_eq!(
        metadata::parse::<sigstore_tuf::Timestamp>(
            state
                .timestamp
                .as_ref()
                .ok_or("timestamp missing")?
                .bytes
                .as_bytes()
        )?
        .signed()
        .version,
        2
    );
    assert_eq!(
        metadata::parse::<sigstore_tuf::Snapshot>(
            state
                .snapshot
                .as_ref()
                .ok_or("snapshot missing")?
                .bytes
                .as_bytes()
        )?
        .signed()
        .meta["targets.json"]
            .version,
        10
    );
    interrupted.files.insert("snapshot.json".into(), snapshot);
    assert!(run(path, &bootstrap, &mut interrupted, now).is_err());
    let accepted = run(path, &bootstrap, &mut repository(3, 11, &key)?, now)?;
    assert_eq!(accepted.report()["targets_version"], 11);
    let valid_state = fs::read(&state_path)?;
    let mut tampered = repository(4, 12, &key)?;
    tampered
        .files
        .get_mut(TARGET)
        .ok_or("target missing")?
        .push(b' ');
    assert!(run(path, &bootstrap, &mut tampered, now).is_err());
    // Higher authenticated metadata is retained even if target download fails.
    assert!(run(path, &bootstrap, &mut repository(3, 11, &key)?, now).is_err());
    assert!(run(path, &bootstrap, &mut repository(4, 12, &key)?, now).is_ok());
    let mut rotated = repository(5, 13, &key)?;
    let mut annotated: Value = serde_json::from_slice(&root(2, &key)?)?;
    annotated["signed"]["keys"]["synthetic"]["x-owner"] = "public annotation".into();
    rotated.files.insert(
        "2.root.json".into(),
        signed(annotated["signed"].clone(), &key)?,
    );
    rotated.files.insert(
        "3.root.json".into(),
        root(3, &SigningKey::from_bytes(&[43; 32]))?,
    );
    assert!(run(path, &bootstrap, &mut rotated, now).is_err());
    let stored: State = serde_json::from_slice(&fs::read(&state_path)?)?;
    assert_eq!(stored.roots.len(), 1);
    assert!(run(path, &bootstrap, &mut repository(1, 1, &key)?, now).is_err());
    rotated.files.remove("3.root.json");
    rotated.requested.clear();
    assert_eq!(
        run(path, &bootstrap, &mut rotated, now)?.report()["root_version"],
        2
    );
    assert!(!rotated.requested.iter().any(|name| name == "2.root.json"));
    let mut expired = repository(6, 14, &key)?;
    let mut timestamp: Value = serde_json::from_slice(
        expired
            .files
            .get("timestamp.json")
            .ok_or("timestamp missing")?,
    )?;
    timestamp["signed"]["expires"] = "2026-10-09T00:00:00Z".into();
    expired.files.insert(
        "timestamp.json".into(),
        signed(timestamp["signed"].clone(), &key)?,
    );
    assert!(run(path, &bootstrap, &mut expired, now).is_err());
    // Real online-key rotation resets lower-role floors, including opaque IDs
    // reused with new key material. The root transition is signed by both roles.
    let new_key = SigningKey::from_bytes(&[43; 32]);
    let mut new_root: Value = serde_json::from_slice(&root(3, &new_key)?)?;
    let old_root: Value = serde_json::from_slice(&bootstrap)?;
    new_root["signed"]["keys"]["root-signing"] = old_root["signed"]["keys"]["synthetic"].clone();
    new_root["signed"]["roles"]["root"]["keyids"] = json!(["root-signing"]);
    let mut transition: Value = serde_json::from_slice(&signed(new_root["signed"].clone(), &key)?)?;
    let mut self_signature = transition["signatures"][0].clone();
    self_signature["keyid"] = "root-signing".into();
    transition["signatures"]
        .as_array_mut()
        .ok_or("signatures")?
        .push(self_signature);
    let mut recovered = repository(1, 1, &new_key)?;
    recovered
        .files
        .insert("3.root.json".into(), serde_json::to_vec(&transition)?);
    let recovered = run(path, &bootstrap, &mut recovered, now)?;
    assert_eq!(recovered.report()["root_version"], 3);
    assert_eq!(recovered.report()["targets_version"], 1);
    fs::write(&state_path, b"{broken")?;
    let mut repo = repository(6, 14, &key)?;
    assert!(run(path, &bootstrap, &mut repo, now).is_err());
    assert!(repo.requested.is_empty());
    assert_eq!(fs::read(&state_path)?, b"{broken");
    fs::remove_file(&state_path)?;
    assert!(run(path, &bootstrap, &mut repo, now).is_err());
    // Restore only this disposable synthetic fixture to exercise write failure.
    fs::write(&state_path, valid_state)?;
    repo.break_storage = Some(marker);
    assert!(run(path, &bootstrap, &mut repo, now).is_err());
    assert!(!repo.requested.iter().any(|name| name == "targets.json"));
    threshold_rotation_preserves_floors(now, &key)?;
    Ok(())
}

fn threshold_rotation_preserves_floors(
    now: jiff::Timestamp,
    key: &SigningKey,
) -> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let other = SigningKey::from_bytes(&[44; 32]);
    let mut initial: Value = serde_json::from_slice(&root(1, key)?)?;
    initial["signed"]["keys"]["second"] = json!({"keytype":"ed25519","scheme":"ed25519","keyval":{"public":hex(other.verifying_key().as_bytes())}});
    for role in ["timestamp", "snapshot"] {
        initial["signed"]["roles"][role]["keyids"] = json!(["synthetic", "second"]);
    }
    let bootstrap = signed(initial["signed"].clone(), key)?;
    run(
        temporary.path(),
        &bootstrap,
        &mut repository(1, 10, key)?,
        now,
    )?;
    initial["signed"]["version"] = 2.into();
    for role in ["timestamp", "snapshot"] {
        initial["signed"]["roles"][role]["threshold"] = 2.into();
    }
    let mut repo = repository(2, 9, key)?;
    repo.files.insert(
        "2.root.json".into(),
        signed(initial["signed"].clone(), key)?,
    );
    assert!(run(temporary.path(), &bootstrap, &mut repo, now).is_err());
    let sign_both = |repo: &mut Repo| -> std::result::Result<(), Box<dyn Error>> {
        for name in ["snapshot.json", "timestamp.json"] {
            let mut value: Value = serde_json::from_slice(repo.files.get(name).ok_or("metadata")?)?;
            if name == "timestamp.json" {
                let version = value["signed"]["version"].as_u64().ok_or("version")?;
                value["signed"]["meta"]["snapshot.json"] =
                    pin(version, repo.files.get("snapshot.json").ok_or("snapshot")?);
                value = serde_json::from_slice(&signed(value["signed"].clone(), key)?)?;
            }
            let bytes = sigstore_tuf::canonical_json::to_canonical_bytes(&value["signed"])?;
            value["signatures"]
                .as_array_mut()
                .ok_or("signatures")?
                .push(json!({"keyid":"second","sig":hex(&other.sign(&bytes).to_bytes())}));
            repo.files.insert(name.into(), serde_json::to_vec(&value)?);
        }
        Ok(())
    };
    sign_both(&mut repo)?;
    // The new threshold authenticates the candidate, but cannot erase the old
    // targets floor, even after the root update was persisted and reopened.
    assert!(run(temporary.path(), &bootstrap, &mut repo, now).is_err());
    let mut valid = repository(3, 11, key)?;
    sign_both(&mut valid)?;
    assert_eq!(
        run(temporary.path(), &bootstrap, &mut valid, now)?.report()["root_version"],
        2
    );
    assert!(run(temporary.path(), &bootstrap, &mut valid, now).is_ok());
    Ok(())
}
