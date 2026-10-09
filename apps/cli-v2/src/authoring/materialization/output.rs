//! Immutable output allocation and private provenance inside the caller's writer.

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Identity, Mode, Plan, Request, exact, invalid, text, verify};
use crate::{
    error::{Failure, Result},
    objects::Objects,
    passport,
    store::{
        database,
        revisions::{self, Write},
        versions::{self, Increment},
    },
};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Effect {
    Blocked,
    Reuse,
    RecordVersion,
    CreateOverlay,
    ReuseOverlay,
}

fn origin(connection: &Connection, request: &Request, document: &Value) -> Result<()> {
    let id = text(document, "stable_id")?;
    let fork: Option<(String,String,String,String)> = connection.query_row(
        "SELECT source_stable_id,source_version,source_digest,created_at FROM fork_origin WHERE stable_id=?",
        [id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).optional().map_err(database)?;
    let expected = (
        request.source.stable_id.clone(),
        request.source.version.clone(),
        request.source.passport_digest.clone(),
        text(document, "created_at")?.into(),
    );
    let overlay: Option<(String,String,String,String)> = connection.query_row(
        "SELECT source_kind,source_ref,base_digest,applied_at FROM overlay_origin WHERE revision_id=?",
        [text(document,"revision_id")?],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).optional().map_err(database)?;
    let Some((kind, source, base, applied)) = overlay else {
        return Err(invalid());
    };
    if fork != Some(expected)
        || kind != "generated"
        || source != request.source.passport_digest
        || base != source
        || !passport::timestamp(&applied)
    {
        return Err(invalid());
    }
    Ok(())
}

pub(super) fn prepare(
    connection: &Connection,
    request: &Request,
    mut document: Value,
    changed: bool,
    identity: &Identity,
    at: &str,
) -> Result<(Effect, Value)> {
    if request.output == Mode::Owned {
        if !changed {
            return Ok((Effect::Reuse, document));
        }
        let latest: String = connection.query_row(
            "SELECT version FROM object_version WHERE stable_id=? ORDER BY major DESC,minor DESC LIMIT 1",
            [&request.source.stable_id],|r|r.get(0)).map_err(database)?;
        if latest != request.source.version {
            return Err(Failure::precondition(
                "owned derivation requires the latest immutable source version",
            ));
        }
        document["version"] =
            versions::next(connection, &request.source.stable_id, Increment::Minor)?.into();
        document["created_at"] = at.into();
        document["parent_revision_ids"] = json!([]);
        let document = revisions::seal(&document)?;
        passport::versions::validate_document(&document)?;
        return Ok((Effect::RecordVersion, document));
    }
    let id = request.overlay_id.as_deref().ok_or_else(invalid)?;
    let objects = Objects { connection };
    objects.require_active(id)?;
    let exists: bool = connection
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM entity WHERE stable_id=?)",
            [id],
            |r| r.get(0),
        )
        .map_err(database)?;
    let existing = if exists {
        let held = exact(connection, id, "1.0", None)?;
        let head = objects.head("component", id)?;
        if held["owner_id"] != identity.account_id
            || head["owner_id"] != identity.account_id
            || held["visibility"] != "private"
            || head["visibility"] != "private"
        {
            return Err(invalid());
        }
        verify(connection, &held)?;
        origin(connection, request, &held)?;
        Some(held)
    } else {
        None
    };
    let created = existing
        .as_ref()
        .map(|d| text(d, "created_at"))
        .transpose()?
        .unwrap_or(at);
    document["stable_id"] = id.into();
    document["owner_id"] = identity.account_id.clone().into();
    document["visibility"] = "private".into();
    document["version"] = "1.0".into();
    document["created_at"] = created.into();
    document["parent_revision_ids"] = json!([]);
    document["compatibility_evidence_refs"] = json!([]);
    // Facts are also presented by passport readers; source evidence cannot be
    // presented as evidence for a new component identity through either surface.
    document["facts"]
        .as_object_mut()
        .ok_or_else(invalid)?
        .remove("compatibility_evidence_refs");
    document["facts"]["source_component"] = json!({"value":request.source,
        "origin":"derived","confirmation":"none","observed_at":created});
    let document = revisions::seal(&document)?;
    passport::versions::validate_document(&document)?;
    if let Some(held) = existing {
        if document != held {
            return Err(Failure::precondition(
                "the private output identity already has different immutable content",
            ));
        }
        Ok((Effect::ReuseOverlay, document))
    } else {
        Ok((Effect::CreateOverlay, document))
    }
}

pub(super) fn record(
    transaction: &Transaction<'_>,
    plan: &Plan,
    document: &Value,
    at: &str,
) -> Result<()> {
    match plan.effect {
        Effect::CreateOverlay => {
            revisions::commit(
                transaction,
                document,
                &plan.identity.device_id,
                Some(&plan.operation_id),
                Write::Advance {
                    expected_heads: &[],
                },
            )?;
            versions::record(
                transaction,
                document,
                &plan.identity.device_id,
                Some(&plan.operation_id),
                at,
            )?;
            transaction.execute("INSERT INTO fork_origin(stable_id,source_stable_id,source_version,source_digest,created_at) VALUES (?,?,?,?,?)",
                params![text(document,"stable_id")?,plan.request.source.stable_id,plan.request.source.version,
                    plan.request.source.passport_digest,text(document,"created_at")?]).map_err(database)?;
            transaction.execute("INSERT INTO overlay_origin(revision_id,source_kind,source_ref,base_digest,applied_at) VALUES (?,'generated',?,?,?)",
                params![text(document,"revision_id")?,plan.request.source.passport_digest,plan.request.source.passport_digest,at]).map_err(database)?;
        }
        Effect::RecordVersion => {
            versions::record(
                transaction,
                document,
                &plan.identity.device_id,
                Some(&plan.operation_id),
                at,
            )?;
        }
        Effect::Reuse | Effect::ReuseOverlay => {}
        Effect::Blocked => return Err(invalid()),
    }
    Ok(())
}

pub(super) fn replay(connection: &Connection, plan: &Plan) -> Result<Value> {
    let expected = plan.passport.as_ref().ok_or_else(invalid)?;
    let document = exact(
        connection,
        text(expected, "stable_id")?,
        text(expected, "version")?,
        None,
    )?;
    if &document != expected {
        return Err(invalid());
    }
    verify(connection, &document)?;
    if plan.request.output == Mode::Private {
        origin(connection, &plan.request, &document)?;
    }
    Ok(document)
}
