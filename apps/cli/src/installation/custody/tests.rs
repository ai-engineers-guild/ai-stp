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
    let recovered = custody.pending()?.ok_or("pending custody review")?;
    assert_eq!(recovered.digest()?, hash);
    assert_eq!(custody.status(&recovered)?["state"], "applying");
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
fn a_deleted_claimed_root_does_not_block_another_target() -> std::result::Result<(), Box<dyn Error>>
{
    let (_temporary, metadata, path) = fixture()?;
    let first = target(&path)?;
    let mut custody = Custody::open(&metadata)?;
    let installed = custody.review(
        operation(),
        &[Change {
            subject: subject("deleted-project", &first)?,
            desired: vec![desired(&first, b"guidance")?],
        }],
    )?;
    custody.prepare(&installed, &installed.digest()?)?;
    custody.start(&installed)?;
    put(&path.join("AGENTS.md"), b"guidance")?;
    custody.complete(&installed)?;
    // The second root exists before the first is deleted: a file system may
    // hand a deleted directory's identity to the next one, and a recorded root
    // whose identity reappears is treated as that root, which fails closed.
    let other = path.with_file_name("other");
    std::fs::create_dir(&other)?;
    let second = target(&other)?;
    drop(first);
    std::fs::remove_dir_all(&path)?;
    let review = custody.review(
        operation(),
        &[Change {
            subject: subject("other-project", &second)?,
            desired: vec![desired(&second, b"guidance")?],
        }],
    )?;
    assert!(!review.digest()?.is_empty());
    assert_eq!(
        claim_count(&custody)?,
        1,
        "the deleted root keeps its recorded claim"
    );
    // A replaced root is not absent: it still refuses.
    std::fs::create_dir(&path)?;
    let nested = path.join("nested");
    std::fs::create_dir(&nested)?;
    let nested = target(&nested)?;
    assert!(
        custody
            .review(
                operation(),
                &[Change {
                    subject: subject("replaced-project", &nested)?,
                    desired: vec![desired(&nested, b"nested")?],
                }],
            )
            .is_err()
    );
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
        assert!(
            output.status.success(),
            "native placement probe failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
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

fn native_admission(review: &Review) -> Result<forward::Admission> {
    Ok(forward::Admission {
        operation_id: review.operation_id.clone(),
        plan_digest: review.digest()?,
        operation: "replace".into(),
        target_precondition_digest: review.before_digest.clone(),
        target_scope: Some("project".into()),
    })
}
fn publish_review(
    custody: &mut Custody,
    target: &Target,
    review: &Review,
    desired: &BTreeMap<String, forward::Content>,
) -> Result<()> {
    let changes = review.configuration_changes(target, desired)?;
    custody.prepare(review, &review.digest()?)?;
    let admission = native_admission(review)?;
    let mut writer = native(Writer::acquire(target, ".native-fixture"))?;
    native(writer.prepare(&admission, &review.value()?, &changes))?;
    custody.start(review)?;
    native(writer.start(&admission))?;
    native(writer.apply(&admission))?;
    native(writer.finish(&admission, &[], &json!({"state":"completed"})))?;
    native(writer.apply(&admission))?;
    native(writer.complete(&admission))?;
    custody.complete(review)?;
    Ok(())
}

#[test]
fn real_writer_recovers_reviewed_files_and_preserves_unowned_host_bytes()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let original =
        b"{\n // Keep this owner comment.\n \"unowned\":{\"value\":\"private-canary\"}\n}\n";
    put(&path.join("config.jsonc"), original)?;
    // The adapter must derive rights from the review, not from other fields
    // present in incoming assembled bytes.
    let incoming=br#"{"unowned":{"value":"must-not-replace"},"mcpServers":{"review":{"command":"review-helper"}}}"#;
    let mut custody = Custody::open(&metadata)?;
    let review = custody.review(
        operation(),
        &[Change {
            subject: subject("original-native-context", &target)?,
            desired: vec![
                desired(&target, b"reviewed guidance")?,
                Desired::capture(
                    &target,
                    "config.jsonc",
                    Ownership::Contribution {
                        parser_id: "json/1".into(),
                        key: "mcpServers".into(),
                    },
                    incoming,
                    0o600,
                    source(),
                )?,
            ],
        }],
    )?;
    let desired = BTreeMap::from([
        (
            "AGENTS.md".into(),
            native(forward::Content::new(b"reviewed guidance".to_vec(), 0o600))?,
        ),
        (
            "config.jsonc".into(),
            native(forward::Content::new(incoming.to_vec(), 0o600))?,
        ),
    ]);
    let changes = review.configuration_changes(&target, &desired)?;
    assert_eq!(changes.len(), 2);
    let bound = review.clone().bind_publications(&[(&target, &changes)])?;
    bound.verify_publications(&target, &changes)?;
    assert_ne!(bound.digest()?, review.digest()?);
    let mut changed = changes.clone();
    changed[0]
        .after
        .as_mut()
        .ok_or("desired content")?
        .bytes
        .push(b'!');
    assert!(bound.verify_publications(&target, &changed).is_err());
    let mut reordered = changes.clone();
    reordered.swap(0, 1);
    assert!(bound.verify_publications(&target, &reordered).is_err());
    let retained = Review::parse(&serde_json::to_vec(&bound.value()?)?, &bound.digest()?)?;
    retained.verify_publications(&target, &changes)?;
    custody.prepare(&review, &review.digest()?)?;
    let admission = native_admission(&review)?;
    {
        let mut writer = native(Writer::acquire(&target, ".native-fixture"))?;
        native(writer.prepare(&admission, &review.value()?, &changes))?;
        custody.start(&review)?;
        native(writer.start(&admission))?;
        let mut calls = 0;
        let interrupted = writer.apply_checked(&admission, || {
            calls += 1;
            if calls == 2 {
                return Err(crate::installation::Error::new(
                    crate::installation::ReasonCode::StateUnavailable,
                    "fixture: current authority unavailable",
                ));
            }
            Ok(())
        });
        assert!(interrupted.is_err());
        assert_eq!(calls, 2);
    }
    assert_eq!(std::fs::read(path.join("AGENTS.md"))?, b"reviewed guidance");
    assert_eq!(std::fs::read(path.join("config.jsonc"))?, original);
    drop(custody);
    let mut custody = Custody::open(&metadata)?;
    let recovered = custody.pending()?.ok_or("original custody review")?;
    assert_eq!(recovered.digest()?, review.digest()?);
    let mut writer = native(Writer::acquire(&target, ".native-fixture"))?;
    let (held, context) = native(writer.pending())?.ok_or("original desired payload")?;
    assert_eq!(held, admission);
    assert_eq!(context, recovered.value()?);
    native(writer.apply_checked(&admission, || Ok(())))?;
    native(writer.finish(&admission, &[], &json!({"state":"completed"})))?;
    native(writer.apply(&admission))?;
    native(writer.complete(&admission))?;
    let receipt = custody.complete(&recovered)?;
    let retained = custody
        .retained(&recovered.operation_id)?
        .ok_or("original terminal review")?;
    assert_eq!(retained.value()?, recovered.value()?);
    let metadata = serde_json::to_string(&retained.value()?)?;
    assert!(!metadata.contains("private-canary"));
    assert!(!metadata.contains("must-not-replace"));
    let host = std::fs::read(path.join("config.jsonc"))?;
    let text = std::str::from_utf8(&host)?;
    assert!(text.contains("Keep this owner comment."));
    assert!(text.contains("private-canary"));
    assert!(!text.contains("must-not-replace"));
    assert!(text.contains("review-helper"));
    assert_eq!(claim_count(&custody)?, 2);
    assert_eq!(custody.complete(&recovered)?, receipt);
    assert_eq!(std::fs::read(path.join("config.jsonc"))?, host);
    Ok(())
}

#[test]
fn structured_key_replacement_and_last_withdrawal_use_the_real_native_writer()
-> std::result::Result<(), Box<dyn Error>> {
    use crate::authoring::contribution::{self, Format};
    for (file, original, old, incoming) in [
        (
            "config.jsonc",
            b"{\n // Keep this owner comment.\n \"unowned\":{\"value\":\"private-canary\"}\n}\n"
                .as_slice(),
            br#"{"mcpServers":{"review":{"command":"review-helper"}}}"#.as_slice(),
            br#"{"hooks":{"ready":{}},"unowned":{"value":"must-not-replace"}}"#.as_slice(),
        ),
        (
            "config.toml",
            b"# Keep this owner comment.\n[unowned]\nvalue='private-canary'\n".as_slice(),
            b"[mcpServers.review]\ncommand='review-helper'\n".as_slice(),
            b"[hooks.ready]\n[unowned]\nvalue='must-not-replace'\n".as_slice(),
        ),
    ] {
        let (_temporary, metadata, path) = fixture()?;
        let target = target(&path)?;
        put(&path.join(file), original)?;
        let mut custody = Custody::open(&metadata)?;
        let subject = subject("original-native-context", &target)?;
        let kind = |key: &str| Ownership::Contribution {
            parser_id: if file.ends_with("toml") {
                "toml/1"
            } else {
                "json/1"
            }
            .into(),
            key: key.into(),
        };
        let initial = custody.review(
            operation(),
            &[Change {
                subject: subject.clone(),
                desired: vec![Desired::capture(
                    &target,
                    file,
                    kind("mcpServers"),
                    old,
                    0o600,
                    source(),
                )?],
            }],
        )?;
        publish_review(
            &mut custody,
            &target,
            &initial,
            &BTreeMap::from([(
                file.into(),
                native(forward::Content::new(old.to_vec(), 0o600))?,
            )]),
        )?;
        let replace = custody.review(
            operation(),
            &[Change {
                subject: subject.clone(),
                desired: vec![Desired::capture(
                    &target,
                    file,
                    kind("hooks"),
                    incoming,
                    0o600,
                    source(),
                )?],
            }],
        )?;
        publish_review(
            &mut custody,
            &target,
            &replace,
            &BTreeMap::from([(
                file.into(),
                native(forward::Content::new(incoming.to_vec(), 0o600))?,
            )]),
        )?;
        let host = std::fs::read(path.join(file))?;
        let format = Format::for_path(file)?;
        assert!(contribution::extract(format, &host, "mcpServers").is_err());
        assert!(contribution::extract(format, &host, "hooks").is_ok());
        assert!(std::str::from_utf8(&host)?.contains("private-canary"));
        assert!(!std::str::from_utf8(&host)?.contains("must-not-replace"));
        let remove = custody.review(
            operation(),
            &[Change {
                subject,
                desired: vec![],
            }],
        )?;
        publish_review(&mut custody, &target, &remove, &BTreeMap::new())?;
        let final_host = std::fs::read(path.join(file))?;
        assert!(contribution::extract(format, &final_host, "hooks").is_err());
        assert!(std::str::from_utf8(&final_host)?.contains("Keep this owner comment."));
        assert!(std::str::from_utf8(&final_host)?.contains("private-canary"));
        assert_eq!(claim_count(&custody)?, 0);
    }
    Ok(())
}

#[test]
fn repeating_an_unchanged_native_review_preserves_the_exact_digest()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let custody = Custody::open(&metadata)?;
    let operation = operation();
    let build = || {
        custody.review(
            operation.clone(),
            &[Change {
                subject: subject("original-context", &target)?,
                desired: vec![desired(&target, b"exact native guidance")?],
            }],
        )
    };
    assert_eq!(build()?.value()?, build()?.value()?);
    assert_eq!(build()?.digest()?, build()?.digest()?);
    assert!(std::fs::read_dir(&path)?.next().is_none());
    Ok(())
}

