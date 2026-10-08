use std::{error::Error, fs};

use ai_stp_cli_v2::{
    authoring::{scaffold, source_project},
    canonical,
};
use serde_json::{Value, json};

#[test]
fn project_readiness_binds_real_source_and_preserves_literal_examples() -> Result<(), Box<dyn Error>>
{
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().join("author");
    let plan = scaffold::plan(
        &root,
        scaffold::Request {
            component_type: "skill".into(),
            name: "safe-skill".into(),
            language: "none".into(),
        },
    )?;
    scaffold::apply(&plan, &plan.digest()?)?;
    let initial = source_project::capture(&root)?;
    assert_eq!(initial.report["source_ready"], false);
    assert_eq!(initial.files.len(), 1);
    assert_eq!(initial.files[0].path, "SKILL.md");
    let mut patch: Value = initial.patch.into();
    patch["description"] = "A bounded code review skill.".into();
    fs::write(
        root.join("component-passport.json"),
        canonical::bytes(&patch)?,
    )?;
    let described = source_project::inspect(&root)?;
    assert_eq!(described["source_ready"], false);
    assert_eq!(initial.report["source_digest"], described["source_digest"]);
    assert_ne!(
        initial.report["snapshot_digest"],
        described["snapshot_digest"]
    );
    assert_eq!(
        described["issues"],
        json!([{"code":"scaffold_marker","path":"source/SKILL.md"}])
    );

    let authored = "---\nname: safe-skill\ndescription: Review changed code.\n---\n\n# Review\n\nReview changes and report concrete findings.\n\nTODO: add an example.\n\n`TODO(ai-stp-scaffold):` is a literal marker example.\n\n```text\nTODO(ai-stp-scaffold): quoted example\n```\n";
    fs::write(root.join("source/SKILL.md"), authored)?;
    fs::write(root.join("source/fixture.bin"), [0, 255, 1])?;
    fs::write(
        root.join("notes.md"),
        b"Project notes never become native source.\n",
    )?;
    let ready = source_project::capture(&root)?;
    assert_eq!(ready.report["source_ready"], true);
    assert_eq!(ready.report["execution"], "not_run");
    assert_eq!(ready.report["publication"], "not_assessed");
    assert_eq!(ready.files.len(), 2);
    assert!(
        ready
            .files
            .iter()
            .all(|file| !file.path.contains("passport") && file.path != "notes.md")
    );
    assert_eq!(source_project::inspect(&root)?, ready.report);
    fs::write(root.join("source/SKILL.md"), " \n\t")?;
    assert_eq!(
        source_project::inspect(&root)?["issues"][0]["code"],
        "entry_point_empty"
    );
    fs::write(root.join("source/SKILL.md"), [255])?;
    assert_eq!(
        source_project::inspect(&root)?["issues"][0]["code"],
        "entry_point_not_utf8"
    );
    fs::remove_file(root.join("source/SKILL.md"))?;
    assert_eq!(
        source_project::inspect(&root)?["issues"][0]["code"],
        "entry_point_missing"
    );
    fs::write(root.join("source/SKILL.md"), authored)?;
    fs::write(
        root.join("source/.env"),
        b"synthetic fixture, no credential",
    )?;
    assert!(source_project::inspect(&root).is_err());
    fs::remove_file(root.join("source/.env"))?;
    let descriptor = fs::read(root.join(".ai-stp-template.json"))?;
    let mut changed = canonical::parse(&descriptor)?;
    changed["template_version"] = "component-scaffold/6".into();
    fs::write(
        root.join(".ai-stp-template.json"),
        canonical::bytes(&changed)?,
    )?;
    assert!(source_project::inspect(&root).is_err());
    fs::write(root.join(".ai-stp-template.json"), descriptor)?;
    patch["entry_points"] = json!(["../notes.md"]);
    fs::write(
        root.join("component-passport.json"),
        canonical::bytes(&patch)?,
    )?;
    assert!(source_project::inspect(&root).is_err());
    Ok(())
}
