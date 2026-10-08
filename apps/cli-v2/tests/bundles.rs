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
    } else if file.path.starts_with("commands/") || file.path.starts_with("prompts/") {
        "command"
    } else if file.path.starts_with("agents/") {
        "agent"
    } else if file.path.ends_with("/SKILL.md") {
        "skill"
    } else {
        "instruction"
    };
    let native_ids = if matches!(kind, "mcp" | "agent") {
        json!(["review"])
    } else if kind == "command" {
        let stem = file
            .path
            .strip_prefix("commands/")
            .or_else(|| file.path.strip_prefix("prompts/"))
            .ok_or("command root missing")?
            .strip_suffix(".md")
            .ok_or("command suffix missing")?;
        json!([if provider.document()["harness_id"] != "claude-code" {
            stem.to_owned()
        } else {
            stem.replace('/', ":")
        }])
    } else if kind == "skill" {
        json!([file.path.rsplit('/').nth(1).ok_or("skill folder missing")?])
    } else {
        json!([])
    };
    let declared = json!({"path":file.path,"object_type":"file","mode":file.mode,"content_artifact":{"digest":digest::bytes("ai-stp:artifact:v1",&file.bytes)?,"size_bytes":file.bytes.len()},
        "native_ids":native_ids,"content_format":"application/octet-stream","parser_id":contribution.map(|_|if file.path.ends_with("toml"){"toml/1"}else{"json/1"}),
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
// A retained catalog setup is schema-valid without passing local authoring.
// Repin both its passport and canonical definition to exercise that boundary.
fn catalog_repin(
    store: &mut Store,
    setup: &bundle::Bundle,
    component: &Value,
) -> Result<(Value, BTreeMap<String, Evidence>), Box<dyn Error>> {
    let mut archive = zip::ZipArchive::new(std::io::Cursor::new(&setup.archive))?;
    let mut bytes = Vec::new();
    std::io::Read::read_to_end(&mut archive.by_name("setup-passport.json")?, &mut bytes)?;
    let mut document: Value = serde_json::from_slice(&bytes)?;
    document["version"] = "2.0".into();
    document["components"] = json!([reference(component)?]);
    let payload = canonical::bytes(
        &json!({"schema_version":1,"format":"ai-stp-setup-definition/1",
        "stable_id":document["stable_id"],"version":document["version"],"harness_id":document["harness_id"],
        "input_digest":document["facts"]["snapshot"]["value"],"components":document["components"]}),
    )?;
    document["artifact"] =
        json!({"digest":digest::bytes("ai-stp:artifact:v1",&payload)?,"size_bytes":payload.len()});
    let document = store.transaction(|t| {
        revisions::content(t, &payload, AT)?;
        versions::record(t, &document, &identity().device_id, None, AT)
    })?;
    let evidence = [&document, component]
        .into_iter()
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
    Ok((serde_json::to_value(reference(&document)?)?, evidence))
}
fn rejects_fabricated_ids(
    store: &mut Store,
    component: &Value,
    built: &bundle::Bundle,
    target: &Target,
    provider: &Info,
    hosts: &Hosts,
) -> Result<(), Box<dyn Error>> {
    let mut forged = component.clone();
    forged["version"] = "2.0".into();
    forged["adaptations"][0]["scope_adaptations"][0]["members"][0]["native_ids"] =
        json!(["fabricated"]);
    forged["adaptations"][0] = passport::versions::seal_adaptation(&forged["adaptations"][0])?;
    let forged =
        store.transaction(|t| versions::record(t, &forged, &identity().device_id, None, AT))?;
    assert!(compose(store, &target.harness_id, std::slice::from_ref(&forged)).is_err());
    let (catalog_setup, catalog_evidence) = catalog_repin(store, built, &forged)?;
    let refused = bundle::compile(
        store,
        &catalog_setup,
        target,
        &catalog_evidence,
        provider,
        hosts,
    )
    .err()
    .ok_or("bundle trusted fabricated native IDs")?;
    assert_eq!(refused.details["constraint"], "native_identifier_mismatch");

    Ok(())
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

fn skill_inventory(
    store: &mut Store,
    declarations: &[Value],
    harness: &str,
) -> Result<(), Box<dyn Error>> {
    let declaration = declarations
        .iter()
        .find(|value| value["harness_id"] == harness)
        .ok_or("skill provider missing")?;
    let provider = Info::parse(&serde_json::to_vec(declaration)?)?;
    let scope = Scope::UserRoot;
    let target = target(harness, scope);
    let skill = component(
        store,
        &provider,
        scope,
        File {
            path: "skills/review/SKILL.md".into(),
            bytes: b"---\ndescription: Review source.\n---\nBody.\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let (setup, evidence) = compose(store, harness, std::slice::from_ref(&skill))?;
    let built = bundle::compile(store, &setup, &target, &evidence, &provider, &Hosts::new())?;
    export(&format!("{harness}-fallback-skill"), &built)?;
    rejects_fabricated_ids(store, &skill, &built, &target, &provider, &Hosts::new())?;
    // A skill hidden in a different logical kind cannot bypass the entry inventory.
    let hidden = component(
        store,
        &provider,
        scope,
        File {
            path: "skills/extra/SKILL.md".into(),
            bytes: b"---\nname: extra\ndescription: Extra.\n---\nBody.\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let mut hidden = hidden;
    hidden["component_type"] = "instruction".into();
    hidden["adaptations"][0]["logical_component_type"] = "instruction".into();
    hidden["adaptations"][0]["scope_adaptations"][0]["members"][0]["native_ids"] = json!([]);
    hidden["adaptations"][0] = passport::versions::seal_adaptation(&hidden["adaptations"][0])?;
    hidden["stable_id"] = format!("component_{}", ulid::Ulid::generate()).into();
    let hidden = store.transaction(|t| {
        revisions::commit(
            t,
            &hidden,
            &identity().device_id,
            None,
            revisions::Write::Advance {
                expected_heads: &[],
            },
        )?;
        versions::record(t, &hidden, &identity().device_id, None, AT)
    })?;
    let (catalog_setup, catalog_evidence) = compose(store, harness, &[hidden])?;
    let refusal = bundle::compile(
        store,
        &catalog_setup,
        &target,
        &catalog_evidence,
        &provider,
        &Hosts::new(),
    )
    .err()
    .ok_or("undeclared skill accepted")?;
    assert_eq!(
        refusal.details.get("constraint"),
        Some(&json!("native_visibility_mismatch")),
        "{refusal:?}"
    );
    Ok(())
}

fn pi_namespaces(store: &mut Store, declarations: &[Value]) -> Result<(), Box<dyn Error>> {
    let declaration = declarations
        .iter()
        .find(|value| value["harness_id"] == "pi")
        .ok_or("Pi missing")?;
    let provider = Info::parse(&serde_json::to_vec(declaration)?)?;
    let target = target("pi", Scope::Global);
    let skill = component(
        store,
        &provider,
        Scope::Global,
        File {
            path: "skills/review/SKILL.md".into(),
            bytes: b"---\ndescription: Review source.\n---\nReview.\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let prompt = component(
        store,
        &provider,
        Scope::Global,
        File {
            path: "prompts/review.md".into(),
            bytes: b"---\nname: ignored\n---\nReview.\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let (setup, evidence) = compose(store, "pi", &[skill.clone(), prompt])?;
    let built = bundle::compile(store, &setup, &target, &evidence, &provider, &Hosts::new())?;
    export("pi-entries", &built)?;
    rejects_fabricated_ids(store, &skill, &built, &target, &provider, &Hosts::new())?;
    // Separate, individually valid components must not hide one another.
    for (path, body) in [
        (
            "skills/SKILL.md",
            "---\ndescription: A skill at the scan root.\n---\nRoot.\n",
        ),
        ("skills/.ignore", "review/\n"),
    ] {
        let masking = component(
            store,
            &provider,
            Scope::Global,
            File {
                path: path.into(),
                bytes: body.as_bytes().to_vec(),
                mode: 0o644,
            },
            None,
        )?;
        let (setup, evidence) = compose(store, "pi", &[skill.clone(), masking])?;
        let refusal = bundle::compile(store, &setup, &target, &evidence, &provider, &Hosts::new())
            .err()
            .ok_or("Pi component was hidden by another component")?;
        assert_eq!(refusal.details["constraint"], "native_visibility_mismatch");
    }
    Ok(())
}

fn opencode_namespaces(store: &mut Store, declarations: &[Value]) -> Result<(), Box<dyn Error>> {
    let declaration = declarations
        .iter()
        .find(|value| value["harness_id"] == "opencode")
        .ok_or("OpenCode missing")?;
    let provider = Info::parse(&serde_json::to_vec(declaration)?)?;
    let target = target("opencode", Scope::Global);
    let mut members = Vec::new();
    for (path, body, contribution) in [
        (
            "skills/inspect/SKILL.md",
            "---\nname: inspect\n---\nInspect source.\n",
            None,
        ),
        ("commands/review.md", "Review source.\n", None),
        (
            "agents/review.md",
            "---\nmode: subagent\n---\nReview source.\n",
            None,
        ),
        (
            "opencode.json",
            r#"{"review":{"type":"local","command":["review-tool"]}}"#,
            Some("mcp"),
        ),
    ] {
        members.push(component(
            store,
            &provider,
            Scope::Global,
            File {
                path: path.into(),
                bytes: body.as_bytes().to_vec(),
                mode: 0o644,
            },
            contribution,
        )?);
    }
    let hosts: Hosts = [(
        "opencode.json".into(),
        Some(br#"{"autoupdate":false}"#.to_vec()),
    )]
    .into();
    let (setup, evidence) = compose(store, "opencode", &members)?;
    let built = bundle::compile(store, &setup, &target, &evidence, &provider, &hosts)?;
    export("opencode-entries", &built)?;
    rejects_fabricated_ids(
        store,
        &members[0],
        &built,
        &target,
        &provider,
        &Hosts::new(),
    )?;
    // Skill invocations participate in explicit command exclusions too.
    for declarer in [1, 0] {
        let mut document = members[declarer].clone();
        document["version"] = "3.0".into();
        document["conflicts"]["commands"] = json!(["inspect"]);
        let document = store
            .transaction(|t| versions::record(t, &document, &identity().device_id, None, AT))?;
        let mut selected = members.clone();
        selected[declarer] = document;
        let (setup, evidence) = compose(store, "opencode", &selected)?;
        let result = bundle::compile(store, &setup, &target, &evidence, &provider, &hosts);
        if declarer == 0 {
            result?;
        } else {
            assert_eq!(
                result.err().ok_or("command exclusion ignored")?.details["constraint"],
                "declared_conflict"
            );
        }
    }
    let shadowing = component(
        store,
        &provider,
        Scope::Global,
        File {
            path: "commands/inspect.md".into(),
            bytes: b"Inspect source.\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let (setup, evidence) = compose(store, "opencode", &[members[0].clone(), shadowing])?;
    assert!(
        bundle::compile(store, &setup, &target, &evidence, &provider, &Hosts::new())
            .err()
            .ok_or("OpenCode command shadowed skill")?
            .message
            .contains("native_id_collision")
    );
    let duplicate = component(
        store,
        &provider,
        Scope::Global,
        File {
            path: "agents/duplicate.md".into(),
            bytes: b"---\nname: review\nmode: subagent\n---\nReview source.\n".to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    members.push(duplicate);
    let (setup, evidence) = compose(store, "opencode", &members)?;
    let refused = bundle::compile(store, &setup, &target, &evidence, &provider, &hosts)
        .err()
        .ok_or("duplicate OpenCode agent accepted")?;
    assert!(refused.message.contains("native_id_collision"));
    Ok(())
}

#[test]
fn exact_bundles_cover_every_released_profile_and_refuse_unrepresentable_inputs()
-> Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let mut store = Store::open(root.path(), true)?;
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    opencode_namespaces(&mut store, &declarations)?;
    pi_namespaces(&mut store, &declarations)?;
    for harness in ["codex", "cursor"] {
        skill_inventory(&mut store, &declarations, harness)?;
    }
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
                    bytes: if skill.is_some() {
                        b"---\nname: review\ndescription: Inspect project conventions.\n---\n# Review\nInspect project conventions.\n".to_vec()
                    } else {
                        b"# Review\nInspect project conventions.\n".to_vec()
                    },
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
    rejects_fabricated_ids(&mut store, &mcp, &built, &target, &provider, &hosts)?;
    // A digest-valid catalog entry must not bypass the source credential guard.
    let reference_mcp = component(
        &mut store,
        &provider,
        Scope::Global,
        File {
            path: "settings.json".into(),
            bytes: br#"{"review":{"command":"review-tool","env":{"API_KEY":"${REVIEW_TOKEN}"}}}"#
                .to_vec(),
            mode: 0o644,
        },
        Some("mcpServers"),
    )?;
    let (reference_setup, reference_evidence) =
        compose(&mut store, "claude-code", &[reference_mcp])?;
    let reference_bundle = bundle::compile(
        &mut store,
        &reference_setup,
        &target,
        &reference_evidence,
        &provider,
        &hosts,
    )?;
    export("claude-code-references", &reference_bundle)?;
    let literal_mcp = component(
        &mut store, &provider, Scope::Global,
        File {
            path: "settings.json".into(),
            bytes: br#"{"review":{"command":"review-tool","env":{"API_KEY":"synthetic-sensitive-value"}}}"#.to_vec(),
            mode: 0o644,
        }, Some("mcpServers"),
    )?;
    assert!(
        compose(
            &mut store,
            "claude-code",
            std::slice::from_ref(&literal_mcp)
        )
        .is_err()
    );
    let (catalog_setup, catalog_evidence) =
        catalog_repin(&mut store, &reference_bundle, &literal_mcp)?;
    let refusal = bundle::compile(
        &mut store,
        &catalog_setup,
        &target,
        &catalog_evidence,
        &provider,
        &hosts,
    )
    .err()
    .ok_or("catalog literal credential accepted")?;
    assert_eq!(refusal.details["constraint"], "literal_credential");
    assert!(!refusal.message.contains("synthetic-sensitive-value"));
    let agent = component(
        &mut store,
        &provider,
        Scope::Global,
        File {
            path: "agents/auditor.md".into(),
            bytes: b"---\nname: review\ndescription: Review project conventions.\n---\n# Review\n"
                .to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    let (agent_setup, agent_evidence) =
        compose(&mut store, "claude-code", std::slice::from_ref(&agent))?;
    let agent_bundle = bundle::compile(
        &mut store,
        &agent_setup,
        &target,
        &agent_evidence,
        &provider,
        &Hosts::new(),
    )?;
    export("claude-code-agent", &agent_bundle)?;
    rejects_fabricated_ids(
        &mut store,
        &agent,
        &agent_bundle,
        &target,
        &provider,
        &Hosts::new(),
    )?;
    let (separate, separate_evidence) = compose(&mut store, "claude-code", &[mcp.clone(), agent])?;
    let separate_bundle = bundle::compile(
        &mut store,
        &separate,
        &target,
        &separate_evidence,
        &provider,
        &hosts,
    )?;
    export("claude-code-separate-names", &separate_bundle)?;
    let aliased = component(
        &mut store,
        &provider,
        Scope::Global,
        File {
            path: "skills/directory/SKILL.md".into(),
            bytes: b"---\nname: review\ndescription: Review source.\n---\nReview source.\n"
                .to_vec(),
            mode: 0o644,
        },
        None,
    )?;
    // The catalog fixture's directory-only declaration cannot omit its explicit alias.
    assert!(compose(&mut store, "claude-code", std::slice::from_ref(&aliased)).is_err());
    let mut aliased = aliased;
    aliased["version"] = "1.1".into();
    aliased["adaptations"][0]["scope_adaptations"][0]["members"][0]["native_ids"] =
        json!(["directory", "review"]);
    aliased["adaptations"][0] = passport::versions::seal_adaptation(&aliased["adaptations"][0])?;
    let aliased =
        store.transaction(|t| versions::record(t, &aliased, &identity().device_id, None, AT))?;
    for name in ["review", "directory", "team:review"] {
        let command = component(
            &mut store,
            &provider,
            Scope::Global,
            File {
                path: format!("commands/{}.md", name.replace(':', "/")),
                bytes: b"---\nname: ignored\n---\nReview source.\n".to_vec(),
                mode: 0o644,
            },
            None,
        )?;
        let (mixed, mixed_evidence) =
            compose(&mut store, "claude-code", &[aliased.clone(), command])?;
        let result = bundle::compile(
            &mut store,
            &mixed,
            &target,
            &mixed_evidence,
            &provider,
            &Hosts::new(),
        );
        if name == "team:review" {
            export("claude-code-invocations", &result?)?;
        } else {
            assert!(
                result
                    .err()
                    .ok_or("skill alias command collision accepted")?
                    .message
                    .contains("native_id_collision")
            );
        }
    }
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
    for scenario in ["paths", "commands", "skill-invocations"] {
        let family = if scenario == "skill-invocations" {
            "commands"
        } else {
            scenario
        };
        let mut originals = Vec::new();
        for name in ["left", "right"] {
            let path = if scenario != "commands" {
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
                if scenario == "commands" {
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
