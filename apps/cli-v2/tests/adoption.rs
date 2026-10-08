use std::{error::Error, fs, path::Path};

use ai_stp_cli_v2::{
    authoring::{
        Identity,
        adoption::{self, Source},
        discovery,
    },
    canonical, digest,
    error::Failure,
    harnesses::{Root, Scope},
    store::{
        Store,
        revisions::{self, Write},
    },
};
use serde_json::json;

fn source(root: &Path) -> Result<Source, Box<dyn Error>> {
    selected(root, "codex", Scope::Global, "mcp")
}

fn selected(
    root: &Path,
    harness: &str,
    scope: Scope,
    kind: &str,
) -> Result<Source, Box<dyn Error>> {
    selected_root(root, harness, scope, Root::Config, kind)
}

fn selected_root(
    root: &Path,
    harness: &str,
    scope: Scope,
    root_kind: Root,
    kind: &str,
) -> Result<Source, Box<dyn Error>> {
    let discovered = discovery::at(root, harness, scope, root_kind)?;
    assert!(discovered.complete);
    let candidate = discovered
        .components
        .into_iter()
        .find(|item| item.component_type == kind)
        .ok_or("candidate absent")?;
    Ok(Source {
        root: root.to_owned(),
        harness_id: harness.into(),
        scope,
        root_kind,
        candidate_id: candidate.candidate_id,
    })
}

fn counts(store: &mut Store) -> Result<(i64, i64, i64), Failure> {
    store.transaction(|transaction| transaction.query_row("SELECT (SELECT count(*) FROM entity), (SELECT count(*) FROM revision), (SELECT count(*) FROM content)",[],|row|Ok((row.get(0)?,row.get(1)?,row.get(2)?))).map_err(|_| Failure::precondition("proof query failed")))
}

