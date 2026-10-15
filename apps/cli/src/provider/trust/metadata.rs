//! TUF signatures stay in the upstream core; persistent rollback floors are explicit.

use std::collections::BTreeMap;

use sigstore_tuf::{Metadata, Root, Snapshot, Timestamp, TrustedMetadataSet, metadata::Role};

use super::{Evidence, MAX_METADATA, State, invalid};
use crate::{error::Result, wire};

pub(super) fn parse<T: Role>(bytes: &[u8]) -> Result<Metadata<T>> {
    if bytes.is_empty() || bytes.len() > MAX_METADATA {
        return Err(invalid());
    }
    // Reject duplicate/ambiguous JSON without changing the bytes TUF signs.
    wire::parse(bytes)?;
    let metadata = Metadata::<T>::from_slice(bytes).map_err(|_| invalid())?;
    if metadata.signed().version() == 0 || metadata.signed().version() >= 9_007_199_254_740_991 {
        return Err(invalid());
    }
    metadata.signed().expires_at().map_err(|_| invalid())?;
    Ok(metadata)
}

pub(super) fn fresh<T: Role>(metadata: &T, now: jiff::Timestamp) -> Result<()> {
    if metadata.expires_at().map_err(|_| invalid())? <= now {
        return Err(invalid());
    }
    Ok(())
}

pub(super) fn signed<T: Role>(bytes: &[u8], root: &Root) -> Result<Metadata<T>> {
    let metadata = parse::<T>(bytes)?;
    metadata
        .verify_threshold(&root.keys, root.role(T::TYPE).ok_or_else(invalid)?, T::TYPE)
        .map_err(|_| invalid())?;
    Ok(metadata)
}

#[derive(Default)]
pub(super) struct Floors {
    timestamp: Option<Timestamp>,
    snapshot: Option<Snapshot>,
}

pub(super) fn restore(state: &State, bootstrap: &[u8]) -> Result<(TrustedMetadataSet, Floors)> {
    if state.schema_version != 1 || state.roots.len() > 256 {
        return Err(invalid());
    }
    parse::<Root>(bootstrap)?;
    let mut trusted = TrustedMetadataSet::from_root(bootstrap).map_err(|_| invalid())?;
    let mut reset_index = 0;
    for (index, root) in state.roots.iter().enumerate() {
        let next = parse::<Root>(root.as_bytes())?;
        if online_keys_changed(trusted.root(), next.signed())? {
            reset_index = index + 1;
        }
        trusted
            .update_root(root.as_bytes())
            .map_err(|_| invalid())?;
    }
    // A threshold-only root change must preserve old authenticated floors.
    // Their original root authenticates history; only the latest root can
    // authorize new metadata or the target used by this refresh.
    let retained = |evidence: &Evidence| -> Result<Metadata<Root>> {
        if evidence.root_index < reset_index || evidence.root_index > state.roots.len() {
            return Err(invalid());
        }
        let bytes = if evidence.root_index == 0 {
            bootstrap
        } else {
            state.roots[evidence.root_index - 1].as_bytes()
        };
        parse::<Root>(bytes)
    };
    let mut floors = Floors::default();
    if let Some(evidence) = &state.timestamp {
        let timestamp =
            signed::<Timestamp>(evidence.bytes.as_bytes(), retained(evidence)?.signed())?;
        timestamp_shape(timestamp.signed())?;
        floors.timestamp = Some(timestamp.signed().clone());
    }
    if let Some(evidence) = &state.snapshot {
        let snapshot = signed::<Snapshot>(evidence.bytes.as_bytes(), retained(evidence)?.signed())?;
        snapshot_shape(snapshot.signed())?;
        if floors
            .timestamp
            .as_ref()
            .and_then(Timestamp::snapshot_meta)
            .is_none_or(|pin| snapshot.signed().version > pin.version)
        {
            return Err(invalid());
        }
        floors.snapshot = Some(snapshot.signed().clone());
    }
    Ok((trusted, floors))
}

fn timestamp_shape(timestamp: &Timestamp) -> Result<()> {
    if timestamp.meta.len() != 1 || timestamp.snapshot_meta().is_none_or(|pin| pin.version == 0) {
        return Err(invalid());
    }
    Ok(())
}

fn snapshot_shape(snapshot: &Snapshot) -> Result<()> {
    if !snapshot.meta.contains_key("targets.json")
        || snapshot.meta.len() > 4096
        || snapshot.meta.values().any(|pin| pin.version == 0)
    {
        return Err(invalid());
    }
    Ok(())
}

pub(super) fn timestamp(
    trusted: &mut TrustedMetadataSet,
    floors: &Floors,
    bytes: &[u8],
    now: jiff::Timestamp,
) -> Result<String> {
    let candidate = parse::<Timestamp>(bytes)?;
    timestamp_shape(candidate.signed())?;
    if let Some(previous) = &floors.timestamp
        && (candidate.signed().version < previous.version
            || (candidate.signed().version == previous.version && candidate.signed() != previous)
            || candidate
                .signed()
                .snapshot_meta()
                .ok_or_else(invalid)?
                .version
                < previous.snapshot_meta().ok_or_else(invalid)?.version)
    {
        return Err(invalid());
    }
    // Equal versions may gain signatures after a threshold increase, but their
    // signed content (including expiry and pins) cannot change.
    trusted
        .update_timestamp(bytes, now)
        .map_err(|_| invalid())?;
    fresh(candidate.signed(), now)?;
    String::from_utf8(bytes.to_vec()).map_err(|_| invalid())
}

pub(super) fn snapshot(
    trusted: &mut TrustedMetadataSet,
    floors: &Floors,
    bytes: &[u8],
    now: jiff::Timestamp,
) -> Result<String> {
    let candidate = parse::<Snapshot>(bytes)?;
    snapshot_shape(candidate.signed())?;
    // A failed refresh can leave a newer timestamp beside an older snapshot.
    // Authenticate the old snapshot independently: comparing it to the new
    // timestamp pin would discard the very floors needed after a restart.
    if let Some(previous) = &floors.snapshot
        && (candidate.signed().version < previous.version
            || (candidate.signed().version == previous.version && candidate.signed() != previous)
            || previous.meta.iter().any(|(name, floor)| {
                candidate
                    .signed()
                    .meta
                    .get(name)
                    .is_none_or(|next| next.version < floor.version)
            }))
    {
        return Err(invalid());
    }
    trusted.update_snapshot(bytes, now).map_err(|_| invalid())?;
    fresh(candidate.signed(), now)?;
    String::from_utf8(bytes.to_vec()).map_err(|_| invalid())
}

pub(super) fn online_keys_changed(old: &Root, new: &Root) -> Result<bool> {
    for role in ["timestamp", "snapshot"] {
        let keys = |root: &Root| -> Result<BTreeMap<String, sigstore_tuf::key::Key>> {
            root.role(role)
                .ok_or_else(invalid)?
                .keyids
                .iter()
                .map(|id| {
                    let mut key = root.keys.get(id).ok_or_else(invalid)?.clone();
                    // Publisher annotations do not rotate verification authority.
                    key.extra.clear();
                    key.keyval.extra.clear();
                    Ok((id.clone(), key))
                })
                .collect()
        };
        if keys(old)? != keys(new)? {
            return Ok(true);
        }
    }
    Ok(false)
}
