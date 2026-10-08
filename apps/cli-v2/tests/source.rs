use std::{error::Error, fs, path::Path, process::Command};

use ai_stp_cli_v2::{artifacts, authoring::source};

fn git(root: &Path, arguments: &[&str]) -> Result<(), Box<dyn Error>> {
    let result = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(arguments)
        .output()?;
    if !result.status.success() {
        return Err("Git fixture failed".into());
    }
    Ok(())
}

#[test]
fn git_and_plain_capture_preserve_complete_safe_content() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let repository = temporary.path().join("repository");
    let component = repository.join("components/demo");
    fs::create_dir_all(component.join("scripts"))?;
    fs::write(component.join("SKILL.md"), b"# Component\n")?;
    fs::write(component.join("scripts/run.sh"), b"#!/bin/sh\nexit 0\n")?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(
            component.join("scripts/run.sh"),
            fs::Permissions::from_mode(0o755),
        )?;
    }
    fs::write(component.join("tracked.ignored"), b"retained")?;
    fs::write(component.join("untracked.ignored"), b"excluded")?;
    fs::write(component.join(".env"), b"synthetic secret fixture")?;
    fs::write(component.join(".gitignore"), b"*.ignored\n.env\n")?;
    fs::write(repository.join("outside.md"), b"outside component")?;
    git(&repository, &["init", "--quiet"])?;
    git(
        &repository,
        &[
            "add",
            "-f",
            "components/demo/tracked.ignored",
            "components/demo/scripts/run.sh",
        ],
    )?;
    git(
        &repository,
        &[
            "update-index",
            "--chmod=+x",
            "components/demo/scripts/run.sh",
        ],
    )?;
    git(
        &repository,
        &["config", "core.fsmonitor", "missing-helper-must-not-run"],
    )?;
    let index = fs::read(repository.join(".git/index"))?;
    let captured = source::capture(&component)?;
    assert_eq!(captured.format, artifacts::TREE_FORMAT);
    let files = artifacts::decode_tree(&captured.bytes)?;
    assert_eq!(
        files
            .iter()
            .map(|file| file.path.as_str())
            .collect::<Vec<_>>(),
        [
            ".gitignore",
            "SKILL.md",
            "scripts/run.sh",
            "tracked.ignored"
        ]
    );
    assert_eq!(
        files
            .iter()
            .find(|file| file.path == "scripts/run.sh")
            .ok_or("script absent")?
            .mode,
        0o755
    );
    assert_eq!(source::capture(&component)?.bytes, captured.bytes);
    assert_eq!(
        source::capture_scoped(&repository, "components/demo")?.bytes,
        captured.bytes
    );
    assert_eq!(
        fs::read(repository.join(".git/index"))?,
        index,
        "capture mutated the Git index"
    );
    let file = source::capture(&component.join("SKILL.md"))?;
    assert_eq!(file.format, artifacts::FILE_FORMAT);
    assert_eq!(file.bytes, b"# Component\n");
    assert!(source::capture(&component.join(".env")).is_err());
    fs::hard_link(component.join("SKILL.md"), component.join("linked.md"))?;
    assert!(
        source::capture(&component).is_err(),
        "hard link was captured"
    );
    fs::remove_file(component.join("linked.md"))?;
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(repository.join("outside.md"), component.join("linked.md"))?;
        assert!(source::capture(&component).is_err(), "symlink was captured");
        fs::remove_file(component.join("linked.md"))?;
        std::os::unix::fs::symlink(&component, repository.join("alias"))?;
        assert!(source::capture_scoped(&repository, "alias/SKILL.md").is_err());
    }
    fs::write(component.join(".env.local"), b"synthetic secret fixture")?;
    assert!(
        source::capture(&component).is_err(),
        "unignored credential path was captured"
    );

    let plain = temporary.path().join("plain");
    fs::create_dir_all(plain.join("hooks"))?;
    fs::write(plain.join("hooks.json"), b"{}")?;
    fs::write(plain.join("hooks/helper.sh"), b"exit 0\n")?;
    let captured = source::capture(&plain.join("hooks.json"))?;
    assert_eq!(
        source::capture_scoped(&plain, "hooks.json")?.bytes,
        captured.bytes
    );
    assert_eq!(captured.format, artifacts::TREE_FORMAT);
    let files = artifacts::decode_tree(&captured.bytes)?;
    assert_eq!(
        files
            .iter()
            .map(|file| file.path.as_str())
            .collect::<Vec<_>>(),
        ["hooks.json", "hooks/helper.sh"]
    );
    fs::write(plain.join("hooks/credentials"), b"synthetic secret fixture")?;
    assert!(source::capture(&plain.join("hooks.json")).is_err());
    Ok(())
}
