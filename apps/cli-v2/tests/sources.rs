use std::{error::Error, ffi::OsString};

use ai_stp_cli_v2::{invoke, sources};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use serde_json::json;

#[test]
fn addresses_are_bounded_intents_not_provenance_or_filesystem_observations()
-> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().join("absent");
    let sha = "a".repeat(40);
    for (value, kind) in [
        ("@author/review@1.2", "published"),
        ("gh:owner/repo@review", "github"),
        ("owner/repo/path/to/skill", "github"),
        (
            "https://github.com/owner/repo.git/tree/main/skills/a%20b",
            "github",
        ),
        ("col:owner/team", "collection"),
        ("https://askill.sh/c/owner/team", "collection"),
        ("./skills/a", "local"),
        ("../skills/a", "local"),
    ] {
        let result = sources::inspect(value, Some(&root), None)?;
        assert_eq!(result["source"]["kind"], kind);
        assert_eq!(result["provenance"], "not_observed");
        assert_eq!(result["network_accessed"], false);
        assert_eq!(result["filesystem_accessed"], false);
    }
    let address = format!("https://github.com/owner/repo/tree/{sha}/skills/a%20b");
    let exact = sources::inspect(&address, None, Some(&sha))?;
    assert_eq!(exact["source"]["commit"], sha);
    assert_eq!(exact["source"]["subpath"], "skills/a b");
    assert!(sources::inspect(&address, None, Some(&"b".repeat(40))).is_err());
    for value in [
        "",
        " owner/repo",
        "owner/repo ",
        "owner/repo/a/../../secret",
        "owner/repo/a//b",
        "owner/repo@",
        "gh:owner/repo@ref/../x",
        "https://user:token@github.com/owner/repo",
        "https://@github.com/owner/repo",
        "https://github.com:443/owner/repo",
        "https://github.com/owner/repo?token=secret",
        "https://github.com/owner/repo#fragment",
        "https://github.com/owner/repo/tree/main/../secret",
        "https://github.com/owner/repo/tree/main/%2e%2e/secret",
        "https://github.com/owner/repo/tree/main/a%2Fb",
        "https://github.com/owner/repo/tree/main/a%5Cb",
        "https://github.com/owner/repo/tree/main/%252e%252e",
        "https://github.com/owner/repo/tree/main/%FF",
        "https://github.com/owner/repo/tree/main/%1",
        "https://github.com/owner/repo/tree/main/%00",
        "https://github.com/owner/repo/issues/1",
        "https://github.com/owner/repo/blob/main",
        "http://github.com/owner/repo",
        "https://askill.sh/c/owner/team?token=secret",
        "git@example.com:owner/repo.git",
    ] {
        assert!(
            sources::inspect(value, Some(&root), None).is_err(),
            "{value}"
        );
    }
    assert!(sources::inspect(&"x".repeat(2049), None, None).is_err());
    assert!(sources::inspect("./source", None, None).is_err());
    assert!(sources::inspect("C:relative", Some(&root), None).is_err());
    assert!(sources::inspect("./source", Some(&root.join("x".repeat(32768))), None).is_err());
    for revision in ["main", "v1.0.0", &"a".repeat(39), &"A".repeat(40)] {
        assert!(sources::inspect("owner/repo", None, Some(revision)).is_err());
    }
    for value in ["./source", "@author/skill", "col:owner/team"] {
        assert!(sources::inspect(value, Some(&root), Some(&sha)).is_err());
    }
    let mut arguments: Vec<OsString> = [
        "ai-stp-v2",
        "component",
        "source",
        "parse",
        "--source",
        "./e\u{301}",
        "--root",
    ]
    .into_iter()
    .map(Into::into)
    .collect();
    arguments.push(root.as_os_str().to_owned());
    arguments.push("--json".into());
    let response = invoke(arguments);
    assert_eq!(response.exit_code(), 0);
    assert!(response.envelope()["data"]["source"]["path"]["utf8_base64"].is_string());
    let response = invoke(
        [
            "ai-stp-v2",
            "component",
            "source",
            "resolve",
            "--source",
            "owner/repo",
            "--commit",
            &sha,
            "--json",
        ]
        .into_iter()
        .map(Into::into),
    );
    assert_eq!(response.exit_code(), 0);
    assert_eq!(
        response.envelope()["data"]["source"],
        json!({"kind":"github","repository":"https://github.com/owner/repo","selector":null,"commit":sha,"subpath":null})
    );
    assert!(!root.exists());
    assert_eq!(std::fs::read_dir(temporary.path())?.count(), 0);
    Ok(())
}

