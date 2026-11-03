//! Persistent physical-target fencing for historical external configuration writers.
//!
//! Released setup components refuse an unknown journal schema before mutation
//! or recovery. These markers are operational metadata, never backup payloads.

pub(crate) mod adoption;
mod locks;
pub(crate) use locks::Locks;

use super::{custody::Custody, forward, target::Target};
use crate::{
    error::{Failure, Result},
    files::physical::DirectoryIdentity,
};
use serde_json::json;

const CONTROLS: [&str; 7] = [
    ".claude-setup-system",
    ".codex-setup-system",
    ".cursor-setup-system",
    ".grok-setup-system",
    ".pi-setup-system",
    ".opencode-setup-system",
    ".antigravity-setup-system",
];
pub(crate) fn is_guard(path: &str) -> bool {
    CONTROLS
        .iter()
        .any(|control| path == format!("{control}/journal.json"))
}
fn invalid() -> Failure {
    Failure::precondition(
        "existing external configuration custody requires its explicit adoption or original recovery before native installation",
    )
}
fn native<T>(value: super::Result<T>) -> Result<T> {
    value.map_err(|_| invalid())
}

/// Review a fixed set of permanent legacy-writer guards. This reads existing
/// directories and creates no files. The qualified writer later publishes these
/// exact changes together with the native operation, before configuration files.
pub fn review(target: &Target, custody: &Custody) -> Result<Vec<forward::Change>> {
    review_with(target, custody, None)
}
pub(crate) fn review_with(
    target: &Target,
    custody: &Custody,
    adoption: Option<&adoption::Adoption>,
) -> Result<Vec<forward::Change>> {
    let directory = native(target.directory())?;
    let marker = marker(target, custody)?;
    let mut changes = Vec::new();
    for control in CONTROLS {
        let path = format!("{control}/journal.json");
        let (before, content) = native(forward::observe(target, &path))?;
        if let Some(content) = content {
            if content.bytes != marker || content.mode != 0o600 {
                return Err(invalid());
            }
            continue;
        }
        match super::target::child(&directory, std::ffi::OsStr::new(control)) {
            Ok(_) if adoption.is_some_and(|proof| proof.control() == control) => (),
            Ok(directory) if locks::lock_only(target, &directory, control)? => (),
            Ok(_) => return Err(invalid()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
            Err(_) => return Err(invalid()),
        }
        changes.push(forward::Change {
            path,
            before,
            after: Some(native(forward::Content::new(marker.clone(), 0o600))?),
        });
    }
    native(forward::validate_changes(&changes))?;
    Ok(changes)
}

pub(crate) fn marker(target: &Target, custody: &Custody) -> Result<Vec<u8>> {
    let directory = native(target.directory())?;
    let identity = DirectoryIdentity::capture(&directory)?;
    let marker = crate::canonical::bytes(&json!({"schema_version":2,
        "format":"ai-stp-native-custody-fence/1","target":identity,
        "coordinator":custody.physical_identity()?,"phase":"committed",
        "operation_id":"native-custody","operation":"native-custody",
        "plan_digest":crate::digest::sha256(b"ai-stp-native-custody-fence/1"),
        "target_precondition_digest":crate::digest::canonical("ai-stp:installation-operation:v1",&serde_json::to_value(&identity).map_err(|_|invalid())?)?,
        "backup_ref":null}))?;
    Ok(marker)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::error::Error;
    fn fixture() -> std::result::Result<(tempfile::TempDir, Target, Custody), Box<dyn Error>> {
        let temporary = tempfile::tempdir()?;
        let root = temporary.path().canonicalize()?;
        let config = root.join("configuration");
        let state = root.join("custody");
        std::fs::create_dir(&config)?;
        std::fs::create_dir(&state)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&state, std::fs::Permissions::from_mode(0o700))?;
        }
        #[cfg(windows)]
        super::super::private_fixture(&root)?;
        Ok((
            temporary,
            Target::resolve(&config, ".ai-stp-native")?,
            Custody::open(&state)?,
        ))
    }
    fn publish(
        target: &Target,
        changes: &[forward::Change],
    ) -> std::result::Result<(), Box<dyn Error>> {
        let mut writer = forward::Writer::acquire(target, ".ai-stp-native")?;
        let admission = forward::Admission {
            operation_id: format!("operation_{}", ulid::Ulid::generate()),
            plan_digest: crate::digest::sha256(b"reviewed native target custody transfer"),
            operation: "install".into(),
            target_precondition_digest: crate::digest::sha256(b"physical observations"),
            target_scope: None,
        };
        writer.prepare(
            &admission,
            &json!({"fixture":"target-custody-transfer"}),
            changes,
        )?;
        writer.start(&admission)?;
        writer.apply(&admission)?;
        writer.finish(&admission, &[], &json!({"state":"completed"}))?;
        writer.apply(&admission)?;
        writer.complete(&admission)?;
        Ok(())
    }
    #[test]
    fn permanent_guards_bind_both_physical_roots_and_preserve_configuration()
    -> std::result::Result<(), Box<dyn Error>> {
        let (_temporary, target, custody) = fixture()?;
        std::fs::write(target.root().join("AGENTS.md"), b"unowned instructions")?;
        let changes = review(&target, &custody)?;
        assert_eq!(changes.len(), 7);
        assert_eq!(std::fs::read_dir(target.root())?.count(), 1);
        publish(&target, &changes)?;
        for control in CONTROLS {
            assert!(super::super::journal::Journal::read(&target.root().join(control)).is_err());
        }
        assert!(review(&target, &custody)?.is_empty());
        assert_eq!(
            std::fs::read(target.root().join("AGENTS.md"))?,
            b"unowned instructions"
        );
        let other = target
            .root()
            .parent()
            .ok_or("parent")?
            .join("other-custody");
        std::fs::create_dir(&other)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&other, std::fs::Permissions::from_mode(0o700))?;
        }
        #[cfg(windows)]
        super::super::private_fixture(&other)?;
        assert!(review(&target, &Custody::open(&other)?).is_err());
        Ok(())
    }
    #[test]
    fn existing_legacy_controls_are_never_silently_adopted_or_overwritten()
    -> std::result::Result<(), Box<dyn Error>> {
        let (_temporary, target, custody) = fixture()?;
        let old = target.root().join(".codex-setup-system");
        std::fs::create_dir(&old)?;
        std::fs::write(
            old.join("original-receipt"),
            b"historical immutable receipt",
        )?;
        assert!(review(&target, &custody).is_err());
        assert_eq!(
            std::fs::read(old.join("original-receipt"))?,
            b"historical immutable receipt"
        );
        assert!(!old.join("journal.json").exists());
        assert!(!target.control_directory().exists());
        Ok(())
    }
    #[test]
    fn busy_legacy_writer_refuses_before_publication_and_empty_coordination_can_retry()
    -> std::result::Result<(), Box<dyn Error>> {
        let (_temporary, target, custody) = fixture()?;
        let control = target.root().join(".codex-setup-system");
        std::fs::create_dir(&control)?;
        let writer = crate::installation::lock::TargetLock::acquire(&control)?;
        assert!(Locks::acquire(&target, &custody, None).is_err());
        assert!(!target.root().join("AGENTS.md").exists());
        assert!(!control.join("journal.json").exists());
        drop(writer);
        let held = Locks::acquire(&target, &custody, None)?;
        held.revalidate()?;
        assert_eq!(review(&target, &custody)?.len(), 7);
        drop(held);
        std::fs::write(
            control.join("original-receipt"),
            b"unknown external custody",
        )?;
        assert!(Locks::acquire(&target, &custody, None).is_err());
        assert!(review(&target, &custody).is_err());
        assert_eq!(
            std::fs::read(control.join("original-receipt"))?,
            b"unknown external custody"
        );
        Ok(())
    }

    #[cfg(target_os = "linux")]
    #[test]
    #[ignore = "requires an independently verified published external Codex setup component"]
    fn released_external_writer_refuses_the_physical_target_after_native_transfer()
    -> std::result::Result<(), Box<dyn Error>> {
        let binary = std::env::var_os("AI_STP_TEST_PREVIOUS_SETUP_BINARY")
            .ok_or("published setup binary")?;
        let expected = std::env::var("AI_STP_TEST_PREVIOUS_SETUP_SHA256")?;
        assert_eq!(crate::digest::sha256(&std::fs::read(&binary)?), expected);
        let (_temporary, target, custody) = fixture()?;
        let run = || {
            crate::process::run(crate::process::Request {
                executable: std::path::Path::new(&binary),
                arguments: &[
                    "install".into(),
                    "minimal".into(),
                    "--target".into(),
                    target.root().as_os_str().into(),
                ],
                directory: target.root(),
                environment: &[("PATH".into(), "".into())],
                timeout: std::time::Duration::from_secs(10),
                output_limit: 65536,
            })
        };
        let changes = review(&target, &custody)?;
        let held = Locks::acquire(&target, &custody, None)?;
        let busy = run()?;
        assert!(!busy.status.success());
        assert!(std::str::from_utf8(&busy.stderr)?.contains("lock"));
        assert!(!target.root().join("AGENTS.md").exists());
        publish(&target, &changes)?;
        held.revalidate()?;
        drop(held);
        let output = run()?;
        assert!(!output.status.success());
        let stderr = std::str::from_utf8(&output.stderr)?;
        assert!(stderr.contains("journal schema 2"), "{stderr}");
        assert!(!target.root().join("AGENTS.md").exists());
        assert!(review(&target, &custody)?.is_empty());
        println!(
            "published external setup writer: unknown native custody journal refused before configuration effects"
        );
        Ok(())
    }
}
