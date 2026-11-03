use super::*;
use crate::{
    digest,
    installation::custody::{Change, Custody, Desired, Source, Subject},
    projection::Scope,
};
use serde_json::json;
use std::{error::Error, path::PathBuf};

struct Fixture {
    _temporary: tempfile::TempDir,
    target: Target,
    metadata: PathBuf,
    setup: Value,
}
impl Fixture {
    fn new() -> std::result::Result<Self, Box<dyn Error>> {
        let temporary = tempfile::tempdir()?;
        let root = temporary.path().canonicalize()?;
        let path = root.join("target");
        let metadata = root.join("custody");
        std::fs::create_dir(&path)?;
        std::fs::create_dir(&metadata)?;
        let control = path.join(".codex-setup-system");
        std::fs::create_dir(&control)?;
        std::fs::write(control.join("target.lock"), [])?;
        std::fs::write(path.join("AGENTS.md"), b"exact legacy guidance\n")?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&metadata, std::fs::Permissions::from_mode(0o700))?;
            std::fs::set_permissions(
                path.join("AGENTS.md"),
                std::fs::Permissions::from_mode(0o600),
            )?;
        }
        #[cfg(windows)]
        crate::installation::private_fixture(&root)?;
        let setup = json!({"stable_id":"component_01ARZ3NDEKTSV4RRFFQ69G5FAV", "version":"1.0", "passport_digest":digest::sha256(b"legacy-source")});
        std::fs::write(
            path.join("NDDEV-CODEX-PROVIDER.json"),
            serde_json::to_vec(&json!({
                "state_schema":4,"protocol_version":3,"provider_id":"codex-setup-system","provider_version":"0.0.95","harness_id":"codex",
                "canonical_target":path,"setup_stable_id":setup["stable_id"],"setup_version":setup["version"],"setup_version_passport_digest":setup["passport_digest"],
                "written_paths":["AGENTS.md"],"drift_state":"clean"
            }))?,
        )?;
        Ok(Self {
            _temporary: temporary,
            target: Target::resolve(&path, ".ai-stp-native")?,
            metadata,
            setup,
        })
    }
    fn rights(&self) -> BTreeMap<String, Ownership> {
        BTreeMap::from([("AGENTS.md".into(), Ownership::Whole)])
    }
    fn proof(&self) -> Result<Adoption> {
        Adoption::capture(&self.target, "codex", &self.setup, self.rights())
    }
    fn changes(&self) -> Result<Vec<Change>> {
        Ok(vec![Change {
            subject: Subject::capture(
                digest::sha256(b"original-native-context"),
                "codex".into(),
                Scope::Project,
                &self.target,
            )?,
            desired: vec![Desired::capture(
                &self.target,
                "AGENTS.md",
                Ownership::Whole,
                b"exact legacy guidance\n",
                0o600,
                serde_json::from_value::<Source>(self.setup.clone()).map_err(|_| invalid())?,
            )?],
        }])
    }
}
#[test]
fn exact_terminal_adoption_preserves_legacy_data_and_only_publishes_writer_fences()
-> std::result::Result<(), Box<dyn Error>> {
    let fixture = Fixture::new()?;
    let state = std::fs::read(fixture.target.root().join("NDDEV-CODEX-PROVIDER.json"))?;
    let mut custody = Custody::open(&fixture.metadata)?;
    let operation = format!("operation_{}", ulid::Ulid::generate());
    let desired = fixture.changes()?;
    assert!(custody.review(operation.clone(), &desired).is_err());
    let proof = fixture.proof()?;
    let evidence = proof.evidence()?;
    let proofs = vec![proof];
    let review = custody.review_adopting(operation.clone(), &desired, &proofs)?;
    assert!(
        review
            .configuration_changes(&fixture.target, &desired[0].desired)?
            .is_empty()
    );
    let guards = super::super::review_with(&fixture.target, &custody, Some(&proofs[0]))?;
    assert_eq!(guards.len(), 7);
    let review = review.bind_publications(&[(&fixture.target, &guards)])?;
    custody.prepare(&review, &review.digest()?)?;
    custody.start(&review)?;
    let admission = forward::Admission {
        operation_id: operation,
        plan_digest: review.digest()?,
        operation: "install".into(),
        target_precondition_digest: digest::sha256(b"legacy-custody-transfer"),
        target_scope: None,
    };
    let mut writer = forward::Writer::acquire(&fixture.target, ".ai-stp-native")?;
    writer.prepare(
        &admission,
        &json!({"fixture":"exact-legacy-adoption"}),
        &guards,
    )?;
    writer.start(&admission)?;
    writer.apply_checked(&admission, || {
        proofs[0]
            .revalidate(&fixture.target, &custody)
            .map_err(|_| {
                crate::installation::Error::new(
                    crate::installation::ReasonCode::RecoveryRequired,
                    "legacy evidence changed",
                )
            })
    })?;
    writer.finish(&admission, &[], &json!({"state":"completed"}))?;
    writer.apply(&admission)?;
    writer.complete(&admission)?;
    custody.complete(&review)?;
    drop(proofs);
    let reopened = Adoption::reopen(
        &fixture.target,
        "codex",
        &fixture.setup,
        &custody,
        &evidence,
    )?;
    reopened.revalidate(&fixture.target, &custody)?;
    assert_eq!(
        std::fs::read(fixture.target.root().join("AGENTS.md"))?,
        b"exact legacy guidance\n"
    );
    assert_eq!(
        std::fs::read(fixture.target.root().join("NDDEV-CODEX-PROVIDER.json"))?,
        state
    );
    assert_eq!(
        custody.inspect()?["claims"]
            .as_array()
            .ok_or("claims")?
            .len(),
        1
    );
    Ok(())
}
#[test]
fn ambiguous_owner_changed_source_and_unfinished_legacy_work_refuse_without_native_writes()
-> std::result::Result<(), Box<dyn Error>> {
    let fixture = Fixture::new()?;
    let mut wrong = fixture.setup.clone();
    wrong["version"] = json!("2.0");
    assert!(Adoption::capture(&fixture.target, "codex", &wrong, fixture.rights()).is_err());
    let control = fixture.target.root().join(".codex-setup-system");
    std::fs::write(control.join("journal.json"), b"{\"schema_version\":1}")?;
    assert!(fixture.proof().is_err());
    std::fs::remove_file(control.join("journal.json"))?;
    std::fs::create_dir(fixture.target.root().join(".cursor-setup-system"))?;
    assert!(fixture.proof().is_err());
    assert!(!fixture.target.control_directory().exists());
    assert_eq!(
        std::fs::read(fixture.target.root().join("AGENTS.md"))?,
        b"exact legacy guidance\n"
    );
    Ok(())
}
#[test]
fn foreign_asfw_database_is_checked_read_only_and_active_records_refuse()
-> std::result::Result<(), Box<dyn Error>> {
    let fixture = Fixture::new()?;
    let directory = fixture.target.root().join(".codex-setup-system/forward");
    std::fs::create_dir(&directory)?;
    let path = directory.join(sqlite::DATABASE);
    let db = rusqlite::Connection::open(&path)?;
    db.execute_batch("PRAGMA application_id=1095976535; PRAGMA user_version=2; CREATE TABLE operations(active INTEGER,phase TEXT); CREATE TABLE changes(payload BLOB); INSERT INTO operations VALUES(NULL,\"completed\");")?;
    db.close().map_err(|(_, error)| error)?;
    let before = std::fs::read(&path)?;
    let proof = fixture.proof()?;
    assert_eq!(std::fs::read(&path)?, before);
    drop(proof);
    let db = rusqlite::Connection::open(&path)?;
    db.execute("UPDATE operations SET active=1,phase=\"applying\"", [])?;
    db.close().map_err(|(_, error)| error)?;
    assert!(fixture.proof().is_err());
    assert!(!fixture.target.control_directory().exists());
    Ok(())
}