#[test]
fn local_snapshots_bind_original_bytes_and_refuse_escaping_or_unsafe_members()
-> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path();
    let source = root.join("source");
    std::fs::create_dir(&source)?;
    let bytes = "Original e\u{301} bytes.\n".as_bytes();
    std::fs::write(source.join("readme.txt"), bytes)?;
    let report = sources::local::capture(root, "source")?;
    assert_eq!(report, sources::local::capture(root, "source")?);
    let archive =
        URL_SAFE_NO_PAD.decode(report["artifact"]["bytes_b64"].as_str().ok_or("archive")?)?;
    let files = ai_stp_cli_v2::artifacts::decode_tree(&archive)?;
    assert_eq!(files.len(), 1);
    assert_eq!(files[0].bytes, bytes);
    assert_eq!(report["snapshot"]["canonical_coordinate"], "path:source");
    assert_eq!(report["snapshot"]["author_verified"], false);
    assert_eq!(report["snapshot"]["component_verified"], false);
    assert_eq!(report["snapshot"]["target_write"], false);
    assert!(!serde_json::to_string(&report)?.contains(root.to_str().ok_or("root")?));

    for path in [
        "../source",
        "source/../source",
        "source//readme.txt",
        ".",
        "/source",
    ] {
        assert!(sources::local::capture(root, path).is_err());
    }
    for (name, bytes) in [
        (".env", b"SECRET=example".as_slice()),
        ("invalid.txt", b"\xff".as_slice()),
        ("binary.txt", b"a\0b".as_slice()),
    ] {
        std::fs::write(source.join(name), bytes)?;
        assert!(sources::local::capture(root, "source").is_err());
        std::fs::remove_file(source.join(name))?;
    }
    std::fs::hard_link(source.join("readme.txt"), source.join("alias.txt"))?;
    assert!(sources::local::capture(root, "source").is_err());
    std::fs::remove_file(source.join("alias.txt"))?;
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(&source, root.join("alias"))?;
        assert!(sources::local::capture(root, "alias/readme.txt").is_err());
        std::os::unix::fs::symlink(source.join("readme.txt"), source.join("link"))?;
        assert!(sources::local::capture(root, "source").is_err());
        std::fs::remove_file(source.join("link"))?;
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(
            source.join("readme.txt"),
            std::fs::Permissions::from_mode(0o755),
        )?;
        let executable = sources::local::capture(root, "source")?;
        assert_eq!(executable["snapshot"], report["snapshot"]);
        assert_ne!(
            executable["artifact"]["digest"],
            report["artifact"]["digest"]
        );
    }
    // Selecting a file does not silently include provider-specific sibling trees.
    std::fs::write(source.join("hooks.json"), b"{}")?;
    std::fs::create_dir(source.join("hooks"))?;
    std::fs::write(source.join("hooks/handler.sh"), b"exit 0\n")?;
    let single = sources::local::capture(root, "source/hooks.json")?;
    assert_eq!(single["snapshot"]["file_paths"], json!(["hooks.json"]));
    std::fs::write(source.join("large.txt"), vec![b'a'; 4 * 1024 * 1024 + 1])?;
    assert!(sources::local::capture(root, "source").is_err());
    let repository = root.join("repository");
    std::fs::create_dir(&repository)?;
    let git = |arguments: &[&str]| -> Result<(), Box<dyn Error>> {
        let result = std::process::Command::new("git")
            .current_dir(&repository)
            .args(arguments)
            .output()?;
        assert!(result.status.success(), "Git fixture initialization failed");
        Ok(())
    };
    git(&["init", "--quiet"])?;
    std::fs::create_dir(repository.join("selected"))?;
    std::fs::write(repository.join(".gitignore"), b"selected/.env\n")?;
    std::fs::write(repository.join("selected/tracked.txt"), b"tracked\n")?;
    git(&["add", "--", "selected/tracked.txt"])?;
    std::fs::write(repository.join("selected/untracked.txt"), b"untracked\n")?;
    std::fs::write(repository.join("selected/.env"), b"SECRET=fixture\n")?;
    let selected = sources::local::capture(&repository, "selected")?;
    assert_eq!(
        selected["snapshot"]["file_paths"],
        json!(["tracked.txt", "untracked.txt"])
    );
    let deep = repository.join("deep");
    let mut nested = deep.clone();
    for _ in 0..33 {
        nested.push("x");
    }
    std::fs::create_dir_all(&nested)?;
    std::fs::write(nested.join("note.txt"), b"beyond the directory bound")?;
    assert!(sources::local::capture(&repository, "deep").is_err());
    // Ignore rules do not conceal an explicitly tracked secret file.
    git(&["add", "--force", "--", "selected/.env"])?;
    assert!(sources::local::capture(&repository, "selected").is_err());
    Ok(())
}
