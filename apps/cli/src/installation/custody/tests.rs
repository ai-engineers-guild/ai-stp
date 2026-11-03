use super::*;
use std::{error::Error, path::PathBuf};

fn source() -> Source {
    Source {
        stable_id: "component_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        version: "1.0".into(),
        passport_digest: digest::sha256(b"immutable-source"),
    }
}
fn operation() -> String {
    format!("operation_{}", ulid::Ulid::generate())
}
fn fixture() -> Result<(tempfile::TempDir, PathBuf, PathBuf)> {
    let temporary = tempfile::tempdir().map_err(|_| invalid())?;
    let root = temporary.path().canonicalize().map_err(|_| invalid())?;
    let metadata = root.join("metadata");
    let target = root.join("target");
    std::fs::create_dir(&metadata).map_err(|_| invalid())?;
    std::fs::create_dir(&target).map_err(|_| invalid())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&metadata, std::fs::Permissions::from_mode(0o700))
            .map_err(|_| invalid())?;
    }
    #[cfg(windows)]
    super::super::private_fixture(&root).map_err(|_| invalid())?;
    Ok((temporary, metadata, target))
}
fn target(path: &Path) -> Result<Target> {
    native(Target::resolve(path, ".native-fixture"))
}
fn subject(label: &str, target: &Target) -> Result<Subject> {
    Subject::capture(
        digest::sha256(label.as_bytes()),
        "codex".into(),
        crate::projection::Scope::Project,
        target,
    )
}
fn desired(target: &Target, bytes: &[u8]) -> Result<Desired> {
    Desired::capture(
        target,
        "AGENTS.md",
        Ownership::Whole,
        bytes,
        0o600,
        source(),
    )
}
fn put(path: &Path, bytes: &[u8]) -> std::result::Result<(), Box<dyn Error>> {
    // Exercise a genuine atomic replacement, including a new held file identity.
    let staging = path.with_extension("candidate");
    std::fs::write(&staging, bytes)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&staging, std::fs::Permissions::from_mode(0o600))?;
    }
    #[cfg(windows)]
    if path.exists() {
        std::fs::remove_file(path)?;
    }
    std::fs::rename(staging, path)?;
    Ok(())
}
fn claim_count(custody: &Custody) -> Result<usize> {
    Ok(custody.inspect()?["claims"]
        .as_array()
        .ok_or_else(invalid)?
        .len())
}
fn refs(custody: &Custody) -> Result<usize> {
    Ok(custody.inspect()?["claims"][0]["references"]
        .as_object()
        .ok_or_else(invalid)?
        .len())
}

#[test]
fn shared_references_survive_restart_and_one_owner_release_preserves_the_file()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let first = subject("state-directory-one:personal", &target)?;
    let second = subject("state-directory-two:corporate", &target)?;
    let mut custody = Custody::open(&metadata)?;
    let initial = custody.review(
        operation(),
        &[Change {
            subject: first.clone(),
            desired: vec![desired(&target, b"owned guidance")?],
        }],
    )?;
    assert!(custody.prepare(&initial, "sha256:wrong").is_err());
    custody.prepare(&initial, &initial.digest()?)?;
    assert!(
        !path.join("AGENTS.md").exists(),
        "custody preparation must not write harness files"
    );
    custody.start(&initial)?;
    put(&path.join("AGENTS.md"), b"owned guidance")?;
    let original = custody.complete(&initial)?;
    assert_eq!(claim_count(&custody)?, 1);
    assert_eq!(refs(&custody)?, 1);
    drop(custody);
    let mut custody = Custody::open(&metadata)?;
    let shared = custody.review(
        operation(),
        &[Change {
            subject: second.clone(),
            desired: vec![desired(&target, b"owned guidance")?],
        }],
    )?;
    custody.prepare(&shared, &shared.digest()?)?;
    custody.start(&shared)?;
    custody.complete(&shared)?;
    assert_eq!(refs(&custody)?, 2);
    let release = custody.review(
        operation(),
        &[Change {
            subject: first,
            desired: vec![],
        }],
    )?;
    custody.prepare(&release, &release.digest()?)?;
    custody.start(&release)?;
    custody.complete(&release)?;
    assert_eq!(refs(&custody)?, 1);
    assert_eq!(std::fs::read(path.join("AGENTS.md"))?, b"owned guidance");
    assert_eq!(
        custody.complete(&initial)?,
        original,
        "historical replay cannot restore old reference state"
    );
    assert_eq!(refs(&custody)?, 1);
    let final_release = custody.review(
        operation(),
        &[Change {
            subject: second,
            desired: vec![],
        }],
    )?;
    custody.prepare(&final_release, &final_release.digest()?)?;
    custody.start(&final_release)?;
    assert!(
        custody.complete(&final_release).is_err(),
        "a metadata intent is not proof of file removal"
    );
    std::fs::remove_file(path.join("AGENTS.md"))?;
    custody.complete(&final_release)?;
    assert_eq!(claim_count(&custody)?, 0);
    Ok(())
}