fn native_identity_journey(identity: &Identity, at: &str) -> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let mut store = Store::open(root.path(), true)?;
    let cases: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/codex-native-entries.json"))?;
    for case in cases.as_array().ok_or("Codex cases missing")? {
        let native = tempfile::tempdir()?;
        let folder = case["folder"].as_str().ok_or("Codex folder missing")?;
        let body = case["body"].as_str().ok_or("Codex body missing")?;
        let file = native
            .path()
            .join(".agents/skills")
            .join(folder)
            .join("SKILL.md");
        fs::create_dir_all(file.parent().ok_or("parent")?)?;
        fs::write(&file, body)?;
        let source = selected_root(native.path(), "codex", Scope::Global, Root::Home, "skill")?;
        let shared = discovery::at(native.path(), "undefined", Scope::Global, Root::Home)?;
        assert_eq!(shared.components.len(), 1);
        assert_eq!(source.candidate_id, shared.components[0].candidate_id);
        assert_eq!(shared.components[0].harness_id, "undefined");
        let before = counts(&mut store)?;
        let result = adoption::plan(&mut store, source, identity.clone(), at);
        if case["name"].is_null() {
            assert!(result.is_err(), "{}", case["id"]);
            assert_eq!(counts(&mut store)?, before);
        } else {
            let plan = result?;
            assert_eq!(
                plan.passport["facts"]["native_ids"]["value"],
                json!([case["name"]]),
                "{}",
                case["id"]
            );
            assert_eq!(plan.passport["facts"]["harness_id"]["value"], "codex");
            assert_eq!(plan.passport["facts"]["harness_id"]["origin"], "declared");
            assert_eq!(plan.binding.harness_id, "codex");
            assert_eq!(
                plan.passport["facts"]["observed_harness_id"]["value"],
                json!(null)
            );
            adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
        }
        assert_eq!(fs::read_to_string(file)?, body);
    }
    // Shared discovery stays neutral while adoption chooses an explicit consumer.
    for (scope, root_kind) in [(Scope::Global, Root::Home), (Scope::Project, Root::Config)] {
        let native = tempfile::tempdir()?;
        let base = native.path().join(".agents/skills/review");
        for (path, name) in [
            ("SKILL.md", "review"),
            ("nested/SKILL.md", "nested"),
            ("a/b/c/d/e/SKILL.md", "deep"),
            ("a/b/c/d/e/f/SKILL.md", "unreachable"),
            (".hidden/SKILL.md", "hidden"),
        ] {
            let file = base.join(path);
            fs::create_dir_all(file.parent().ok_or("parent")?)?;
            fs::write(
                file,
                format!("---\nname: {name}\ndescription: Inspect.\n---\nBody.\n"),
            )?;
        }
        let source = selected_root(native.path(), "codex", scope, root_kind, "skill")?;
        let mut neutral = source.clone();
        neutral.harness_id = "undefined".into();
        let before = counts(&mut store)?;
        assert!(adoption::plan(&mut store, neutral, identity.clone(), at).is_err());
        assert_eq!(counts(&mut store)?, before);
        let plan = adoption::plan(&mut store, source.clone(), identity.clone(), at)?;
        assert_eq!(
            plan.passport["facts"]["native_ids"]["value"],
            json!(["deep", "nested", "review"])
        );
        // Plugin context can appear after planning and must invalidate apply too.
        for marker in [".codex-plugin", ".claude-plugin", ".cursor-plugin"] {
            let plan = adoption::plan(&mut store, source.clone(), identity.clone(), at)?;
            let directory = native.path().join(marker);
            fs::create_dir(&directory)?;
            fs::write(directory.join("plugin.json"), b"{\"name\":\"example\"}")?;
            assert!(adoption::apply(&mut store, &plan, &plan.digest()?, identity, at).is_err());
            assert_eq!(counts(&mut store)?, before);
            fs::remove_file(directory.join("plugin.json"))?;
            fs::remove_dir(directory)?;
        }
        let plan = adoption::plan(&mut store, source.clone(), identity.clone(), at)?;
        adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
        let initial = counts(&mut store)?;
        adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
        assert_eq!(counts(&mut store)?, initial);
        fs::write(
            base.join("nested/SKILL.md"),
            b"---\nname: review\ndescription: Duplicate.\n---\nBody.\n",
        )?;
        assert!(adoption::plan(&mut store, source, identity.clone(), at).is_err());
        assert_eq!(counts(&mut store)?, initial);
    }
    for harness in ["claude-code", "opencode", "pi", "cursor", "grok-build"] {
        let native = tempfile::tempdir()?;
        fs::create_dir_all(native.path().join(".agents/skills/review"))?;
        fs::write(
            native.path().join(".agents/skills/review/SKILL.md"),
            b"---\nname: review\ndescription: Inspect.\n---\nBody.\n",
        )?;
        let plan = adoption::plan(
            &mut store,
            selected_root(native.path(), harness, Scope::Global, Root::Home, "skill")?,
            identity.clone(),
            at,
        )?;
        assert_eq!(
            plan.passport["facts"]["native_ids"]["value"],
            json!(["review"])
        );
        assert_eq!(plan.binding.harness_id, harness);
    }
    {
        let harness = "opencode";
        for (header, name) in [
            ("name: yes\ndescription: yes", Some("yes")),
            (
                "defaults: &defaults\n  name: merged\n<<: *defaults\ndescription: Inspect.",
                Some("merged"),
            ),
            ("name: 2026-01-01\ndescription: Inspect.", None),
            ("name: !!binary aGVsbG8=\ndescription: Inspect.", None),
        ] {
            let native = tempfile::tempdir()?;
            let folder = native.path().join("skills/folder");
            fs::create_dir_all(&folder)?;
            let body = format!("---\n{header}\n---\nBody.\n");
            fs::write(folder.join("SKILL.md"), &body)?;
            let before = counts(&mut store)?;
            let planned = adoption::plan(
                &mut store,
                selected(native.path(), harness, Scope::Global, "skill")?,
                identity.clone(),
                at,
            );
            if let Some(name) = name {
                let plan = planned?;
                let names = vec![name];
                assert_eq!(plan.passport["facts"]["native_ids"]["value"], json!(names));
                adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
            } else {
                assert!(planned.is_err(), "{harness}: {header}");
                assert_eq!(counts(&mut store)?, before);
            }
            assert_eq!(fs::read_to_string(folder.join("SKILL.md"))?, body);
        }
    }
    // Shared cases are also exercised with the pinned upstream loaders.
    for (harness, fixture) in [
        ("pi", include_str!("fixtures/pi-native-entries.json")),
        (
            "antigravity",
            include_str!("fixtures/antigravity-native-agents.json"),
        ),
        (
            "grok-build",
            include_str!("fixtures/grok-native-entries.json"),
        ),
        (
            "claude-code",
            include_str!("fixtures/claude-native-entries.json"),
        ),
        (
            "cursor",
            include_str!("fixtures/cursor-native-entries.json"),
        ),
    ] {
        let cases: serde_json::Value = serde_json::from_str(fixture)?;
        for case in cases.as_array().ok_or("native cases missing")? {
            let native = tempfile::tempdir()?;
            for (path, body) in case["files"].as_object().ok_or("native files missing")? {
                let file = native.path().join(path);
                fs::create_dir_all(file.parent().ok_or("parent")?)?;
                fs::write(file, body.as_str().ok_or("native body missing")?)?;
            }
            let before = counts(&mut store)?;
            let planned = adoption::plan(
                &mut store,
                selected(
                    native.path(),
                    harness,
                    Scope::Global,
                    case["kind"].as_str().ok_or("native kind missing")?,
                )?,
                identity.clone(),
                at,
            );
            if case["adoptable"] == true {
                let plan = planned?;
                assert_eq!(
                    plan.passport["facts"]["native_ids"]["value"], case["names"],
                    "{}",
                    case["id"]
                );
                adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
            } else {
                assert!(planned.is_err(), "{}", case["id"]);
                assert_eq!(counts(&mut store)?, before);
            }
            for (path, body) in case["files"].as_object().ok_or("native files missing")? {
                assert_eq!(
                    fs::read_to_string(native.path().join(path))?,
                    body.as_str().ok_or("native body missing")?
                );
            }
        }
    }
    for (harness, scope, name, content) in [
        (
            "claude-code",
            Scope::Project,
            ".mcp.json",
            "{\"mcpServers\":{\"a.b\":{\"command\":\"server\"},\"review\":{\"command\":\"server\"}}}",
        ),
        (
            "cursor",
            Scope::Global,
            "mcp.json",
            "{\"mcpServers\":{\"a.b\":{\"command\":\"server\"},\"review\":{\"command\":\"server\"}}}",
        ),
        (
            "antigravity",
            Scope::Global,
            "config/mcp_config.json",
            "{\"mcpServers\":{\"a.b\":{\"command\":\"server\"},\"review\":{\"command\":\"server\"}}}",
        ),
        (
            "opencode",
            Scope::Global,
            "opencode.jsonc",
            "{ /* preserve */ \"mcp\":{\"a.b\":{\"command\":[\"server\"]},\"review\":{\"command\":[\"server\"]},},}",
        ),
        (
            "grok-build",
            Scope::Global,
            "config.toml",
            "[mcp_servers.'a.b']\ncommand = 'server'\n[mcp_servers.review]\ncommand = 'server'\n",
        ),
    ] {
        let native = root.path().join(harness);
        let file = native.join(name);
        fs::create_dir_all(file.parent().ok_or("parent")?)?;
        fs::write(&file, content)?;
        let selected = selected(&native, harness, scope, "mcp")?;
        if harness == "claude-code" {
            // Credential-named .mcp.json remains unreadable to source adoption.
            let before = counts(&mut store)?;
            assert!(adoption::plan(&mut store, selected, identity.clone(), at).is_err());
            assert_eq!(counts(&mut store)?, before);
            continue;
        }
        let plan = adoption::plan(&mut store, selected, identity.clone(), at)?;
        assert_eq!(
            plan.passport["facts"]["native_ids"]["value"],
            json!(["a.b", "review"]),
            "{harness}"
        );
        let adopted = adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
        assert_eq!(
            adopted["facts"]["native_ids"],
            plan.passport["facts"]["native_ids"]
        );
        assert_eq!(fs::read_to_string(file)?, content);
    }
    for (kind, path, body, names) in [
        (
            "skill",
            "skills/folder/SKILL.md",
            "---\nname: inspect\n---\nInspect source.\n",
            vec!["inspect"],
        ),
        (
            "command",
            "commands/team/review.md",
            "Review source.\n",
            vec!["team/review"],
        ),
        (
            "command",
            "commands/review.md",
            "---\nname: inspect\n---\nInspect source.\n",
            vec!["inspect"],
        ),
        (
            "agent",
            "agents/auditor.md",
            "---\nname: inspect\nmode: subagent\n---\nInspect source.\n",
            vec!["inspect"],
        ),
    ] {
        let native = tempfile::tempdir()?;
        let file = native.path().join(path);
        fs::create_dir_all(file.parent().ok_or("parent")?)?;
        fs::write(&file, body)?;
        let plan = adoption::plan(
            &mut store,
            selected(native.path(), "opencode", Scope::Global, kind)?,
            identity.clone(),
            at,
        )?;
        assert_eq!(
            plan.passport["facts"]["native_ids"]["value"],
            json!(names),
            "OpenCode {kind}: {path}"
        );
        adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
        assert_eq!(fs::read_to_string(file)?, body);
    }
    // Category directories retain all executable definitions and auxiliary bytes.
    let category = root.path().join("opencode-category");
    for (directory, name) in [("first", "inspect"), ("second", "review")] {
        let directory = category.join("skills/team").join(directory);
        fs::create_dir_all(&directory)?;
        fs::write(
            directory.join("SKILL.md"),
            format!("---\nname: {name}\n---\nReview.\n"),
        )?;
        fs::write(directory.join("notes.txt"), "Keep this auxiliary file.\n")?;
    }
    let plan = adoption::plan(
        &mut store,
        selected(&category, "opencode", Scope::Global, "skill")?,
        identity.clone(),
        at,
    )?;
    assert_eq!(
        plan.passport["facts"]["native_ids"]["value"],
        json!(["inspect", "review"])
    );
    adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
    let before = counts(&mut store)?;
    for body in [
        "---\nname: inspect\n---\nDuplicate actual name.\n",
        "Review without a header.\n",
        "---\ndescription: Missing name\n---\nReview.\n",
        "---\nname: review\ndescription: 42\n---\nReview.\n",
        "---\nname: first\nname: second\n---\nReview.\n",
    ] {
        fs::write(category.join("skills/team/second/SKILL.md"), body)?;
        assert!(
            adoption::plan(
                &mut store,
                selected(&category, "opencode", Scope::Global, "skill")?,
                identity.clone(),
                at,
            )
            .is_err()
        );
        assert_eq!(counts(&mut store)?, before);
    }
    for (index, (kind, path, content, names)) in [
        ("skill", "skills/folder/SKILL.md", "---\nname: inspect\ndescription: Inspect source.\nallowed-tools: Read\n---\nInspect source.\n", vec!["folder", "inspect"]),
        ("skill", "skills/folder/SKILL.md", "Inspect source with the directory name.\n", vec!["folder"]),
        ("command", "commands/review.md", "---\nname: ignored-name\ndescription: Review source.\n---\nReview source.\n", vec!["review"]),
        ("command", "commands/team/review.md", "Review source.\n", vec!["team:review"]),
    ].into_iter().enumerate() {
        let native = root.path().join(format!("invocation-{index}"));
        let file = native.join(path);
        fs::create_dir_all(file.parent().ok_or("parent")?)?;
        fs::write(&file, content)?;
        let plan = adoption::plan(&mut store, selected(&native, "claude-code", Scope::Global, kind)?, identity.clone(), at)?;
        assert_eq!(plan.passport["facts"]["native_ids"]["value"], json!(names), "{kind}: {path}");
        adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
        assert_eq!(fs::read_to_string(file)?, content);
    }
    let invalid_skill = root.path().join("invalid-skill");
    fs::create_dir_all(invalid_skill.join("skills/folder"))?;
    let before = counts(&mut store)?;
    for body in [
        "---\nname: first\nname: second\n---\nReview.\n",
        "---\nname: has space\n---\nReview.\n",
        "---\nname: cafe\u{301}\n---\nReview.\n",
        "---\nname: anthropic-skills:review\n---\nReview.\n",
    ] {
        fs::write(invalid_skill.join("skills/folder/SKILL.md"), body)?;
        assert!(
            adoption::plan(
                &mut store,
                selected(&invalid_skill, "claude-code", Scope::Global, "skill")?,
                identity.clone(),
                at
            )
            .is_err()
        );
        assert_eq!(counts(&mut store)?, before);
    }
    let duplicate_commands = root.path().join("duplicate-commands");
    fs::create_dir_all(duplicate_commands.join("commands/team/sub"))?;
    fs::write(
        duplicate_commands.join("commands/team/sub/review.md"),
        "Review source.",
    )?;
    #[cfg(unix)]
    {
        fs::write(
            duplicate_commands.join("commands/team/sub:review.md"),
            "Review again.",
        )?;
        assert!(
            adoption::plan(
                &mut store,
                selected(&duplicate_commands, "claude-code", Scope::Global, "command")?,
                identity.clone(),
                at
            )
            .is_err()
        );
        assert_eq!(counts(&mut store)?, before);
    }
    let native = root.path().join("local-agents");
    fs::create_dir_all(native.join("agents"))?;
    let agent = native.join("agents/different-filename.md");
    let body = "---\nname: repo-auditor\ndescription: Review local source.\nallowed-tools: Read\n---\nReport findings.\n";
    fs::write(&agent, body)?;
    let plan = adoption::plan(
        &mut store,
        selected(&native, "claude-code", Scope::Global, "agent")?,
        identity.clone(),
        at,
    )?;
    assert_eq!(
        plan.passport["facts"]["native_ids"]["value"],
        json!(["repo-auditor"])
    );
    adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
    assert_eq!(fs::read_to_string(&agent)?, body);
    let before = counts(&mut store)?;
    for content in [
        "Documentation without an agent header.",
        "---\nname: one\nname: two\ndescription: Duplicate name\n---\n",
        "---\nname: -invalid\ndescription: Invalid name\n---\n",
        "---\nname: plugin:agent\ndescription: Wrong namespace\n---\n",
        "---\nname: missing-description\n---\n",
        "---\nname: cafe\u{301}\ndescription: Noncanonical identifier\n---\n",
    ] {
        fs::write(&agent, content)?;
        let source = selected(&native, "claude-code", Scope::Global, "agent")?;
        assert!(adoption::plan(&mut store, source, identity.clone(), at).is_err());
        assert_eq!(counts(&mut store)?, before);
    }
    for (harness, name, content) in [
        (
            "cursor",
            "mcp.json",
            r#"{"mcpServers":{"review":{"command":"server","env":{"GITHUB_TOKEN":"synthetic-sensitive-value"}}}}"#,
        ),
        (
            "codex",
            "config.toml",
            "[mcp_servers.review]\ncommand = 'server'\nhttp_headers = { Authorization = 'Bearer synthetic-sensitive-value' }\n",
        ),
        (
            "grok-build",
            "config.toml",
            "[mcp_servers.review]\ncommand = 'server'\nenv = { API_KEY = '${TOKEN:-synthetic-sensitive-value}' }\n",
        ),
        (
            "antigravity",
            "config/mcp_config.json",
            r#"{"mcpServers":{"review":{"serverUrl":"https://example.invalid/mcp","oauth":{"clientSecret":"synthetic-sensitive-value"}}}}"#,
        ),
        (
            "opencode",
            "opencode.jsonc",
            r#"{"mcp":{"review":{"type":"remote","url":"https://example.invalid/mcp","headers":{"X-Api-Key":"synthetic-sensitive-value"}}}}"#,
        ),
        (
            "codex",
            "config.toml",
            "[mcp_servers.review]\ncommand = 'server'\n[mcp_servers.review.unknown.env_http_headers]\nAuthorization = 'synthetic-sensitive-value'\n",
        ),
        (
            "cursor",
            "mcp.json",
            r#"{"mcpServers":{"review":{"command":"server","auth":{"credentials":[{"value":"synthetic-sensitive-value"}]}}}}"#,
        ),
        (
            "cursor",
            "mcp.json",
            r#"{"accessToken":"synthetic-sensitive-value","mcpServers":{"review":{"command":"server"}}}"#,
        ),
    ] {
        let native = root.path().join(format!("credential-{harness}"));
        let file = native.join(name);
        fs::create_dir_all(file.parent().ok_or("parent")?)?;
        fs::write(&file, content)?;
        let selected = selected(&native, harness, Scope::Global, "mcp")?;
        let before = counts(&mut store)?;
        let result = adoption::plan(&mut store, selected, identity.clone(), at);
        assert!(
            result.is_err(),
            "literal MCP credential was accepted for {harness}"
        );
        assert!(
            !result
                .err()
                .ok_or("refusal")?
                .message
                .contains("synthetic-sensitive-value")
        );
        assert_eq!(counts(&mut store)?, before);
        assert_eq!(fs::read_to_string(file)?, content);
    }
    for (harness, name, key, content) in [
        (
            "cursor",
            "mcp.json",
            "",
            r#"{"mcpServers":{"review":{"command":"server","envFile":".env","env":{"API_KEY":"${env:my-api-key}","LOG_LEVEL":"info"},"headers":{"Authorization":"Bearer ${env:REVIEW_TOKEN}"}}}}"#,
        ),
        (
            "codex",
            "config.toml",
            "mcp_servers",
            "api_key = 'synthetic-unowned-value'\n[mcp_servers.review]\ncommand = 'server'\nenv_vars = ['GITHUB_TOKEN']\nbearer_token_env_var = 'REVIEW_TOKEN'\nenv_http_headers = { Authorization = 'REVIEW_TOKEN' }\nenv = { LOG_LEVEL = 'info' }\n",
        ),
        (
            "grok-build",
            "config.toml",
            "mcp_servers",
            "[mcp_servers.review]\ncommand = 'server'\nenv = { API_KEY = '${MY_API_KEY}' }\nheaders = { Authorization = 'Bearer ${REVIEW_TOKEN}' }\n",
        ),
        (
            "opencode",
            "opencode.jsonc",
            "mcp",
            r#"{ /* retained references */ "mcp":{"review":{"type":"remote","url":"https://example.invalid/mcp","headers":{"Authorization":"Bearer {env:REVIEW_TOKEN}"},"oauth":{"clientSecret":"{file:~/.secrets/review}"}}}}"#,
        ),
    ] {
        let native = root.path().join(format!("references-{harness}"));
        let file = native.join(name);
        fs::create_dir_all(file.parent().ok_or("parent")?)?;
        fs::write(&file, content)?;
        let plan = adoption::plan(
            &mut store,
            selected(&native, harness, Scope::Global, "mcp")?,
            identity.clone(),
            at,
        )?;
        let adopted = adoption::apply(&mut store, &plan, &plan.digest()?, identity, at)?;
        let held = store.transaction(|transaction| {
            revisions::read_content(
                transaction,
                adopted["facts"]["content_digest"]["value"]
                    .as_str()
                    .ok_or_else(|| Failure::precondition("content missing"))?,
            )
        })?;
        let expected = if key.is_empty() {
            content.as_bytes().to_vec()
        } else {
            ai_stp_cli_v2::authoring::contribution::extract(
                ai_stp_cli_v2::authoring::contribution::Format::for_path(name)?,
                content.as_bytes(),
                key,
            )?
        };
        assert_eq!(held, expected, "external references changed for {harness}");
        assert!(!std::str::from_utf8(&held)?.contains("synthetic-unowned-value"));
        assert_eq!(fs::read_to_string(file)?, content);
    }
    let before = counts(&mut store)?;
    let mcp = root.path().join("cursor/mcp.json");
    for content in [
        "{}",
        "{\"mcpServers\": []}",
        "{\"mcpServers\":{\"\":{}}}",
        "{\"mcpServers\":{\"cafe\u{301}\":{}}}",
    ] {
        fs::write(&mcp, content)?;
        let source = selected(
            mcp.parent().ok_or("parent")?,
            "cursor",
            Scope::Global,
            "mcp",
        )?;
        assert!(adoption::plan(&mut store, source, identity.clone(), at).is_err());
        assert_eq!(counts(&mut store)?, before);
    }
    Ok(())
}

