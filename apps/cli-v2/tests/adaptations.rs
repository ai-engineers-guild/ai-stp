use std::{collections::BTreeMap, error::Error, fs};

use ai_stp_cli_v2::{
    artifacts,
    authoring::{adaptations, scaffold},
    canonical, digest,
    projection::{self, Scope, artifact},
    provider::Info,
};
use serde_json::{Value, json};

#[test]
fn portable_sources_preserve_behavior_and_bind_exact_native_surfaces() -> Result<(), Box<dyn Error>>
{
    let temporary = tempfile::tempdir()?;
    assert!(
        scaffold::plan(
            &temporary.path().join("invalid-skill"),
            scaffold::Request {
                component_type: "skill".into(),
                name: "invalid--skill".into(),
                language: "none".into(),
            }
        )
        .is_err()
    );
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let providers = declarations
        .iter()
        .map(|value| {
            Ok((
                value["harness_id"].as_str().ok_or("harness missing")?,
                Info::parse(&serde_json::to_vec(value)?)?,
            ))
        })
        .collect::<Result<BTreeMap<_, _>, Box<dyn Error>>>()?;
    let body = "# Review\n\nPreserve the complete café body, quotes \" and ' and backslashes \\.\n\nUse `git diff` and report findings.\n";
    for kind in ["instruction", "skill", "command", "agent"] {
        let root = temporary.path().join(kind);
        let plan = scaffold::plan(
            &root,
            scaffold::Request {
                component_type: kind.into(),
                name: "safe-review".into(),
                language: "none".into(),
            },
        )?;
        scaffold::apply(&plan, &plan.digest()?)?;
        let mut patch = canonical::parse(&fs::read(root.join("component-passport.json"))?)?;
        patch["description"] = "Review changes with explicit findings.".into();
        patch["permissions"] = json!({"filesystem":["read"],"network":[],"process":[]});
        patch["supported_os"] = json!(["linux"]);
        fs::write(
            root.join("component-passport.json"),
            canonical::bytes(&patch)?,
        )?;
        let entry = patch["entry_points"][0]
            .as_str()
            .ok_or("entry missing")?
            .to_owned();
        let authored = if kind == "skill" {
            format!("---\nname: safe-review\ndescription: Review changed code.\n---\n{body}")
        } else {
            body.into()
        };
        fs::write(root.join("source").join(&entry), &authored)?;
        if kind == "skill" {
            fs::create_dir(root.join("source/scripts"))?;
            fs::write(root.join("source/scripts/check.sh"), b"#!/bin/sh\nexit 0\n")?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(
                    root.join("source/scripts/check.sh"),
                    fs::Permissions::from_mode(0o755),
                )?;
            }
        }
        for route in projection::routes()?
            .iter()
            .filter(|route| route.component_type == kind)
        {
            let provider = providers
                .get(route.harness_id.as_str())
                .ok_or("provider missing")?;
            if (kind == "agent" && route.harness_id == "grok-build")
                || (kind == "command" && route.harness_id == "antigravity")
            {
                assert!(adaptations::prepare(&root, route.target_scope, provider).is_err());
                continue;
            }
            let prepared = adaptations::prepare(&root, route.target_scope, provider)?;
            if let Some(destination) = std::env::var_os("AI_STP_ADAPTATION_PROOF_DIR") {
                let destination = std::path::PathBuf::from(destination);
                fs::create_dir_all(&destination)?;
                let stem = format!(
                    "{}-{}-{kind}",
                    route.harness_id,
                    route.target_scope.as_str()
                );
                fs::write(
                    destination.join(format!("{stem}.json")),
                    canonical::bytes(&prepared.adaptation)?,
                )?;
                fs::write(
                    destination.join(format!("{stem}.projection.zip")),
                    &prepared.projection_bytes,
                )?;
                fs::write(
                    destination.join(format!("{stem}.source.zip")),
                    &prepared.source_bytes,
                )?;
            }
            let repeated = adaptations::prepare(&root, route.target_scope, provider)?;
            assert_eq!(prepared.adaptation, repeated.adaptation);
            assert_eq!(prepared.projection_bytes, repeated.projection_bytes);
            assert_eq!(prepared.snapshot_digest, repeated.snapshot_digest);
            assert_eq!(prepared.adaptation["implementation_mode"], "derived");
            assert_eq!(
                prepared.adaptation["source_artifact"]["digest"],
                digest::bytes("ai-stp:artifact:v1", &prepared.source_bytes)?
            );
            let scope = &prepared.adaptation["scope_adaptations"][0];
            assert_eq!(scope["scope"], route.target_scope.as_str());
            assert_eq!(scope["permissions"], patch["permissions"]);
            assert_eq!(scope["supported_os"], json!(["linux"]));
            let files = artifact::verify(scope, &prepared.projection_bytes)?;
            if kind == "agent" && route.harness_id == "cursor" {
                assert_eq!(scope["members"][0]["native_ids"], json!(["safe-review"]));
                assert!(files[0].bytes.starts_with(b"---\nname: safe-review\n"));
            }
            if kind == "skill" {
                assert_eq!(files.len(), 2);
                assert_eq!(files[0].bytes, authored.as_bytes());
                #[cfg(unix)]
                assert_eq!(files[1].mode, 0o755);
                assert_eq!(artifacts::decode_tree(&prepared.source_bytes)?.len(), 2);
            } else {
                assert_eq!(files.len(), 1);
                let native = std::str::from_utf8(&files[0].bytes)?;
                if kind == "agent" && route.harness_id == "codex" {
                    assert!(files[0].path.ends_with("/safe-review.toml"));
                    let document = native.parse::<toml_edit::DocumentMut>()?;
                    assert_eq!(document["developer_instructions"].as_str(), Some(body));
                    assert_eq!(
                        document["description"].as_str(),
                        patch["description"].as_str()
                    );
                } else {
                    assert!(native.ends_with(body));
                    if native.starts_with("---\n") {
                        let header = native
                            .strip_prefix("---\n")
                            .ok_or("header")?
                            .split_once("---\n")
                            .ok_or("end")?
                            .0;
                        let metadata: Value = serde_saphyr::from_str(header)?;
                        if kind == "instruction" && route.harness_id == "cursor" {
                            assert!(files[0].path.ends_with(".mdc"));
                            assert_eq!(metadata["alwaysApply"], true);
                        } else if kind == "instruction" && route.harness_id == "antigravity" {
                            assert_eq!(metadata["trigger"], "always_on");
                        } else if kind == "agent" && route.harness_id == "opencode" {
                            assert_eq!(metadata["mode"], "subagent");
                        }
                    }
                }
            }
        }
        if kind == "agent" {
            let cursor = providers.get("cursor").ok_or("Cursor missing")?;
            patch["description"] = "Review: preserve \"quotes\" # literally.".into();
            fs::write(
                root.join("component-passport.json"),
                canonical::bytes(&patch)?,
            )?;
            let prepared = adaptations::prepare(&root, Scope::Project, cursor)?;
            let scope = &prepared.adaptation["scope_adaptations"][0];
            let files = artifact::verify(scope, &prepared.projection_bytes)?;
            assert!(
                std::str::from_utf8(&files[0].bytes)?
                    .contains("\ndescription: Review: preserve \"quotes\" # literally.\n")
            );
            for description in [
                "Review\nmodel: unwanted",
                " Review.",
                "Review. ",
                "\u{feff}Review.",
            ] {
                patch["description"] = description.into();
                fs::write(
                    root.join("component-passport.json"),
                    serde_json::to_vec(&patch)?,
                )?;
                assert!(adaptations::prepare(&root, Scope::Project, cursor).is_err());
                assert_eq!(fs::read_to_string(root.join("source").join(&entry))?, body);
            }
            patch["description"] = "Review changes with explicit findings.".into();
            fs::write(
                root.join("component-passport.json"),
                canonical::bytes(&patch)?,
            )?;
        }
        if kind == "skill" {
            let codex = providers.get("codex").ok_or("Codex missing")?;
            assert!(adaptations::prepare(&root, Scope::Global, codex).is_err());
            for header in [
                "name: wrong\ndescription: Review",
                "name: safe-review\nname: again\ndescription: Review",
                "name: safe-review\ndescription: Review\nallowed-tools: Bash",
            ] {
                fs::write(
                    root.join("source/SKILL.md"),
                    format!("---\n{header}\n---\n{body}"),
                )?;
                assert!(adaptations::prepare(&root, Scope::UserRoot, codex).is_err());
            }
        } else {
            fs::write(
                root.join("source").join(&entry),
                format!("---\nmodel: example\n---\n{body}"),
            )?;
            assert!(
                adaptations::prepare(
                    &root,
                    Scope::Global,
                    providers.get("claude-code").ok_or("Claude missing")?
                )
                .is_err()
            );
            fs::write(root.join("source").join(&entry), body)?;
            fs::write(root.join("source/unmapped.txt"), b"keep this file")?;
            assert!(
                adaptations::prepare(
                    &root,
                    Scope::Global,
                    providers.get("claude-code").ok_or("Claude missing")?
                )
                .is_err()
            );
            assert!(root.join("source/unmapped.txt").is_file());
        }
    }
    Ok(())
}
