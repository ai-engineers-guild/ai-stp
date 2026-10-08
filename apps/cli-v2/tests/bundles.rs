use ai_stp_cli_v2::{
    artifacts::Member as File,
    authoring::{
        Identity,
        setups::{self, Member, Request},
    },
    bundle::{self, Hosts},
    canonical, digest, passport,
    projection::{self, Scope},
    provider::Info,
    selection::eligibility::{Evidence, Target},
    store::{Store, revisions, versions},
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, error::Error};

const AT: &str = "2026-10-08T00:00:00.000Z";
fn identity() -> Identity {
    Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    }
}
fn text<'a>(value: &'a Value, name: &str) -> Result<&'a str, Box<dyn Error>> {
    value[name]
        .as_str()
        .ok_or_else(|| format!("{name} missing").into())
}
fn reference(document: &Value) -> Result<Member, Box<dyn Error>> {
    Ok(Member {
        stable_id: text(document, "stable_id")?.into(),
        version: text(document, "version")?.into(),
        passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
    })
}
fn target(harness: &str, scope: Scope) -> Target {
    Target {
        harness_id: harness.into(),
        scope,
        os: "linux".into(),
        arch: "x86_64".into(),
        harness_version: "unknown".into(),
        owner_id: identity().account_id,
        capabilities: Default::default(),
        permissions: Default::default(),
        entitlements: Default::default(),
        env_present: Default::default(),
        grants: Default::default(),
        pinned_passport_digests: Default::default(),
        for_redistribution: false,
    }
}
fn component(
    store: &mut Store,
    provider: &Info,
    scope: Scope,
    file: File,
    contribution: Option<&str>,
) -> Result<Value, Box<dyn Error>> {
    let catalog: Value = serde_json::from_str(include_str!(
        "../../../packages/contracts/src/ai_stp_contracts/fixtures/v1/catalog.json"
    ))?;
    let mut document = catalog["cases"]
        .as_array()
        .ok_or("cases missing")?
        .iter()
        .find(|case| case["case_id"] == "readComponentVersion.published")
        .ok_or("fixture missing")?["body"]["passport"]
        .clone();
    let profile = provider.profile(scope).ok_or("profile missing")?;
    let kind = if contribution.is_some() {
        "mcp"
    } else if file.path.contains("skills/") {
        "skill"
    } else {
        "instruction"
    };
    let declared = json!({"path":file.path,"object_type":"file","mode":file.mode,"content_artifact":{"digest":digest::bytes("ai-stp:artifact:v1",&file.bytes)?,"size_bytes":file.bytes.len()},
        "native_ids":[],"content_format":"application/octet-stream","parser_id":contribution.map(|_|if file.path.ends_with("toml"){"toml/1"}else{"json/1"}),
        "ownership":if contribution.is_some(){"contribution"}else{"whole"},"ownership_key":contribution,
        "write_semantics":if contribution.is_some(){"merge"}else{"replace"},"withdrawal_semantics":if contribution.is_some(){"preserve_unowned"}else{"remove_path"}});
    let payload = projection::artifact::build_members(std::slice::from_ref(&declared), &[file])?;
    let artifact =
        json!({"digest":digest::bytes("ai-stp:artifact:v1",&payload)?,"size_bytes":payload.len()});
    let adaptation = passport::versions::seal_adaptation(
        &json!({"harness_id":provider.document()["harness_id"],"implementation_mode":"native",
        "source_artifact":null,"transform":null,"logical_component_type":kind,"scope_adaptations":[{"scope":scope,"projection_format":projection::artifact::FORMAT,
        "projection_artifact":artifact,"provider_component_kind":if contribution.is_some(){"setting"}else{kind},"projection_kind":"native_files",
        "required_surface":{"profile_id":profile["profile_id"],"profile_digest":profile["digest"],"bundle_format":"ai-stp-bundle/2"},
        "permissions":{"filesystem":[],"network":[],"process":[]},"members":[declared],"technical_support":"experimental","technical_support_reason":"Local proof", "semantic_losses":[]}]}),
    )?;
    document["stable_id"] = format!("component_{}", ulid::Ulid::generate()).into();
    document["owner_id"] = identity().account_id.into();
    document["visibility"] = "private".into();
    document["version"] = "1.0".into();
    document["parent_revision_ids"] = json!([]);
    document["facts"] = json!({});
    document["component_type"] = kind.into();
    document["origin_harness_id"] = provider.document()["harness_id"].clone();
    document["adaptations"] = json!([adaptation]);
    document["artifact"] = artifact;
    document["artifact_format"] = projection::artifact::FORMAT.into();
    document["requires_components"] = json!([]);
    document["requires_capabilities"] = json!([]);
    document["permissions"] = json!({"filesystem":[],"network":[],"process":[]});
    Ok(store.transaction(|t| {
        revisions::content(t, &payload, AT)?;
        revisions::commit(
            t,
            &document,
            &identity().device_id,
            None,
            revisions::Write::Advance {
                expected_heads: &[],
            },
        )?;
        versions::record(t, &document, &identity().device_id, None, AT)
    })?)
}
fn compose(
    store: &mut Store,
    harness: &str,
    members: &[Value],
) -> Result<(Value, BTreeMap<String, Evidence>), Box<dyn Error>> {
    let plan = setups::plan(
        store,
        Request {
            harness_id: harness.into(),
            name: "Bundle proof".into(),
            description: "Inspect project conventions.".into(),
            purpose: "Verify exact native packaging.".into(),
            members: members.iter().map(reference).collect::<Result<_, _>>()?,
        },
        identity(),
        AT,
    )?;
    let setup = setups::apply(store, &plan, &plan.digest()?, &identity(), AT)?;
    let evidence = members
        .iter()
        .chain(std::iter::once(&setup))
        .map(|document| {
            Ok((
                text(document, "stable_id")?.into(),
                Evidence {
                    passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
                    registrable: true,
                    blocked: false,
                    author_verified: false,
                    component_verified: false,
                    checks_current: false,
                    consented: false,
                },
            ))
        })
        .collect::<Result<_, Box<dyn Error>>>()?;
    Ok((serde_json::to_value(reference(&setup)?)?, evidence))
}
fn export(name: &str, bundle: &bundle::Bundle) -> Result<(), Box<dyn Error>> {
    if let Some(path) = std::env::var_os("AI_STP_BUNDLE_PROOF_DIR") {
        let path = std::path::PathBuf::from(path);
        std::fs::create_dir_all(&path)?;
        std::fs::write(path.join(format!("{name}.zip")), &bundle.archive)?;
        std::fs::write(
            path.join(format!("{name}.json")),
            canonical::bytes(&bundle.manifest)?,
        )?;
    }
    Ok(())
}

