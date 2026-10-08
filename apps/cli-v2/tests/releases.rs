use std::{error::Error, fs, path::Path};

use ai_stp_cli_v2::{
    authoring::{
        Identity, adoption, discovery, forks,
        passports::{self, Patch},
        releases,
    },
    canonical, digest,
    error::Failure,
    harnesses::{Root, Scope},
    projection::artifact,
    store::{
        Store,
        revisions::{self, Write},
        versions::{self, Increment},
    },
};
use serde_json::{Value, json};

const AT: &str = "2026-10-08T00:00:00.000Z";
const LATER: &str = "2026-10-08T00:00:01.000Z";

fn field<'a>(document: &'a Value, key: &str) -> Result<&'a str, Box<dyn Error>> {
    document[key]
        .as_str()
        .ok_or_else(|| format!("missing {key}").into())
}

fn counts(store: &mut Store) -> Result<(i64, i64, i64, i64), Failure> {
    store.transaction(|t| t.query_row("SELECT (SELECT count(*) FROM revision), (SELECT count(*) FROM content), (SELECT count(*) FROM operation), (SELECT count(*) FROM object_version)",[],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?)))
        .map_err(|_| Failure::precondition("proof query failed")))
}

fn adopt(
    store: &mut Store,
    root: &Path,
    harness: &str,
    kind: &str,
    identity: &Identity,
) -> Result<Value, Box<dyn Error>> {
    let report = discovery::at(
        root,
        harness,
        Scope::Global,
        if harness == "undefined" {
            Root::Home
        } else {
            Root::Config
        },
    )?;
    assert!(report.complete);
    let candidate = report
        .components
        .into_iter()
        .find(|item| item.component_type == kind)
        .ok_or("candidate missing")?;
    let source = adoption::Source {
        root: root.into(),
        harness_id: harness.into(),
        scope: Scope::Global,
        root_kind: if harness == "undefined" {
            Root::Home
        } else {
            Root::Config
        },
        candidate_id: candidate.candidate_id,
    };
    let plan = adoption::plan(store, source, identity.clone(), AT)?;
    Ok(adoption::apply(
        store,
        &plan,
        &plan.digest()?,
        identity,
        AT,
    )?)
}

