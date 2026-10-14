//! A received page and its opaque cursor commit together, without network I/O.

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde_json::{Value, json};
use std::collections::BTreeSet;

use crate::{
    canonical,
    error::{ErrorKind, Failure, Result},
    http, passport,
    store::{
        Store, database,
        revisions::{self, Write},
    },
};

use super::{
    event::Event,
    ledger::{self, Scope},
    network, versions,
};

fn invalid() -> Failure {
    Failure::precondition("the private sync page disagrees with its retained account history")
}

fn encode(value: &Value) -> Result<String> {
    let bytes = canonical::bytes(value)?;
    if bytes.len() as u64 > http::MAX_BODY {
        return Err(invalid());
    }
    String::from_utf8(bytes).map_err(|_| invalid())
}

pub fn cursor(connection: &Connection, scope: &Scope) -> Result<Option<String>> {
    scope.require(connection)?;
    let held: Option<Option<String>> = connection
        .query_row(
            "SELECT cursor FROM sync_cursor WHERE account_id=?",
            [scope.account()],
            |r| r.get(0),
        )
        .optional()
        .map_err(database)?;
    let held = held.flatten();
    if held.as_deref().is_some_and(|v| !network::cursor(v)) {
        return Err(invalid());
    }
    Ok(held)
}

pub fn apply(
    store: &mut Store,
    scope: &Scope,
    response: &Value,
    expected_cursor: Option<&str>,
    page_size: u16,
    skip: &BTreeSet<String>,
    at: &str,
) -> Result<Value> {
    store.transaction(|t| {
        apply_transaction(t, scope, response, expected_cursor, page_size, skip, at)
    })
}

pub(super) fn apply_transaction(
    t: &Transaction<'_>,
    scope: &Scope,
    response: &Value,
    expected_cursor: Option<&str>,
    page_size: u16,
    skip: &BTreeSet<String>,
    at: &str,
) -> Result<Value> {
    let request = network::Request::Pull {
        cursor: expected_cursor,
        page_size,
    };
    request.validate(scope.account(), "")?;
    request.response(response.clone(), scope.account())?;
    encode(response)?;
    if !passport::timestamp(at)
        || skip.len() > 100
        || skip.iter().any(|id| {
            !(8..=128).contains(&id.len())
                || !id
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'~' | b'-'))
        })
    {
        return Err(invalid());
    }
    if cursor(t, scope)?.as_deref() != expected_cursor {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "the sync pull position changed before page application",
        ));
    }
    for id in skip {
        t.execute("INSERT INTO sync_abandoned_event(account_id,event_id,abandoned_at) VALUES (?,?,?) ON CONFLICT(account_id,event_id) DO NOTHING",
                params![scope.account(),id,at]).map_err(database)?;
    }
    let mut applied = 0;
    let mut replayed = 0;
    let mut skipped = Vec::new();
    for raw in response["items"].as_array().ok_or_else(invalid)? {
        let id = raw["event_id"].as_str().ok_or_else(invalid)?;
        let abandoned: bool = t.query_row("SELECT EXISTS(SELECT 1 FROM sync_abandoned_event WHERE account_id=? AND event_id=?)",
                params![scope.account(),id], |r|r.get(0)).map_err(database)?;
        if abandoned {
            skipped.push(id.to_owned());
            continue;
        }
        let result =
            Event::stream(raw, scope.account()).and_then(|event| apply_event(t, scope, &event));
        match result {
            Ok(true) => replayed += 1,
            Ok(false) => applied += 1,
            Err(mut failure) => {
                failure.details.insert("event_id".into(), id.into());
                failure
                    .details
                    .insert("entity_id".into(), raw["entity_id"].clone());
                return Err(failure);
            }
        }
    }
    versions::reconcile(t, scope)?;
    if response["page"]["next_cursor"].is_null() {
        // A final/empty page must not reset a previously retained position.
        t.execute("INSERT INTO sync_cursor(account_id,cursor,updated_at) VALUES (?,NULL,?) ON CONFLICT(account_id) DO UPDATE SET updated_at=excluded.updated_at",
                params![scope.account(),at]).map_err(database)?;
    } else {
        let next = response["page"]["next_cursor"]
            .as_str()
            .ok_or_else(invalid)?;
        t.execute("INSERT INTO sync_cursor(account_id,cursor,updated_at) VALUES (?,?,?) ON CONFLICT(account_id) DO UPDATE SET cursor=excluded.cursor,updated_at=excluded.updated_at",
                params![scope.account(),next,at]).map_err(database)?;
    }
    let pending: i64 = t
        .query_row(
            "SELECT count(*) FROM sync_pending_version WHERE account_id=?",
            [scope.account()],
            |r| r.get(0),
        )
        .map_err(database)?;
    Ok(
        json!({"schema_version":1,"account_id":scope.account(),"api_origin":scope.origin(),
            "applied":applied,"replayed":replayed,"skipped_event_ids":skipped,
            "cursor":cursor(t,scope)?,"pending_version_count":pending}),
    )
}

