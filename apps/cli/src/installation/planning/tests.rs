use super::*;
use crate::{
    account::contexts::{Authority, Context},
    authoring::{Identity, embedded},
    selection::eligibility::{Evidence, Target as SelectionTarget},
};
use serde_json::json;
use std::{
    collections::{BTreeMap, BTreeSet},
    error::Error,
    path::PathBuf,
};

const AT: &str = "2026-11-03T00:00:00.000Z";
fn actor() -> Identity {
    Identity {
        account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
        device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAV".into(),
    }
}
fn context(root: &Path, identity: Identity) -> Context {
    Context {
        schema_version: 1,
        context_id: format!("context_{}", ulid::Ulid::generate()),
        label: "Local plan fixture".into(),
        root: root.to_owned(),
        root_identity: ["0".into(), "0".into()],
        local_identity: identity,
        observed_at: AT.into(),
        authority: Authority::Local,
    }
}
fn request(
    store: &mut Store,
    input: &Path,
    target: PathBuf,
    identity: Identity,
    at: &str,
) -> std::result::Result<Request, Box<dyn Error>> {
    std::fs::create_dir(input)?;
    std::fs::write(
        input.join("guide.md"),
        b"# Native guidance\nVerify the affected behavior.\n",
    )?;
    let authored = embedded::plan(
        store,
        embedded::Request {
            directory: input.to_owned(),
            harness_id: "codex".into(),
            component_type: "instruction".into(),
            name: "native-guidance".into(),
            license_spdx: "MIT".into(),
        },
        identity.clone(),
        at,
    )?;
    embedded::apply(store, &authored, &authored.digest()?, &identity, at)?;
    let setup = json!({"stable_id":authored.setup["stable_id"],"version":authored.setup["version"],"passport_digest":digest::canonical("ai-stp:passport:v1",&authored.setup)?});
    let evidence = [&authored.component, &authored.setup]
        .into_iter()
        .map(|document| {
            Ok((
                document["stable_id"]
                    .as_str()
                    .ok_or_else(invalid)?
                    .to_owned(),
                Evidence {
                    passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
                    registrable: true,
                    blocked: false,
                    author_verified: false,
                    component_verified: false,
                    checks_current: false,
                    consented: true,
                },
            ))
        })
        .collect::<crate::error::Result<BTreeMap<_, _>>>()?;
    let (os, arch) = crate::platform::current()
        .and_then(|p| p.split_once('/'))
        .ok_or("platform")?;
    Ok(Request {
        operation: Operation::Install,
        setup,
        target: SelectionTarget {
            harness_id: "codex".into(),
            scope: Scope::Global,
            os: os.into(),
            arch: arch.into(),
            harness_version: "unknown".into(),
            owner_id: identity.account_id,
            capabilities: BTreeSet::new(),
            permissions: BTreeSet::new(),
            entitlements: BTreeSet::new(),
            env_present: BTreeSet::new(),
            grants: BTreeSet::new(),
            accessible_passport_digests: BTreeSet::new(),
            access_context_digest: None,
            pinned_passport_digests: BTreeSet::new(),
            owned_passport_digests: BTreeSet::new(),
            for_redistribution: false,
        },
        evidence,
        roots: BTreeMap::from([(Scope::Global, target)]),
        placements: BTreeMap::new(),
        corporate_binding: None,
    })
}
fn parse(value: &Value) -> crate::error::Result<Plan> {
    let digest = digest::canonical("ai-stp:installation-operation:v1", value)?;
    Plan::parse(&serde_json::to_vec(value).map_err(|_| invalid())?, &digest)
}

#[test]
fn native_plan_retains_actual_roots_and_source_without_writes_or_before_images()
-> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().canonicalize()?;
    let state = root.join("state");
    std::fs::create_dir(&state)?;
    let target = root.join("Cafe\u{301}");
    std::fs::create_dir(&target)?;
    let before = b"PRIVATE-UNOWNED-BEFORE-IMAGE-CANARY\n";
    std::fs::write(target.join("AGENTS.md"), before)?;
    let mut store = Store::open(&state, true)?;
    let request = request(
        &mut store,
        &root.join("source"),
        target.clone(),
        actor(),
        AT,
    )?;
    let changes: i64 = store
        .connection
        .query_row("SELECT total_changes()", [], |row| row.get(0))?;
    let native = capture(&mut store, context(&state, actor()), None, &request, AT)?;
    assert_eq!(native.packages.len(), 1);
    let document = native.plan.value()?;
    let encoded = serde_json::to_vec(&document)?;
    assert!(!String::from_utf8(encoded.clone())?.contains("PRIVATE-UNOWNED-BEFORE-IMAGE-CANARY"));
    let retained = Plan::parse(&encoded, &native.plan.digest()?)?;
    assert_eq!(
        retained.roots[&Scope::Global].directory.path.as_os_str(),
        target.as_os_str()
    );
    assert_eq!(retained.value()?, document);
    retained.revalidate_targets()?;
    assert_eq!(std::fs::read(target.join("AGENTS.md"))?, before);
    assert!(!target.join(CONTROL).exists());
    assert_eq!(
        store
            .connection
            .query_row("SELECT total_changes()", [], |row| row.get::<_, i64>(0))?,
        changes
    );
    std::fs::write(
        target.join("AGENTS.md"),
        b"changed outside the original plan",
    )?;
    assert!(retained.revalidate_targets().is_err());
    assert_eq!(
        parse(&document)?.value()?,
        document,
        "history parsing must not reopen current targets"
    );
    assert!(!target.join(CONTROL).exists());
    Ok(())
}

