use std::{error::Error, fs};

use ai_stp_cli_v2::{
    authoring::discovery,
    harnesses::{self, Root, Scope},
    projection::{self, Scope as TargetScope},
};

#[test]
fn declared_discovery_distinguishes_ownership_without_exposing_values() -> Result<(), Box<dyn Error>>
{
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().join("project");
    fs::create_dir_all(root.join(".codex"))?;
    fs::create_dir_all(root.join(".claude/skills/plain"))?;
    fs::create_dir_all(root.join(".claude/skills/pack/.claude-plugin"))?;
    fs::create_dir_all(root.join(".claude/skills/plain.bak-20261008"))?;
    fs::write(
        root.join(".claude/skills/plain/SKILL.md"),
        b"# Plain skill\n",
    )?;
    fs::write(
        root.join(".claude/skills/pack/.claude-plugin/plugin.json"),
        b"{}",
    )?;
    fs::write(root.join(".claude/skills/index.json"), b"{}")?;
    fs::write(root.join("AGENTS.md"), b"# Instructions\n")?;
    // Discovery must never parse a dedicated credential-bearing path.
    fs::write(root.join(".mcp.json"), [0xff, 0xfe])?;
    let config = b"model = 'synthetic-private-value'\n[mcp_servers.example]\ncommand = 'synthetic-private-command'\n";
    fs::write(root.join(".codex/config.toml"), config)?;

    let codex = discovery::at(&root, "codex", Scope::Project, Root::Config)?;
    assert!(codex.complete);
    assert_eq!(codex.components.len(), 2);
    let mcp = codex
        .components
        .iter()
        .find(|item| item.component_type == "mcp")
        .ok_or("MCP absent")?;
    assert_eq!(mcp.evidence_refs, ["mcp_servers.example"]);
    assert_eq!(mcp.declared_key, "mcp_servers");
    assert_eq!(mcp.native_path, ".codex/config.toml");
    // A discovered source does not create a provider route for that scope.
    assert!(projection::route("mcp", "codex", TargetScope::Project)?.is_none());
    let route =
        projection::route("mcp", "codex", TargetScope::Global)?.ok_or("MCP route absent")?;
    assert_eq!(route.declared_key, mcp.declared_key);
    assert_eq!(route.provider_kind, "setting");
    let shared =
        projection::route("skill", "codex", TargetScope::Global)?.ok_or("skill route absent")?;
    assert_eq!(shared.target_scope, TargetScope::UserRoot);
    assert_eq!(
        projection::covers("skill", "codex", "plain", TargetScope::Global)?,
        ["skills/plain"]
    );
    assert_eq!(
        projection::profile("codex", shared.target_scope)?.profile_id,
        "codex/native-files/user-root/1"
    );
    assert_eq!(
        projection::route("mcp", "pi", TargetScope::Global)?
            .ok_or("Pi MCP route absent")?
            .provider_kind,
        "plugin"
    );
    assert!(projection::route("mcp", "claude-code", TargetScope::Global)?.is_none());
    assert_eq!(
        projection::covers("hook", "cursor", "hooks.json", TargetScope::Project)?,
        [".cursor/hooks.json", ".cursor/hooks"]
    );
    assert!(projection::covers("skill", "codex", "../escape", TargetScope::Global).is_err());
    let encoded = serde_json::to_string(&codex)?;
    assert!(!encoded.contains("synthetic-private"));
    assert_eq!(
        serde_json::to_string(&discovery::at(
            &root,
            "codex",
            Scope::Project,
            Root::Config
        )?)?,
        encoded
    );
    assert_eq!(fs::read(root.join(".codex/config.toml"))?, config);

    let claude = discovery::at(&root, "claude-code", Scope::Project, Root::Config)?;
    assert!(claude.complete);
    assert_eq!(claude.components.len(), 2);
    assert!(
        claude
            .components
            .iter()
            .any(|item| item.native_path == ".claude/skills/plain")
    );
    assert!(
        claude
            .components
            .iter()
            .any(|item| item.native_path == ".mcp.json" && item.holds_secret)
    );
    let portable = discovery::at(&root, "undefined", Scope::Project, Root::Config)?;
    assert!(
        portable
            .components
            .iter()
            .any(|item| item.native_path == "AGENTS.md")
    );

    let cursor = temporary.path().join("cursor-config");
    fs::create_dir(&cursor)?;
    fs::write(cursor.join("cli-config.json"), b"{}")?;
    fs::write(cursor.join("hooks.json"), b"{}")?;
    let separate = discovery::at(&cursor, "cursor", Scope::Global, Root::CursorConfig)?;
    assert!(separate.complete);
    assert_eq!(separate.components.len(), 1);
    assert_eq!(separate.components[0].native_path, "cli-config.json");
    assert!(
        discovery::at(&cursor, "cursor", Scope::Global, Root::Config)?
            .components
            .iter()
            .all(|item| item.native_path != "cli-config.json")
    );
    for harness in harnesses::definitions()? {
        assert!(discovery::at(&root, &harness.harness_id, Scope::Project, Root::Config)?.complete);
    }

    fs::write(root.join(".codex/config.toml"), b"mcp_servers = {}")?;
    assert_eq!(
        discovery::at(&root, "codex", Scope::Project, Root::Config)?
            .components
            .len(),
        1
    );
    fs::write(
        root.join(".codex/config.toml"),
        b"mcp_servers = {}\nmcp_servers = {}",
    )?;
    assert!(!discovery::at(&root, "codex", Scope::Project, Root::Config)?.complete);
    fs::write(root.join(".codex/config.toml"), config)?;
    fs::hard_link(root.join(".codex/config.toml"), root.join("alias.toml"))?;
    let linked = discovery::at(&root, "codex", Scope::Project, Root::Config)?;
    assert!(!linked.complete);
    assert!(linked.components.is_empty());
    fs::remove_file(root.join("alias.toml"))?;
    #[cfg(unix)]
    {
        let alias = temporary.path().join("alias-project");
        fs::create_dir(&alias)?;
        std::os::unix::fs::symlink(root.join(".codex"), alias.join(".codex"))?;
        let linked = discovery::at(&alias, "codex", Scope::Project, Root::Config)?;
        assert!(!linked.complete);
        assert!(linked.components.is_empty());
    }
    fs::create_dir_all(root.join(".claude/commands"))?;
    for i in 0..1001 {
        fs::write(root.join(format!(".claude/commands/{i:04}.md")), b"fixture")?;
    }
    let exhausted = discovery::at(&root, "claude-code", Scope::Project, Root::Config)?;
    assert!(!exhausted.complete);
    assert!(
        !exhausted
            .components
            .iter()
            .any(|item| item.component_type == "command")
    );
    assert!(discovery::at(&root, "invented", Scope::Project, Root::Config).is_err());
    Ok(())
}
