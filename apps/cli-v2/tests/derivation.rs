use std::{error::Error, fs, path::Path};

use ai_stp_cli_v2::{
    authoring::{
        Identity, adoption, derivation, discovery, forks,
        passports::{self, Patch},
        releases, setups,
    },
    canonical, digest,
    error::Failure,
    harnesses::{Root, Scope},
    projection::artifact,
    provider::Info,
    store::{Store, revisions, versions::Increment},
};
use serde_json::{Value, json};

#[path = "derivation/materialization.rs"]
mod materialization;
#[path = "derivation/skills.rs"]
mod skills;

const AT: &str = "2026-10-08T00:00:00.000Z";
const LATER: &str = "2026-10-09T00:00:00.000Z";

fn field<'a>(value: &'a Value, key: &str) -> Result<&'a str, Box<dyn Error>> {
    value[key]
        .as_str()
        .ok_or_else(|| format!("missing {key}").into())
}

fn stored(store: &mut Store, id: &str, version: Option<&str>) -> Result<Value, Failure> {
    store.transaction(|t| {
        let sql = if version.is_some() { "SELECT r.content FROM revision r JOIN object_version v ON v.revision_id=r.revision_id WHERE v.stable_id=?1 AND v.version=?2" } else { "SELECT r.content FROM revision r JOIN head h ON h.revision_id=r.revision_id WHERE h.stable_id=?1 AND ?2 IS NULL" };
        let content: String = t.query_row(sql,rusqlite::params![id,version],|r|r.get(0)).map_err(|_|Failure::input("proof read failed"))?;
        canonical::parse(content.as_bytes())
    })
}

fn counts(store: &mut Store) -> Result<[i64; 6], Failure> {
    store.transaction(|t| t.query_row("SELECT (SELECT count(*) FROM revision),(SELECT count(*) FROM content),(SELECT count(*) FROM operation),(SELECT count(*) FROM object_version),(SELECT count(*) FROM fork_origin),(SELECT count(*) FROM overlay_origin)",[],|r| Ok([r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?])).map_err(|_|Failure::input("proof query failed")))
}

fn release(
    store: &mut Store,
    root: &Path,
    harness: &str,
    config: &[u8],
    providers: &[Info],
    identity: &Identity,
) -> Result<Value, Box<dyn Error>> {
    fs::create_dir_all(root)?;
    let path = match harness {
        "codex" => "config.toml",
        "cursor" => "mcp.json",
        _ => "opencode.json",
    };
    fs::write(root.join(path), config)?;
    let candidate = discovery::at(root, harness, Scope::Global, Root::Config)?
        .components
        .into_iter()
        .find(|c| c.component_type == "mcp")
        .ok_or("missing MCP")?;
    let plan = adoption::plan(
        store,
        adoption::Source {
            root: root.into(),
            harness_id: harness.into(),
            scope: Scope::Global,
            root_kind: Root::Config,
            candidate_id: candidate.candidate_id,
        },
        identity.clone(),
        AT,
    )?;
    let draft = adoption::apply(store, &plan, &plan.digest()?, identity, AT)?;
    let update = passports::plan(
        store,
        field(&draft, "stable_id")?,
        field(&draft, "revision_id")?,
        Patch::try_from(
            json!({"name":"stdio-proof","description":"Run the explicit review server.","tags":["review"],"license":{"spdx_id":"MIT","redistribution_allowed":true},"permissions":{"filesystem":["read"],"network":[],"process":["spawn"]},"supported_os":["linux"],"supported_arch":["x86_64"]}),
        )?,
        identity.clone(),
        AT,
    )?;
    let draft = passports::apply(store, &update, &update.digest()?, identity, AT)?;
    let plan = releases::plan(
        store,
        field(&draft, "stable_id")?,
        field(&draft, "revision_id")?,
        Increment::Minor,
        providers,
        identity.clone(),
        AT,
    )?;
    let released = releases::apply(store, &plan, &plan.digest()?, identity, AT)?;
    let fork = forks::plan(
        store,
        forks::Source {
            stable_id: field(&released, "stable_id")?.into(),
            version: field(&released, "version")?.into(),
            passport_digest: digest::canonical("ai-stp:passport:v1", &released)?,
        },
        identity.clone(),
        AT,
    )?;
    let draft = forks::apply(store, &fork, &fork.digest()?, identity, AT)?;
    let frozen = releases::plan(
        store,
        field(&draft, "stable_id")?,
        field(&draft, "revision_id")?,
        Increment::Minor,
        &[],
        identity.clone(),
        AT,
    )?;
    releases::apply(store, &frozen, &frozen.digest()?, identity, AT)?;
    Ok(draft)
}