#[test]
fn unowned_host_edits_do_not_revoke_an_unchanged_named_contribution()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let mut custody = Custody::open(&metadata)?;
    let subject = subject("contribution-owner", &target)?;
    let original = br#"{"unowned":{"value":"first"}}"#;
    put(&path.join("config.json"), original)?;
    let incoming = br#"{"mcpServers":{"review":{"command":"review-helper"}}}"#;
    let review = custody.review(
        operation(),
        &[Change {
            subject: subject.clone(),
            desired: vec![Desired::capture(
                &target,
                "config.json",
                Ownership::Contribution {
                    parser_id: "json/1".into(),
                    key: "mcpServers".into(),
                },
                incoming,
                0o600,
                source(),
            )?],
        }],
    )?;
    publish_review(
        &mut custody,
        &target,
        &review,
        &BTreeMap::from([(
            "config.json".into(),
            native(forward::Content::new(incoming.to_vec(), 0o600))?,
        )]),
    )?;
    put(&path.join("config.json"),br#"{"unowned":{"value":"edited-by-user"},"mcpServers":{"review":{"command":"review-helper"}}}"#)?;
    let remove = custody.review(
        operation(),
        &[Change {
            subject,
            desired: vec![],
        }],
    )?;
    publish_review(&mut custody, &target, &remove, &BTreeMap::new())?;
    let current: Value = serde_json::from_slice(&std::fs::read(path.join("config.json"))?)?;
    assert_eq!(current["unowned"]["value"], "edited-by-user");
    assert!(current.get("mcpServers").is_none());
    assert_eq!(claim_count(&custody)?, 0);
    Ok(())
}

