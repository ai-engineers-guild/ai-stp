use std::{
    error::Error,
    fs,
    path::{Path, PathBuf},
    sync::{Arc, Barrier},
};

use ai_stp_cli_v2::{
    authoring::scaffold::{self, Plan, Request},
    canonical,
};

fn private_dir(path: &Path) -> Result<(), Box<dyn Error>> {
    fs::create_dir(path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    }
    Ok(())
}

fn private_file(path: &Path, bytes: &[u8]) -> Result<(), Box<dyn Error>> {
    fs::write(path, bytes)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}

fn request(name: &str) -> Request {
    Request {
        component_type: "skill".into(),
        name: name.into(),
        language: "none".into(),
    }
}

fn staged(root: &Path, plan: &Plan) -> Result<PathBuf, Box<dyn Error>> {
    let digest = plan.digest()?;
    let stage = root.join(format!(
        ".ai-stp-scaffold-{}",
        digest.strip_prefix("sha256:").ok_or("digest")?
    ));
    private_dir(&stage)?;
    private_file(
        &stage.join("owner"),
        format!("ai-stp-scaffold/1\n{digest}\n").as_bytes(),
    )?;
    private_file(&stage.join("lock"), b"")?;
    private_dir(&stage.join("tree"))?;
    Ok(stage)
}

#[test]
fn source_tree_creation_recovers_without_overwriting_or_claiming_a_product()
-> Result<(), Box<dyn Error>> {
    let temp = tempfile::tempdir()?;
    let root = temp.path();
    let output = root.join("skill-cafe\u{301}");
    let plan = scaffold::plan(&output, request("safe-skill"))?;
    assert_eq!(fs::read_dir(root)?.count(), 0);
    let plan: Plan = serde_json::from_value(canonical::parse(&canonical::bytes(
        &serde_json::to_value(&plan)?,
    )?)?)?;
    assert_eq!(
        Path::new(&plan.output)
            .parent()
            .ok_or("parent")?
            .canonicalize()?,
        root.canonicalize()?
    );
    assert_eq!(Path::new(&plan.output).file_name(), output.file_name());
    let digest = plan.digest()?;
    assert!(scaffold::apply(&plan, "sha256:invalid").is_err());
    let mut substituted = plan.clone();
    substituted
        .files
        .insert("../../escape".into(), "bad".into());
    assert!(scaffold::apply(&substituted, &substituted.digest()?).is_err());
    assert_eq!(fs::read_dir(root)?.count(), 0);

    let stage = staged(root, &plan)?;
    private_dir(&stage.join("tree/source"))?;
    private_file(&stage.join("tree/source/SKILL.md"), b"---\nname: ")?;
    assert_eq!(scaffold::apply(&plan, &digest)?["outcome"], "created");
    assert!(!stage.exists());
    for (name, content) in &plan.files {
        assert_eq!(fs::read(output.join(name))?, content.as_bytes());
    }
    assert!(!output.join("README.md").exists());
    assert!(!output.join("eval-profile.json").exists());
    assert!(!output.join(".git").exists());
    assert_eq!(
        scaffold::apply(&plan, &digest)?["outcome"],
        "already_matches"
    );
    assert!(scaffold::plan(&output, request("safe-skill")).is_err());
    fs::write(output.join("source/SKILL.md"), "authored by the user")?;
    assert!(scaffold::apply(&plan, &digest).is_err());
    assert_eq!(
        fs::read_to_string(output.join("source/SKILL.md"))?,
        "authored by the user"
    );

    for obstruction in ["empty", "file", "extra", "unknown-stage", "hardlink"] {
        let target = root.join(obstruction);
        let plan = scaffold::plan(&target, request("safe-skill"))?;
        let digest = plan.digest()?;
        match obstruction {
            "empty" => private_dir(&target)?,
            "file" => fs::write(&target, b"keep")?,
            "extra" => {
                let stage = staged(root, &plan)?;
                private_file(&stage.join("tree/user-notes"), b"keep")?;
            }
            "unknown-stage" => {
                let stage = root.join(format!(
                    ".ai-stp-scaffold-{}",
                    digest.strip_prefix("sha256:").ok_or("digest")?
                ));
                private_dir(&stage)?;
                private_file(&stage.join("user-notes"), b"keep")?;
            }
            "hardlink" => {
                let stage = staged(root, &plan)?;
                private_file(&root.join("outside"), b"")?;
                fs::hard_link(root.join("outside"), stage.join("tree/.gitignore"))?;
            }
            _ => return Err("unknown proof".into()),
        }
        assert!(scaffold::apply(&plan, &digest).is_err(), "{obstruction}");
        if obstruction == "file" {
            assert_eq!(fs::read(&target)?, b"keep");
        }
        if obstruction == "hardlink" {
            assert!(fs::read(root.join("outside"))?.is_empty());
        }
    }
    #[cfg(unix)]
    {
        let target = root.join("linked");
        let plan = scaffold::plan(&target, request("safe-skill"))?;
        std::os::unix::fs::symlink(&output, &target)?;
        assert!(scaffold::apply(&plan, &plan.digest()?).is_err());
    }
    let parent = root.join("parent");
    private_dir(&parent)?;
    let plan = scaffold::plan(&parent.join("child"), request("safe-skill"))?;
    fs::rename(&parent, root.join("old-parent"))?;
    private_dir(&parent)?;
    assert!(scaffold::apply(&plan, &plan.digest()?).is_err());
    assert_eq!(fs::read_dir(&parent)?.count(), 0);

    let target = root.join("raced");
    let plans = [
        scaffold::plan(&target, request("one"))?,
        scaffold::plan(&target, request("two"))?,
    ];
    let barrier = Arc::new(Barrier::new(2));
    let jobs: Vec<_> = plans
        .clone()
        .into_iter()
        .map(|plan| {
            let barrier = Arc::clone(&barrier);
            std::thread::spawn(move || {
                barrier.wait();
                let digest = plan.digest()?;
                scaffold::apply(&plan, &digest)
            })
        })
        .collect();
    let results = jobs
        .into_iter()
        .map(|job| job.join().map_err(|_| "writer panicked"))
        .collect::<Result<Vec<_>, _>>()?;
    assert_eq!(results.iter().filter(|result| result.is_ok()).count(), 1);
    let winner = results.iter().position(Result::is_ok).ok_or("no winner")?;
    assert_eq!(
        fs::read_to_string(target.join("source/SKILL.md"))?,
        plans[winner].files["source/SKILL.md"]
    );

    for language in scaffold::LANGUAGES.iter().filter(|v| **v != "none") {
        let plan = scaffold::plan(
            &root.join(language),
            Request {
                component_type: "cli".into(),
                name: "safe-cli".into(),
                language: (*language).into(),
            },
        )?;
        assert_eq!(
            scaffold::apply(&plan, &plan.digest()?)?["publication_ready"],
            false
        );
    }
    assert!(
        scaffold::plan(
            &root.join("invalid"),
            Request {
                component_type: "hook".into(),
                name: "invalid".into(),
                language: "python".into()
            }
        )
        .is_err()
    );
    Ok(())
}
