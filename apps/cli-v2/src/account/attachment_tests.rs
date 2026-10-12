//! A transfer journey exercises the real journal, HTTP, SQLite, old writers,
//! historical authoring replay and independently bounded immutable access.

use super::*;
use crate::{
    authoring::{
        passports::{self, Patch},
        runtime,
    },
    digest,
    objects::Objects,
    store::{
        revisions::{self, Write},
        versions,
    },
};

fn save_plan(
    root: &Path,
    name: &str,
    value: &Value,
) -> std::result::Result<std::path::PathBuf, Box<dyn Error>> {
    let path = root.join(name);
    fs::write(&path, canonical::bytes(&value["plan"])?)?;
    Ok(path)
}

#[test]
fn attachment_is_atomic_exact_and_fences_stale_authority() -> std::result::Result<(), Box<dyn Error>>
{
    let root = tempfile::tempdir()?;
    let at = after(&format!("{:.3}", jiff::Timestamp::now()), 3600)?;
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let device = identity::apply(&init, &init.digest()?, &at)?;
    let original = device.context();
    let stale_writer = runtime::owner(root.path())?;
    let account = format!("account_{}", ulid::Ulid::generate());
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let origin = format!("http://{}", listener.local_addr()?);
    let start = plan(root.path(), Action::Start, Some(&origin), None, &at)?;
    let journal = Journal::open(&device, true)?.ok_or("journal")?;
    journal.write(&State {
        plan: start.clone(),
        revision: start.operation_id.clone(),
        session: Session::Authorized {
            account_id: account.clone(),
            access_token: model::Secret(Zeroizing::new("generated-access-credential".into())),
            refresh_token: model::Secret(Zeroizing::new("generated-refresh-credential".into())),
            expires_at: after(&at, 3600)?,
        },
        outcome: Outcome::Authorized,
        completed_at: at.clone(),
    })?;
    let credentials = fs::read(
        root.path()
            .join("ai-stp-v2-account")
            .join(format!("account-{}", original.device_id)),
    )?;
    drop(journal);
    let mut store = stale_writer.open(true)?;
    let mut drafts = Vec::new();
    for kind in ["component", "setup", "project", "developer", "device"] {
        let mut document = json!({"kind":kind,"stable_id":format!("{kind}_{}",ulid::Ulid::generate()),
            "owner_id":original.account_id,"created_at":at,"visibility":"private"});
        if kind == "setup" {
            document["harness_id"] = "claude-code".into();
        }
        drafts.push(store.transaction(|t| {
            revisions::commit(
                t,
                &document,
                &original.device_id,
                None,
                Write::Advance {
                    expected_heads: &[],
                },
            )
        })?);
    }
    let component_id = drafts[0]["stable_id"].as_str().ok_or("id")?.to_owned();
    let catalog: Value = serde_json::from_str(include_str!(
        "../../../../packages/contracts/src/ai_stp_contracts/fixtures/v1/catalog.json"
    ))?;
    let mut version = catalog["cases"]
        .as_array()
        .ok_or("cases")?
        .iter()
        .find(|c| c["case_id"] == "readComponentVersion.published")
        .ok_or("fixture")?["body"]["passport"]
        .clone();
    version["stable_id"] = component_id.clone().into();
    version["owner_id"] = original.account_id.clone().into();
    version["visibility"] = "private".into();
    version =
        store.transaction(|t| versions::record(t, &version, &original.device_id, None, &at))?;
    let version_number = version["version"].as_str().ok_or("version")?.to_owned();
    drop(store);
    let project_root = root.path().join("project");
    fs::create_dir(&project_root)?;
    fs::write(project_root.join("main.rs"), "fn main() {}\n")?;
    let project_plan = runtime::plan(root.path(), |s, owner, _| {
        crate::projects::passports::plan(s, &project_root, owner, &at)
    })?;
    let project_operation: crate::projects::passports::Plan =
        serde_json::from_value(project_plan["plan"]["operation"].clone())?;
    let mut store = stale_writer.open(false)?;
    let project = crate::projects::passports::apply(
        &mut store,
        &project_operation,
        &project_operation.digest()?,
        &original,
        &at,
    )?;
    drafts.push(project_operation.passport.clone());
    drop(store);
    let technology_plan = runtime::plan(root.path(), |s, owner, _| {
        crate::projects::technology::retained::plan(s, &project_root, owner, &at)
    })?;
    let technology_operation: crate::projects::technology::retained::Plan =
        serde_json::from_value(technology_plan["plan"]["operation"].clone())?;
    let mut store = stale_writer.open(false)?;
    let technology = crate::projects::technology::retained::apply(
        &mut store,
        &technology_operation,
        &technology_operation.digest()?,
        &original,
        &at,
    )?;
    drop(store);
    let plan_edit = |name: &str| {
        runtime::plan(root.path(), |store, owner, _| {
            passports::plan(
                store,
                &component_id,
                drafts[0]["revision_id"]
                    .as_str()
                    .ok_or_else(super::super::invalid)?,
                Patch::parse(
                    serde_json::to_string(&json!({"name":name}))
                        .map_err(|_| super::super::invalid())?
                        .as_bytes(),
                )?,
                owner,
                &at,
            )
        })
    };
    let completed = plan_edit("Before attachment")?;
    let unapplied = plan_edit("Never applied")?;
    let completed_path = save_plan(root.path(), "completed.json", &completed)?;
    let unapplied_path = save_plan(root.path(), "unapplied.json", &unapplied)?;
    // The runtime's clock is real; direct service execution creates the exact
    // completed receipt at our future logical fixture clock.
    let completed_operation: passports::Plan =
        serde_json::from_value(completed["plan"]["operation"].clone())?;
    let mut store = stale_writer.open(false)?;
    let edited = passports::apply(
        &mut store,
        &completed_operation,
        &completed_operation.digest()?,
        &original,
        &at,
    )?;
    drafts[0] = edited.clone();
    store.connection.execute(
        "INSERT INTO operation(operation_id,kind,state,started_at) VALUES ('fixture-unfinished','fixture','applying',?)",
        [&at],
    )?;
    assert!(attachment::selection(&store.connection, &original, &account, &at).is_err());
    store.connection.execute(
        "DELETE FROM operation WHERE operation_id='fixture-unfinished'",
        [],
    )?;
    let old_revision = completed_operation.expected_revision.clone();
    store.connection.execute(
        "INSERT INTO head(stable_id,revision_id) VALUES (?,?)",
        [&component_id, &old_revision],
    )?;
    assert!(attachment::selection(&store.connection, &original, &account, &at).is_err());
    store.connection.execute(
        "DELETE FROM head WHERE stable_id=? AND revision_id=?",
        [&component_id, &old_revision],
    )?;
    drop(store);
    let attachment = plan(root.path(), Action::Attach, None, None, &at)?;
    assert_eq!(
        attachment
            .attachment
            .as_ref()
            .ok_or("selection")?
            .heads
            .len(),
        6
    );
    let mut forged = attachment.clone();
    forged.attachment.as_mut().ok_or("selection")?.heads.clear();
    assert!(apply(&forged, &forged.digest()?, &at).is_err());

    let mut store = stale_writer.open(false)?;
    // A failure after head revisions were inserted must roll back the entire
    // transfer, effective owner and access inventory together.
    store.fence_legacy_writers()?;
    store.connection.execute_batch("CREATE TEMP TRIGGER fail_attachment BEFORE INSERT ON operation_event BEGIN SELECT RAISE(ABORT,'fixture interruption'); END;")?;
    assert!(attachment::commit(&mut store, &attachment, &at, &at).is_err());
    assert_eq!(
        attachment::effective(&store.connection, &original)?,
        original
    );
    for draft in &drafts {
        assert_eq!(
            Objects {
                connection: &store.connection
            }
            .head(
                draft["kind"].as_str().ok_or("kind")?,
                draft["stable_id"].as_str().ok_or("id")?
            )?,
            *draft
        );
    }
    store
        .connection
        .execute_batch("DROP TRIGGER fail_attachment")?;
    drop(store);
    assert!(
        crate::files::OwnedDirectory::open(
            root.path(),
            "ai-stp-v2-state",
            b"ai-stp-cli-v2 local registry v1\n",
            false
        )
        .is_err()
    );
    let server_account = account.clone();
    let server_device = original.device_id.clone();
    let server = thread::spawn(move || -> std::io::Result<()> {
        // Wrong-device responses are refused even for the intended account.
        for id in [None, Some(server_device)] {
            let mut socket = accept(&listener)?;
            let (headers, body) = receive(&mut socket)?;
            assert!(headers.starts_with("GET /v1/auth/me HTTP/1.1"));
            assert!(body.is_empty());
            respond(
                &mut socket,
                200,
                json!({"schema_version":1,"account_id":server_account,"device_id":id,"account_status":"active"}),
            )?;
        }
        Ok(())
    });
    assert!(apply(&attachment, &attachment.digest()?, &at).is_err());
    let applied = apply(&attachment, &attachment.digest()?, &at)?;
    server.join().map_err(|_| "server panic")??;
    assert_eq!(applied["owner_attached"], true);
    assert_eq!(
        apply(&attachment, &attachment.digest()?, &after(&at, 7200)?)?,
        applied
    );
    assert!(stale_writer.open(false).is_err());
    assert!(stale_writer.planning().is_err());
    assert_eq!(
        identity::current(root.path())?.ok_or("identity")?.context(),
        original
    );
    assert_eq!(
        fs::read(
            root.path()
                .join("ai-stp-v2-account")
                .join(format!("account-{}", original.device_id))
        )?,
        credentials
    );
    assert_eq!(status(root.path(), &at)?["effective_owner_id"], account);
    let owner = runtime::owner(root.path())?;
    assert_eq!(owner.account_id, account);
    let mut store = owner.open(false)?;
    for draft in &drafts {
        let head = Objects {
            connection: &store.connection,
        }
        .head(
            draft["kind"].as_str().ok_or("kind")?,
            draft["stable_id"].as_str().ok_or("id")?,
        )?;
        assert_eq!(head["owner_id"], account);
        assert_eq!(head["visibility"], draft["visibility"]);
        assert_eq!(head["parent_revision_ids"], json!([draft["revision_id"]]));
    }
    assert_eq!(
        Objects {
            connection: &store.connection
        }
        .exact_version(&component_id, &version_number, None)?,
        version
    );
    assert!(attachment::retained(&store.connection, &account, &version)?);
    let mut ungranted = version.clone();
    ungranted["version"] = "99.0".into();
    ungranted = revisions::seal(&ungranted)?;
    assert!(!attachment::retained(
        &store.connection,
        &account,
        &ungranted
    )?);
    assert!(!attachment::retained(
        &store.connection,
        "account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        &version
    )?);
    let mut new_version = version.clone();
    new_version["owner_id"] = account.clone().into();
    new_version["version"] = "99.0".into();
    store.transaction(|t| versions::record(t, &new_version, &original.device_id, None, &at))?;
    assert_eq!(
        attachment::effective(&store.connection, &original)?.account_id,
        account
    );
    drop(store);
    assert_eq!(
        runtime::apply(
            &completed_path,
            completed["plan_digest"].as_str().ok_or("digest")?
        )?,
        edited
    );
    assert!(
        runtime::apply(
            &unapplied_path,
            unapplied["plan_digest"].as_str().ok_or("digest")?
        )
        .is_err()
    );
    assert!(plan(root.path(), Action::Attach, None, None, &at).is_err());
    for (name, prepared, expected) in [
        ("project-replay", project_plan, project),
        ("technology-replay", technology_plan, technology),
    ] {
        let path = save_plan(root.path(), name, &prepared)?;
        assert_eq!(
            runtime::apply(&path, prepared["plan_digest"].as_str().ok_or("digest")?)?,
            expected
        );
    }
    assert_eq!(
        digest::canonical("ai-stp:passport:v1", &version)?,
        attachment
            .attachment
            .as_ref()
            .ok_or("selection")?
            .versions
            .keys()
            .next()
            .ok_or("hash")?
            .clone()
    );
    Ok(())
}
