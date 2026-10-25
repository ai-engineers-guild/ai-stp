//! Real SQLite/vault boundaries. Fixtures never enroll or contact an account.

use super::*;
use std::{error::Error, fs, os::unix::fs::PermissionsExt};

struct RestorePermissions(PathBuf);
impl Drop for RestorePermissions {
    fn drop(&mut self) {
        let _ = fs::set_permissions(&self.0, fs::Permissions::from_mode(0o700));
    }
}

fn initialized() -> std::result::Result<(tempfile::TempDir, String, Value), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let plan = identity::plan(root.path(), identity::Storage::File, &at)?;
    let report = identity::apply(&plan, &plan.digest()?, &at)?.report();
    Ok((root, at, report))
}

fn entries(root: &Path) -> std::io::Result<Vec<std::ffi::OsString>> {
    let mut entries = fs::read_dir(root)?
        .map(|entry| entry.map(|entry| entry.file_name()))
        .collect::<std::io::Result<Vec<_>>>()?;
    entries.sort();
    Ok(entries)
}

#[test]
fn independent_enrollments_keep_one_registry_local_identity_and_unfinished_operations()
-> std::result::Result<(), Box<dyn Error>> {
    let (root, at, original) = initialized()?;
    let before = entries(root.path())?;
    let first = plan(
        root.path(),
        "Personal",
        "https://same-origin.example.test",
        "github",
        &at,
    )?;
    assert_eq!(first.registry_schema_before, 53);
    assert_eq!(entries(root.path())?, before);
    assert!(apply(&first, "sha256:incorrect", &at).is_err());
    assert!(apply(&first, &first.digest()?, &first.expires_at).is_err());
    assert_eq!(entries(root.path())?, before);
    let pending = format!("operation_{}", ulid::Ulid::generate());
    let id = super::super::identity_at(root.path())?;
    {
        let mut store = Store::open_at(id.root_directory(), true)?;
        store.transaction(|tx| {
            tx.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?1,'publication.run','applying',?2,'preserved intent')",params![pending,at]).map_err(database)?;
            Ok(())
        })?;
    }
    let first_result = apply(&first, &first.digest()?, &at)?;
    assert_eq!(
        first_result,
        apply(&first, &first.digest()?, &first.expires_at)?
    );
    let second = plan(
        root.path(),
        "Corporate",
        "https://same-origin.example.test",
        "keycloak",
        &at,
    )?;
    let second_result = apply(&second, &second.digest()?, &at)?;
    assert_ne!(
        first_result["connection"]["public_key"],
        second_result["connection"]["public_key"]
    );
    assert_ne!(
        first_result["connection"]["public_key"],
        original["public_key"]
    );
    assert_eq!(super::super::identity_at(root.path())?.report(), original);
    assert_eq!(
        list(root.path())?["connections"]
            .as_array()
            .ok_or("connections")?
            .len(),
        2
    );
    let store = Store::open_at(id.root_directory(), false)?;
    assert!(store.profiles_enabled()?);
    let retained: (String, String, Option<String>) = store
        .connection
        .query_row(
            "SELECT state,detail,finished_at FROM operation WHERE operation_id=?",
            [pending],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .map_err(database)?;
    assert_eq!(
        retained,
        ("applying".into(), "preserved intent".into(), None)
    );
    assert_eq!(
        entries(root.path())?,
        vec![
            std::ffi::OsString::from("ai-stp-v2-connections"),
            std::ffi::OsString::from("ai-stp-v2-identity"),
            std::ffi::OsString::from("ai-stp-v2-state")
        ]
    );
    Ok(())
}

