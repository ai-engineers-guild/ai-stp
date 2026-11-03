//! Fresh native eligibility. Serialized observations never supply cloud rights.

use super::{Target, access, inputs_scope, owner, text};
use crate::{
    account::contexts::Context,
    error::{Failure, Result},
    installation::profiles::Profiles,
    objects::Objects,
    projection::Scope,
    selection::eligibility,
};
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

/// The caller has an exact admitted local intent. Pins, consent and local
/// permissions are explicit decisions from that intent; remote access and all
/// eligibility facts below are re-established through the original account.
pub(crate) fn authorize(
    root: &Path,
    context: &Context,
    setup: &Value,
    expected: &Target,
    placements: &BTreeMap<String, Scope>,
    consented: &BTreeSet<String>,
) -> Result<()> {
    let owner = owner(root)?;
    context.require_current_native_identity(&owner)?;
    if context.root != root || expected.owner_id != owner.account_id || expected.for_redistribution
    {
        return Err(Failure::precondition(
            "native execution changed its original local owner",
        ));
    }
    let (os, arch) = crate::platform::current()
        .and_then(|p| p.split_once('/'))
        .ok_or_else(|| Failure::precondition("native platform is unavailable"))?;
    if expected.os != os || expected.arch != arch {
        return Err(Failure::precondition(
            "native execution requires its original platform",
        ));
    }
    let mut target = Target {
        harness_id: expected.harness_id.clone(),
        scope: expected.scope,
        os: os.into(),
        arch: arch.into(),
        harness_version: String::new(),
        owner_id: owner.account_id.clone(),
        capabilities: Default::default(),
        permissions: expected.permissions.clone(),
        entitlements: Default::default(),
        env_present: Default::default(),
        grants: Default::default(),
        accessible_passport_digests: Default::default(),
        access_context_digest: None,
        pinned_passport_digests: Default::default(),
        owned_passport_digests: Default::default(),
        for_redistribution: false,
    };
    let program = crate::program::observe(&target.harness_id, None)?;
    target.harness_version = program["version"].as_str().unwrap_or("").into();
    if !expected.harness_version.is_empty()
        && expected.harness_version != "unknown"
        && expected.harness_version != target.harness_version
    {
        return Err(Failure::precondition(
            "the observed harness version changed; review a fresh native plan",
        ));
    }
    let request = access::Request::native(context, expected.pinned_passport_digests.clone())?;
    // The account lock precedes the registry, and is released before returning.
    let access = access::Observed::capture(
        root,
        &owner,
        &[vec![setup.clone()]],
        access::Intent::Review(&request),
    )?;
    access.require_native_account(context)?;
    let profiles = Profiles::resolve(&target.harness_id)?;
    let mut store = owner.planning()?;
    store.transaction(|connection| {
        // Original desired payloads were verified before admission and survive
        // source/bundle loss. Current checks need immutable passport metadata,
        // actual declared environment names and fresh private catalog access.
        let mut observed = inputs_scope(
            connection,
            std::slice::from_ref(setup),
            target,
            super::MAX_CONTENT,
            false,
        )?;
        access.apply(&mut observed)?;
        let graph = super::graph::exact(connection, std::slice::from_ref(setup))?;
        if graph["resolved"] != true {
            return Err(Failure::precondition(
                "the original native graph is unavailable",
            ));
        }
        for node in graph["nodes"]
            .as_array()
            .ok_or_else(|| Failure::precondition("native graph nodes missing"))?
        {
            let id = text(node, "stable_id")?;
            let mut evidence = observed
                .evidence
                .get(id)
                .ok_or_else(|| Failure::precondition("native eligibility metadata missing"))?
                .clone();
            evidence.consented = consented.contains(&evidence.passport_digest);
            let document = Objects { connection }.exact_version(
                id,
                text(node, "version")?,
                Some(text(node, "passport_digest")?),
            )?;
            let mut target = observed.target.clone();
            target.scope = placements.get(id).copied().unwrap_or(expected.scope);
            let report =
                eligibility::assess_surface(&document, &target, &evidence, Some(&profiles))?;
            if report["admissible"] != true {
                return Err(Failure::precondition(
                    "current native eligibility refuses this protected effect",
                )
                .with_details([("eligibility".into(), report)]));
            }
        }
        access.revalidate()?;
        Ok(())
    })
}