#[test]
fn closed_native_format_preserves_full_windows_ids_and_refuses_foreign_or_changed_frames()
-> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().canonicalize()?;
    let state = root.join("state");
    let target = root.join("target");
    std::fs::create_dir(&state)?;
    std::fs::create_dir(&target)?;
    let mut store = Store::open(&state, true)?;
    let request = request(&mut store, &root.join("source"), target, actor(), AT)?;
    let plan = capture(&mut store, context(&state, actor()), None, &request, AT)?.plan;
    let document = plan.value()?;
    for changed in [
        {
            let mut v = document.clone();
            v["format"] = "ai-stp-external-installation/1".into();
            v
        },
        {
            let mut v = document.clone();
            v["foreign_authority"] = true.into();
            v
        },
        {
            let mut v = document.clone();
            v["scope_bindings"] = json!({});
            v
        },
        {
            let mut v = document.clone();
            v["roots"]["global"]["extra"] = true.into();
            v
        },
        {
            let mut v = document.clone();
            v["expires_at"] = "2026-11-03T01:00:00.000Z".into();
            v
        },
        {
            let mut v = document.clone();
            v["setup"]["version"] = "999.0".into();
            v
        },
    ] {
        assert!(parse(&changed).is_err());
    }
    let mut windows = document.clone();
    windows["target"]["os"] = "windows".into();
    windows["state"]["physical"] =
        json!({"kind":"windows","volume":u64::MAX.to_string(),"file_id":u128::MAX.to_string()});
    windows["roots"]["global"]["directory"]["physical"] =
        json!({"kind":"windows","volume":u64::MAX.to_string(),"file_id":u128::MAX.to_string()});
    let retained = parse(&windows)?;
    assert_eq!(retained.value()?, windows);
    let changed =
        json!({"kind":"windows","volume":u64::MAX.to_string(),"file_id":u64::MAX.to_string()});
    assert_ne!(windows["roots"]["global"]["directory"]["physical"], changed);
    assert!(Plan::parse(&serde_json::to_vec(&document)?, "sha256:wrong").is_err());
    let legacy = json!({"schema_version":1,"action":"configuration.install","operation_id":document["operation_id"]});
    assert!(parse(&legacy).is_err());
    Ok(())
}

#[test]
fn replaced_root_and_duplicate_physical_roles_refuse_without_target_state()
-> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().canonicalize()?;
    let state = root.join("state");
    let target = root.join("target");
    std::fs::create_dir(&state)?;
    std::fs::create_dir(&target)?;
    let mut store = Store::open(&state, true)?;
    let mut request = request(
        &mut store,
        &root.join("source"),
        target.clone(),
        actor(),
        AT,
    )?;
    let plan = capture(&mut store, context(&state, actor()), None, &request, AT)?.plan;
    request.roots.insert(Scope::Project, target.clone());
    assert!(capture(&mut store, context(&state, actor()), None, &request, AT).is_err());
    assert!(!target.join(CONTROL).exists());
    std::fs::rename(&target, root.join("original"))?;
    std::fs::create_dir(&target)?;
    assert!(plan.revalidate_targets().is_err());
    assert!(std::fs::read_dir(&target)?.next().is_none());
    assert!(parse(&plan.value()?).is_ok());
    Ok(())
}

#[cfg(unix)]
#[test]
fn original_context_survives_selection_and_restart_while_expired_admission_refuses()
-> std::result::Result<(), Box<dyn Error>> {
    let temporary = tempfile::tempdir()?;
    let root = temporary.path().canonicalize()?;
    let state = root.join("state");
    let target = root.join("target");
    std::fs::create_dir(&state)?;
    std::fs::create_dir(&target)?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = crate::identity::plan(&state, crate::identity::Storage::File, &at)?;
    crate::identity::apply(&init, &init.digest()?, &at)?;
    let first = contexts::create_plan(&state, "First", None, None, &at)?;
    let first_value = serde_json::to_value(&first)?;
    let id = first_value["change"]["context"]["context_id"]
        .as_str()
        .ok_or("context id")?;
    contexts::apply(&first, &first.digest()?, &at)?;
    let owner = runtime::owner(&state)?;
    let actor = crate::authoring::Identity {
        account_id: owner.account_id.clone(),
        device_id: owner.device_id.clone(),
    };
    let mut store = owner.open(false)?;
    let request = request(&mut store, &root.join("source"), target.clone(), actor, &at)?;
    drop(store);
    let planned = create(&state, id, &request, &at)?;
    let second = contexts::create_plan(&state, "Second", None, None, &at)?;
    let second_value = serde_json::to_value(&second)?;
    let second_id = second_value["change"]["context"]["context_id"]
        .as_str()
        .ok_or("context id")?;
    contexts::apply(&second, &second.digest()?, &at)?;
    let select = contexts::select_plan(&state, second_id, &at)?;
    contexts::apply(&select, &select.digest()?, &at)?;
    let parsed = Plan::parse(
        &serde_json::to_vec(&planned.plan.value()?)?,
        &planned.plan.digest()?,
    )?;
    parsed.revalidate(&state, &at)?;
    assert_eq!(parsed.context.context_id, id);
    assert_eq!(contexts::list(&state)?["selected"]["context_id"], second_id);
    assert!(parsed.revalidate(&state, &parsed.expires_at).is_err());
    assert!(std::fs::read_dir(&target)?.next().is_none());
    Ok(())
}