#[test]
fn conflicting_shared_updates_unowned_files_and_external_drift_refuse()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let a = subject("first", &target)?;
    let b = subject("second", &target)?;
    let mut custody = Custody::open(&metadata)?;
    put(&path.join("AGENTS.md"), b"unowned")?;
    assert!(
        custody
            .review(
                operation(),
                &[Change {
                    subject: a.clone(),
                    desired: vec![desired(&target, b"unowned")?]
                }]
            )
            .is_err()
    );
    std::fs::remove_file(path.join("AGENTS.md"))?;
    let plan = custody.review(
        operation(),
        &[Change {
            subject: a.clone(),
            desired: vec![desired(&target, b"owned")?],
        }],
    )?;
    custody.prepare(&plan, &plan.digest()?)?;
    custody.start(&plan)?;
    put(&path.join("AGENTS.md"), b"owned")?;
    custody.complete(&plan)?;
    let share = custody.review(
        operation(),
        &[Change {
            subject: b,
            desired: vec![desired(&target, b"owned")?],
        }],
    )?;
    custody.prepare(&share, &share.digest()?)?;
    custody.start(&share)?;
    custody.complete(&share)?;
    assert!(
        custody
            .review(
                operation(),
                &[Change {
                    subject: a.clone(),
                    desired: vec![desired(&target, b"replacement")?]
                }]
            )
            .is_err()
    );
    put(&path.join("AGENTS.md"), b"external edit")?;
    assert!(
        custody
            .review(
                operation(),
                &[Change {
                    subject: a,
                    desired: vec![]
                }]
            )
            .is_err()
    );
    assert_eq!(std::fs::read(path.join("AGENTS.md"))?, b"external edit");
    Ok(())
}

#[test]
fn prepared_cancellation_and_lost_reply_recovery_keep_the_exact_operation()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let owner = subject("owner", &target)?;
    let mut custody = Custody::open(&metadata)?;
    let cancelled = custody.review(
        operation(),
        &[Change {
            subject: owner.clone(),
            desired: vec![desired(&target, b"cancelled")?],
        }],
    )?;
    custody.prepare(&cancelled, &cancelled.digest()?)?;
    let cancellation = custody.cancel(&cancelled)?;
    assert_eq!(
        custody.prepare(&cancelled, &cancelled.digest()?)?,
        cancellation
    );
    assert!(custody.start(&cancelled).is_err());
    assert!(!path.join("AGENTS.md").exists());
    let plan = custody.review(
        operation(),
        &[Change {
            subject: owner,
            desired: vec![desired(&target, b"resume")?],
        }],
    )?;
    custody.prepare(&plan, &plan.digest()?)?;
    custody.start(&plan)?;
    let bytes = serde_json::to_vec(&plan.value()?)?;
    let hash = plan.digest()?;
    drop(custody);
    put(&path.join("AGENTS.md"), b"resume")?;
    let parsed = Review::parse(&bytes, &hash)?;
    let mut custody = Custody::open(&metadata)?;
    let result = custody.complete(&parsed)?;
    assert_eq!(custody.complete(&parsed)?, result);
    assert_eq!(refs(&custody)?, 1);
    Ok(())
}

