use super::{AT, LATER, counts, field};
use ai_stp_cli_v2::{
    authoring::{
        Identity, adoption, derivation, discovery, forks,
        passports::{self, Patch},
        releases,
    },
    digest,
    error::Failure,
    harnesses::{Root, Scope},
    projection::artifact,
    provider::Info,
    store::{Store, revisions, versions::Increment},
};
use serde_json::{Value, json};
use std::{error::Error, fs, path::Path};

fn draft(
    store: &mut Store,
    root: &Path,
    source: (&str, Scope),
    providers: &[Info],
    identity: &Identity,
    body: &str,
) -> Result<Value, Box<dyn Error>> {
    fs::create_dir_all(root)?;
    fs::write(
        root.join(if source.0 == "claude-code" {
            "CLAUDE.md"
        } else {
            "AGENTS.md"
        }),
        body,
    )?;
    let candidate = discovery::at(root, source.0, source.1, Root::Config)?
        .components
        .into_iter()
        .find(|c| c.component_type == "instruction")
        .ok_or_else(|| {
            format!(
                "missing instruction fixture for {} {:?} at {}",
                source.0,
                source.1,
                root.display()
            )
        })?;
    let plan = adoption::plan(
        store,
        adoption::Source {
            root: root.into(),
            harness_id: source.0.into(),
            scope: source.1,
            root_kind: Root::Config,
            candidate_id: candidate.candidate_id,
        },
        identity.clone(),
        AT,
    )?;
    let before = adoption::apply(store, &plan, &plan.digest()?, identity, AT)?;
    let plan = passports::plan(
        store,
        field(&before, "stable_id")?,
        field(&before, "revision_id")?,
        Patch::try_from(
            json!({"name":"standalone-review","description":"Inspect source conventions.",
            "tags":["review"],"license":{"spdx_id":"MIT","redistribution_allowed":true},
            "permissions":{"filesystem":["read"],"network":[],"process":[]},
            "supported_os":["linux"],"supported_arch":["x86_64"]}),
        )?,
        identity.clone(),
        AT,
    )?;
    let before = passports::apply(store, &plan, &plan.digest()?, identity, AT)?;
    let plan = releases::plan(
        store,
        field(&before, "stable_id")?,
        field(&before, "revision_id")?,
        Increment::Minor,
        providers,
        identity.clone(),
        AT,
    )?;
    let version = releases::apply(store, &plan, &plan.digest()?, identity, AT)?;
    let plan = forks::plan(
        store,
        forks::Source {
            stable_id: field(&version, "stable_id")?.into(),
            version: field(&version, "version")?.into(),
            passport_digest: digest::canonical("ai-stp:passport:v1", &version)?,
        },
        identity.clone(),
        AT,
    )?;
    Ok(forks::apply(store, &plan, &plan.digest()?, identity, AT)?)
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
    for (index, (source, target, scope)) in [
        ("claude-code", "codex", Scope::Global),
        ("codex", "opencode", Scope::Global),
        ("opencode", "pi", Scope::Global),
        ("pi", "claude-code", Scope::Global),
        ("claude-code", "codex", Scope::Project),
    ]
    .into_iter()
    .enumerate()
    {
        let directory = root.join(format!("instruction-{index}"));
        let body = format!(
            "# Review {index}\r\nPreserve cafe\u{301} bytes.\r\nInspect changed code before committing.\r\n"
        );
        let before = draft(
            store,
            &directory,
            (source, scope),
            providers,
            identity,
            &body,
        )?;
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
        assert_eq!(counts(store)?, initial);
        let after = derivation::apply(store, &plan, &plan.digest()?, identity, AT)?;
        let derived = after["adaptations"]
            .as_array()
            .ok_or("adaptations")?
            .iter()
            .find(|a| a["harness_id"] == target)
            .ok_or("target")?;
        assert_eq!(
            derived["transform"]["transform_id"],
            "standalone-instruction"
        );
        let from = &before["adaptations"][0]["scope_adaptations"][0];
        let to = &derived["scope_adaptations"][0];
        for key in [
            "scope",
            "permissions",
            "supported_os",
            "supported_arch",
            "supported_harness_versions",
        ] {
            assert_eq!(to[key], from[key]);
        }
        assert_eq!(to["technical_support"], "experimental");
        assert_eq!(to["members"][0]["mode"], from["members"][0]["mode"]);
        let bytes = store.transaction(|t| {
            revisions::read_content(
                t,
                to["projection_artifact"]["digest"]
                    .as_str()
                    .ok_or_else(|| Failure::input("proof digest"))?,
            )
        })?;
        let files = artifact::verify(to, &bytes)?;
        assert_eq!(files.len(), 1);
        assert_eq!(
            files[0].path,
            if target == "claude-code" {
                "CLAUDE.md"
            } else {
                "AGENTS.md"
            }
        );
        assert_eq!(files[0].bytes, body.as_bytes());
        fs::remove_dir_all(directory)?;
        let current = counts(store)?;
        assert_eq!(
            derivation::apply(store, &plan, &plan.digest()?, identity, LATER)?,
            after
        );
        assert_eq!(counts(store)?, current);
    }
    for (index, body) in [
        "---\npaths: src/**\n---\nRead code.\n",
        "See @shared.md.\n",
        "Use ${HOME}.\n",
        "Use {env:HOME}.\n",
        "Use {file:instructions.md}.\n",
        "!`git status`\n",
        "```!\ngit status\n```\n",
        "Read $ARGUMENTS.\n",
        "Read $1.\n",
        "\u{feff}Read code.\n",
        "Read\u{0}code.\n",
    ]
    .iter()
    .enumerate()
    {
        let directory = root.join(format!("refused-instruction-{index}"));
        let before = draft(
            store,
            &directory,
            ("claude-code", Scope::Global),
            providers,
            identity,
            body,
        )?;
        let initial = counts(store)?;
        assert!(
            derivation::plan(
                store,
                field(&before, "stable_id")?,
                field(&before, "revision_id")?,
                "claude-code",
                provider("codex")?,
                identity.clone(),
                AT
            )
            .is_err(),
            "accepted instruction {index}"
        );
        assert_eq!(counts(store)?, initial);
    }
    let before = draft(
        store,
        &root.join("instruction-scope"),
        ("claude-code", Scope::Project),
        providers,
        identity,
        "# Same scope\nRead code.\n",
    )?;
    for target in ["pi", "opencode", "cursor", "antigravity", "grok-build"] {
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
