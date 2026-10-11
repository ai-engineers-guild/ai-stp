use std::{error::Error, fs};

use ai_stp_cli_v2::{
    artifacts,
    authoring::{Identity, adoption, discovery, importing},
    digest,
    harnesses::{Root, Scope},
    store::Store,
};
use serde_json::json;

const AT: &str = "2026-10-09T00:00:00.000Z";
const SKILL: &str = "---\nname: review\ndescription: Review changes.\n---\nReport findings.\n";

fn identity() -> Identity {
    Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    }
}

#[test]
fn metadata_import_binds_claims_bytes_and_explicit_destination() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().join("source");
    let state = temporary.path().join("state");
    fs::create_dir(&state)?;
    for path in ["skills/review", "subagents", "slashcommands", ".git"] {
        fs::create_dir_all(root.join(path))?;
    }
    // Deliberately invalid Git state: metadata imports must never invoke Git.
    fs::write(root.join(".git/config"), b"not a git configuration")?;
    fs::write(root.join("skills/review/SKILL.md"), SKILL)?;
    fs::write(
        root.join("subagents/audit.md"),
        b"---\nname: audit\ndescription: Inspect changes.\n---\nReport.\n",
    )?;
    fs::write(
        root.join("slashcommands/review.code.md"),
        b"Inspect the changed code.\n",
    )?;
    let manifest = json!({"name":"example","version":"1.0.0","type":"skillset",
        "skills":[{"id":"review"}],"subagents":[{"id":"audit"}],
        "slashcommands":[{"command":"review.code"}],"scripts":["must-not-run"]});
    let bytes = serde_json::to_vec(&manifest)?;
    fs::write(root.join("nori.json"), &bytes)?;
    let report = discovery::at(&root, "claude-code", Scope::Project, Root::Config)?;
    assert!(report.complete);
    assert_eq!(report.components.len(), 3);
    assert!(
        report
            .components
            .iter()
            .all(|c| c.harness_id == "undefined")
    );
    let mut candidates = report
        .components
        .iter()
        .map(|c| c.candidate_id.clone())
        .collect::<Vec<_>>();
    candidates.sort();
    let request = importing::Request {
        root: root.clone(),
        harness_id: "claude-code".into(),
        scope: Scope::Project,
        root_kind: Root::Config,
        candidates,
    };
    let mut store = Store::open(&state, true)?;
    let plan = importing::plan(&mut store, request, identity(), AT)?;
    for component in &plan.components {
        let facts = &component.passport["facts"];
        assert_eq!(facts["harness_id"]["origin"], "declared");
        assert_eq!(facts["observed_harness_id"]["value"], json!(null));
        assert_eq!(facts["source_repository"]["value"], json!(null));
        assert_eq!(facts["source_revision"]["value"], json!(null));
        assert_eq!(
            facts["source_manifest_digest"]["value"],
            digest::bytes("ai-stp:artifact:v1", &bytes)?
        );
        assert_eq!(facts["evidence_refs"]["value"], json!(["nori.json"]));
        assert_eq!(facts["projection_kind"]["value"], "native_files");
    }
    let mut changed = manifest.clone();
    changed["version"] = "2.0.0".into();
    fs::write(root.join("nori.json"), serde_json::to_vec(&changed)?)?;
    assert!(importing::apply(&mut store, &plan, &plan.digest()?, &identity(), AT).is_err());
    fs::write(root.join("nori.json"), &bytes)?;
    fs::write(root.join("skills/review/SKILL.md"), "Changed source.")?;
    assert!(importing::apply(&mut store, &plan, &plan.digest()?, &identity(), AT).is_err());
    fs::write(root.join("skills/review/SKILL.md"), SKILL)?;
    let result = importing::apply(&mut store, &plan, &plan.digest()?, &identity(), AT)?;
    assert_eq!(
        serde_json::to_value(result)?,
        serde_json::to_value(importing::apply(
            &mut store,
            &plan,
            &plan.digest()?,
            &identity(),
            AT
        )?)?
    );
    assert_eq!(fs::read(root.join("nori.json"))?, bytes);

    for (scope, root_kind) in [(Scope::Project, Root::Config), (Scope::Global, Root::Home)] {
        let root = temporary.path().join(format!("lock-{scope:?}"));
        fs::create_dir_all(root.join(".agents/skills/review"))?;
        fs::create_dir(root.join(".git"))?;
        fs::write(root.join(".agents/skills/review/SKILL.md"), SKILL)?;
        let lock = json!({"version":3,"skills":{"Review":{"source":"example/skills","skillFolderHash":"a".repeat(40)}}});
        fs::write(
            root.join(".agents/.skill-lock.json"),
            serde_json::to_vec(&lock)?,
        )?;
        let report = discovery::at(&root, "codex", scope, root_kind)?;
        assert!(report.complete);
        assert_eq!(report.components.len(), 1);
        let candidate = &report.components[0];
        let plan = adoption::plan(
            &mut store,
            adoption::Source {
                root: root.clone(),
                harness_id: "codex".into(),
                scope,
                root_kind,
                candidate_id: candidate.candidate_id.clone(),
            },
            identity(),
            AT,
        )?;
        let facts = &plan.passport["facts"];
        assert_eq!(facts["source_digest"]["value"], json!(null));
        assert_eq!(facts["source_claimed_folder_hash"]["value"], "a".repeat(40));
        assert_eq!(facts["native_ids"]["value"], json!(["review"]));
        let payload = artifacts::encode_tree(&[artifacts::Member {
            path: "SKILL.md".into(),
            bytes: SKILL.as_bytes().to_vec(),
            mode: 0o644,
        }])?;
        assert_eq!(
            facts["content_digest"]["value"],
            digest::bytes("ai-stp:artifact:v1", &payload)?
        );
        adoption::apply(&mut store, &plan, &plan.digest()?, &identity(), AT)?;
    }
    let standalone = temporary.path().join("standalone");
    fs::create_dir_all(standalone.join(".git"))?;
    fs::write(standalone.join("SKILL.md"), SKILL)?;
    fs::write(
        standalone.join("nori.json"),
        br#"{"name":"external-name","version":"1","type":"skill","skills":null}"#,
    )?;
    let report = discovery::at(&standalone, "claude-code", Scope::Project, Root::Config)?;
    assert!(report.complete);
    assert_eq!(report.components.len(), 1);
    let plan = adoption::plan(
        &mut store,
        adoption::Source {
            root: standalone.clone(),
            harness_id: "claude-code".into(),
            scope: Scope::Project,
            root_kind: Root::Config,
            candidate_id: report.components[0].candidate_id.clone(),
        },
        identity(),
        AT,
    )?;
    assert_eq!(
        plan.passport["facts"]["native_ids"]["value"],
        json!(["review", "standalone"])
    );
    adoption::apply(&mut store, &plan, &plan.digest()?, &identity(), AT)?;
    Ok(())
}