#[test]
fn metadata_lock_and_replaced_target_refuse_before_claiming_unknown_data()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let mut custody = Custody::open(&metadata)?;
    assert!(Custody::open(&metadata).is_err());
    let plan = custody.review(
        operation(),
        &[Change {
            subject: subject("owner", &target)?,
            desired: vec![desired(&target, b"planned")?],
        }],
    )?;
    drop(target);
    std::fs::rename(&path, path.with_extension("retained"))?;
    std::fs::create_dir(&path)?;
    assert!(custody.prepare(&plan, &plan.digest()?).is_err());
    assert!(std::fs::read_dir(&path)?.next().is_none());
    Ok(())
}

#[test]
fn independent_contribution_owners_preserve_each_other_and_unowned_fields()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let a = subject("company-a", &target)?;
    let b = subject("personal-b", &target)?;
    let mut custody = Custody::open(&metadata)?;
    let file = path.join("config.json");
    let original = br#"{"unowned":{"value":"private-canary"}}"#;
    put(&file, original)?;
    let kind_a = Ownership::Contribution {
        parser_id: "json/1".into(),
        key: "mcpServers".into(),
    };
    let kind_b = Ownership::Contribution {
        parser_id: "json/1".into(),
        key: "hooks".into(),
    };
    let after_a=br#"{"unowned":{"value":"private-canary"},"mcpServers":{"review":{"command":"review-helper"}}}"#;
    let wanted_a = Desired::capture(
        &target,
        "config.json",
        kind_a.clone(),
        after_a,
        0o600,
        source(),
    )?;
    let plan = custody.review(
        operation(),
        &[Change {
            subject: a.clone(),
            desired: vec![wanted_a],
        }],
    )?;
    custody.prepare(&plan, &plan.digest()?)?;
    assert_eq!(std::fs::read(&file)?, original);
    custody.start(&plan)?;
    put(&file, after_a)?;
    custody.complete(&plan)?;
    let after_b=br#"{"unowned":{"value":"private-canary"},"mcpServers":{"review":{"command":"review-helper"}},"hooks":{"ready":{}}}"#;
    let wanted_b = Desired::capture(&target, "config.json", kind_b, after_b, 0o600, source())?;
    let plan = custody.review(
        operation(),
        &[Change {
            subject: b.clone(),
            desired: vec![wanted_b],
        }],
    )?;
    custody.prepare(&plan, &plan.digest()?)?;
    custody.start(&plan)?;
    put(&file, after_b)?;
    custody.complete(&plan)?;
    assert_eq!(claim_count(&custody)?, 2);
    let plan = custody.review(
        operation(),
        &[Change {
            subject: a,
            desired: vec![],
        }],
    )?;
    custody.prepare(&plan, &plan.digest()?)?;
    custody.start(&plan)?;
    let only_b = br#"{"unowned":{"value":"private-canary"},"hooks":{"ready":{}}}"#;
    put(&file, only_b)?;
    custody.complete(&plan)?;
    assert_eq!(claim_count(&custody)?, 1);
    let data: Value = serde_json::from_slice(&std::fs::read(&file)?)?;
    assert_eq!(data["unowned"]["value"], "private-canary");
    assert!(data.get("hooks").is_some());
    let plan = custody.review(
        operation(),
        &[Change {
            subject: b,
            desired: vec![],
        }],
    )?;
    custody.prepare(&plan, &plan.digest()?)?;
    custody.start(&plan)?;
    put(&file, original)?;
    custody.complete(&plan)?;
    assert_eq!(claim_count(&custody)?, 0);
    assert_eq!(std::fs::read(&file)?, original);
    Ok(())
}