#[test]
fn native_release_preserves_owned_bytes_graphs_and_atomic_history() -> Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let mut store = Store::open(temporary.path(), true)?;
    let identity = Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    };
    let declarations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/provider-declarations.json"))?;
    let providers = declarations
        .iter()
        .map(|value| {
            Ok(ai_stp_cli_v2::provider::Info::parse(&serde_json::to_vec(
                value,
            )?)?)
        })
        .collect::<Result<Vec<_>, Box<dyn Error>>>()?;
    let cases = [
        ("claude-code","hook","settings.json",br#"{"model":"unowned","hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"example"}]}]}}"#.as_slice(),"json/1"),
        ("codex","mcp","config.toml",b"model = 'unowned'\n[mcp_servers.example]\ncommand = 'example'\n".as_slice(),"toml/1"),
        ("cursor","hook","hooks.json",br#"{"version":1,"hooks":{}}"#.as_slice(),""),
        ("undefined","skill",".agents/skills/example/SKILL.md",b"# Example\n".as_slice(),""),
    ];
    let mut released = Vec::new();
    let mut first_plan = None;
    for (index, (harness, kind, path, bytes, parser)) in cases.into_iter().enumerate() {
        let root = temporary.path().join(format!("source-{index}"));
        let path = root.join(path);
        fs::create_dir_all(path.parent().ok_or("parent missing")?)?;
        fs::write(&path, bytes)?;
        if harness == "cursor" {
            fs::create_dir(root.join("hooks"))?;
            fs::write(root.join("hooks/helper.sh"), b"#!/bin/sh\nprintf example\n")?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(
                    root.join("hooks/helper.sh"),
                    fs::Permissions::from_mode(0o755),
                )?;
            }
        }
        let draft = adopt(&mut store, &root, harness, kind, &identity)?;
        let id = field(&draft, "stable_id")?;
        assert!(
            releases::plan(
                &mut store,
                id,
                field(&draft, "revision_id")?,
                Increment::Minor,
                &providers,
                identity.clone(),
                AT
            )
            .is_err()
        );
        let mut facts = json!({"name":"Example","description":"Run the example safely.","tags":["development"],
            "license":{"spdx_id":"MIT","redistribution_allowed":true}});
        if harness == "undefined" {
            facts["harness_id"] = "codex".into();
        }
        let edit = passports::plan(
            &mut store,
            id,
            field(&draft, "revision_id")?,
            Patch::try_from(facts)?,
            identity.clone(),
            AT,
        )?;
        let mut draft = passports::apply(&mut store, &edit, &edit.digest()?, &identity, AT)?;
        if harness == "claude-code" {
            // A finished passport description cannot turn an unedited source stub into a release.
            fs::write(
                &path,
                br#"{"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"TODO(ai-stp-scaffold): implement the handler"}]}]}}"#,
            )?;
            let unfinished = adopt(&mut store, &root, harness, kind, &identity)?;
            let before = counts(&mut store)?;
            let refusal = releases::plan(
                &mut store,
                field(&unfinished, "stable_id")?,
                field(&unfinished, "revision_id")?,
                Increment::Minor,
                &providers,
                identity.clone(),
                AT,
            )
            .err()
            .ok_or("unfinished source released")?;
            assert_eq!(refusal.details["constraint"], "scaffold_marker");
            assert_eq!(refusal.details["path"], "settings.json");
            assert_eq!(counts(&mut store)?, before);
            fs::write(&path, bytes)?;
            draft = adopt(&mut store, &root, harness, kind, &identity)?;
        }
        if harness == "cursor" {
            // The released provider owns hooks.json but not the hooks/ sibling.
            // Capture keeps helper bytes; release must refuse, never drop them.
            assert!(
                releases::plan(
                    &mut store,
                    field(&draft, "stable_id")?,
                    field(&draft, "revision_id")?,
                    Increment::Minor,
                    &providers,
                    identity.clone(),
                    AT
                )
                .is_err()
            );
            assert!(root.join("hooks/helper.sh").is_file());
            fs::remove_file(root.join("hooks/helper.sh"))?;
            fs::remove_dir(root.join("hooks"))?;
            draft = adopt(&mut store, &root, harness, kind, &identity)?;
        }
        let id = field(&draft, "stable_id")?;
        let head = field(&draft, "revision_id")?;
        let before = counts(&mut store)?;
        assert!(
            releases::plan(
                &mut store,
                id,
                head,
                Increment::Minor,
                &[],
                identity.clone(),
                AT
            )
            .is_err()
        );
        let plan = releases::plan(
            &mut store,
            id,
            head,
            Increment::Minor,
            &providers,
            identity.clone(),
            AT,
        )?;
        assert_eq!(counts(&mut store)?, before);
        let plan: releases::Plan =
            serde_json::from_slice(&canonical::bytes(&serde_json::to_value(plan)?)?)?;
        assert_eq!(plan.passport["version"], "1.0");
        let competing = releases::plan(
            &mut store,
            id,
            head,
            Increment::Minor,
            &providers,
            identity.clone(),
            AT,
        )?;
        assert!(
            releases::apply(
                &mut store,
                &plan,
                &digest::sha256(b"wrong"),
                &identity,
                LATER
            )
            .is_err()
        );
        let mut tampered = plan.clone();
        tampered.passport["name"] = "Substitution".into();
        assert!(
            releases::apply(&mut store, &tampered, &tampered.digest()?, &identity, LATER).is_err()
        );
        assert_eq!(counts(&mut store)?, before);
        if index == 0 {
            store.transaction(|t| t.execute_batch("CREATE TEMP TRIGGER fail_release BEFORE INSERT ON object_version BEGIN SELECT RAISE(ABORT,'interrupted'); END;").map_err(|_| Failure::precondition("proof injection failed")))?;
            assert!(releases::apply(&mut store, &plan, &plan.digest()?, &identity, LATER).is_err());
            assert_eq!(counts(&mut store)?, before);
            store.transaction(|t| {
                t.execute_batch("DROP TRIGGER fail_release")
                    .map_err(|_| Failure::precondition("proof cleanup failed"))
            })?;
            first_plan = Some(plan.clone());
        }
        let version = releases::apply(&mut store, &plan, &plan.digest()?, &identity, LATER)?;
        assert!(
            releases::apply(
                &mut store,
                &competing,
                &competing.digest()?,
                &identity,
                LATER
            )
            .is_err()
        );
        let scope = &version["adaptations"][0]["scope_adaptations"][0];
        assert_eq!(scope["technical_support"], "experimental");
        store.transaction(|t| {
            assert_eq!(revisions::heads(t, id)?, [head]);
            let payload = revisions::read_content(
                t,
                scope["projection_artifact"]["digest"]
                    .as_str()
                    .ok_or_else(|| Failure::input("digest missing"))?,
            )?;
            let files = artifact::verify(scope, &payload)?;
            if !parser.is_empty() {
                assert_eq!(scope["members"][0]["parser_id"], parser);
                assert_eq!(scope["provider_component_kind"], "setting");
                assert!(!String::from_utf8_lossy(&files[0].bytes).contains("unowned"));
            } else if harness == "cursor" {
                assert_eq!(
                    files
                        .iter()
                        .map(|file| file.path.as_str())
                        .collect::<Vec<_>>(),
                    ["hooks.json"]
                );
                assert_eq!(files[0].bytes, bytes);
            } else {
                assert_eq!(scope["scope"], "user_root");
                assert_eq!(
                    scope["required_surface"]["profile_id"],
                    "codex/native-files/user-root/1"
                );
                assert_eq!(files[0].path, "skills/example/SKILL.md");
                assert_eq!(files[0].bytes, bytes);
            }
            Ok(())
        })?;
        assert_eq!(fs::read(&path)?, bytes);
        released.push(version);
    }

    // An exact fork retains both harnesses through a metadata edit.
    let mut complete = released[0].clone();
    let id = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
    complete["stable_id"] = id.into();
    complete["owner_id"] = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z".into();
    complete["visibility"] = "public".into();
    complete["adaptations"]
        .as_array_mut()
        .ok_or("adaptations missing")?
        .push(released[2]["adaptations"][0].clone());
    let complete = store.transaction(|t| {
        revisions::commit(
            t,
            &complete,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: &[],
            },
        )
    })?;
    store.transaction(|t| versions::record(t, &complete, &identity.device_id, None, AT))?;
    let before = counts(&mut store)?;
    let fork = forks::plan(
        &mut store,
        forks::Source {
            stable_id: id.into(),
            version: "1.0".into(),
            passport_digest: digest::canonical("ai-stp:passport:v1", &complete)?,
        },
        identity.clone(),
        AT,
    )?;
    assert_eq!(counts(&mut store)?, before);
    assert!(
        forks::apply(
            &mut store,
            &fork,
            &digest::sha256(b"wrong"),
            &identity,
            LATER
        )
        .is_err()
    );
    store.transaction(|t| t.execute_batch("CREATE TEMP TRIGGER fail_fork BEFORE INSERT ON fork_origin BEGIN SELECT RAISE(ABORT,'interrupted'); END;").map_err(|_| Failure::precondition("proof injection failed")))?;
    assert!(forks::apply(&mut store, &fork, &fork.digest()?, &identity, LATER).is_err());
    assert_eq!(counts(&mut store)?, before);
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER fail_fork")
            .map_err(|_| Failure::precondition("proof cleanup failed"))
    })?;
    let complete = forks::apply(&mut store, &fork, &fork.digest()?, &identity, LATER)?;
    assert_eq!(complete["visibility"], "private");
    assert_eq!(complete["owner_id"], identity.account_id);
    assert_ne!(complete["stable_id"], fork.source.stable_id);
    let id = field(&complete, "stable_id")?;
    let stale = releases::plan(
        &mut store,
        id,
        field(&complete, "revision_id")?,
        Increment::Minor,
        &providers,
        identity.clone(),
        AT,
    )?;
    assert!(
        passports::plan(
            &mut store,
            id,
            field(&complete, "revision_id")?,
            Patch::parse(br#"{"managed_paths":["elsewhere"]}"#)?,
            identity.clone(),
            AT
        )
        .is_err()
    );
    let edit = passports::plan(
        &mut store,
        id,
        field(&complete, "revision_id")?,
        Patch::parse(
            br#"{"name":"Two harnesses","description":"Kill child processes after a timeout."}"#,
        )?,
        identity.clone(),
        AT,
    )?;
    let edited = passports::apply(&mut store, &edit, &edit.digest()?, &identity, LATER)?;
    assert!(releases::apply(&mut store, &stale, &stale.digest()?, &identity, LATER).is_err());
    assert_eq!(edited["name"], "Two harnesses");
    assert_eq!(edited["adaptations"], complete["adaptations"]);
    let release = releases::plan(
        &mut store,
        id,
        field(&edited, "revision_id")?,
        Increment::Minor,
        &providers,
        identity.clone(),
        LATER,
    )?;
    let first = releases::apply(&mut store, &release, &release.digest()?, &identity, LATER)?;
    assert_eq!(first["adaptations"], complete["adaptations"]);
    assert_eq!(first["name"], "Two harnesses");
    let major = releases::plan(
        &mut store,
        id,
        field(&edited, "revision_id")?,
        Increment::Major,
        &providers,
        identity.clone(),
        LATER,
    )?;
    let next = releases::apply(&mut store, &major, &major.digest()?, &identity, LATER)?;
    assert_eq!(next["version"], "2.0");

    // Explicit source arrays compile every adaptation, including a one-item array.
    let sources: Vec<Value> = [0, 2]
        .into_iter()
        .map(|index| {
            Ok::<_, Failure>(Value::Object(
                released[index]["facts"]
                    .as_object()
                    .ok_or_else(|| Failure::input("fixture facts missing"))?
                    .iter()
                    .map(|(key, fact)| (key.clone(), fact["value"].clone()))
                    .collect(),
            ))
        })
        .collect::<Result<_, _>>()?;
    for count in [1, 2] {
        let mut facts = released[0]["facts"].clone();
        facts["adaptation_contents"] = json!({"value":sources[..count],"origin":"declared","confirmation":"user_confirmed","confirmed_at":AT});
        let seed = json!({"kind":"component","stable_id":format!("component_{}",ulid::Ulid::generate()),
            "owner_id":identity.account_id,"created_at":AT,"facts":facts});
        let head = store.transaction(|t| {
            revisions::commit(
                t,
                &seed,
                &identity.device_id,
                None,
                Write::Advance {
                    expected_heads: &[],
                },
            )
        })?;
        let plan = releases::plan(
            &mut store,
            field(&head, "stable_id")?,
            field(&head, "revision_id")?,
            Increment::Minor,
            &providers,
            identity.clone(),
            AT,
        )?;
        let stored = releases::apply(&mut store, &plan, &plan.digest()?, &identity, LATER)?;
        assert_eq!(
            stored["adaptations"]
                .as_array()
                .ok_or("adaptations missing")?
                .len(),
            count
        );
        assert_eq!(stored["adaptations"][0], released[0]["adaptations"][0]);
        if count == 2 {
            assert_eq!(stored["adaptations"][1], released[2]["adaptations"][0]);
        }
    }
    // One harness may have several explicit scopes; duplicate resolved scopes
    // refuse and source-specific prerequisites must survive compilation.
    let global = sources[1].clone();
    let mut project = global.clone();
    project["scope"] = "project".into();
    project["managed_paths"] = json!([".cursor/hooks.json", ".cursor/hooks"]);
    project["supported_os"] = json!(["windows"]);
    project["permissions"] = json!({"filesystem":[],"network":["project-endpoint"],"process":[]});
    let mut previous_scopes = None;
    for (index, entries) in [
        vec![global.clone(), global.clone()],
        vec![global.clone(), project.clone()],
        vec![project, global],
    ]
    .into_iter()
    .enumerate()
    {
        let mut facts = released[2]["facts"].clone();
        facts["adaptation_contents"] = json!({"value":entries,"origin":"declared","confirmation":"user_confirmed","confirmed_at":AT});
        let seed = json!({"kind":"component","stable_id":format!("component_{}",ulid::Ulid::generate()),"owner_id":identity.account_id,"created_at":AT,"facts":facts});
        let head = store.transaction(|t| {
            revisions::commit(
                t,
                &seed,
                &identity.device_id,
                None,
                Write::Advance {
                    expected_heads: &[],
                },
            )
        })?;
        let planned = releases::plan(
            &mut store,
            field(&head, "stable_id")?,
            field(&head, "revision_id")?,
            Increment::Minor,
            &providers,
            identity.clone(),
            AT,
        );
        if index == 0 {
            assert!(planned.is_err());
            continue;
        }
        let planned = planned?;
        let stored = releases::apply(&mut store, &planned, &planned.digest()?, &identity, AT)?;
        let scopes = &stored["adaptations"][0]["scope_adaptations"];
        assert_eq!(
            stored["adaptations"]
                .as_array()
                .ok_or("adaptations missing")?
                .len(),
            1
        );
        assert_eq!(scopes.as_array().ok_or("scopes missing")?.len(), 2);
        assert_eq!(scopes[0]["scope"], "global");
        assert_eq!(scopes[1]["scope"], "project");
        assert_eq!(scopes[0]["permissions"]["network"], json!([]));
        assert_eq!(
            scopes[1]["permissions"]["network"],
            json!(["project-endpoint"])
        );
        assert_eq!(scopes[1]["supported_os"], json!(["windows"]));
        if let Some(previous) = previous_scopes {
            assert_eq!(previous, stored["adaptations"]);
        }
        previous_scopes = Some(stored["adaptations"].clone());
    }
    let mut corrupt = complete.clone();
    corrupt["stable_id"] = format!("component_{}", ulid::Ulid::generate()).into();
    corrupt["adaptations"][1] = corrupt["adaptations"][0].clone();
    let corrupt = store.transaction(|t| {
        revisions::commit(
            t,
            &corrupt,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: &[],
            },
        )
    })?;
    assert!(
        releases::plan(
            &mut store,
            field(&corrupt, "stable_id")?,
            field(&corrupt, "revision_id")?,
            Increment::Minor,
            &providers,
            identity.clone(),
            AT
        )
        .is_err()
    );
    let mut missing_source = complete.clone();
    missing_source["stable_id"] = format!("component_{}", ulid::Ulid::generate()).into();
    missing_source["adaptations"][0]["source_artifact"] =
        json!({"digest":digest::sha256(b"absent source"),"size_bytes":17});
    missing_source["adaptations"][0] =
        ai_stp_cli_v2::passport::versions::seal_adaptation(&missing_source["adaptations"][0])?;
    let missing_source = store.transaction(|t| {
        revisions::commit(
            t,
            &missing_source,
            &identity.device_id,
            None,
            Write::Advance {
                expected_heads: &[],
            },
        )
    })?;
    assert!(
        releases::plan(
            &mut store,
            field(&missing_source, "stable_id")?,
            field(&missing_source, "revision_id")?,
            Increment::Minor,
            &providers,
            identity.clone(),
            AT
        )
        .is_err()
    );
    drop(store);
    let mut store = Store::open(temporary.path(), false)?;
    assert_eq!(
        forks::apply(
            &mut store,
            &fork,
            &fork.digest()?,
            &identity,
            "2026-10-09T00:00:00.000Z"
        )?,
        complete
    );
    let old = first_plan.ok_or("release plan missing")?;
    assert_eq!(
        releases::apply(
            &mut store,
            &old,
            &old.digest()?,
            &identity,
            "2026-10-09T00:00:00.000Z"
        )?,
        released[0]
    );
    store.transaction(|t| {
        assert_eq!(
            revisions::heads(t, id)?,
            [edited["revision_id"]
                .as_str()
                .ok_or_else(|| Failure::input("head missing"))?]
        );
        t.execute(
            "UPDATE content SET bytes = zeroblob(byte_length) WHERE digest=?",
            [released[0]["artifact"]["digest"]
                .as_str()
                .ok_or_else(|| Failure::input("digest missing"))?],
        )
        .map_err(|_| Failure::precondition("proof corruption failed"))?;
        Ok(())
    })?;
    assert!(releases::apply(&mut store, &old, &old.digest()?, &identity, LATER).is_err());
    assert!(forks::apply(&mut store, &fork, &fork.digest()?, &identity, LATER).is_err());
    Ok(())
}