#[test]
fn invalid_metadata_and_unsafe_paths_never_become_verified_candidates() -> Result<(), Box<dyn Error>>
{
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().join("source");
    fs::create_dir_all(root.join("skills/review"))?;
    fs::write(root.join("skills/review/SKILL.md"), SKILL)?;
    for document in [
        r#"{"name":"x","name":"y","version":"1"}"#.into(),
        r#"{"name":"x","version":"1","skills":[{"id":"../escape"}]}"#.into(),
        r#"{"name":"x","version":"1","skills":[{"id":"review"},{"id":"review"}]}"#.into(),
        r#"{"name":"x","version":"1","skills":[{"id":"missing"}]}"#.into(),
        serde_json::to_string(
            &json!({"name":"x","version":"1","skills":vec![json!({"id":"review"});501]}),
        )?,
        " ".repeat(1024 * 1024 + 1),
    ] {
        fs::write(root.join("nori.json"), document)?;
        let report = discovery::at(&root, "claude-code", Scope::Project, Root::Config)?;
        assert!(!report.complete);
        assert!(report.components.is_empty());
        assert_eq!(report.diagnostics[0].code, "invalid_metadata");
    }
    fs::write(
        root.join("nori.json"),
        br#"{"name":"x","version":"1","skills":[{"id":"review"}]}"#,
    )?;
    fs::hard_link(root.join("nori.json"), root.join("manifest-alias"))?;
    assert!(!discovery::at(&root, "claude-code", Scope::Project, Root::Config)?.complete);
    fs::remove_file(root.join("manifest-alias"))?;
    #[cfg(unix)]
    {
        fs::rename(root.join("skills"), root.join("real-skills"))?;
        std::os::unix::fs::symlink("real-skills", root.join("skills"))?;
        assert!(!discovery::at(&root, "claude-code", Scope::Project, Root::Config)?.complete);
        fs::remove_file(root.join("skills"))?;
        fs::rename(root.join("real-skills"), root.join("skills"))?;
    }
    fs::remove_file(root.join("nori.json"))?;
    fs::create_dir_all(root.join(".agents/skills/review"))?;
    fs::write(root.join(".agents/skills/review/SKILL.md"), SKILL)?;
    for document in [
        json!({"version":4,"skills":{}}),
        json!({"version":3,"skills":{"review":{"source":"example/skills","skillFolderHash":"weak0001"}}}),
        json!({"version":3,"skills":{"Review":{"source":"example/skills","skillFolderHash":"a".repeat(40)},"review":{"source":"example/other","skillFolderHash":"b".repeat(40)}}}),
    ] {
        fs::write(
            root.join(".agents/.skill-lock.json"),
            serde_json::to_vec(&document)?,
        )?;
        let report = discovery::at(&root, "codex", Scope::Project, Root::Config)?;
        assert!(!report.complete);
        assert!(
            report
                .components
                .iter()
                .all(|c| c.provenance["kind"] == "filesystem")
        );
    }
    Ok(())
}