fn known(t: &Transaction<'_>, scope: &Scope, event: &Event) -> Result<bool> {
    let mut query = t.prepare(&format!("SELECT event_id,direction,state,remote_revision_id,entity_id,CASE WHEN length(CAST(request_json AS BLOB))<={} THEN request_json ELSE NULL END,local_revision_id,sync_key,created_at FROM sync_event WHERE account_id=? AND (event_id=? OR remote_revision_id=?) LIMIT 2",http::MAX_BODY)).map_err(database)?;
    let mut rows = query
        .query(params![scope.account(), event.event_id, event.revision_id])
        .map_err(database)?;
    let Some(row) = rows.next().map_err(database)? else {
        return Ok(false);
    };
    let id: String = row.get(0).map_err(database)?;
    let direction: String = row.get(1).map_err(database)?;
    let state: String = row.get(2).map_err(database)?;
    let revision: String = row.get(3).map_err(database)?;
    let entity: String = row.get(4).map_err(database)?;
    let body: String = row.get(5).map_err(database)?;
    let local: Option<String> = row.get(6).map_err(database)?;
    let key: String = row.get(7).map_err(database)?;
    let created: String = row.get(8).map_err(database)?;
    let value = canonical::parse(body.as_bytes())?;
    let held = match direction.as_str() {
        "push" => Event::push(&value, scope.account())?,
        "pull" if state == "accepted" => Event::stream(&value, scope.account())?,
        _ => return Err(invalid()),
    };
    if held.event_id != id
        || held.revision_id != revision
        || held.entity_id != entity
        || held.sealed() != event.sealed()
        || local != ledger::local_revision(t, &held)?
        || key != revision
        || created != held.created_at
        || (direction == "pull" && held.sequence != event.sequence)
        || rows.next().map_err(database)?.is_some()
    {
        return Err(invalid());
    }
    if direction == "push" {
        ledger::recorded(t, scope, &id)?;
    }
    if direction == "push" && matches!(state.as_str(), "pending" | "failed") && id == event.event_id
    {
        ledger::record_receipt(
            t,
            scope,
            &json!({"schema_version":1,"event_id":id,"state":"accepted",
            "revision_id":revision,"server_head_revision_id":revision,"cursor":null,
            "conflict":null,"conflicting_entity_id":null,"error_code":null}),
        )?;
    }
    Ok(true)
}

