#![allow(clippy::unwrap_used)]

use std::{
    fs,
    time::{SystemTime, UNIX_EPOCH},
};

use super::*;

fn fixture() -> (PathBuf, Target, Admission) {
    let serial = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let root = std::env::temp_dir().join(format!("forward-config-{}-{serial}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let root = fs::canonicalize(root).unwrap();
    #[cfg(windows)]
    super::super::private_fixture(&root).unwrap();
    let target = Target::resolve(&root, ".control").unwrap();
    let admission = Admission {
        operation_id: "operation_FORWARD_1".into(),
        operation: "replace".into(),
        plan_digest: crate::digest::sha256(b"original full plan"),
        target_precondition_digest: crate::digest::sha256(b"original target"),
        target_scope: None,
    };
    (root, target, admission)
}

fn content(bytes: &[u8]) -> Content {
    Content::new(bytes.to_vec(), 0o600).unwrap()
}

#[cfg(unix)]
#[test]
fn an_existing_shared_control_directory_refuses_without_repair_or_private_records() {
    use std::os::unix::fs::PermissionsExt;
    let (root, target, _) = fixture();
    let control = target.control_directory();
    fs::create_dir(&control).unwrap();
    fs::set_permissions(&control, fs::Permissions::from_mode(0o755)).unwrap();
    fs::write(control.join("unowned"), b"preserve").unwrap();
    assert!(Writer::acquire(&target, ".control").is_err());
    assert_eq!(fs::read_dir(&control).unwrap().count(), 1);
    assert_eq!(fs::read(control.join("unowned")).unwrap(), b"preserve");
    assert_eq!(
        fs::metadata(&control).unwrap().permissions().mode() & 0o777,
        0o755
    );
    drop(target);
    fs::remove_dir_all(root).unwrap();
}

#[cfg(windows)]
#[test]
fn an_existing_shared_control_acl_refuses_without_repair_or_private_records() {
    let (root, target, _) = fixture();
    let control = target.control_directory();
    fs::create_dir(&control).unwrap();
    fs::write(control.join("unowned"), b"preserve").unwrap();
    let user = win_custody::current_user_sid_string().unwrap();
    win_custody::SecurityDescriptor::from_sddl(&format!("D:P(A;OICI;FA;;;{user})(A;OICI;FR;;;WD)"))
        .unwrap()
        .apply_to_tree(&control, true)
        .unwrap();
    assert!(Writer::acquire(&target, ".control").is_err());
    assert_eq!(fs::read_dir(&control).unwrap().count(), 1);
    assert_eq!(fs::read(control.join("unowned")).unwrap(), b"preserve");
    let everyone = win_custody::OwnedSid::from_string("S-1-1-0").unwrap();
    assert!(
        win_custody::ObjectSecurityDescriptor::query_file(&control)
            .unwrap()
            .dacl()
            .unwrap()
            .allowed_aces()
            .any(|ace| ace.trustee_matches(&everyone))
    );
    drop(target);
    fs::remove_dir_all(root).unwrap();
}

#[cfg(unix)]
#[test]
fn widened_control_permissions_stop_an_already_held_writer_before_admission() {
    use std::os::unix::fs::PermissionsExt;
    let (root, target, admission) = fixture();
    let mut writer = Writer::acquire(&target, ".control").unwrap();
    let control = target.control_directory();
    let database = control.join("forward/records.sqlite3");
    let before = fs::read(&database).unwrap();
    fs::set_permissions(&control, fs::Permissions::from_mode(0o755)).unwrap();
    assert!(
        writer
            .admit(&admission, &serde_json::json!({}), &[])
            .is_err()
    );
    assert!(writer.progress(&admission).is_err());
    assert!(writer.change("config", Some(content(b"private"))).is_err());
    assert!(
        writer
            .finish(&admission, &[], &serde_json::json!({}))
            .is_err()
    );
    assert_eq!(fs::read(&database).unwrap(), before);
    assert!(!root.join("config").exists());
    assert_eq!(
        fs::metadata(&control).unwrap().permissions().mode() & 0o777,
        0o755
    );
    drop(writer);
    drop(target);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn portable_effect_paths_refuse_case_aliases_parent_files_and_windows_devices() {
    let (root, target, _admission) = fixture();
    let writer = Writer::acquire(&target, ".control").unwrap();
    for paths in [
        ["Owned", "owned"],
        ["Config/a", "config/b"],
        ["leaf", "leaf/nested"],
    ] {
        let changes: Vec<_> = paths
            .iter()
            .map(|path| writer.change(path, Some(content(b"desired"))).unwrap())
            .collect();
        assert!(
            validate_changes(&changes).is_err(),
            "conflicting effects were accepted: {paths:?}"
        );
    }
    for path in [
        "CON",
        "nested/AUX.txt",
        "LPT1",
        "COM\u{b9}.json",
        "wild?card",
        "trailing.",
        "cafe\u{301}/file",
    ] {
        assert!(
            writer.change(path, Some(content(b"desired"))).is_err(),
            "nonportable effect was accepted: {path}"
        );
    }
    assert_eq!(fs::read_dir(&root).unwrap().count(), 1);
    drop(writer);
    drop(target);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn final_metadata_is_checked_together_with_all_admitted_effects() {
    for prior in [false, true] {
        let (root, target, admission) = fixture();
        let mut writer = Writer::acquire(&target, ".control").unwrap();
        let initial = if prior {
            vec![
                writer
                    .change("Config/a", Some(content(b"desired")))
                    .unwrap(),
            ]
        } else {
            vec![]
        };
        writer
            .admit(&admission, &serde_json::json!({}), &initial)
            .unwrap();
        writer.apply(&admission).unwrap();
        let mut conflicting = vec![];
        if !prior {
            conflicting.push(
                writer
                    .change("Config/a", Some(content(b"desired")))
                    .unwrap(),
            );
        }
        conflicting.push(writer.change("config/b", Some(content(b"alias"))).unwrap());
        let outcome = serde_json::json!({"state":"verified"});
        assert!(
            writer.finish(&admission, &conflicting, &outcome).is_err(),
            "finalization admitted a case-ambiguous namespace; prior={prior}"
        );
        assert!(matches!(
            writer.progress(&admission).unwrap(),
            Progress::Applying(_)
        ));
        assert!(!root.join("config/b").exists());
        let metadata = writer
            .change("state.json", Some(content(b"owned metadata")))
            .unwrap();
        writer.finish(&admission, &[metadata], &outcome).unwrap();
        writer.apply(&admission).unwrap();
        assert_eq!(writer.complete(&admission).unwrap(), outcome);
        assert_eq!(
            fs::read(root.join("state.json")).unwrap(),
            b"owned metadata"
        );
        drop(writer);
        drop(target);
        fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn an_external_component_database_is_refused_without_migration_or_byte_changes() {
    let (root, target, _admission) = fixture();
    let directory = target.control_directory().join("forward");
    fs::create_dir_all(&directory).unwrap();
    let database = directory.join("records.sqlite3");
    let db = rusqlite::Connection::open(&database).unwrap();
    db.execute_batch("PRAGMA application_id=1095976535; PRAGMA user_version=1; CREATE TABLE original(value TEXT); INSERT INTO original VALUES('retained external transaction');").unwrap();
    drop(db);
    let before = fs::read(&database).unwrap();
    assert!(Writer::acquire(&target, ".control").is_err());
    assert_eq!(fs::read(&database).unwrap(), before);
    assert!(!directory.join("records.sqlite3-journal").exists());
    drop(target);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn configuration_effects_cannot_read_or_overwrite_the_transaction_namespace() {
    let (root, target, admission) = fixture();
    let mut writer = Writer::acquire(&target, ".control").unwrap();
    let database = target.control_directory().join("forward/records.sqlite3");
    let before = fs::read(&database).unwrap();
    for path in [
        ".control/forward/records.sqlite3",
        ".CONTROL/target.lock",
        ".control/journal.json",
    ] {
        assert!(writer.read(path).is_err());
        assert!(
            writer
                .change(path, Some(content(b"untrusted component")))
                .is_err()
        );
        let mut injected = writer.change("allowed", Some(content(b"desired"))).unwrap();
        injected.path = path.into();
        assert!(
            writer
                .prepare(&admission, &serde_json::json!({}), &[injected])
                .is_err()
        );
    }
    assert!(
        writer
            .change(".control-neighbor", Some(content(b"desired")))
            .is_ok()
    );
    assert!(matches!(
        writer.progress(&admission).unwrap(),
        Progress::Absent
    ));
    assert_eq!(fs::read(database).unwrap(), before);
    drop(writer);
    drop(target);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn preparation_survives_restart_without_opening_the_publication_window() {
    for boundary in 0..3 {
        let (root, target, admission) = fixture();
        fs::write(root.join("owned"), b"original").unwrap();
        let mut writer = Writer::acquire(&target, ".control").unwrap();
        let old = admission.cancellation();
        assert_eq!(writer.cancel(&admission).unwrap(), old);
        let mut prepared = admission.clone();
        prepared.operation_id = "operation_PREPARED".into();
        let change = writer.change("owned", Some(content(b"desired"))).unwrap();
        writer
            .admit_inner(
                &prepared,
                &serde_json::json!({"exact":true}),
                &[change],
                true,
            )
            .unwrap();
        if boundary == 1 {
            fs::create_dir(target.control_directory().join(STAGING)).unwrap();
        } else if boundary == 2 {
            writer.prepared(&prepared).unwrap();
        }
        drop(writer);
        let header = fs::read(
            target
                .control_directory()
                .join("forward")
                .join(crate::installation::sqlite::DATABASE),
        )
        .unwrap();
        assert_eq!(u32::from_be_bytes(header[60..64].try_into().unwrap()), 2);
        let mut writer = Writer::acquire(&target, ".control").unwrap();
        assert!(
            matches!(writer.progress(&admission).unwrap(), Progress::Cancelled(value) if value == old)
        );
        assert!(matches!(
            writer.progress(&prepared).unwrap(),
            Progress::Prepared(_)
        ));
        assert!(writer.apply(&prepared).is_err());
        let receipt = writer.prepared(&prepared).unwrap();
        assert_eq!(writer.prepared(&prepared).unwrap(), receipt);
        assert_eq!(fs::read(root.join("owned")).unwrap(), b"original");
        assert!(
            crate::installation::journal::require_clean_for_planning(
                &target.control_directory(),
                &target.control_directory().join(STAGING),
                &[]
            )
            .is_err()
        );
        fs::write(root.join("owned"), b"foreign").unwrap();
        assert!(writer.start(&prepared).is_err());
        assert!(writer.cancel(&prepared).is_err());
        fs::write(root.join("owned"), b"original").unwrap();
        if boundary < 2 {
            // Simulate loss after the cancellation commit, before guard cleanup.
            writer
                .store
                .cancel(&prepared, &prepared.cancellation(), true)
                .unwrap();
            drop(writer);
            let mut writer = Writer::acquire(&target, ".control").unwrap();
            assert_eq!(writer.cancel(&prepared).unwrap(), prepared.cancellation());
            assert!(writer.journal().unwrap().is_none());
            assert!(!target.control_directory().join(STAGING).exists());
            assert_eq!(fs::read(root.join("owned")).unwrap(), b"original");
        } else {
            writer.start(&prepared).unwrap();
            assert!(writer.cancel(&prepared).is_err());
            drop(writer);
            let mut writer = Writer::acquire(&target, ".control").unwrap();
            let outcome = settle(&mut writer, &prepared);
            assert!(
                matches!(writer.progress(&prepared).unwrap(), Progress::Completed(value) if value == outcome)
            );
            assert_eq!(fs::read(root.join("owned")).unwrap(), b"desired");
        }
        assert!(!target.control_directory().join("backups").exists());
        drop(target);
        fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn cancellation_closes_admission_gaps_without_resurrecting_or_erasing_operations() {
    for admitted in [false, true] {
        let (root, target, admission) = fixture();
        fs::write(root.join("owned"), b"original").unwrap();
        let mut writer = Writer::acquire(&target, ".control").unwrap();
        let change = writer
            .change("owned", Some(content(b"desired only")))
            .unwrap();
        if admitted {
            writer
                .admit(&admission, &serde_json::json!({}), &[change])
                .unwrap();
            assert!(writer.journal().unwrap().is_none());
            fs::write(root.join("owned"), b"foreign edit").unwrap();
            assert!(writer.cancel(&admission).is_err());
            fs::write(root.join("owned"), b"original").unwrap();
            fs::create_dir(target.control_directory().join(STAGING)).unwrap();
            assert!(writer.cancel(&admission).is_err());
            fs::remove_dir(target.control_directory().join(STAGING)).unwrap();
        }
        let result = writer.cancel(&admission).unwrap();
        assert_eq!(result, admission.cancellation());
        drop(writer);
        let mut writer = Writer::acquire(&target, ".control").unwrap();
        assert_eq!(writer.cancel(&admission).unwrap(), result);
        assert!(
            matches!(writer.progress(&admission).unwrap(), Progress::Cancelled(value) if value == result)
        );
        assert!(writer.apply(&admission).is_err());
        assert!(
            writer
                .store
                .changes(&admission.operation_id)
                .unwrap()
                .is_empty()
        );
        assert_eq!(fs::read(root.join("owned")).unwrap(), b"original");
        let mut wrong = admission.clone();
        wrong.plan_digest = crate::digest::sha256(b"another plan");
        assert!(writer.cancel(&wrong).is_err());

        let mut later = admission.clone();
        later.operation_id = "operation_FORWARD_2".into();
        later.plan_digest = crate::digest::sha256(b"later plan");
        let change = writer
            .change("owned", Some(content(b"later bytes")))
            .unwrap();
        writer
            .admit(&later, &serde_json::json!({}), &[change])
            .unwrap();
        writer.apply(&later).unwrap();
        let guard = writer.journal().unwrap();
        assert!(guard.is_some());
        assert!(writer.cancel(&later).is_err());
        // Historical cancellation never removes a later operation's guard.
        assert_eq!(writer.cancel(&admission).unwrap(), result);
        let mut absent = admission.clone();
        absent.operation_id = "operation_NEVER_ADMITTED".into();
        writer.cancel(&absent).unwrap();
        assert_eq!(writer.journal().unwrap(), guard);
        let terminal = settle(&mut writer, &later);
        assert!(writer.cancel(&later).is_err());
        assert!(
            matches!(writer.progress(&later).unwrap(), Progress::Completed(value) if value == terminal)
        );
        assert_eq!(fs::read(root.join("owned")).unwrap(), b"later bytes");
        assert!(!target.control_directory().join("backups").exists());
        drop(writer);
        drop(target);
        fs::remove_dir_all(root).unwrap();
    }
}

fn settle(writer: &mut Writer, admission: &Admission) -> serde_json::Value {
    writer.apply(admission).unwrap();
    let outcome = serde_json::json!({"state":"verified", "operation_id":admission.operation_id});
    let metadata = writer
        .change("state.json", Some(content(b"new state")))
        .unwrap();
    writer.finish(admission, &[metadata], &outcome).unwrap();
    writer.apply(admission).unwrap();
    assert_eq!(writer.complete(admission).unwrap(), outcome);
    outcome
}

#[test]
fn interrupted_files_and_metadata_resume_without_before_images_or_historical_reapplication() {
    let (root, target, admission) = fixture();
    fs::write(root.join("old"), b"previous bytes are never retained").unwrap();
    fs::write(root.join("neighbor"), b"user-owned bytes").unwrap();
    let mut writer = Writer::acquire(&target, ".control").unwrap();
    assert!(Writer::acquire(&target, ".control").is_err());
    let changes = [
        writer.change("old", None).unwrap(),
        writer
            .change("skills/new/file", Some(content(b"complete desired bytes")))
            .unwrap(),
    ];
    writer
        .admit(
            &admission,
            &serde_json::json!({"runtime":"original"}),
            &changes,
        )
        .unwrap();
    let record = writer.store.record(&admission).unwrap().unwrap();
    let stage = writer.staging(&record).unwrap();
    files::publish(&writer.root, &stage, "0", &changes[0]).unwrap();
    stage.write("1", b"complete desired").unwrap();
    let guard = writer.journal().unwrap().unwrap();
    assert_eq!(guard.backup_ref, None);
    assert!(
        crate::installation::journal::require_clean_for_planning(
            &target.control_directory(),
            &target.control_directory().join(STAGING),
            &[]
        )
        .is_err()
    );
    drop(stage);
    drop(writer);
    let mut writer = Writer::acquire(&target, ".control").unwrap();
    let mut wrong = admission.clone();
    wrong.plan_digest = crate::digest::sha256(b"another plan");
    assert!(writer.progress(&wrong).is_err());
    assert!(matches!(
        writer.progress(&admission).unwrap(),
        Progress::Applying(_)
    ));
    writer.apply(&admission).unwrap();
    let outcome = serde_json::json!({"state":"verified", "operation_id":admission.operation_id});
    let metadata = writer
        .change("state.json", Some(content(b"new state")))
        .unwrap();
    writer.finish(&admission, &[metadata], &outcome).unwrap();
    let record = writer.store.record(&admission).unwrap().unwrap();
    let stage = writer.staging(&record).unwrap();
    let changes = writer.store.changes(&admission.operation_id).unwrap();
    files::publish(&writer.root, &stage, "2", &changes[2]).unwrap();
    drop(stage);
    drop(writer);
    let mut writer = Writer::acquire(&target, ".control").unwrap();
    assert!(matches!(
        writer.progress(&admission).unwrap(),
        Progress::Finishing
    ));
    writer.apply(&admission).unwrap();
    assert_eq!(writer.complete(&admission).unwrap(), outcome);
    assert!(
        writer
            .store
            .changes(&admission.operation_id)
            .unwrap()
            .is_empty()
    );
    assert!(writer.journal().unwrap().is_none());
    assert!(!target.control_directory().join(STAGING).exists());
    assert!(!target.control_directory().join("backups").exists());
    assert!(!root.join("old").exists());
    assert_eq!(
        fs::read(root.join("skills/new/file")).unwrap(),
        b"complete desired bytes"
    );
    assert_eq!(
        fs::read(root.join("neighbor")).unwrap(),
        b"user-owned bytes"
    );
    let mut later = admission.clone();
    later.operation_id = "operation_FORWARD_2".into();
    later.plan_digest = crate::digest::sha256(b"later plan");
    let replacement = writer
        .change("skills/new/file", Some(content(b"later desired bytes")))
        .unwrap();
    writer
        .admit(&later, &serde_json::json!({}), &[replacement])
        .unwrap();
    settle(&mut writer, &later);
    assert!(
        matches!(writer.progress(&admission).unwrap(), Progress::Completed(value) if value == outcome)
    );
    assert_eq!(
        fs::read(root.join("skills/new/file")).unwrap(),
        b"later desired bytes"
    );
    drop(writer);
    assert_no_payloads(&target);
    drop(target);
    fs::remove_dir_all(root).unwrap();
}

fn assert_no_payloads(target: &Target) {
    let database = fs::read(target.control_directory().join("forward/records.sqlite3")).unwrap();
    for absent in [
        b"previous bytes are never retained".as_slice(),
        b"complete desired bytes",
        b"later desired bytes",
    ] {
        assert!(!database.windows(absent.len()).any(|part| part == absent));
    }
}

#[test]
fn interrupted_removal_finishes_original_metadata_without_deleting_later_files() {
    let (root, target, mut admission) = fixture();
    admission.operation = "remove".into();
    fs::write(root.join("old"), b"previous bytes are never retained").unwrap();
    let mut writer = Writer::acquire(&target, ".control").unwrap();
    let change = writer.change("old", None).unwrap();
    writer
        .admit(
            &admission,
            &serde_json::json!({}),
            std::slice::from_ref(&change),
        )
        .unwrap();
    let record = writer.store.record(&admission).unwrap().unwrap();
    let stage = writer.staging(&record).unwrap();
    files::publish(&writer.root, &stage, "0", &change).unwrap();
    drop(stage);
    drop(writer);
    let mut writer = Writer::acquire(&target, ".control").unwrap();
    let outcome = settle(&mut writer, &admission);
    assert!(!root.join("old").exists());
    fs::write(root.join("old"), b"a later user's file").unwrap();
    assert!(
        matches!(writer.progress(&admission).unwrap(), Progress::Completed(value) if value == outcome)
    );
    assert_eq!(fs::read(root.join("old")).unwrap(), b"a later user's file");
    drop(writer);
    assert_no_payloads(&target);
    assert!(!target.control_directory().join("backups").exists());
    drop(target);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn admission_and_recovery_refuse_foreign_content_and_replaced_parent_directories() {
    let (root, target, admission) = fixture();
    fs::create_dir(root.join("skills")).unwrap();
    fs::write(root.join("skills/existing"), b"initial").unwrap();
    let mut writer = Writer::acquire(&target, ".control").unwrap();
    let change = writer
        .change("skills/existing", Some(content(b"intended")))
        .unwrap();
    fs::write(root.join("skills/existing"), b"changed before admission").unwrap();
    assert!(
        writer
            .admit(&admission, &serde_json::json!({}), &[change])
            .is_err()
    );
    let change = writer
        .change("skills/new/entry", Some(content(b"intended")))
        .unwrap();
    writer
        .admit(&admission, &serde_json::json!({}), &[change])
        .unwrap();
    // The first existing ancestor stays bound even when later parents were absent.
    fs::rename(root.join("skills"), root.join("held-skills")).unwrap();
    fs::create_dir(root.join("skills")).unwrap();
    assert!(writer.apply(&admission).is_err());
    assert!(!root.join("skills/new").exists());
    fs::remove_dir(root.join("skills")).unwrap();
    fs::rename(root.join("held-skills"), root.join("skills")).unwrap();
    writer.apply(&admission).unwrap();
    fs::write(root.join("skills/new/entry"), b"external edit").unwrap();
    assert!(writer.apply(&admission).is_err());
    assert_eq!(
        fs::read(root.join("skills/new/entry")).unwrap(),
        b"external edit"
    );
    drop(writer);
    drop(target);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn closed_transaction_scope_releases_its_lock_with_a_retained_descriptor() {
    let (root, target, _admission) = fixture();
    fs::create_dir(root.join("metadata")).unwrap();
    let directory =
        cap_std::fs::Dir::open_ambient_dir(&root, cap_std::ambient_authority()).unwrap();
    crate::installation::sqlite::check_lock_release_with_retained_descriptor(
        &directory, "metadata",
    );
    drop(directory);
    drop(target);
    fs::remove_dir_all(root).unwrap();
}