fn graph_recast(
    store: &mut Store,
    root: &Path,
    source: &Value,
    providers: &[Info],
    identity: &Identity,
    recipient: &Identity,
) -> Result<(), Box<dyn Error>> {
    let provider = providers
        .iter()
        .find(|p| p.document()["harness_id"] == "cursor")
        .ok_or("provider")?;
    let member = |document: &Value| -> Result<setups::Member, Box<dyn Error>> {
        Ok(setups::Member {
            stable_id: field(document, "stable_id")?.into(),
            version: field(document, "version")?.into(),
            passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
        })
    };
    let dependent = release(
        store,
        &root.join("graph-dependent"),
        "codex",
        b"[mcp_servers.audit]\ncommand = 'audit-server'\n",
        providers,
        identity,
    )?;
    let patch = passports::plan(
        store,
        field(&dependent, "stable_id")?,
        field(&dependent, "revision_id")?,
        Patch::try_from(json!({"requires_components":[member(source)?]}))?,
        identity.clone(),
        AT,
    )?;
    let dependent = passports::apply(store, &patch, &patch.digest()?, identity, AT)?;
    let derived = derivation::plan(
        store,
        field(&dependent, "stable_id")?,
        field(&dependent, "revision_id")?,
        "codex",
        provider,
        identity.clone(),
        AT,
    )?;
    let dependent = derivation::apply(store, &derived, &derived.digest()?, identity, AT)?;
    let release = releases::plan(
        store,
        field(&dependent, "stable_id")?,
        field(&dependent, "revision_id")?,
        Increment::Minor,
        &[],
        identity.clone(),
        AT,
    )?;
    let dependent = releases::apply(store, &release, &release.digest()?, identity, AT)?;
    let compose = setups::plan(
        store,
        setups::Request {
            harness_id: "codex".into(),
            name: "Exact dependency recast".into(),
            description: "Derive one member and retain the dependent's existing adaptation.".into(),
            purpose: "Review code.".into(),
            members: vec![member(&dependent)?],
            requirements: None,
        },
        identity.clone(),
        AT,
    )?;
    let original = setups::apply(store, &compose, &compose.digest()?, identity, AT)?;
    let reference = setups::Source {
        stable_id: field(&original, "stable_id")?.into(),
        version: field(&original, "version")?.into(),
        passport_digest: digest::canonical("ai-stp:passport:v1", &original)?,
    };
    let before = counts(store)?;
    assert!(
        setups::copies::plan(
            store,
            reference.clone(),
            Some("cursor"),
            recipient.clone(),
            AT
        )
        .is_err()
    );
    let plan =
        setups::copies::plan_with_provider(store, reference, provider, recipient.clone(), AT)?;
    assert_eq!(counts(store)?, before);
    let replacements = &plan.derivation.as_ref().ok_or("derived members")?.members;
    assert_eq!(replacements.len(), 2);
    let child = replacements
        .iter()
        .find(|m| m.source.stable_id == source["stable_id"])
        .ok_or("child")?;
    let parent = replacements
        .iter()
        .find(|m| m.source.stable_id == dependent["stable_id"])
        .ok_or("parent")?;
    for replacement in replacements {
        assert_ne!(
            replacement.passport["stable_id"],
            replacement.source.stable_id
        );
        assert_eq!(replacement.passport["owner_id"], recipient.account_id);
        assert_eq!(replacement.passport["version"], "1.0");
        assert_eq!(replacement.passport["visibility"], "private");
    }
    assert_eq!(
        parent.passport["requires_components"][0]["stable_id"],
        child.passport["stable_id"]
    );
    assert_eq!(
        parent.passport["requires_components"][0]["passport_digest"],
        digest::canonical("ai-stp:passport:v1", &child.passport)?
    );
    assert_eq!(parent.passport["adaptations"], dependent["adaptations"]);
    let mut tampered = plan.clone();
    tampered
        .derivation
        .as_mut()
        .ok_or("derived members")?
        .members[0]
        .passport["description"] = "Changed after planning".into();
    assert!(setups::copies::apply(store, &tampered, &tampered.digest()?, recipient, AT).is_err());
    store.transaction(|t| t.execute_batch("CREATE TEMP TRIGGER refuse_recast_setup BEFORE INSERT ON object_version WHEN NEW.stable_id LIKE 'setup_%' BEGIN SELECT RAISE(ABORT,'interrupted after components'); END;").map_err(|_|Failure::input("proof trigger failed")))?;
    assert!(setups::copies::apply(store, &plan, &plan.digest()?, recipient, AT).is_err());
    assert_eq!(counts(store)?, before);
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER refuse_recast_setup")
            .map_err(|_| Failure::input("proof trigger failed"))
    })?;
    let result = setups::copies::apply(store, &plan, &plan.digest()?, recipient, AT)?;
    assert_eq!(result, plan.passport);
    assert_eq!(
        stored(
            store,
            field(source, "stable_id")?,
            Some(field(source, "version")?)
        )?,
        *source
    );
    assert_eq!(
        stored(
            store,
            field(&dependent, "stable_id")?,
            Some(field(&dependent, "version")?)
        )?,
        dependent
    );
    let after = counts(store)?;
    assert_eq!(
        setups::copies::apply(store, &plan, &plan.digest()?, recipient, LATER)?,
        result
    );
    assert_eq!(counts(store)?, after);
    for replacement in replacements {
        assert_eq!(
            stored(
                store,
                field(&replacement.passport, "stable_id")?,
                Some("1.0")
            )?,
            replacement.passport
        );
    }
    Ok(())
}

