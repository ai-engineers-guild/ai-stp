use super::{AT, identity, json, passport, versions};
use super::{
    File, Hosts, Info, Scope, Store, Value, bundle, component, compose, export, target, text,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    error::Error,
};

pub(super) fn journey(store: &mut Store, declarations: &[Value]) -> Result<(), Box<dyn Error>> {
    let provider = Info::parse(&serde_json::to_vec(
        declarations
            .iter()
            .find(|value| value["harness_id"] == "codex")
            .ok_or("Codex declaration absent")?,
    )?)?;
    let instruction = component(
        store,
        &provider,
        Scope::Global,
        File {
            path: "AGENTS.md".into(),
            bytes: b"# Review\nInspect the current source.\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let skill = component(store, &provider, Scope::UserRoot, File {
        path: "skills/review/SKILL.md".into(),
        bytes: b"---\nname: review\ndescription: Review current source.\n---\nInspect the current source.\n".to_vec(),
        mode: 0o644,
    }, None)?;
    let (setup, evidence) = compose(store, "codex", &[instruction.clone(), skill.clone()])?;
    for scope in [Scope::Global, Scope::UserRoot] {
        assert!(
            bundle::compile(
                store,
                &setup,
                &target("codex", scope),
                &evidence,
                &provider,
                &Hosts::new()
            )
            .is_err()
        );
    }
    let hosts = BTreeMap::from([
        (Scope::Global, Hosts::new()),
        (Scope::UserRoot, Hosts::new()),
    ]);
    let selected = target("codex", Scope::Global);
    let result = bundle::scopes::compile(
        store,
        &setup,
        &selected,
        &evidence,
        &provider,
        &hosts,
        &BTreeMap::new(),
    )?;
    assert_eq!(result.bundles.len(), 2);
    assert_eq!(
        result.assessment["scope_bindings"][text(&instruction, "stable_id")?],
        "global"
    );
    assert_eq!(
        result.assessment["scope_bindings"][text(&skill, "stable_id")?],
        "user_root"
    );
    for (scope, built) in &result.bundles {
        assert!(
            bundle::coverage::verify(
                store,
                &setup,
                "codex",
                *scope,
                built.manifest["component_adaptations"]
                    .as_array()
                    .ok_or("bindings absent")?,
            )
            .is_err(),
            "a scope subset claimed the complete setup"
        );
        assert_eq!(
            built.manifest["setup"], setup,
            "a scope invented another setup"
        );
        assert_eq!(
            built.manifest["component_adaptations"]
                .as_array()
                .ok_or("bindings absent")?
                .len(),
            1
        );
        let expected = if *scope == Scope::Global {
            "AGENTS.md"
        } else {
            "skills/review/SKILL.md"
        };
        assert_eq!(built.manifest["files"][0]["path"], expected);
        let mut archive = zip::ZipArchive::new(std::io::Cursor::new(&built.archive))?;
        let mut bytes = Vec::new();
        std::io::Read::read_to_end(&mut archive.by_name("setup-passport.json")?, &mut bytes)?;
        let passport: Value = serde_json::from_slice(&bytes)?;
        assert_eq!(
            passport["components"]
                .as_array()
                .ok_or("setup members absent")?
                .len(),
            2
        );
        export(&format!("codex-multi-{}", scope.as_str()), built)?;
    }
    let repeat = bundle::scopes::compile(
        store,
        &setup,
        &selected,
        &evidence,
        &provider,
        &hosts,
        &BTreeMap::new(),
    )?;
    for (scope, built) in &result.bundles {
        assert_eq!(
            built.archive,
            repeat.bundles.get(scope).ok_or("scope absent")?.archive
        );
    }
    let incomplete = BTreeMap::from([
        (Scope::Global, Hosts::new()),
        (Scope::Project, Hosts::new()),
    ]);
    assert!(
        bundle::scopes::compile(
            store,
            &setup,
            &selected,
            &evidence,
            &provider,
            &incomplete,
            &BTreeMap::new()
        )
        .is_err()
    );
    let wrong = BTreeMap::from([(text(&skill, "stable_id")?.into(), Scope::Global)]);
    assert!(
        bundle::scopes::compile(
            store, &setup, &selected, &evidence, &provider, &hosts, &wrong
        )
        .is_err()
    );

    // Individually valid roots must still refuse a logical collision across roots.
    let command = component(
        store,
        &provider,
        Scope::Global,
        File {
            path: "prompts/review.md".into(),
            bytes: b"Review the current source.\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let (conflict, evidence) = compose(store, "codex", &[command, skill.clone()])?;
    let error = bundle::scopes::compile(
        store,
        &conflict,
        &selected,
        &evidence,
        &provider,
        &hosts,
        &BTreeMap::new(),
    )
    .err()
    .ok_or("cross-root native collision was accepted")?;
    assert_eq!(error.details["constraint"], "native_id_collision");
    ambiguity(store, &provider, &instruction)?;
    contributions(store, &provider, skill)?;
    coverage(store, declarations)?;
    Ok(())
}

fn coverage(store: &mut Store, declarations: &[Value]) -> Result<(), Box<dyn Error>> {
    let provider = Info::parse(&serde_json::to_vec(
        declarations
            .iter()
            .find(|value| value["harness_id"] == "cursor")
            .ok_or("Cursor declaration absent")?,
    )?)?;
    let dependency = component(
        store,
        &provider,
        Scope::Project,
        File {
            path: ".cursor/skills/dependency/SKILL.md".into(),
            bytes: b"---\nname: dependency\ndescription: Inspect the complete project.\n---\nInspect every retained member.\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let mut skill = component(
        store, &provider, Scope::Project,
        File { path: ".cursor/skills/coverage/SKILL.md".into(),
            bytes: b"---\nname: coverage\ndescription: Verify complete setup coverage.\n---\nInspect every dependency.\n".to_vec(), mode: 0o644 }, None,
    )?;
    skill["version"] = "2.0".into();
    skill["requires_components"] = json!([super::reference(&dependency)?]);
    let skill =
        store.transaction(|t| versions::record(t, &skill, &identity().device_id, None, AT))?;
    let (_, mut evidence) = compose(store, "cursor", std::slice::from_ref(&dependency))?;
    let (setup, more) = compose(store, "cursor", std::slice::from_ref(&skill))?;
    evidence.extend(more);
    let built = bundle::compile(
        store,
        &setup,
        &target("cursor", Scope::Project),
        &evidence,
        &provider,
        &Hosts::new(),
    )?;
    // Catalog passports may retain a direct member whose dependency is not a root.
    let (setup, more) = super::catalog_repin(store, &built, &skill)?;
    evidence.extend(more);
    let built = bundle::compile(
        store,
        &setup,
        &target("cursor", Scope::Project),
        &evidence,
        &provider,
        &Hosts::new(),
    )?;
    let bindings = built.manifest["component_adaptations"]
        .as_array()
        .ok_or("bindings absent")?;
    assert_eq!(bindings.len(), 2);
    bundle::coverage::verify(store, &setup, "cursor", Scope::Project, bindings)?;
    let mut reversed = bindings.clone();
    reversed.reverse();
    bundle::coverage::verify(store, &setup, "cursor", Scope::Project, &reversed)?;
    assert!(bundle::coverage::verify(store, &setup, "cursor", Scope::Global, bindings).is_err());
    let missing_dependency: Vec<_> = bindings
        .iter()
        .filter(|item| item["stable_id"] != dependency["stable_id"])
        .cloned()
        .collect();
    assert!(
        bundle::coverage::verify(store, &setup, "cursor", Scope::Project, &missing_dependency)
            .is_err()
    );
    let mut duplicate = bindings.clone();
    duplicate.push(bindings[0].clone());
    assert!(bundle::coverage::verify(store, &setup, "cursor", Scope::Project, &duplicate).is_err());
    for field in [
        "version",
        "passport_digest",
        "adaptation_id",
        "projection_artifact",
        "member_paths",
    ] {
        let mut forged = bindings.clone();
        forged[0][field] = Value::Null;
        assert!(
            bundle::coverage::verify(store, &setup, "cursor", Scope::Project, &forged).is_err(),
            "accepted forged {field}"
        );
    }
    let files = payload(&built)?;
    let verify = |store: &mut Store, files: &BTreeMap<String, bundle::coverage::File>| {
        bundle::coverage::verify_payload(
            store,
            &setup,
            "cursor",
            Scope::Project,
            bindings,
            files,
            &Hosts::new(),
        )
    };
    verify(store, &files)?;
    let path = files.keys().next().ok_or("file absent")?.clone();
    for changed in ["bytes", "mode", "owner", "contribution", "missing", "extra"] {
        let mut altered = files.clone();
        match changed {
            "missing" => {
                altered.remove(&path);
            }
            "extra" => {
                altered.insert("unclaimed.md".into(), files[&path].clone());
            }
            _ => {
                let file = altered.get_mut(&path).ok_or("file absent")?;
                match changed {
                    "bytes" => file
                        .bytes
                        .extend_from_slice(b"\nSubstituted instructions.\n"),
                    "mode" => file.mode = 0o755,
                    "owner" => file.owner = "another-component".into(),
                    "contribution" => file.contribution = Some(json!({})),
                    _ => unreachable!(),
                }
            }
        }
        assert!(
            verify(store, &altered).is_err(),
            "accepted substituted {changed}"
        );
    }
    Ok(())
}

fn payload(
    built: &bundle::Bundle,
) -> Result<BTreeMap<String, bundle::coverage::File>, Box<dyn Error>> {
    let mut archive = zip::ZipArchive::new(std::io::Cursor::new(&built.archive))?;
    built.manifest["files"]
        .as_array()
        .ok_or("files absent")?
        .iter()
        .map(|file| {
            let path = text(file, "path")?;
            let mut bytes = Vec::new();
            std::io::Read::read_to_end(
                &mut archive.by_name(&format!("files/{path}"))?,
                &mut bytes,
            )?;
            Ok((
                path.into(),
                bundle::coverage::File {
                    bytes,
                    mode: file["mode"].as_u64().ok_or("mode absent")? as u32,
                    owner: text(file, "owner")?.into(),
                    contribution: file.get("contribution").cloned(),
                },
            ))
        })
        .collect()
}

fn contributions(store: &mut Store, provider: &Info, skill: Value) -> Result<(), Box<dyn Error>> {
    let settings = component(
        store,
        provider,
        Scope::Global,
        File {
            path: "config.toml".into(),
            bytes: b"LOG_LEVEL = 'info'\n".to_vec(),
            mode: 0o644,
        },
        Some("env"),
    )?;
    let (setup, evidence) = compose(store, "codex", &[settings.clone(), skill])?;
    let scopes = BTreeSet::from([Scope::Global, Scope::UserRoot]);
    let paths =
        bundle::scopes::contribution_paths(store, &setup, "codex", &scopes, &BTreeMap::new())?;
    assert_eq!(
        paths[&Scope::Global],
        BTreeSet::from(["config.toml".into()])
    );
    assert!(paths[&Scope::UserRoot].is_empty());
    let selected = target("codex", Scope::Global);
    let mut hosts = BTreeMap::from([
        (Scope::Global, Hosts::new()),
        (Scope::UserRoot, Hosts::new()),
    ]);
    assert!(
        bundle::scopes::compile(
            store,
            &setup,
            &selected,
            &evidence,
            provider,
            &hosts,
            &BTreeMap::new()
        )
        .is_err()
    );
    hosts
        .get_mut(&Scope::Global)
        .ok_or("host scope absent")?
        .insert(
            "config.toml".into(),
            Some(b"model = 'user-choice'\n".to_vec()),
        );
    let built = bundle::scopes::compile(
        store,
        &setup,
        &selected,
        &evidence,
        provider,
        &hosts,
        &BTreeMap::new(),
    )?;
    let mut archive =
        zip::ZipArchive::new(std::io::Cursor::new(&built.bundles[&Scope::Global].archive))?;
    let mut text = String::new();
    std::io::Read::read_to_string(&mut archive.by_name("files/config.toml")?, &mut text)?;
    let configuration: toml_edit::DocumentMut = text.parse()?;
    assert_eq!(configuration["model"].as_str(), Some("user-choice"));
    assert_eq!(configuration["env"]["LOG_LEVEL"].as_str(), Some("info"));
    let (complete, evidence) = compose(store, "codex", &[settings])?;
    let observed_hosts = &hosts[&Scope::Global];
    let built = bundle::compile(
        store,
        &complete,
        &selected,
        &evidence,
        provider,
        observed_hosts,
    )?;
    let files = payload(&built)?;
    let bindings = built.manifest["component_adaptations"]
        .as_array()
        .ok_or("bindings absent")?;
    bundle::coverage::verify_payload(
        store,
        &complete,
        "codex",
        Scope::Global,
        bindings,
        &files,
        observed_hosts,
    )?;
    let mut forged = files.clone();
    forged
        .get_mut("config.toml")
        .ok_or("configuration absent")?
        .bytes = b"model = 'user-choice'\n[env]\nLOG_LEVEL = 'substituted'\n".to_vec();
    assert!(
        bundle::coverage::verify_payload(
            store,
            &complete,
            "codex",
            Scope::Global,
            bindings,
            &forged,
            observed_hosts
        )
        .is_err()
    );
    let changed_hosts =
        Hosts::from([("config.toml".into(), Some(b"model = 'changed'\n".to_vec()))]);
    assert!(
        bundle::coverage::verify_payload(
            store,
            &complete,
            "codex",
            Scope::Global,
            bindings,
            &files,
            &changed_hosts
        )
        .is_err()
    );
    Ok(())
}

fn ambiguity(store: &mut Store, provider: &Info, original: &Value) -> Result<(), Box<dyn Error>> {
    let mut document = original.clone();
    document["version"] = "2.0".into();
    let mut adaptation = document["adaptations"][0].clone();
    let mut scoped = adaptation["scope_adaptations"][0].clone();
    let profile = provider
        .profile(Scope::Project)
        .ok_or("project profile absent")?;
    scoped["scope"] = "project".into();
    scoped["required_surface"]["profile_id"] = profile["profile_id"].clone();
    scoped["required_surface"]["profile_digest"] = profile["digest"].clone();
    adaptation["scope_adaptations"]
        .as_array_mut()
        .ok_or("scopes absent")?
        .push(scoped);
    document["adaptations"] = json!([passport::versions::seal_adaptation(&adaptation)?]);
    let document =
        store.transaction(|t| versions::record(t, &document, &identity().device_id, None, AT))?;
    let command = component(
        store,
        provider,
        Scope::Global,
        File {
            path: "prompts/focus.md".into(),
            bytes: b"Inspect the current change.\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let (setup, evidence) = compose(store, "codex", &[document.clone(), command])?;
    let selected = target("codex", Scope::Global);
    let hosts = BTreeMap::from([
        (Scope::Global, Hosts::new()),
        (Scope::Project, Hosts::new()),
    ]);
    let refusal = bundle::scopes::compile(
        store,
        &setup,
        &selected,
        &evidence,
        provider,
        &hosts,
        &BTreeMap::new(),
    )
    .err()
    .ok_or("ambiguous component was silently routed")?;
    assert_eq!(refusal.details["stable_id"], document["stable_id"]);
    assert_eq!(
        refusal.details["available_scopes"],
        json!(["global", "project"])
    );
    let placements = BTreeMap::from([(text(&document, "stable_id")?.into(), Scope::Project)]);
    let built = bundle::scopes::compile(
        store,
        &setup,
        &selected,
        &evidence,
        provider,
        &hosts,
        &placements,
    )?;
    assert_eq!(
        built.bundles[&Scope::Project].manifest["files"][0]["path"],
        "AGENTS.md"
    );
    assert_eq!(
        bundle::scopes::contribution_paths(
            store,
            &setup,
            "codex",
            &hosts.keys().copied().collect(),
            &placements
        )?,
        BTreeMap::from([
            (Scope::Global, BTreeSet::new()),
            (Scope::Project, BTreeSet::new())
        ])
    );
    Ok(())
}
