//! Capture, release and compile each advertised project kind through the public engine APIs.

use super::{
    AT, Hosts, Info, Scope, Store, Value, bundle, compose, export, identity, json, target, text,
};
use ai_stp_cli::{
    authoring::{
        adoption, discovery,
        passports::{self, Patch},
        releases,
    },
    harnesses::{Root, Scope as DiscoveryScope, Shape},
    projection::{self, artifact},
    store::{revisions, versions::Increment},
};
use std::{collections::BTreeSet, error::Error, fs, path::Path};

fn fixture(
    route: &projection::Route,
    replacement: bool,
) -> Result<(String, Vec<u8>), Box<dyn Error>> {
    let body = if replacement {
        "Inspect updated conventions."
    } else {
        "Inspect project conventions."
    };
    let (leaf, content) = match route.component_type.as_str() {
        "instruction" => ("review.mdc", format!("# Review\n{body}\n")),
        "skill" => (
            "review/SKILL.md",
            format!("---\nname: review\ndescription: {body}\n---\n{body}\n"),
        ),
        "agent" => (
            "review.md",
            format!("---\nname: review\ndescription: {body}\n---\n{body}\n"),
        ),
        "command" => ("review.md", format!("{body}\n")),
        "plugin" if route.harness_id == "grok-build" => (
            "review/plugin.json",
            format!("{{\"name\":\"review\",\"version\":\"1.0.0\",\"description\":\"{body}\"}}\n"),
        ),
        "plugin" if route.harness_id == "antigravity" => (
            "review/plugin.json",
            format!("{{\"name\":\"review\",\"description\":\"{body}\"}}\n"),
        ),
        "plugin" => (
            "review.ts",
            format!("// {body}\nexport default function review() {{}}\n"),
        ),
        "setting" => (
            "",
            format!(
                "{{\"model\":\"{}\"}}\n",
                if replacement { "review-next" } else { "review" }
            ),
        ),
        "hook" => (
            "review.json",
            format!("{{\"hooks\":{{}},\"version\":1,\"description\":\"{body}\"}}\n"),
        ),
        "mcp" => (
            "",
            format!(
                "{{\"mcpServers\":{{\"review\":{{\"command\":\"{}\"}}}}}}\n",
                if replacement { "review-next" } else { "review" }
            ),
        ),
        _ => return Err("project kind has no explicit proof fixture".into()),
    };
    let path = if route.shape == Shape::File {
        route.relative.clone()
    } else {
        format!("{}/{leaf}", route.relative)
    };
    Ok((path, content.into_bytes()))
}

