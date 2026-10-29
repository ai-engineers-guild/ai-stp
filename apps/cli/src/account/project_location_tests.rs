//! Real local location transitions through the independent corporate HTTP peer.

use super::*;
use crate::account::project_links::location;

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
    let (_, original) = project_links::binding::capture(state, &binding)?;
    let parent = checkout.parent().ok_or("parent")?;
    let moved = parent.join("location-cafe\u{301}");
    let marker = ".ai-stp-v2-project/project-id";
    let marker_before = fs::read(checkout.join(marker))?;
    let canary_before = fs::read(checkout.join(".env"))?;
    let mode_before = fs::metadata(checkout.join(".env"))?.permissions().mode();
    let registry = || -> std::result::Result<Vec<u8>, Box<dyn Error>> {
        Ok(Store::planning_at(local.root_directory())?
            .connection
            .serialize("main")?
            .to_vec())
    };
    let before = registry()?;
    fs::rename(checkout, &moved)?;
    let unanchored =
        location::relocation_plan(state, Some(&contexts[0]), &binding, &moved, None, at);
    fs::rename(&moved, checkout)?;
    assert!(unanchored.is_err());
    assert_eq!(registry()?, before);

    let anchor = location::anchor_plan(state, Some(&contexts[0]), &binding, None, at)?;
    let stale_anchor = location::anchor_plan(state, Some(&contexts[0]), &binding, None, at)?;
    let anchor: location::Plan =
        serde_json::from_slice(&crate::canonical::bytes(&serde_json::to_value(anchor)?)?)?;
    let anchored = location::apply(state, &anchor, &anchor.digest()?, None, at)?;
    assert_eq!(anchored["outcome"], "location_anchored");
    assert_eq!(Store::planning_at(local.root_directory())?.version()?, 61);
    let before = registry()?;
    assert!(location::apply(state, &stale_anchor, &stale_anchor.digest()?, None, at).is_err());
    assert_eq!(registry()?, before);
    assert_eq!(fs::read(checkout.join(marker))?, marker_before);

    fs::rename(checkout, &moved)?;
    fs::create_dir(checkout)?;
    fs::write(checkout.join("keep"), b"unrelated restored path\n")?;
    assert!(
        location::relocation_plan(state, Some(&contexts[0]), &binding, &moved, None, at).is_err()
    );
    assert_eq!(registry()?, before);
    let replacement = parent.join("preserved-location-replacement");
    fs::rename(checkout, &replacement)?;

    git(&moved, &["checkout", "-b", "changed-after-anchor"])?;
    assert!(
        location::relocation_plan(state, Some(&contexts[0]), &binding, &moved, None, at).is_err()
    );
    git(&moved, &["checkout", "main"])?;
    assert!(
        location::relocation_plan(state, Some(&contexts[1]), &binding, &moved, None, at).is_err()
    );
    assert_eq!(registry()?, before);

    let plan = location::relocation_plan(state, Some(&contexts[0]), &binding, &moved, None, at)?;
    peer.lock().map_err(|_| "peer")?.deny_link = true;
    let revoked = location::apply(state, &plan, &plan.digest()?, None, at);
    peer.lock().map_err(|_| "peer")?.deny_link = false;
    assert!(revoked.is_err());
    assert_eq!(registry()?, before);
    assert_eq!(fs::read(moved.join(marker))?, marker_before);
    let expired = after(at, 901)?;
    assert!(location::apply(state, &plan, &plan.digest()?, None, &expired).is_err());
    assert_eq!(registry()?, before);
    let completed = location::apply(state, &plan, &plan.digest()?, None, at)?;
    assert_eq!(completed["outcome"], "checkout_relocated");
    assert_eq!(completed["installation_authority"], false);
    assert_eq!(completed["remote_write_submitted"], false);
    assert_eq!(completed["tasks_changed"], false);
    assert_eq!(completed["harness_files_changed"], false);
    let (_, current) = project_links::binding::capture(state, &binding)?;
    assert_eq!(current.checkout_root, fs::canonicalize(&moved)?);
    assert!(current.source == original.source);
    assert!(current.request == original.request);
    assert!(current.reservation == original.reservation);
    assert!(current.location.is_some());
    assert_eq!(
        current.local_project["stable_id"],
        original.local_project["stable_id"]
    );
    assert_ne!(
        current.local_project["revision_id"],
        original.local_project["revision_id"]
    );

    let before = registry()?;
    let reads = peer.lock().map_err(|_| "peer")?.reads.len();
    assert_eq!(
        location::apply(state, &plan, &plan.digest()?, None, &expired)?,
        completed
    );
    assert_eq!(
        location::apply(state, &anchor, &anchor.digest()?, None, &expired)?,
        anchored
    );
    assert_eq!(
        project_links::apply(state, adoption, &adoption.digest()?, None, None, &expired)?,
        *adopted
    );
    assert_eq!(peer.lock().map_err(|_| "peer")?.reads.len(), reads);
    assert_eq!(registry()?, before);

    let future = parent.join("future-location");
    fs::rename(&moved, &future)?;
    let second = location::relocation_plan(state, Some(&contexts[0]), &binding, &future, None, at)?;
    location::apply(state, &second, &second.digest()?, None, at)?;
    let before = registry()?;
    let reads = peer.lock().map_err(|_| "peer")?.reads.len();
    assert_eq!(
        location::apply(state, &plan, &plan.digest()?, None, &expired)?,
        completed
    );
    assert_eq!(
        location::apply(state, &anchor, &anchor.digest()?, None, &expired)?,
        anchored
    );
    assert_eq!(peer.lock().map_err(|_| "peer")?.reads.len(), reads);
    assert_eq!(registry()?, before);
    assert_eq!(
        project_links::binding::capture(state, &binding)?
            .1
            .checkout_root,
        fs::canonicalize(&future)?
    );
    fs::rename(&future, checkout)?;
    let returned =
        location::relocation_plan(state, Some(&contexts[0]), &binding, checkout, None, at)?;
    location::apply(state, &returned, &returned.digest()?, None, at)?;
    assert_eq!(fs::read(checkout.join(marker))?, marker_before);
    assert_eq!(fs::read(checkout.join(".env"))?, canary_before);
    assert_eq!(
        fs::metadata(checkout.join(".env"))?.permissions().mode(),
        mode_before
    );
    assert_eq!(
        fs::read(replacement.join("keep"))?,
        b"unrelated restored path\n"
    );
    Ok(())
}
