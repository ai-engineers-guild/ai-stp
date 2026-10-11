use super::{AT, LATER, counts, field, stored};
use ai_stp_cli_v2::{
    authoring::{
        Identity, adoption, derivation, discovery, native_edit, project_binding, releases,
        scaffold, setups,
    },
    canonical, digest,
    error::Failure,
    harnesses::{Root, Scope as DiscoveryScope},
    projection::{Scope, artifact},
    provider::Info,
    store::{Store, revisions, versions::Increment},
};
use serde_json::{Value, json};
use std::{error::Error, fs, path::Path};

const SKILL: &str = "---\nname: portable-check\ndescription: Inspect source conventions.\nlicense: MIT\nmetadata:\n  author: local\n---\nRead [the reference](references/details.md) and run scripts/check.sh when appropriate.\nKeep cafe\u{301} bytes intact.\n";

fn draft(
    store: &mut Store,
    root: &Path,
    target: (&str, Scope),
    provider: &Info,
    identity: &Identity,
    contents: &str,
    extra: Option<(&str, &str)>,
) -> Result<Value, Box<dyn Error>> {
    fs::create_dir_all(root)?;
    let portable = root.join("portable");
    let plan = scaffold::plan(
        &portable,
        scaffold::Request {
            component_type: "skill".into(),
            name: "portable-check".into(),
            language: "none".into(),
        },
    )?;
    scaffold::apply(&plan, &plan.digest()?)?;
    let metadata = portable.join("component-passport.json");
    let mut patch = canonical::parse(&fs::read(&metadata)?)?;
    patch["description"] = "Inspect source conventions.".into();
    patch["tags"] = json!(["development"]);
    patch["license"] = json!({"spdx_id":"MIT","redistribution_allowed":true});
    patch["permissions"] = json!({"filesystem":["read"],"network":[],"process":["spawn"]});
    patch["supported_os"] = json!(["linux"]);
    patch["supported_arch"] = json!(["x86_64"]);
    fs::write(metadata, canonical::bytes(&patch)?)?;
    // Each fixture has a distinct binding even after an earlier source vanishes.
    fs::write(
        portable.join("source/SKILL.md"),
        format!("{SKILL}\nFixture {}.\n", root.display()),
    )?;
    let plan = project_binding::plan(
        store,
        project_binding::Request {
            root: portable,
            targets: vec![project_binding::Target {
                harness_id: target.0.into(),
                scope: target.1,
            }],
        },
        std::slice::from_ref(provider),
        identity.clone(),
        AT,
    )
    .map_err(|error| format!("{} {} binding plan: {error:?}", target.0, target.1.as_str()))?;
    let before =
        project_binding::apply(store, &plan, &plan.digest()?, identity, AT).map_err(|error| {
            format!(
                "{} {} binding apply: {error:?}",
                target.0,
                target.1.as_str()
            )
        })?;

    let native = root.join("native");
    let skill = native.join(".agents/skills/portable-check");
    fs::create_dir_all(skill.join("scripts"))?;
    fs::create_dir_all(skill.join("references"))?;
    fs::write(skill.join("SKILL.md"), contents)?;
    fs::write(
        skill.join("references/details.md"),
        "Preserve cafe\u{301} and native bytes.\n",
    )?;
    fs::write(
        skill.join("scripts/check.sh"),
        "#!/bin/sh\nprintf '%s' 'cafe\u{301}'\n",
    )?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(
            skill.join("scripts/check.sh"),
            fs::Permissions::from_mode(0o755),
        )?;
    }
    if let Some((path, bytes)) = extra {
        let file = skill.join(path);
        fs::create_dir_all(file.parent().ok_or("parent")?)?;
        fs::write(file, bytes)?;
    }
    let candidate = discovery::at(&native, "undefined", DiscoveryScope::Global, Root::Home)?
        .components
        .into_iter()
        .find(|c| c.component_type == "skill")
        .ok_or("skill")?;
    let plan = native_edit::plan(
        store,
        field(&before, "stable_id")?,
        field(&before, "revision_id")?,
        vec![native_edit::Source {
            scope: target.1,
            source: adoption::Source {
                root: native,
                harness_id: "undefined".into(),
                scope: DiscoveryScope::Global,
                root_kind: Root::Home,
                candidate_id: candidate.candidate_id,
            },
        }],
        provider,
        identity.clone(),
        AT,
    )?;
    Ok(native_edit::apply(
        store,
        &plan,
        &plan.digest()?,
        identity,
        AT,
    )?)
}

