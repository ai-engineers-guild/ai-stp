use std::{error::Error, ffi::OsString};

use ai_stp_cli_v2::{invoke, sources};
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