#[test]
fn inventory_observes_only_actual_current_refs_and_never_discloses_file_contents_or_paths()
-> std::result::Result<(), Box<dyn Error>> {
    let (_temporary, metadata, path) = fixture()?;
    let target = target(&path)?;
    let mut custody = Custody::open(&metadata)?;
    let id = operation();
    let review = custody.review(
        id.clone(),
        &[Change {
            subject: subject("inventory-native-subject", &target)?,
            desired: vec![desired(&target, b"PRIVATE-INVENTORY-FILE-CANARY")?],
        }],
    )?;
    custody.prepare(&review, &review.digest()?)?;
    custody.start(&review)?;
    put(&path.join("AGENTS.md"), b"PRIVATE-INVENTORY-FILE-CANARY")?;
    custody.complete(&review)?;
    let observations = custody.inventory(&id)?;
    assert_eq!(observations.len(), 1);
    assert_eq!(observations[0]["state"], "present");
    assert_eq!(observations[0]["source"], serde_json::to_value(source())?);
    let encoded = serde_json::to_string(&observations)?;
    for private in [
        "PRIVATE-INVENTORY-FILE-CANARY",
        "AGENTS.md",
        path.to_str().ok_or("fixture path")?,
    ] {
        assert!(!encoded.contains(private));
    }
    assert!(custody.inventory(&operation())?.is_empty());
    put(&path.join("AGENTS.md"), b"changed outside the setup")?;
    assert_eq!(custody.inventory(&id)?[0]["state"], "modified");
    std::fs::remove_file(path.join("AGENTS.md"))?;
    assert_eq!(custody.inventory(&id)?[0]["state"], "missing");
    assert_eq!(
        custody.inspect()?["claims"]
            .as_array()
            .ok_or("claims")?
            .len(),
        1
    );
    Ok(())
}