fn apply_event(t: &Transaction<'_>, scope: &Scope, event: &Event) -> Result<bool> {
    if known(t, scope, event)? {
        if let Some(kind) = event.passport_kind()
            && event.operation == "upsert"
        {
            for binding in versions::bindings(&event.payload, &event.entity_id, kind)? {
                versions::receive(
                    t,
                    scope,
                    &event.entity_id,
                    kind,
                    &event.event_id,
                    &event.device_id,
                    &binding,
                )?;
            }
        }
        ledger::advance(t, scope, event)?;
        return Ok(true);
    }
    let mut local_revision = None;
    if let Some(kind) = event.passport_kind() {
        if event.operation == "upsert" {
            // One developer passport per installation remains a hard boundary.
            if kind == "developer" {
                let other: bool = t.query_row("SELECT EXISTS(SELECT 1 FROM entity WHERE kind='developer' AND stable_id<>?)",
                    [&event.entity_id], |r|r.get(0)).map_err(database)?;
                if other {
                    return Err(Failure::new(
                        ErrorKind::Conflict,
                        "the received account uses another developer identity",
                    ));
                }
            }
            let document = event.passport()?;
            revisions::commit(
                t,
                &document,
                &event.device_id,
                None,
                Write::Received {
                    account_id: scope.account(),
                },
            )?;
            local_revision = document["revision_id"].as_str().map(str::to_owned);
            for binding in versions::bindings(&event.payload, &event.entity_id, kind)? {
                versions::receive(
                    t,
                    scope,
                    &event.entity_id,
                    kind,
                    &event.event_id,
                    &event.device_id,
                    &binding,
                )?;
            }
        } else {
            t.execute("INSERT INTO tombstone(stable_id,reason,created_at) VALUES (?,'received_account_tombstone',?) ON CONFLICT(stable_id) DO NOTHING",
                params![event.entity_id,event.created_at]).map_err(database)?;
        }
    }
    // Foreign device summaries only acknowledge their validated stream event.
    let value = serde_json::to_value(event).map_err(|_| invalid())?;
    t.execute("INSERT INTO sync_event(account_id,event_id,sync_key,local_revision_id,remote_revision_id,entity_id,direction,request_json,state,receipt_json,created_at) VALUES (?,?,?,?,?,?,'pull',?,'accepted',NULL,?)",
        params![scope.account(),event.event_id,event.revision_id,local_revision,event.revision_id,event.entity_id,encode(&value)?,event.created_at]).map_err(database)?;
    ledger::advance(t, scope, event)?;
    if event.entity_kind == "unverified_consent" {
        let current: bool = t.query_row("SELECT EXISTS(SELECT 1 FROM sync_remote_head WHERE account_id=? AND entity_id=? AND remote_revision_id=?)",
            params![scope.account(),event.entity_id,event.revision_id],|r|r.get(0)).map_err(database)?;
        if current {
            consent(t, scope, event)?;
        }
    }
    Ok(false)
}

fn consent(t: &Transaction<'_>, scope: &Scope, event: &Event) -> Result<()> {
    let value = &event.payload;
    let text = |key| value[key].as_str().ok_or_else(invalid);
    if event.operation == "tombstone" {
        let at = value["revoked_at"].as_str().unwrap_or(&event.created_at);
        if !passport::timestamp(at) {
            return Err(invalid());
        }
        t.execute("UPDATE consent SET revoked_at=? WHERE account_id=? AND scope=? AND target=? AND revoked_at IS NULL",
            params![at,scope.account(),text("scope")?,text("target")?]).map_err(database)?;
    } else {
        if !passport::timestamp(text("created_at")?) {
            return Err(invalid());
        }
        let mut observed = value["observed"].as_array().ok_or_else(invalid)?.clone();
        observed.sort_by(|a, b| a.as_str().cmp(&b.as_str()));
        t.execute("INSERT INTO consent(consent_id,account_id,scope,target,fingerprint,observed,decided_by,origin,created_at,revoked_at) VALUES (?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(account_id,scope,target) DO UPDATE SET consent_id=excluded.consent_id,fingerprint=excluded.fingerprint,observed=excluded.observed,decided_by=excluded.decided_by,origin=excluded.origin,created_at=excluded.created_at,revoked_at=NULL",
            params![event.entity_id,scope.account(),text("scope")?,text("target")?,encode(&value["fingerprint"])?,encode(&json!(observed))?,text("decided_by")?,text("origin")?,text("created_at")?]).map_err(database)?;
    }
    Ok(())
}