#[test]
fn exact_native_derivation_preserves_literals_and_atomic_owned_history()
-> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let mut store = Store::open(temporary.path(), true)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let mut foreign = identity.clone();
    foreign.account_id = "account_01ARZ3NDEKTSV4RRFFQ69G5FAW".into();
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let providers = declarations
        .iter()
        .map(|v| {
            Info::parse(&serde_json::to_vec(v).map_err(|_| Failure::input("proof JSON failed"))?)
        })
        .collect::<Result<Vec<_>, _>>()?;
    materialization::journey(
        &mut store,
        temporary.path(),
        &providers,
        &identity,
        &foreign,
    )?;
    skills::journey(&mut store, temporary.path(), &providers, &identity)?;
    let config = "[mcp_servers.docs]\ncommand = 'review-server'\nargs = ['cafe\u{301}', '\"quoted\"', 'C:\\work\\a']\n[mcp_servers.docs.env]\nMODE = 'cafe\u{301}'\n";
    let configs = [
        ("codex", config.as_bytes().to_vec()),
        (
            "cursor",
            serde_json::to_vec(
                &json!({"mcpServers":{"docs":{"type":"stdio","command":"review-server","args":["cafe\u{301}","\"quoted\"","C:\\work\\a"],"env":{"MODE":"cafe\u{301}"}}}}),
            )?,
        ),
        (
            "opencode",
            serde_json::to_vec(
                &json!({"mcp":{"docs":{"type":"local","command":["review-server","cafe\u{301}","\"quoted\"","C:\\work\\a"],"environment":{"MODE":"cafe\u{301}"}}}}),
            )?,
        ),
    ];
    for (source, config) in &configs {
        for target in ["codex", "cursor", "opencode"]
            .into_iter()
            .filter(|t| t != source)
        {
            let root = temporary.path().join(format!("{source}-{target}"));
            let before = release(&mut store, &root, source, config, &providers, &identity)?;
            let id = field(&before, "stable_id")?;
            let expected = field(&before, "revision_id")?;
            let retained = stored(&mut store, id, Some("1.0"))?;
            if *source == "codex" && target == "cursor" {
                graph_recast(
                    &mut store,
                    temporary.path(),
                    &retained,
                    &providers,
                    &identity,
                    &foreign,
                )?;
            }
            let provider = providers
                .iter()
                .find(|p| p.document()["harness_id"] == target)
                .ok_or("missing provider")?;
            let original_counts = counts(&mut store)?;
            assert!(
                derivation::plan(
                    &mut store,
                    id,
                    expected,
                    source,
                    provider,
                    foreign.clone(),
                    AT
                )
                .is_err()
            );
            let plan = derivation::plan(
                &mut store,
                id,
                expected,
                source,
                provider,
                identity.clone(),
                AT,
            )?;
            assert_eq!(counts(&mut store)?, original_counts);
            let digest = plan.digest()?;
            assert!(derivation::apply(&mut store, &plan, "wrong-digest", &identity, AT).is_err());
            assert!(derivation::apply(&mut store, &plan, &digest, &foreign, AT).is_err());
            assert!(derivation::apply(&mut store, &plan, &digest, &identity, LATER).is_err());
            let mut forged = plan.clone();
            forged.passport["description"] = "substituted".into();
            assert!(
                derivation::apply(&mut store, &forged, &forged.digest()?, &identity, AT).is_err()
            );
            store.transaction(|t|t.execute_batch("CREATE TEMP TRIGGER reject_derivation BEFORE INSERT ON operation BEGIN SELECT RAISE(ABORT,'proof failure'); END;").map_err(|_|Failure::input("proof trigger failed")))?;
            assert!(derivation::apply(&mut store, &plan, &digest, &identity, AT).is_err());
            assert_eq!(counts(&mut store)?, original_counts);
            store.transaction(|t| {
                t.execute_batch("DROP TRIGGER reject_derivation;")
                    .map_err(|_| Failure::input("proof trigger failed"))
            })?;
            let derived = derivation::apply(&mut store, &plan, &digest, &identity, AT)?;
            let new = derived["adaptations"]
                .as_array()
                .ok_or("adaptations")?
                .iter()
                .find(|a| a["harness_id"] == target)
                .ok_or("target")?;
            let old = derived["adaptations"]
                .as_array()
                .ok_or("adaptations")?
                .iter()
                .find(|a| a["harness_id"] == *source)
                .ok_or("source")?;
            assert_eq!(old, &before["adaptations"][0]);
            assert_eq!(derived["facts"], before["facts"]);
            assert_eq!(new["implementation_mode"], "derived");
            let scope = &new["scope_adaptations"][0];
            for key in ["permissions", "supported_os", "supported_arch"] {
                assert_eq!(scope[key], old["scope_adaptations"][0][key]);
            }
            assert_eq!(scope["technical_support"], "experimental");
            let bytes = store.transaction(|t| {
                revisions::read_content(
                    t,
                    scope["projection_artifact"]["digest"]
                        .as_str()
                        .ok_or_else(|| Failure::input("proof digest"))?,
                )
            })?;
            let files = artifact::verify(scope, &bytes)?;
            let (command, args, env) = if target == "codex" {
                let document: toml_edit::DocumentMut =
                    std::str::from_utf8(&files[0].bytes)?.parse()?;
                (
                    document["docs"]["command"]
                        .as_str()
                        .ok_or("command")?
                        .to_owned(),
                    document["docs"]["args"]
                        .as_array()
                        .ok_or("args")?
                        .iter()
                        .map(|v| v.as_str().ok_or("arg").map(String::from))
                        .collect::<Result<Vec<_>, _>>()?,
                    document["docs"]["env"]["MODE"]
                        .as_str()
                        .ok_or("env")?
                        .to_owned(),
                )
            } else {
                let document: Value = serde_json::from_slice(&files[0].bytes)?;
                let server = if target == "cursor" {
                    &document["mcpServers"]["docs"]
                } else {
                    &document["docs"]
                };
                if target == "cursor" {
                    (
                        field(server, "command")?.into(),
                        server["args"]
                            .as_array()
                            .ok_or("args")?
                            .iter()
                            .map(|v| v.as_str().ok_or("arg").map(String::from))
                            .collect::<Result<Vec<_>, _>>()?,
                        field(&server["env"], "MODE")?.into(),
                    )
                } else {
                    let parts = server["command"].as_array().ok_or("command")?;
                    (
                        parts[0].as_str().ok_or("command")?.into(),
                        parts[1..]
                            .iter()
                            .map(|v| v.as_str().ok_or("arg").map(String::from))
                            .collect::<Result<Vec<_>, _>>()?,
                        field(&server["environment"], "MODE")?.into(),
                    )
                }
            };
            assert_eq!(command, "review-server");
            assert_eq!(args, ["cafe\u{301}", "\"quoted\"", "C:\\work\\a"]);
            assert_eq!(env, "cafe\u{301}");
            assert!(
                derivation::plan(
                    &mut store,
                    id,
                    field(&derived, "revision_id")?,
                    source,
                    provider,
                    identity.clone(),
                    AT
                )
                .is_err()
            );
            let mut stale = plan.clone();
            stale.operation_id = format!("operation_{}", ulid::Ulid::generate());
            assert!(
                derivation::apply(&mut store, &stale, &stale.digest()?, &identity, AT).is_err()
            );
            let edit = passports::plan(
                &mut store,
                id,
                field(&derived, "revision_id")?,
                Patch::try_from(
                    json!({"description":"New metadata must survive old plan replay."}),
                )?,
                identity.clone(),
                AT,
            )?;
            let edited = passports::apply(&mut store, &edit, &edit.digest()?, &identity, AT)?;
            let next = releases::plan(
                &mut store,
                id,
                field(&edited, "revision_id")?,
                Increment::Minor,
                &[],
                identity.clone(),
                AT,
            )?;
            let next = releases::apply(&mut store, &next, &next.digest()?, &identity, AT)?;
            assert_eq!(next["version"], "1.1");
            assert_eq!(stored(&mut store, id, Some("1.0"))?, retained);
            fs::remove_dir_all(root)?;
            assert_eq!(
                derivation::apply(&mut store, &plan, &digest, &identity, LATER)?,
                derived
            );
            assert_eq!(stored(&mut store, id, None)?, edited);
            if *source == "codex" && target == "cursor" {
                let address = field(&new["source_artifact"], "digest")?;
                store.transaction(|t| {
                    t.execute(
                        "UPDATE content SET byte_length=byte_length+1 WHERE digest=?",
                        [address],
                    )
                    .map(|_| ())
                    .map_err(|_| Failure::input("proof tamper"))
                })?;
                assert!(derivation::apply(&mut store, &plan, &digest, &identity, LATER).is_err());
                store.transaction(|t| {
                    t.execute(
                        "UPDATE content SET byte_length=byte_length-1 WHERE digest=?",
                        [address],
                    )
                    .map(|_| ())
                    .map_err(|_| Failure::input("proof restore"))
                })?;
            }
        }
    }
    // Valid source syntax may contain controls this conversion cannot represent.
    for (index, extra) in [
        "enabled = false",
        "disabled_tools = ['delete']",
        "cwd = '/workspace'",
        "tool_timeout_sec = 60",
        "url = 'https://example.invalid/mcp'",
        "args = [1]",
        "env = { MODE = '${MODE}' }",
        "environment = { MODE = 'read' }",
        "command = ['server']",
    ]
    .iter()
    .enumerate()
    {
        let config = if extra.starts_with("command") {
            format!("[mcp_servers.docs]\n{extra}\n")
        } else {
            format!("[mcp_servers.docs]\ncommand = 'server'\n{extra}\n")
        };
        let before = release(
            &mut store,
            &temporary.path().join(format!("refusal-{index}")),
            "codex",
            config.as_bytes(),
            &providers,
            &identity,
        )?;
        let count = counts(&mut store)?;
        let target = providers
            .iter()
            .find(|p| p.document()["harness_id"] == "opencode")
            .ok_or("provider")?;
        let refused = derivation::plan(
            &mut store,
            field(&before, "stable_id")?,
            field(&before, "revision_id")?,
            "codex",
            target,
            identity.clone(),
            AT,
        )
        .err()
        .ok_or_else(|| format!("accepted {extra}"))?;
        assert_eq!(
            refused.details["constraint"],
            "native_derivation_unsupported"
        );
        assert_eq!(counts(&mut store)?, count);
    }
    for (key, value) in [
        ("supported_harness_versions", json!([">=1.0"])),
        ("technical_support", json!("unsupported")),
        ("semantic_losses", json!(["manual routing"])),
    ] {
        let original = release(
            &mut store,
            &temporary.path().join(key),
            "codex",
            &configs[0].1,
            &providers,
            &identity,
        )?;
        let mut restricted = original.clone();
        restricted["adaptations"][0]["scope_adaptations"][0][key] = value;
        restricted["adaptations"][0] =
            ai_stp_cli_v2::passport::versions::seal_adaptation(&restricted["adaptations"][0])?;
        restricted["parent_revision_ids"] = json!([original["revision_id"]]);
        let restricted = store.transaction(|t| {
            revisions::commit(
                t,
                &restricted,
                &identity.device_id,
                None,
                revisions::Write::Advance {
                    expected_heads: &[original["revision_id"]
                        .as_str()
                        .ok_or_else(|| Failure::input("proof revision"))?
                        .into()],
                },
            )
        })?;
        let count = counts(&mut store)?;
        let provider = providers
            .iter()
            .find(|p| p.document()["harness_id"] == "opencode")
            .ok_or("provider")?;
        let refused = derivation::plan(
            &mut store,
            field(&restricted, "stable_id")?,
            field(&restricted, "revision_id")?,
            "codex",
            provider,
            identity.clone(),
            AT,
        )
        .err()
        .ok_or("accepted restricted source")?;
        assert_eq!(
            refused.details["constraint"],
            "native_derivation_unsupported"
        );
        assert_eq!(counts(&mut store)?, count);
    }
    if let Some(path) = std::env::var_os("AI_STP_DERIVATION_PROOF_FILE") {
        let dump = store.transaction(|t| {
            let mut q = t
                .prepare("SELECT r.content FROM revision r JOIN object_version v ON v.revision_id=r.revision_id")
                .map_err(|_| Failure::input("proof query"))?;
            let rows = q
                .query_map([], |r| r.get::<_, String>(0))
                .map_err(|_| Failure::input("proof query"))?;
            let mut out = Vec::new();
            for row in rows {
                out.push(canonical::parse(
                    row.map_err(|_| Failure::input("proof row"))?.as_bytes(),
                )?);
            }
            Ok(out)
        })?;
        fs::write(path, serde_json::to_vec(&dump)?)?;
    }
    Ok(())
}
