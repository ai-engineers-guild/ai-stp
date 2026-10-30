//! Explicit absent-checkout retirement through the independent current-authority peer.

use super::*;
use crate::account::project_unlinks::missing_checkout;

pub(super) fn prove(
    local: &identity::Identity,
    checkout: &Path,
    contexts: &[String],
    adoption: &project_links::Plan,
    adopted: &Value,
    peer: &Mutex<Peer>,
    at: &str,
) -> std::result::Result<(), Box<dyn Error>> {
    let state = local.root_binding().0;
    let binding = serde_json::to_value(adoption)?["operation_id"]
        .as_str()
        .ok_or("binding")?
        .to_owned();
    let preserved = checkout.with_file_name("missing-preserved-cafe\u{301}");
    let marker = ".ai-stp-v2-project/project-id";
    let before_marker = fs::read(checkout.join(marker))?;
    let before_canary = fs::read(checkout.join(".env"))?;
    let before_mode = fs::metadata(checkout.join(".env"))?.permissions().mode();
    let registry = || -> std::result::Result<Vec<u8>, Box<dyn Error>> {
        Ok(Store::planning_at(local.root_directory())?
            .connection
            .serialize("main")?
            .to_vec())
    };
    let before = registry()?;
    let reads = peer.lock().map_err(|_| "peer")?.reads.len();
    assert!(missing_checkout::plan(state, Some(&contexts[0]), &binding, at).is_err());
    assert_eq!(peer.lock().map_err(|_| "peer")?.reads.len(), reads);
    fs::rename(checkout, &preserved)?;
    assert!(missing_checkout::plan(state, Some(&contexts[1]), &binding, at).is_err());
    assert_eq!(peer.lock().map_err(|_| "peer")?.reads.len(), reads);
    assert!(missing_checkout::plan(state, Some(&contexts[0]), &binding, at).is_err());
    assert_eq!(registry()?, before);
    {
        let mut remote = peer.lock().map_err(|_| "peer")?;
        let plan_id = adopted["effect"]["link"]["plan_id"]
            .as_str()
            .ok_or("plan")?;
        let link = remote.links.get_mut(plan_id).ok_or("remote link")?;
        link["state"] = "unlinked".into();
        link["revision"] = (link["revision"].as_u64().ok_or("revision")? + 2).into();
        link["updated_at"] = after(at, 1)?.into();
    }
    let planned = missing_checkout::plan(state, Some(&contexts[0]), &binding, at)?;
    let encoded = serde_json::to_value(&planned)?;
    assert_eq!(encoded["registry_schema_before"], 61);
    assert_eq!(encoded["registry_schema_after"], 62);
    assert_eq!(encoded["kind"], "corporate.project_binding.retire_missing");
    let mut unknown = encoded.clone();
    unknown["unexpected"] = true.into();
    assert!(serde_json::from_value::<missing_checkout::Plan>(unknown).is_err());
    let mut wrong_kind = encoded.clone();
    wrong_kind["kind"] = "corporate.project_binding.retire".into();
    let wrong_kind: missing_checkout::Plan = serde_json::from_value(wrong_kind)?;
    assert!(wrong_kind.digest().is_err());
    let restored: missing_checkout::Plan = serde_json::from_value(encoded)?;
    assert_eq!(restored.digest()?, planned.digest()?);
    peer.lock().map_err(|_| "peer")?.deny_link = true;
    assert!(missing_checkout::apply(state, &planned, &planned.digest()?, at).is_err());
    peer.lock().map_err(|_| "peer")?.deny_link = false;
    peer.lock().map_err(|_| "peer")?.settlement = Some("unsupported".into());
    assert!(missing_checkout::apply(state, &planned, &planned.digest()?, at).is_err());
    peer.lock().map_err(|_| "peer")?.settlement = None;
    assert_eq!(registry()?, before);
    let reads = peer.lock().map_err(|_| "peer")?.reads.len();
    let expired = after(at, 901)?;
    assert!(missing_checkout::apply(state, &planned, &planned.digest()?, &expired).is_err());
    assert_eq!(peer.lock().map_err(|_| "peer")?.reads.len(), reads);
    fs::write(checkout, b"reappeared unowned file\n")?;
    assert!(missing_checkout::apply(state, &planned, &planned.digest()?, at).is_err());
    assert_eq!(fs::read(checkout)?, b"reappeared unowned file\n");
    fs::rename(
        checkout,
        checkout.with_file_name("missing-preserved-reappearance"),
    )?;
    assert_eq!(registry()?, before);
    let writes = peer.lock().map_err(|_| "peer")?.writes.len();
    let completed = missing_checkout::apply(state, &planned, &planned.digest()?, at)?;
    assert_eq!(completed["outcome"], "missing_checkout_binding_retired");
    assert_eq!(completed["checkout_observation"], "absent");
    for field in [
        "remote_write_submitted",
        "harness_files_changed",
        "tasks_changed",
        "installation_authority",
    ] {
        assert_eq!(completed[field], false);
    }
    assert_eq!(peer.lock().map_err(|_| "peer")?.writes.len(), writes);
    assert_eq!(Store::planning_at(local.root_directory())?.version()?, 62);
    fs::create_dir(checkout)?;
    fs::write(checkout.join("keep"), b"future unrelated pathname\n")?;
    let before = registry()?;
    let reads = peer.lock().map_err(|_| "peer")?.reads.len();
    assert_eq!(
        missing_checkout::apply(state, &planned, &planned.digest()?, &expired)?,
        completed
    );
    assert_eq!(
        missing_checkout::status(state, &planned.operation_id)?,
        completed
    );
    assert_eq!(
        project_links::status(state, &binding)?["binding_retirement"],
        completed
    );
    assert_eq!(
        project_links::apply(state, adoption, &adoption.digest()?, None, None, &expired)?,
        *adopted
    );
    assert_eq!(registry()?, before);
    assert_eq!(peer.lock().map_err(|_| "peer")?.reads.len(), reads);
    assert_eq!(fs::read(preserved.join(marker))?, before_marker);
    assert_eq!(fs::read(preserved.join(".env"))?, before_canary);
    assert_eq!(
        fs::metadata(preserved.join(".env"))?.permissions().mode(),
        before_mode
    );
    assert_eq!(
        fs::read(checkout.join("keep"))?,
        b"future unrelated pathname\n"
    );
    Ok(())
}