#[test]
fn exact_bundles_cover_every_released_profile_and_refuse_unrepresentable_inputs()
-> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let mut store = Store::open(root.path(), true)?;
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let mut profiles = 0;
    for declaration in &declarations {
        let provider = Info::parse(&serde_json::to_vec(declaration)?)?;
        let harness = text(declaration, "harness_id")?;
        for scope in [Scope::Global, Scope::Project, Scope::UserRoot] {
            let Some(profile) = provider.profile(scope) else {
                continue;
            };
            let namespaces = profile["native_namespaces"]
                .as_array()
                .ok_or("namespaces missing")?;
            let skill = namespaces
                .iter()
                .filter_map(Value::as_str)
                .find(|name| *name == "skills" || name.ends_with("/skills"));
            let path = if let Some(skill) = skill {
                format!("{skill}/review/SKILL.md")
            } else {
                namespaces
                    .iter()
                    .filter_map(Value::as_str)
                    .find(|name| name.ends_with(".md"))
                    .ok_or("instruction namespace missing")?
                    .into()
            };
            let component = component(
                &mut store,
                &provider,
                scope,
                File {
                    path,
                    bytes: b"# Review\nInspect project conventions.\n".to_vec(),
                    mode: 0o644,
                },
                None,
            )?;
            let (setup, evidence) = compose(&mut store, harness, &[component])?;
            let target = target(harness, scope);
            let bundle = bundle::compile(
                &mut store,
                &setup,
                &target,
                &evidence,
                &provider,
                &Hosts::new(),
            )?;
            assert_eq!(
                bundle.manifest["files"]
                    .as_array()
                    .ok_or("files missing")?
                    .len(),
                1
            );
            assert_eq!(
                bundle.manifest["projection_profile"]["profile_digest"],
                profile["digest"]
            );
            assert_eq!(
                bundle.archive,
                bundle::compile(
                    &mut store,
                    &setup,
                    &target,
                    &evidence,
                    &provider,
                    &Hosts::new()
                )?
                .archive
            );
            assert_eq!(bundle.artifact_digest, digest::sha256(&bundle.archive));
            let mut payload = bundle.manifest.clone();
            payload
                .as_object_mut()
                .ok_or("manifest missing")?
                .remove("bundle_digest");
            assert_eq!(
                bundle.manifest["bundle_digest"],
                digest::canonical("ai-stp:bundle:v1", &payload)?
            );
            export(&format!("{harness}-{}", scope.as_str()), &bundle)?;
            profiles += 1;
        }
    }
    assert_eq!(profiles, 16);
    let claude = declarations
        .iter()
        .find(|p| p["harness_id"] == "claude-code")
        .ok_or("Claude missing")?;
    let provider = Info::parse(&serde_json::to_vec(claude)?)?;
    let target = target("claude-code", Scope::Global);
    for paths in [
        ["skills/a/file.md", "skills/a-other.md", "skills/a"],
        ["skills/a", "skills/a-other.md", "skills/a/file.md"],
        [
            "skills/Review/a.md",
            "skills/review/b.md",
            "skills/third.md",
        ],
    ] {
        let members = paths
            .into_iter()
            .map(|path| {
                component(
                    &mut store,
                    &provider,
                    Scope::Global,
                    File {
                        path: path.into(),
                        bytes: b"# Review\n".to_vec(),
                        mode: 0o644,
                    },
                    None,
                )
            })
            .collect::<Result<Vec<_>, _>>()?;
        let (setup, evidence) = compose(&mut store, "claude-code", &members)?;
        assert!(
            bundle::compile(
                &mut store,
                &setup,
                &target,
                &evidence,
                &provider,
                &Hosts::new()
            )
            .is_err()
        );
    }
    let first = component(
        &mut store,
        &provider,
        Scope::Global,
        File {
            path: "skills/review/SKILL.md".into(),
            bytes: b"# Review\n".to_vec(),
            mode: 0o755,
        },
        None,
    )?;
    // Directory declarations are preserved in CAS; the file-only bundle format
    // must refuse them instead of silently losing their presence or permissions.
    let mut with_directory = first.clone();
    let mut directory = first["adaptations"][0]["scope_adaptations"][0]["members"][0].clone();
    directory["path"] = "skills/review/empty".into();
    directory["object_type"] = "directory".into();
    directory["content_artifact"] = Value::Null;
    let scope = &mut with_directory["adaptations"][0]["scope_adaptations"][0];
    scope["members"]
        .as_array_mut()
        .ok_or("members missing")?
        .push(directory);
    let payload = projection::artifact::build_members(
        scope["members"].as_array().ok_or("members missing")?,
        &[File {
            path: "skills/review/SKILL.md".into(),
            bytes: b"# Review\n".to_vec(),
            mode: 0o755,
        }],
    )?;
    let artifact =
        json!({"digest":digest::bytes("ai-stp:artifact:v1",&payload)?,"size_bytes":payload.len()});
    scope["projection_artifact"] = artifact.clone();
    with_directory["artifact"] = artifact;
    with_directory["adaptations"][0] =
        passport::versions::seal_adaptation(&with_directory["adaptations"][0])?;
    with_directory["version"] = "1.1".into();
    let with_directory = store.transaction(|t| {
        revisions::content(t, &payload, AT)?;
        versions::record(t, &with_directory, &identity().device_id, None, AT)
    })?;
    let (setup, evidence) = compose(&mut store, "claude-code", &[with_directory])?;
    assert!(
        bundle::compile(
            &mut store,
            &setup,
            &target,
            &evidence,
            &provider,
            &Hosts::new()
        )
        .is_err()
    );
    let second = component(
        &mut store,
        &provider,
        Scope::Global,
        File {
            path: "skills/review/SKILL.md".into(),
            bytes: b"# Different\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let (setup, evidence) = compose(&mut store, "claude-code", &[first.clone(), second.clone()])?;
    assert!(
        bundle::compile(
            &mut store,
            &setup,
            &target,
            &evidence,
            &provider,
            &Hosts::new()
        )
        .is_err()
    );
    let mut same_native_id = Vec::new();
    for original in [&first, &second] {
        let mut changed = original.clone();
        changed["version"] = "2.0".into();
        changed["adaptations"][0]["scope_adaptations"][0]["members"][0]["native_ids"] =
            json!(["review"]);
        changed["adaptations"][0] =
            passport::versions::seal_adaptation(&changed["adaptations"][0])?;
        same_native_id.push(
            store
                .transaction(|t| versions::record(t, &changed, &identity().device_id, None, AT))?,
        );
    }
    let (setup, evidence) = compose(&mut store, "claude-code", &same_native_id)?;
    let refusal = bundle::compile(
        &mut store,
        &setup,
        &target,
        &evidence,
        &provider,
        &Hosts::new(),
    )
    .err()
    .ok_or("native collision accepted")?;
    assert!(refusal.message.contains("native_id_collision"));
    let (empty, evidence) = compose(&mut store, "claude-code", &[])?;
    assert!(
        bundle::compile(
            &mut store,
            &empty,
            &target,
            &evidence,
            &provider,
            &Hosts::new()
        )
        .is_err()
    );
    let (setup, mut evidence) = compose(&mut store, "claude-code", std::slice::from_ref(&first))?;
    let built = bundle::compile(
        &mut store,
        &setup,
        &target,
        &evidence,
        &provider,
        &Hosts::new(),
    )?;
    assert_eq!(built.manifest["files"][0]["mode"], 0o755);
    evidence
        .get_mut(text(&first, "stable_id")?)
        .ok_or("evidence missing")?
        .blocked = true;
    assert!(
        bundle::compile(
            &mut store,
            &setup,
            &target,
            &evidence,
            &provider,
            &Hosts::new()
        )
        .is_err()
    );
    for path in ["skills/review/.env", "skills/review/id_ed25519"] {
        let secret = component(
            &mut store,
            &provider,
            Scope::Global,
            File {
                path: path.into(),
                bytes: b"synthetic proof bytes".to_vec(),
                mode: 0o644,
            },
            None,
        )?;
        let (setup, evidence) = compose(&mut store, "claude-code", &[secret])?;
        assert!(
            bundle::compile(
                &mut store,
                &setup,
                &target,
                &evidence,
                &provider,
                &Hosts::new()
            )
            .is_err()
        );
    }
    // One contribution preserves the unowned host object and binds its exact bytes.
    let mcp = component(
        &mut store,
        &provider,
        Scope::Global,
        File {
            path: "settings.json".into(),
            bytes: br#"{"review":{"command":"review-tool"}}"#.to_vec(),
            mode: 0o644,
        },
        Some("mcpServers"),
    )?;
    let (setup, evidence) = compose(&mut store, "claude-code", std::slice::from_ref(&mcp))?;
    assert!(
        bundle::compile(
            &mut store,
            &setup,
            &target,
            &evidence,
            &provider,
            &Hosts::new()
        )
        .is_err()
    );
    let hosts: Hosts = [(
        "settings.json".into(),
        Some(br#"{"theme":"night"}"#.to_vec()),
    )]
    .into();
    let built = bundle::compile(&mut store, &setup, &target, &evidence, &provider, &hosts)?;
    let mut archive = zip::ZipArchive::new(std::io::Cursor::new(&built.archive))?;
    let mut bytes = Vec::new();
    std::io::Read::read_to_end(&mut archive.by_name("files/settings.json")?, &mut bytes)?;
    let parsed: Value = serde_json::from_slice(&bytes)?;
    assert_eq!(parsed["theme"], "night");
    assert_eq!(parsed["mcpServers"]["review"]["command"], "review-tool");
    export("claude-code-contribution", &built)?;
    let absent: Hosts = [("settings.json".into(), None)].into();
    let fresh = bundle::compile(&mut store, &setup, &target, &evidence, &provider, &absent)?;
    assert_ne!(
        built.manifest["input_digest"],
        fresh.manifest["input_digest"]
    );
    assert_ne!(built.artifact_digest, fresh.artifact_digest);
    let mut surplus = absent;
    surplus.insert("unowned.json".into(), None);
    assert!(bundle::compile(&mut store, &setup, &target, &evidence, &provider, &surplus).is_err());
    let whole = component(
        &mut store,
        &provider,
        Scope::Global,
        File {
            path: "settings.json".into(),
            bytes: b"{}".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let (setup, evidence) = compose(&mut store, "claude-code", &[mcp.clone(), whole])?;
    assert!(bundle::compile(&mut store, &setup, &target, &evidence, &provider, &hosts).is_err());
    // A corrupt stored projection never becomes a partially compiled package.
    let (setup, evidence) = compose(&mut store, "claude-code", std::slice::from_ref(&mcp))?;
    store.transaction(|t| {
        t.execute(
            "UPDATE content SET bytes=? WHERE digest=?",
            rusqlite::params![
                b"corrupt".as_slice(),
                text(&mcp["artifact"], "digest")
                    .map_err(|_| ai_stp_cli_v2::error::Failure::input("digest missing"))?
            ],
        )
        .map(|_| ())
        .map_err(|_| ai_stp_cli_v2::error::Failure::input("proof corruption failed"))
    })?;
    assert!(bundle::compile(&mut store, &setup, &target, &evidence, &provider, &hosts).is_err());
    Ok(())
}

#[test]
fn declared_exclusions_are_symmetric_and_do_not_conflict_with_their_owner()
-> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let mut store = Store::open(root.path(), true)?;
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let declaration = declarations
        .iter()
        .find(|value| value["harness_id"] == "claude-code")
        .ok_or("Claude missing")?;
    let provider = Info::parse(&serde_json::to_vec(declaration)?)?;
    let target = target("claude-code", Scope::Global);
    for family in ["paths", "commands"] {
        let mut originals = Vec::new();
        for name in ["left", "right"] {
            let path = if family == "paths" {
                format!("skills/{name}/SKILL.md")
            } else {
                format!("commands/{name}.md")
            };
            originals.push(component(
                &mut store,
                &provider,
                Scope::Global,
                File {
                    path,
                    bytes: b"# Review\n".to_vec(),
                    mode: 0o644,
                },
                None,
            )?);
        }
        originals.sort_by(|a, b| a["stable_id"].as_str().cmp(&b["stable_id"].as_str()));
        for case in 0..6 {
            let declarer = case % 2;
            let excluded = if case < 2 { 1 - declarer } else { declarer };
            let mut members = Vec::new();
            for (index, original) in originals.iter().enumerate() {
                let mut document = original.clone();
                document["version"] = format!("2.{case}").into();
                let path = text(
                    &original["adaptations"][0]["scope_adaptations"][0]["members"][0],
                    "path",
                )?;
                let name = path
                    .split('/')
                    .nth(1)
                    .ok_or("name missing")?
                    .trim_end_matches(".md");
                document["adaptations"][0]["scope_adaptations"][0]["members"][0]["native_ids"] =
                    json!([name]);
                if family == "commands" {
                    document["component_type"] = "command".into();
                    document["adaptations"][0]["logical_component_type"] = "command".into();
                    document["adaptations"][0]["scope_adaptations"][0]["provider_component_kind"] =
                        "command".into();
                }
                if index == declarer {
                    let banned_path = text(
                        &originals[excluded]["adaptations"][0]["scope_adaptations"][0]["members"]
                            [0],
                        "path",
                    )?;
                    let banned = if family == "paths" {
                        banned_path.rsplit_once('/').ok_or("parent missing")?.0
                    } else {
                        banned_path
                            .split('/')
                            .nth(1)
                            .ok_or("name missing")?
                            .trim_end_matches(".md")
                    };
                    let banned = if case >= 4 {
                        format!("{banned}-other")
                    } else {
                        banned.to_owned()
                    };
                    document["conflicts"][family] = json!([banned]);
                }
                document["adaptations"][0] =
                    passport::versions::seal_adaptation(&document["adaptations"][0])?;
                members.push(store.transaction(|t| {
                    versions::record(t, &document, &identity().device_id, None, AT)
                })?);
            }
            let (setup, evidence) = compose(&mut store, "claude-code", &members)?;
            let result = bundle::compile(
                &mut store,
                &setup,
                &target,
                &evidence,
                &provider,
                &Hosts::new(),
            );
            if case < 2 {
                let refusal = result
                    .err()
                    .ok_or_else(|| format!("ignored {family} exclusion from member {declarer}"))?;
                assert_eq!(refusal.details["constraint"], "declared_conflict");
                assert_eq!(refusal.details["family"], family);
                assert_eq!(refusal.details["stable_id"], members[declarer]["stable_id"]);
                assert_eq!(refusal.details["also"], members[excluded]["stable_id"]);
                let envelope = ai_stp_cli_v2::Invocation {
                    result: Err(refusal),
                    machine: true,
                    text: None,
                }
                .envelope();
                assert_eq!(
                    envelope["error"]["details"]["constraint"],
                    "declared_conflict"
                );
                assert!(envelope.get("data").is_none());
            } else {
                result?;
            }
        }
    }
    Ok(())
}