pub(super) fn journey(
    store: &mut Store,
    root: &Path,
    providers: &[Info],
    identity: &Identity,
) -> Result<(), Box<dyn Error>> {
    let provider = |harness| {
        providers
            .iter()
            .find(|p| p.document()["harness_id"] == harness)
            .ok_or("provider")
    };
    for (source, target, scope) in [
        ("claude-code", "opencode", Scope::Global),
        ("opencode", "claude-code", Scope::Global),
        ("codex", "opencode", Scope::UserRoot),
        ("opencode", "codex", Scope::UserRoot),
    ] {
        let directory = root.join(format!("skill-{source}-{target}"));
        let before = draft(
            store,
            &directory,
            (source, scope),
            provider(source)?,
            identity,
            SKILL,
            None,
        )?;
        let release = releases::plan(
            store,
            field(&before, "stable_id")?,
            field(&before, "revision_id")?,
            Increment::Minor,
            &[],
            identity.clone(),
            AT,
        )?;
        let original = releases::apply(store, &release, &release.digest()?, identity, AT)?;
        let initial = counts(store)?;
        let plan = derivation::plan(
            store,
            field(&before, "stable_id")?,
            field(&before, "revision_id")?,
            source,
            provider(target)?,
            identity.clone(),
            AT,
        )?;
        assert_eq!(counts(store)?, initial);
        assert!(derivation::apply(store, &plan, "wrong", identity, AT).is_err());
        store.transaction(|t| t.execute_batch("CREATE TEMP TRIGGER reject_skill BEFORE INSERT ON operation BEGIN SELECT RAISE(ABORT,'proof failure'); END;").map_err(|_| Failure::input("proof trigger")))?;
        assert!(derivation::apply(store, &plan, &plan.digest()?, identity, AT).is_err());
        assert_eq!(counts(store)?, initial);
        store.transaction(|t| {
            t.execute_batch("DROP TRIGGER reject_skill;")
                .map_err(|_| Failure::input("proof trigger"))
        })?;
        let result = derivation::apply(store, &plan, &plan.digest()?, identity, AT)?;
        let adaptation = result["adaptations"]
            .as_array()
            .ok_or("adaptations")?
            .iter()
            .find(|a| a["harness_id"] == target)
            .ok_or("target")?;
        assert_eq!(adaptation["transform"]["transform_id"], "common-skill");
        assert_eq!(adaptation["logical_component_type"], "skill");
        assert_eq!(adaptation["implementation_mode"], "derived");
        let from = &before["adaptations"][0]["scope_adaptations"][0];
        let to = &adaptation["scope_adaptations"][0];
        for key in [
            "scope",
            "permissions",
            "supported_os",
            "supported_arch",
            "members",
            "projection_artifact",
        ] {
            assert_eq!(to[key], from[key], "{source} -> {target}: {key}");
        }
        assert_eq!(to["technical_support"], "experimental");
        let bytes = store.transaction(|t| {
            revisions::read_content(
                t,
                to["projection_artifact"]["digest"]
                    .as_str()
                    .ok_or_else(|| Failure::input("digest"))?,
            )
        })?;
        let files = artifact::verify(to, &bytes)?;
        assert_eq!(files.len(), 3);
        assert_eq!(
            files
                .iter()
                .find(|f| f.path.ends_with("/SKILL.md"))
                .ok_or("skill")?
                .bytes,
            SKILL.as_bytes()
        );
        let provenance = store.transaction(|t| {
            revisions::read_content(
                t,
                adaptation["source_artifact"]["digest"]
                    .as_str()
                    .ok_or_else(|| Failure::input("digest"))?,
            )
        })?;
        assert_eq!(
            canonical::parse(&provenance)?,
            json!({"source_revision_id":before["revision_id"],"adaptation":before["adaptations"][0]})
        );
        let release = releases::plan(
            store,
            field(&result, "stable_id")?,
            field(&result, "revision_id")?,
            Increment::Minor,
            &[],
            identity.clone(),
            AT,
        )?;
        assert_eq!(
            releases::apply(store, &release, &release.digest()?, identity, AT)?["version"],
            "1.1"
        );
        assert_eq!(
            stored(store, field(&original, "stable_id")?, Some("1.0"))?,
            original
        );
        fs::remove_dir_all(&directory)?;
        let after = counts(store)?;
        assert_eq!(
            derivation::apply(store, &plan, &plan.digest()?, identity, LATER)?,
            result
        );
        assert_eq!(counts(store)?, after);

        let compose = setups::plan(
            store,
            setups::Request {
                harness_id: source.into(),
                name: "Portable review".into(),
                description: "Inspect source conventions.".into(),
                purpose: "Review code.".into(),
                members: vec![setups::Member {
                    stable_id: field(&original, "stable_id")?.into(),
                    version: "1.0".into(),
                    passport_digest: digest::canonical("ai-stp:passport:v1", &original)?,
                }],
                requirements: None,
            },
            identity.clone(),
            AT,
        )?;
        let setup = setups::apply(store, &compose, &compose.digest()?, identity, AT)?;
        let recast = setups::copies::plan_with_provider(
            store,
            setups::Source {
                stable_id: field(&setup, "stable_id")?.into(),
                version: "1.0".into(),
                passport_digest: digest::canonical("ai-stp:passport:v1", &setup)?,
            },
            provider(target)?,
            identity.clone(),
            AT,
        )?;
        let replacements = &recast.derivation.as_ref().ok_or("derivation")?.members;
        assert_eq!(replacements.len(), 1);
        assert_ne!(replacements[0].passport["stable_id"], original["stable_id"]);
        let recast_result = setups::copies::apply(store, &recast, &recast.digest()?, identity, AT)?;
        assert_eq!(
            setups::copies::apply(store, &recast, &recast.digest()?, identity, LATER)?,
            recast_result
        );
    }
    let mut cases: Vec<(String, Option<(&str, &str)>)> = [
        "allowed-tools: Read",
        "disable-model-invocation: true",
        "context: fork",
        "model: custom",
        "hooks: {}",
        "arguments: [name]",
        "unknown-control: true",
    ]
    .into_iter()
    .map(|extra| (SKILL.replacen("license: MIT", extra, 1), None))
    .collect();
    for extra in [
        "!`git status`",
        "```!\ngit status\n```",
        "$ARGUMENTS",
        "$1",
        "${CLAUDE_SKILL_DIR}",
    ] {
        cases.push((format!("{SKILL}{extra}\n"), None));
    }
    cases.push((
        SKILL.replace("name: portable-check", "name: another-name"),
        None,
    ));
    cases.push((SKILL.into(), Some(("nested/SKILL.md", "# Nested skill"))));
    cases.push((
        SKILL.into(),
        Some((
            "agents/openai.yaml",
            "policy:\n  allow_implicit_invocation: false\n",
        )),
    ));
    cases.push((SKILL.into(), Some((".ignore", "scripts/\n"))));
    for (index, (contents, extra)) in cases.iter().enumerate() {
        let before = draft(
            store,
            &root.join(format!("refused-skill-{index}")),
            ("claude-code", Scope::Global),
            provider("claude-code")?,
            identity,
            contents,
            *extra,
        )?;
        let initial = counts(store)?;
        assert!(
            derivation::plan(
                store,
                field(&before, "stable_id")?,
                field(&before, "revision_id")?,
                "claude-code",
                provider("opencode")?,
                identity.clone(),
                AT
            )
            .is_err(),
            "accepted case {index}"
        );
        assert_eq!(counts(store)?, initial);
    }
    let before = draft(
        store,
        &root.join("refused-scope"),
        ("claude-code", Scope::Global),
        provider("claude-code")?,
        identity,
        SKILL,
        None,
    )?;
    for target in ["codex", "cursor", "pi", "grok-build", "antigravity"] {
        let initial = counts(store)?;
        assert!(
            derivation::plan(
                store,
                field(&before, "stable_id")?,
                field(&before, "revision_id")?,
                "claude-code",
                provider(target)?,
                identity.clone(),
                AT
            )
            .is_err()
        );
        assert_eq!(counts(store)?, initial);
    }
    Ok(())
}