pub(super) fn journey(
    store: &mut Store,
    root: &Path,
    declarations: &[Value],
) -> Result<(), Box<dyn Error>> {
    let routes: Vec<_> = projection::routes()?
        .iter()
        .filter(|r| r.target_scope == Scope::Project)
        .collect();
    assert_eq!(routes.len(), 35);
    let mut covered = BTreeSet::new();
    for route in routes {
        let harness = route.harness_id.as_str();
        let kind = route.component_type.as_str();
        assert!(
            covered.insert((harness, kind)),
            "duplicate project kind route"
        );
        let provider = Info::parse(&serde_json::to_vec(
            declarations
                .iter()
                .find(|d| d["harness_id"] == harness)
                .ok_or("provider missing")?,
        )?)?;
        let mut previous = None;
        for replacement in [false, true] {
            let case = format!(
                "{harness}-project-{kind}{}",
                if replacement { "-replacement" } else { "" }
            );
            let source = root.join(&case);
            let (path, bytes) = fixture(route, replacement)?;
            fs::create_dir_all(source.join(&path).parent().ok_or("source parent missing")?)?;
            fs::write(source.join(&path), &bytes)?;
            if harness == "grok-build" && kind == "plugin" {
                fs::write(
                    source.join(".grok/plugins/known_marketplaces.json"),
                    b"{\"private\":\"unowned-marketplace-canary\"}\n",
                )?;
            }
            let report = discovery::at(&source, harness, DiscoveryScope::Project, Root::Config)?;
            assert!(report.complete, "incomplete discovery for {case}");
            assert!(
                report
                    .components
                    .iter()
                    .all(|c| c.native_path != ".grok/plugins/known_marketplaces.json"),
                "marketplace state became an adoption candidate"
            );
            let candidate = report
                .components
                .into_iter()
                .find(|c| {
                    c.component_type == kind
                        && (c.native_path == path
                            || path.starts_with(&format!("{}/", c.native_path)))
                })
                .ok_or_else(|| format!("no discovery candidate for {case}: {path}"))?;
            let plan = adoption::plan(
                store,
                adoption::Source {
                    root: source.clone(),
                    harness_id: harness.into(),
                    scope: DiscoveryScope::Project,
                    root_kind: Root::Config,
                    candidate_id: candidate.candidate_id,
                },
                identity(),
                AT,
            )?;
            let draft = adoption::apply(store, &plan, &plan.digest()?, &identity(), AT)?;
            let patch = passports::plan(
                store,
                text(&draft, "stable_id")?,
                text(&draft, "revision_id")?,
                Patch::try_from(
                    json!({"name":"review","description":"Inspect project conventions.","tags":["review"],"license":{"spdx_id":"MIT","redistribution_allowed":true},"permissions":{"filesystem":[],"network":[],"process":[]},"supported_os":["linux"],"supported_arch":["x86_64"]}),
                )?,
                identity(),
                AT,
            )?;
            let draft = passports::apply(store, &patch, &patch.digest()?, &identity(), AT)?;
            let planned = releases::plan(
                store,
                text(&draft, "stable_id")?,
                text(&draft, "revision_id")?,
                Increment::Minor,
                std::slice::from_ref(&provider),
                identity(),
                AT,
            )
            .map_err(|e| format!("release {case}: {e:?}"))?;
            let released = releases::apply(store, &planned, &planned.digest()?, &identity(), AT)?;
            let scope = &released["adaptations"][0]["scope_adaptations"][0];
            assert_eq!(scope["scope"], "project");
            assert_eq!(
                scope["required_surface"]["profile_digest"],
                provider
                    .profile(Scope::Project)
                    .ok_or("project profile missing")?["digest"]
            );
            let payload = store.transaction(|t| {
                revisions::read_content(
                    t,
                    scope["projection_artifact"]["digest"]
                        .as_str()
                        .ok_or_else(|| {
                            ai_stp_cli::error::Failure::input("projection digest missing")
                        })?,
                )
            })?;
            let files = artifact::verify(scope, &payload)?;
            assert_eq!(files.len(), 1, "unexpected captured files for {case}");
            assert_eq!(files[0].path, path);
            assert_eq!(files[0].bytes, bytes);
            fs::remove_dir_all(&source)?;
            let (setup, evidence) = compose(store, harness, &[released])?;
            let built = bundle::compile(
                store,
                &setup,
                &target(harness, Scope::Project),
                &evidence,
                &provider,
                &Hosts::new(),
            )?;
            if let Some(old) = previous {
                assert_ne!(
                    old, built.artifact_digest,
                    "replacement has identical bytes for {case}"
                );
            }
            previous = Some(built.artifact_digest.clone());
            export(&case, &built)?;
        }
    }
    for declaration in declarations {
        let harness = text(declaration, "harness_id")?;
        let provider = Info::parse(&serde_json::to_vec(declaration)?)?;
        for kind in provider
            .profile(Scope::Project)
            .ok_or("project profile missing")?["component_kinds"]
            .as_array()
            .ok_or("kinds missing")?
        {
            assert!(
                covered.contains(&(harness, kind.as_str().ok_or("kind missing")?)),
                "advertised project kind was not exercised"
            );
        }
    }
    Ok(())
}