#[test]
fn denied_key_write_leaves_exact_recoverable_admission_and_reuses_persisted_key()
-> std::result::Result<(), Box<dyn Error>> {
    let (root, at, _) = initialized()?;
    let intent = plan(
        root.path(),
        "Team",
        "https://company.example.test",
        "saml",
        &at,
    )?;
    let id = super::super::identity_at(root.path())?;
    {
        let _directory = OwnedDirectory::open_at(id.root_directory(), NAMESPACE, OWNER, true)?
            .ok_or("credentials")?;
    }
    let namespace = root.path().join(NAMESPACE);
    fs::set_permissions(&namespace, fs::Permissions::from_mode(0o500))?;
    let permissions = RestorePermissions(namespace.clone());
    let failure = apply(&intent, &intent.digest()?, &at);
    drop(permissions);
    assert!(failure.is_err());
    let observed = list(root.path())?;
    assert_eq!(observed["connections"][0]["state"], "creating");
    assert_eq!(
        observed["connections"][0]["pending_operation"]["plan_digest"],
        intent.digest()?
    );
    let public = {
        let directory = OwnedDirectory::open_at(id.root_directory(), NAMESPACE, OWNER, false)?
            .ok_or("credentials")?;
        let vault = Vault::new(&directory, intent.credential_store)?;
        assert!(vault.read_key(&intent.device_id)?.is_none());
        let key = identity::generate()?;
        vault.create_key(&intent.device_id, &key)?;
        STANDARD.encode(key.verifying_key().as_bytes())
    };
    let finished = apply(&intent, &intent.digest()?, &intent.expires_at)?;
    assert_eq!(finished["connection"]["public_key"], public);
    assert_eq!(finished["connection"]["pending_operation"], Value::Null);
    assert_eq!(
        finished,
        apply(&intent, &intent.digest()?, &intent.expires_at)?
    );
    {
        let directory = OwnedDirectory::open_at(id.root_directory(), NAMESPACE, OWNER, false)?
            .ok_or("credentials")?;
        Vault::new(&directory, intent.credential_store)?
            .retire(&format!("device-key.{}", intent.device_id))?;
    }
    assert!(apply(&intent, &intent.digest()?, &at).is_err());
    Ok(())
}

#[test]
fn admission_refuses_unowned_keys_and_rolls_back_schema_upgrade_on_identity_collision()
-> std::result::Result<(), Box<dyn Error>> {
    let (root, at, _) = initialized()?;
    let intent = plan(
        root.path(),
        "Private",
        "https://account.example.test",
        "google",
        &at,
    )?;
    let id = super::super::identity_at(root.path())?;
    {
        let directory = OwnedDirectory::open_at(id.root_directory(), NAMESPACE, OWNER, true)?
            .ok_or("credentials")?;
        Vault::new(&directory, intent.credential_store)?
            .create_key(&intent.device_id, &identity::generate()?)?;
    }
    assert!(apply(&intent, &intent.digest()?, &at).is_err());
    assert!(!root.path().join("ai-stp-v2-state").exists());
    {
        let directory = OwnedDirectory::open_at(id.root_directory(), NAMESPACE, OWNER, false)?
            .ok_or("credentials")?;
        Vault::new(&directory, intent.credential_store)?
            .retire(&format!("device-key.{}", intent.device_id))?;
    }
    {
        let mut store = Store::open_at(id.root_directory(), true)?;
        store.transaction(|tx| {
            tx.execute("INSERT INTO operation(operation_id,kind,state,started_at) VALUES (?1,'other.operation','verified',?2)",params![intent.operation_id,at]).map_err(database)?;
            Ok(())
        })?;
    }
    assert!(apply(&intent, &intent.digest()?, &at).is_err());
    let store = Store::open_at(id.root_directory(), false)?;
    assert!(!store.profiles_enabled()?);
    assert_eq!(
        store
            .connection
            .query_row(
                "SELECT count(*) FROM sqlite_schema WHERE name='native_connection'",
                [],
                |row| row.get::<_, i64>(0)
            )
            .map_err(database)?,
        0
    );
    Ok(())
}

#[test]
fn credential_namespace_replacement_does_not_authorize_replay_or_key_replacement()
-> std::result::Result<(), Box<dyn Error>> {
    let (root, at, _) = initialized()?;
    let intent = plan(
        root.path(),
        "Work",
        "https://company.example.test",
        "github",
        &at,
    )?;
    let expected = apply(&intent, &intent.digest()?, &at)?;
    let moved = root.path().join("retained-credentials");
    fs::rename(root.path().join(NAMESPACE), &moved)?;
    assert!(apply(&intent, &intent.digest()?, &at).is_err());
    let replacement = root.path().join(NAMESPACE);
    assert!(
        !replacement
            .join(format!("device-key.{}", intent.device_id))
            .exists()
    );
    // Remove only this empty test-owned replacement, then restore the original.
    fs::remove_dir_all(&replacement)?;
    fs::rename(&moved, &replacement)?;
    assert_eq!(apply(&intent, &intent.digest()?, &at)?, expected);
    Ok(())
}