#[test]
fn adoption_is_planned_atomic_replayable_and_preserves_authored_facts() -> Result<(), Box<dyn Error>>
{
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().join("codex");
    fs::create_dir(&root)?;
    let config = b"model = 'unowned-setting'\n[mcp_servers.example]\ncommand = 'example-server'\n";
    fs::write(root.join("config.toml"), config)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let at = "2026-10-08T00:00:00.000Z";
    let later = "2026-10-08T00:00:01.000Z";
    let mut store = Store::open(temporary.path(), true)?;
    let stale = adoption::plan(&mut store, source(&root)?, identity.clone(), at)?;
    assert_eq!(counts(&mut store)?, (0, 0, 0));
    fs::write(
        root.join("config.toml"),
        b"[mcp_servers.example]\ncommand = 'changed'\n",
    )?;
    assert!(adoption::apply(&mut store, &stale, &stale.digest()?, &identity, later).is_err());
    assert_eq!(counts(&mut store)?, (0, 0, 0));
    fs::write(root.join("config.toml"), config)?;
    let plan = adoption::plan(&mut store, source(&root)?, identity.clone(), at)?;
    let plan: adoption::Plan = serde_json::from_value(serde_json::to_value(plan)?)?;
    assert!(
        adoption::apply(
            &mut store,
            &plan,
            &digest::sha256(b"wrong"),
            &identity,
            later
        )
        .is_err()
    );
    let first = adoption::apply(&mut store, &plan, &plan.digest()?, &identity, later)?;
    assert_eq!(counts(&mut store)?, (1, 1, 1));
    assert_eq!(first["facts"]["native_ids"]["value"], json!(["example"]));
    assert!(
        !serde_json::to_string(&first)?.contains(&temporary.path().to_string_lossy().to_string())
    );
    assert_eq!(
        first["facts"]["source_locator"]["value"],
        "config.toml#mcp_servers"
    );
    assert_eq!(
        first["facts"]["managed_paths"]["value"],
        json!(["config.toml"])
    );
    #[cfg(windows)]
    assert!(!plan.binding.absolute_path.starts_with(r"\\?\"));
    store.transaction(|transaction| {
        let bytes: Vec<u8> = transaction
            .query_row("SELECT bytes FROM content", [], |row| row.get(0))
            .map_err(|_| Failure::precondition("proof query failed"))?;
        let text = std::str::from_utf8(&bytes)
            .map_err(|_| Failure::precondition("proof content invalid"))?;
        assert!(text.contains("[example]"));
        assert!(!text.contains("unowned-setting"));
        assert!(!text.contains("mcp_servers"));
        Ok(())
    })?;
    fs::remove_file(root.join("config.toml"))?;
    assert_eq!(
        adoption::apply(&mut store, &plan, &plan.digest()?, &identity, later)?,
        first
    );
    assert_eq!(counts(&mut store)?, (1, 1, 1));
    fs::write(root.join("config.toml"), config)?;
    let unchanged = adoption::plan(&mut store, source(&root)?, identity.clone(), later)?;
    assert_eq!(unchanged.passport, first);
    adoption::apply(
        &mut store,
        &unchanged,
        &unchanged.digest()?,
        &identity,
        later,
    )?;
    assert_eq!(counts(&mut store)?, (1, 1, 1));

    let stale = adoption::plan(&mut store, source(&root)?, identity.clone(), later)?;
    let original_revision = first["revision_id"]
        .as_str()
        .ok_or("revision absent")?
        .to_owned();
    let mut authored = first.clone();
    authored["parent_revision_ids"] = json!([original_revision]);
    authored["facts"]["name"] = json!({"value":"User title","origin":"declared","confirmation":"user_confirmed","confirmed_at":later});
    let authored = store.transaction(|transaction| {
        revisions::commit(
            transaction,
            &authored,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: std::slice::from_ref(&original_revision),
            },
        )
    })?;
    assert!(adoption::apply(&mut store, &stale, &stale.digest()?, &identity, later).is_err());
    assert_eq!(counts(&mut store)?, (1, 2, 1));
    let changed = b"[mcp_servers.example]\ncommand = 'changed-server'\n";
    fs::write(root.join("config.toml"), changed)?;
    let update = adoption::plan(&mut store, source(&root)?, identity.clone(), later)?;
    assert_eq!(update.passport["facts"]["name"], authored["facts"]["name"]);
    let updated = adoption::apply(&mut store, &update, &update.digest()?, &identity, later)?;
    assert_eq!(
        updated["parent_revision_ids"],
        json!([authored["revision_id"]])
    );
    assert_eq!(counts(&mut store)?, (1, 3, 2));

    let moved = temporary.path().join("moved-codex");
    fs::rename(&root, &moved)?;
    let relocation = adoption::plan(&mut store, source(&moved)?, identity.clone(), later)?;
    assert_eq!(relocation.binding.stable_id, plan.binding.stable_id);
    assert_eq!(relocation.passport, updated);
    adoption::apply(
        &mut store,
        &relocation,
        &relocation.digest()?,
        &identity,
        later,
    )?;
    assert_eq!(counts(&mut store)?, (1, 3, 2));
    fs::create_dir(&root)?;
    fs::write(root.join("config.toml"), changed)?;
    let copy = adoption::plan(&mut store, source(&root)?, identity.clone(), later)?;
    assert_ne!(copy.binding.stable_id, relocation.binding.stable_id);
    adoption::apply(&mut store, &copy, &copy.digest()?, &identity, later)?;
    assert_eq!(counts(&mut store)?, (2, 4, 2));
    let before = counts(&mut store)?;
    let mut tampered = adoption::plan(&mut store, source(&root)?, identity.clone(), later)?;
    tampered.passport["facts"]["name"] = json!({"value":"Forged source metadata","origin":"observed","confirmation":"none","observed_at":later});
    assert!(adoption::apply(&mut store, &tampered, &tampered.digest()?, &identity, later).is_err());
    assert_eq!(counts(&mut store)?, before);
    drop(store);
    let mut store = Store::open(temporary.path(), false)?;
    assert_eq!(
        adoption::apply(
            &mut store,
            &copy,
            &copy.digest()?,
            &identity,
            "2026-10-09T00:00:00.000Z"
        )?,
        copy.passport
    );
    assert_eq!(counts(&mut store)?, before);
    let composed = temporary.path().join("caf\u{e9}");
    let decomposed = temporary.path().join("cafe\u{301}");
    fs::create_dir(&composed)?;
    fs::write(composed.join("config.toml"), changed)?;
    let unicode = adoption::plan(&mut store, source(&composed)?, identity.clone(), later)?;
    adoption::apply(&mut store, &unicode, &unicode.digest()?, &identity, later)?;
    if !decomposed.try_exists()? {
        fs::create_dir(&decomposed)?;
        fs::write(decomposed.join("config.toml"), changed)?;
        assert!(
            adoption::plan(&mut store, source(&decomposed)?, identity.clone(), later).is_err(),
            "Unicode-normalized binding addresses conflated distinct filesystem locations"
        );
    }
    let exact_root = temporary.path().join("only-e\u{301}");
    fs::create_dir(&exact_root)?;
    fs::write(exact_root.join("config.toml"), changed)?;
    let exact = adoption::plan(&mut store, source(&exact_root)?, identity.clone(), later)?;
    let encoded = canonical::bytes(&serde_json::to_value(&exact)?)?;
    let decoded: adoption::Plan = serde_json::from_slice(&encoded)?;
    assert_eq!(decoded.source.root, exact.source.root);
    assert_eq!(decoded.binding.absolute_path, exact.binding.absolute_path);
    assert_eq!(decoded.digest()?, exact.digest()?);
    let mut false_display = serde_json::to_value(&exact)?;
    false_display["source"]["root"]["display"] = json!("/different");
    assert!(serde_json::from_value::<adoption::Plan>(false_display).is_err());
    let exact_digest = decoded.digest()?;
    store.transaction(|transaction| {
        transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?,'component.adopt','applying',?,?)",rusqlite::params![decoded.operation_id,later,exact_digest]).map_err(|_|Failure::precondition("proof journal failed"))?;
        Ok(())
    })?;
    assert_eq!(
        adoption::apply(&mut store, &decoded, &exact_digest, &identity, later)?,
        exact.passport
    );
    let interrupted = adoption::plan(&mut store, source(&root)?, identity.clone(), later)?;
    let interrupted_digest = interrupted.digest()?;
    store.transaction(|transaction| {
        transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?,'component.adopt','applying',?,?)",rusqlite::params![interrupted.operation_id,later,interrupted_digest]).map_err(|_|Failure::precondition("proof journal failed"))?;
        Ok(())
    })?;
    assert!(
        adoption::apply(
            &mut store,
            &interrupted,
            &interrupted_digest,
            &identity,
            "2026-10-08T00:16:00.000Z"
        )
        .is_err()
    );
    let interrupted_state = store.transaction(|transaction| {
        transaction
            .query_row(
                "SELECT state FROM operation WHERE operation_id=?",
                [&interrupted.operation_id],
                |row| row.get::<_, String>(0),
            )
            .map_err(|_| Failure::precondition("proof journal failed"))
    })?;
    store.transaction(|transaction| {
        transaction
            .execute("UPDATE content SET bytes=X'00'", [])
            .map_err(|_| Failure::precondition("proof corruption failed"))?;
        Ok(())
    })?;
    let corrupt_replay_refused =
        adoption::apply(&mut store, &copy, &copy.digest()?, &identity, later).is_err();
    assert_eq!(
        (interrupted_state.as_str(), corrupt_replay_refused),
        ("stale", true)
    );
    native_identity_journey(&identity, at)?;
    Ok(())
}
