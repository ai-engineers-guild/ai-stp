use super::{AT, LATER, counts, field, release, stored};
use ai_stp_cli_v2::{
    authoring::{
        Identity,
        forks::Source,
        materialization::{self, Effect, Mode, Request},
        passports::{self, Patch},
        releases,
    },
    canonical, digest,
    error::Failure,
    provider::Info,
    store::{Store, versions::Increment},
};
use serde_json::json;
use std::{error::Error, fs, path::Path};

pub(super) fn journey(
    store: &mut Store,
    root: &Path,
    providers: &[Info],
    identity: &Identity,
    foreign: &Identity,
) -> Result<(), Box<dyn Error>> {
    let root = root.join("atomic-materialization");
    let draft = release(
        store,
        &root,
        "codex",
        b"[mcp_servers.materialize]\ncommand = 'review-server'\nargs = ['exact']\n",
        providers,
        identity,
    )?;
    let id = field(&draft, "stable_id")?;
    let original = stored(store, id, Some("1.0"))?;
    let request = Request {
        source: Source {
            stable_id: id.into(),
            version: "1.0".into(),
            passport_digest: digest::canonical("ai-stp:passport:v1", &original)?,
        },
        source_harness: "codex".into(),
        targets: vec!["codex".into(), "cursor".into(), "opencode".into()],
        all_missing: false,
        output: Mode::Owned,
        overlay_id: None,
    };
    let initial = counts(store)?;
    let plan = materialization::plan(store, request.clone(), providers, identity.clone(), AT)?;
    assert_eq!(counts(store)?, initial);
    assert_eq!(plan.effect, Effect::RecordVersion);
    assert_eq!(plan.passport.as_ref().ok_or("passport")?["version"], "1.1");
    assert_eq!(
        plan.targets
            .iter()
            .map(|t| t.disposition.as_str())
            .collect::<Vec<_>>(),
        ["reuse", "derive", "derive"]
    );
    let stale = materialization::plan(store, request.clone(), providers, identity.clone(), AT)?;
    assert!(materialization::apply(store, &plan, "wrong", identity, AT).is_err());
    assert!(materialization::apply(store, &plan, &plan.digest()?, foreign, AT).is_err());
    assert!(materialization::apply(store, &plan, &plan.digest()?, identity, LATER).is_err());
    let mut forged = plan.clone();
    forged.passport.as_mut().ok_or("passport")?["name"] = "forged".into();
    assert!(materialization::apply(store, &forged, &forged.digest()?, identity, AT).is_err());
    store.transaction(|t|t.execute_batch("CREATE TEMP TRIGGER fail_materialization BEFORE INSERT ON operation BEGIN SELECT RAISE(ABORT,'late proof failure'); END;").map_err(|_|Failure::input("proof trigger")))?;
    assert!(materialization::apply(store, &plan, &plan.digest()?, identity, AT).is_err());
    assert_eq!(counts(store)?, initial);
    assert_eq!(stored(store, id, None)?, draft);
    store.transaction(|t| {
        t.execute_batch("DROP TRIGGER fail_materialization;")
            .map_err(|_| Failure::input("proof trigger"))
    })?;
    let result = materialization::apply(store, &plan, &plan.digest()?, identity, AT)?;
    assert_eq!(
        result["adaptations"].as_array().ok_or("adaptations")?.len(),
        3
    );
    assert_eq!(stored(store, id, None)?, draft);
    assert_eq!(stored(store, id, Some("1.0"))?, original);
    assert!(materialization::apply(store, &stale, &stale.digest()?, identity, AT).is_err());
    assert!(
        materialization::plan(store, request.clone(), providers, identity.clone(), AT).is_err()
    );
    let mut reuse = request.clone();
    reuse.source.version = "1.1".into();
    reuse.source.passport_digest = digest::canonical("ai-stp:passport:v1", &result)?;
    let reuse = materialization::plan(store, reuse, providers, identity.clone(), AT)?;
    assert_eq!(reuse.effect, Effect::Reuse);
    assert_eq!(
        materialization::apply(store, &reuse, &reuse.digest()?, identity, AT)?,
        result
    );
    let after = counts(store)?;
    assert_eq!(
        materialization::apply(store, &plan, &plan.digest()?, identity, LATER)?,
        result
    );
    assert_eq!(counts(store)?, after);

    // A different author receives one new private immutable identity. Both
    // origin records are part of the same transaction as every derived artifact.
    let mut private = request.clone();
    private.output = Mode::Private;
    let private_plan =
        materialization::plan(store, private.clone(), providers, foreign.clone(), AT)?;
    assert_eq!(private_plan.effect, Effect::CreateOverlay);
    let initial = counts(store)?;
    for table in ["overlay_origin", "operation"] {
        store.transaction(|t|t.execute_batch(&format!("CREATE TEMP TRIGGER fail_materialization BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'late proof failure'); END;")).map_err(|_|Failure::input("proof trigger")))?;
        assert!(
            materialization::apply(store, &private_plan, &private_plan.digest()?, foreign, AT)
                .is_err()
        );
        assert_eq!(counts(store)?, initial);
        store.transaction(|t| {
            t.execute_batch("DROP TRIGGER fail_materialization;")
                .map_err(|_| Failure::input("proof trigger"))
        })?;
    }
    let overlay =
        materialization::apply(store, &private_plan, &private_plan.digest()?, foreign, AT)?;
    assert_ne!(overlay["stable_id"], original["stable_id"]);
    assert_eq!(overlay["version"], "1.0");
    assert_eq!(overlay["owner_id"], foreign.account_id);
    assert_eq!(overlay["visibility"], "private");
    assert_eq!(overlay["compatibility_evidence_refs"], json!([]));
    assert_eq!(
        overlay["facts"]["source_component"]["value"]["passport_digest"],
        request.source.passport_digest
    );
    assert!(
        overlay["facts"]
            .get("compatibility_evidence_refs")
            .is_none()
    );
    let overlay_id = field(&overlay, "stable_id")?;
    let edit = passports::plan(
        store,
        overlay_id,
        field(&overlay, "revision_id")?,
        Patch::try_from(json!({"description":"A newer private draft remains current."}))?,
        foreign.clone(),
        AT,
    )?;
    let newer = passports::apply(store, &edit, &edit.digest()?, foreign, AT)?;
    let version = releases::plan(
        store,
        overlay_id,
        field(&newer, "revision_id")?,
        Increment::Minor,
        &[],
        foreign.clone(),
        AT,
    )?;
    assert_eq!(
        releases::apply(store, &version, &version.digest()?, foreign, AT)?["version"],
        "1.1"
    );
    private.overlay_id = Some(overlay_id.into());
    let overlay_reuse =
        materialization::plan(store, private.clone(), providers, foreign.clone(), LATER)?;
    assert_eq!(overlay_reuse.effect, Effect::ReuseOverlay);
    assert_eq!(
        materialization::apply(
            store,
            &overlay_reuse,
            &overlay_reuse.digest()?,
            foreign,
            LATER
        )?,
        overlay
    );
    assert_eq!(stored(store, overlay_id, None)?, newer);
    let after = counts(store)?;
    fs::remove_dir_all(&root)?;
    assert_eq!(
        materialization::apply(
            store,
            &private_plan,
            &private_plan.digest()?,
            foreign,
            LATER
        )?,
        overlay
    );
    assert_eq!(stored(store, overlay_id, None)?, newer);
    assert_eq!(counts(store)?, after);
    assert!(
        materialization::plan(store, private.clone(), providers, identity.clone(), LATER).is_err()
    );
    let mut collision = private.clone();
    collision.targets = vec!["codex".into()];
    assert!(materialization::plan(store, collision, providers, foreign.clone(), LATER).is_err());
    let mut collision = private.clone();
    collision.overlay_id = Some(id.into());
    assert!(materialization::plan(store, collision, providers, foreign.clone(), LATER).is_err());
    let mut duplicate = private.clone();
    duplicate.targets = vec!["cursor".into(), "cursor".into()];
    assert!(materialization::plan(store, duplicate, providers, foreign.clone(), LATER).is_err());
    let mut wrong = private.clone();
    wrong.source.passport_digest = digest::canonical("ai-stp:passport:v1", &json!({}))?;
    assert!(materialization::plan(store, wrong, providers, foreign.clone(), LATER).is_err());

    for targets in [
        vec!["codex".into(), "cursor".into(), "grok-build".into()],
        Vec::new(),
    ] {
        let mut blocked = request.clone();
        blocked.output = Mode::Private;
        blocked.all_missing = targets.is_empty();
        blocked.targets = targets;
        let plan = materialization::plan(store, blocked, providers, foreign.clone(), AT)?;
        assert_eq!(plan.effect, Effect::Blocked);
        assert!(plan.passport.is_none());
        assert!(plan.targets.iter().any(|t| t.disposition == "derive"));
        assert!(plan.targets.iter().any(|t| t.disposition == "blocked"));
        assert!(materialization::apply(store, &plan, &plan.digest()?, foreign, AT).is_err());
    }
    let mut missing = request.clone();
    missing.output = Mode::Private;
    assert!(
        materialization::plan(store, missing, &[], foreign.clone(), AT)?
            .targets
            .iter()
            .all(|t| t.disposition == "blocked")
    );
    assert_eq!(counts(store)?, after);
    // Corruption remains an error, even when the requested target is unsupported.
    let address = field(&original["artifact"], "digest")?;
    let bytes = store.transaction(|t| ai_stp_cli_v2::store::revisions::read_content(t, address))?;
    store.transaction(|t| {
        t.execute(
            "UPDATE content SET bytes=? WHERE digest=?",
            rusqlite::params![b"corrupt".as_slice(), address],
        )
        .map(|_| ())
        .map_err(|_| Failure::input("proof corruption"))
    })?;
    let mut blocked = request;
    blocked.output = Mode::Private;
    blocked.targets = vec!["grok-build".into()];
    assert!(materialization::plan(store, blocked, providers, foreign.clone(), AT).is_err());
    assert!(materialization::apply(store, &plan, &plan.digest()?, identity, LATER).is_err());
    store.transaction(|t| {
        t.execute(
            "UPDATE content SET bytes=? WHERE digest=?",
            rusqlite::params![bytes, address],
        )
        .map(|_| ())
        .map_err(|_| Failure::input("proof restoration"))
    })?;
    assert_eq!(counts(store)?, after);
    assert_eq!(
        canonical::bytes(&stored(store, id, Some("1.0"))?)?,
        canonical::bytes(&original)?
    );
    Ok(())
}
