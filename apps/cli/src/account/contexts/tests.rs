use super::*;
use std::error::Error;

#[test]
fn selection_is_revision_checked_and_replay_does_not_reselect_or_touch_existing_work()
-> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let at = format!("{:.3}", jiff::Timestamp::now());
    let init = identity::plan(root.path(), identity::Storage::File, &at)?;
    let id = identity::apply(&init, &init.digest()?, &at)?;
    let original = id.report();
    let first = create_plan(root.path(), "Offline", None, None, &at)?;
    let schema_race = create_plan(root.path(), "Planned before upgrade", None, None, &at)?;
    assert_eq!(list(root.path())?["contexts"], json!([]));
    assert!(apply(&first, "sha256:incorrect", &at).is_err());
    assert!(apply(&first, &first.digest()?, &first.expires_at).is_err());
    let first_created = apply(&first, &first.digest()?, &at)?;
    assert!(apply(&schema_race, &schema_race.digest()?, &at).is_err());
    assert_eq!(
        first_created,
        apply(&first, &first.digest()?, &first.expires_at)?
    );
    let second = create_plan(root.path(), "Another local view", None, None, &at)?;
    apply(&second, &second.digest()?, &at)?;
    let select_first = select_plan(root.path(), &first.context().context_id, &at)?;
    let stale = select_plan(root.path(), &second.context().context_id, &at)?;
    let receipt = apply(&select_first, &select_first.digest()?, &at)?;
    assert!(apply(&stale, &stale.digest()?, &at).is_err());
    let selected = select_plan(root.path(), &second.context().context_id, &at)?;
    apply(&selected, &selected.digest()?, &at)?;
    assert_eq!(
        receipt,
        apply(
            &select_first,
            &select_first.digest()?,
            &select_first.expires_at
        )?
    );
    let state = list(root.path())?;
    assert_eq!(state["selected"]["context_id"], second.context().context_id);
    assert_eq!(state["selected"]["revision"], selected.operation_id);
    assert_eq!(state["contexts"].as_array().ok_or("contexts")?.len(), 2);
    assert_eq!(super::super::identity_at(root.path())?.report(), original);
    assert!(!root.path().join("ai-stp-v2-account").exists());
    assert!(!root.path().join("ai-stp-v2-connections").exists());
    let other = tempfile::tempdir()?;
    let init = identity::plan(other.path(), identity::Storage::File, &at)?;
    identity::apply(&init, &init.digest()?, &at)?;
    let mut copied = first.clone();
    if let Change::Create { context, .. } = &mut copied.change {
        context.root = other.path().to_owned();
    }
    assert!(apply(&copied, &copied.digest()?, &at).is_err());
    Ok(())
}

#[test]
fn context_observations_drop_unknown_fields_and_refuse_mixed_authority()
-> std::result::Result<(), Box<dyn Error>> {
    let organization = format!("organization_{}", ulid::Ulid::generate());
    let at = format!("{:.3}", jiff::Timestamp::now());
    let item = json!({"schema_version":1,"organization_id":organization,"kind":"corporate",
        "display_name":"Company","membership_revision":2,"future_private_field":"discarded"});
    let projected = organizations_projection(&json!({"schema_version":1,"items":[item.clone()]}))?;
    assert!(projected["items"][0].get("future_private_field").is_none());
    assert!(
        organizations_projection(&json!({"schema_version":1,"items":[item.clone(),item]})).is_err()
    );
    let mut active = json!({"schema_version":1,"mode":"corporate","organization_id":organization,
        "capabilities":{"schema_version":1,"registry_version":2,"mode":"corporate","context_kind":"corporate",
        "organization_id":organization,"authorization_revision":"corporate:test:2","issued_at":at,"generated_at":at,
        "expires_at":authoring::expiry(&at)?,"capabilities":["organization.read"],"unavailable":{},"future_token":"discarded"},
        "future_sensitive_field":"discarded"});
    let projection = active_projection(&active)?;
    assert!(projection.get("future_sensitive_field").is_none());
    assert!(projection["capabilities"].get("future_token").is_none());
    active["capabilities"]["capabilities"] = json!(["organization.read", "organization.read"]);
    assert!(active_projection(&active).is_err());
    active["capabilities"]["capabilities"] = json!(["organization.read"]);
    active["capabilities"]["context_kind"] = json!("personal");
    assert!(active_projection(&active).is_err());
    Ok(())
}