#[test]
fn existing_unowned_contribution_and_overlapping_root_roles_are_not_adopted()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let mut custody = Custody::open(&metadata)?;
    let existing = br#"{"mcpServers":{"unowned":{"command":"user-program"}}}"#;
    put(&path.join("config.json"), existing)?;
    let ownership = Ownership::Contribution {
        parser_id: "json/1".into(),
        key: "mcpServers".into(),
    };
    let wanted = Desired::capture(&target, "config.json", ownership, existing, 0o600, source())?;
    assert!(
        custody
            .review(
                operation(),
                &[Change {
                    subject: subject("new-owner", &target)?,
                    desired: vec![wanted]
                }]
            )
            .is_err()
    );
    assert_eq!(std::fs::read(path.join("config.json"))?, existing);
    let whole = custody.review(
        operation(),
        &[Change {
            subject: subject("first", &target)?,
            desired: vec![desired(&target, b"guidance")?],
        }],
    )?;
    custody.prepare(&whole, &whole.digest()?)?;
    custody.start(&whole)?;
    put(&path.join("AGENTS.md"), b"guidance")?;
    custody.complete(&whole)?;
    let nested = path.join("nested");
    std::fs::create_dir(&nested)?;
    let nested = super::tests::target(&nested)?;
    assert!(
        custody
            .review(
                operation(),
                &[Change {
                    subject: subject("nested-owner", &nested)?,
                    desired: vec![desired(&nested, b"nested")?]
                }]
            )
            .is_err()
    );
    Ok(())
}

#[test]
fn os_user_custody_address_cannot_be_split_by_state_or_home_environment()
-> std::result::Result<(), Box<dyn Error>> {
    const PROBE: &str = "AI_STP_TEST_CUSTODY_ADDRESS_PROBE";
    if std::env::var_os(PROBE).is_some() {
        let path = user_directory()?;
        println!("CUSTODY_OS_PATH:{}", serde_json::to_string(&path)?);
        return Ok(());
    }
    let temporary = tempfile::tempdir()?;
    let mut answers = Vec::new();
    for directory in ["one", "two"] {
        let path = temporary.path().join(directory);
        std::fs::create_dir(&path)?;
        let output=std::process::Command::new(std::env::current_exe()?)
            .args(["--exact","installation::custody::tests::os_user_custody_address_cannot_be_split_by_state_or_home_environment","--nocapture"])
            .env(PROBE,"1").env("HOME",&path).env("USERPROFILE",&path).env("LOCALAPPDATA",&path)
            .env("XDG_DATA_HOME",&path).env("AI_STP_STATE_DIR",&path).output()?;
        assert!(output.status.success(), "native placement probe failed");
        let stdout = String::from_utf8(output.stdout)?;
        let encoded = stdout
            .lines()
            .find_map(|line| line.strip_prefix("CUSTODY_OS_PATH:"))
            .ok_or("placement probe")?;
        answers.push(serde_json::from_str::<PathBuf>(encoded)?);
    }
    assert_eq!(answers[0], answers[1]);
    assert_eq!(answers[0], user_directory()?);
    assert!(!answers[0].starts_with(temporary.path()));
    Ok(())
}

#[test]
fn drift_after_preparation_cannot_start_the_original_custody_publication()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let mut custody = Custody::open(&metadata)?;
    let plan = custody.review(
        operation(),
        &[Change {
            subject: subject("owner", &target)?,
            desired: vec![desired(&target, b"planned")?],
        }],
    )?;
    custody.prepare(&plan, &plan.digest()?)?;
    put(&path.join("AGENTS.md"), b"new-unowned-data")?;
    assert!(custody.start(&plan).is_err());
    assert_eq!(std::fs::read(path.join("AGENTS.md"))?, b"new-unowned-data");
    custody.cancel(&plan)?;
    assert_eq!(claim_count(&custody)?, 0);
    Ok(())
}
