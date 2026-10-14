//! Account/origin-bound durable requests. HTTP always runs outside these transactions.

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    http,
    objects::Objects,
    passport,
    store::database,
    wire::Schema,
};

use super::event::Event;

const ORIGIN: &str = "sync.origin";
const MAX_BYTES: usize = http::MAX_BODY as usize;
static RECEIPT: Schema = Schema::new(include_str!(
    "../../../../schemas/v1/sync-event-receipt.schema.json"
));

fn invalid() -> Failure {
    Failure::precondition("the private sync journal or its origin binding is inconsistent")
}

fn conflict() -> Failure {
    Failure::new(
        ErrorKind::Conflict,
        "the sync event identity already names another immutable request or receipt",
    )
}

#[derive(Clone)]
pub struct Scope {
    account: String,
    origin: String,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct OriginPlan {
    schema_version: u32,
    action: String,
    operation_id: String,
    account_id: String,
    origin: String,
    created_at: String,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct OriginReceipt {
    plan: OriginPlan,
    digest: String,
}

impl Scope {
    pub fn new(account: &str, origin: &str) -> Result<Self> {
        let url = http::Endpoint::new(origin)?.base;
        if !passport::stable_id(account, "account")
            || url.path() != "/"
            || url.origin().ascii_serialization() != origin
        {
            return Err(invalid());
        }
        Ok(Self {
            account: account.into(),
            origin: origin.into(),
        })
    }

    pub fn account(&self) -> &str {
        &self.account
    }

    pub fn origin(&self) -> &str {
        &self.origin
    }

    fn recorded(&self, connection: &Connection) -> Result<bool> {
        let mut query = connection.prepare(
            "SELECT o.operation_id,o.state,o.started_at,o.finished_at,e.at,e.state_before,e.state_after,e.result,CASE WHEN length(CAST(e.evidence AS BLOB))<=65536 THEN e.evidence ELSE NULL END FROM operation o LEFT JOIN operation_event e ON e.operation_id=o.operation_id AND e.sequence=1 WHERE o.kind=? AND o.detail=? LIMIT 2"
        ).map_err(database)?;
        let mut rows = query
            .query(params![ORIGIN, self.account])
            .map_err(database)?;
        let Some(row) = rows.next().map_err(database)? else {
            return Ok(false);
        };
        let text = |n| row.get::<_, String>(n).map_err(database);
        let bytes = text(8)?;
        let receipt: OriginReceipt =
            serde_json::from_value(canonical::parse(bytes.as_bytes())?).map_err(|_| invalid())?;
        let plan = &receipt.plan;
        if plan.schema_version != 1
            || plan.action != ORIGIN
            || plan.account_id != self.account
            || plan.origin != self.origin
            || !passport::stable_id(&plan.operation_id, "operation")
            || !passport::timestamp(&plan.created_at)
            || plan.operation_id != text(0)?
            || text(1)? != "verified"
            || [text(2)?, text(3)?, text(4)?]
                .iter()
                .any(|at| at != &plan.created_at)
            || text(5)? != "planned"
            || text(6)? != "verified"
            || text(7)? != "bound"
            || receipt.digest
                != digest::canonical(
                    "ai-stp:plan:v1",
                    &serde_json::to_value(plan).map_err(|_| invalid())?,
                )?
            || rows.next().map_err(database)?.is_some()
        {
            return Err(invalid());
        }
        Ok(true)
    }

    /// The caller authenticates the held account before admitting its first ledger.
    /// An unbound populated ledger has no evidence of origin and cannot be adopted.
    pub fn bind(&self, transaction: &Transaction<'_>, at: &str) -> Result<()> {
        if !passport::timestamp(at) {
            return Err(invalid());
        }
        if self.recorded(transaction)? {
            return Ok(());
        }
        for table in [
            "sync_event",
            "sync_cursor",
            "sync_pending_version",
            "sync_remote_head",
            "sync_abandoned_event",
        ] {
            let populated: bool = transaction
                .query_row(
                    &format!("SELECT EXISTS(SELECT 1 FROM {table} WHERE account_id=?)"),
                    [&self.account],
                    |row| row.get(0),
                )
                .map_err(database)?;
            if populated {
                return Err(Failure::precondition(
                    "the existing private sync ledger has no retained origin binding",
                ));
            }
        }
        let plan = OriginPlan {
            schema_version: 1,
            action: ORIGIN.into(),
            operation_id: format!("operation_{}", ulid::Ulid::generate()),
            account_id: self.account.clone(),
            origin: self.origin.clone(),
            created_at: at.into(),
        };
        let hash = digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(&plan).map_err(|_| invalid())?,
        )?;
        let id = plan.operation_id.clone();
        let evidence = encoded(
            &serde_json::to_value(OriginReceipt { plan, digest: hash }).map_err(|_| invalid())?,
        )?;
        transaction.execute(
            "INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![id, ORIGIN, at, at, self.account],
        ).map_err(database)?;
        transaction.execute(
            "INSERT INTO operation_event(operation_id,sequence,at,state_before,state_after,result,evidence) VALUES (?,1,?,'planned','verified','bound',?)",
            params![id, at, evidence],
        ).map_err(database)?;
        Ok(())
    }

    pub fn require(&self, connection: &Connection) -> Result<()> {
        if !self.recorded(connection)? {
            return Err(invalid());
        }
        Ok(())
    }
}

fn encoded(value: &Value) -> Result<String> {
    let bytes = canonical::bytes(value)?;
    if bytes.len() > MAX_BYTES {
        return Err(Failure::input(
            "the private sync record exceeds its byte limit",
        ));
    }
    String::from_utf8(bytes).map_err(|_| invalid())
}

/// The complete retained wire request, including its original key and precondition.
#[derive(Clone)]
pub struct Pending {
    pub request: Value,
    pub state: String,
    pub local_revision_id: Option<String>,
    pub receipt: Option<Value>,
}

fn local_revision(connection: &Connection, event: &Event) -> Result<Option<String>> {
    if event.passport_kind().is_none() || event.operation != "upsert" {
        return Ok(None);
    }
    let document = event.passport()?;
    let revision = document["revision_id"].as_str().ok_or_else(invalid)?;
    if (Objects { connection }).revision(revision)? != document {
        return Err(invalid());
    }
    Ok(Some(revision.into()))
}

fn read(connection: &Connection, row: &rusqlite::Row<'_>, account: &str) -> Result<Pending> {
    let request: String = row.get(0).map_err(database)?;
    let state: String = row.get(1).map_err(database)?;
    let local_revision_id = row.get(2).map_err(database)?;
    let receipt: Option<String> = row.get(3).map_err(database)?;
    if request.len() > MAX_BYTES || receipt.as_ref().is_some_and(|r| r.len() > MAX_BYTES) {
        return Err(invalid());
    }
    let request = canonical::parse(request.as_bytes())?;
    let event = Event::push(&request, account)?;
    if event.event_id != row.get::<_, String>(4).map_err(database)?
        || event.revision_id != row.get::<_, String>(5).map_err(database)?
        || event.entity_id != row.get::<_, String>(6).map_err(database)?
        || event.revision_id != row.get::<_, String>(7).map_err(database)?
        || event.created_at != row.get::<_, String>(8).map_err(database)?
        || local_revision_id != local_revision(connection, &event)?
        || !matches!(
            state.as_str(),
            "pending" | "accepted" | "conflict" | "rejected" | "superseded"
        )
    {
        return Err(invalid());
    }
    let receipt = receipt
        .map(|body| canonical::parse(body.as_bytes()))
        .transpose()?;
    if let Some(receipt) = &receipt {
        validate_receipt(receipt, &event)?;
        if receipt["state"] != state {
            return Err(invalid());
        }
    } else if state != "pending" {
        return Err(invalid());
    }
    Ok(Pending {
        request,
        state,
        local_revision_id,
        receipt,
    })
}

// The size check executes in SQLite, before allocating an untrusted stored body.
fn columns() -> String {
    format!(
        "CASE WHEN length(CAST(request_json AS BLOB))<={MAX_BYTES} THEN request_json ELSE NULL END,state,local_revision_id,CASE WHEN receipt_json IS NULL OR length(CAST(receipt_json AS BLOB))<={MAX_BYTES} THEN receipt_json ELSE '' END,event_id,remote_revision_id,entity_id,sync_key,created_at"
    )
}

pub fn pending(connection: &Connection, scope: &Scope, entity: &str) -> Result<Option<Pending>> {
    scope.require(connection)?;
    let mut query = connection.prepare(&format!(
        "SELECT {} FROM sync_event WHERE account_id=? AND entity_id=? AND direction='push' AND state='pending' ORDER BY rowid LIMIT 2", columns()
    )).map_err(database)?;
    let mut rows = query
        .query(params![scope.account, entity])
        .map_err(database)?;
    let result = rows
        .next()
        .map_err(database)?
        .map(|row| read(connection, row, &scope.account))
        .transpose()?;
    if rows.next().map_err(database)?.is_some() {
        return Err(invalid());
    }
    Ok(result)
}

/// Persist before HTTP. An unfinished earlier request wins over a new payload.
pub fn retain(transaction: &Transaction<'_>, scope: &Scope, request: &Value) -> Result<Pending> {
    scope.require(transaction)?;
    let event = Event::push(request, &scope.account)?;
    encoded(&json!({"schema_version":1,"events":[request]}))?;
    if let Some(held) = pending(transaction, scope, &event.entity_id)? {
        if held.request["event_id"] == request["event_id"] && held.request != *request {
            return Err(conflict());
        }
        return Ok(held);
    }
    let mut query = transaction.prepare(&format!(
        "SELECT {} FROM sync_event WHERE account_id=? AND direction='push' AND (event_id=? OR remote_revision_id=?) LIMIT 2", columns()
    )).map_err(database)?;
    let mut rows = query
        .query(params![scope.account, event.event_id, event.revision_id])
        .map_err(database)?;
    if let Some(row) = rows.next().map_err(database)? {
        let held = read(transaction, row, &scope.account)?;
        if rows.next().map_err(database)?.is_some()
            || Event::push(&held.request, &scope.account)?.sealed() != event.sealed()
            || (held.request["event_id"] == request["event_id"] && held.request != *request)
        {
            return Err(conflict());
        }
        return Ok(held);
    }
    let local_revision_id = local_revision(transaction, &event)?;
    let body = encoded(request)?;
    transaction.execute(
        "INSERT INTO sync_event(account_id,event_id,sync_key,local_revision_id,remote_revision_id,entity_id,direction,request_json,state,receipt_json,created_at) VALUES (?,?,?,?,?,?,'push',?,'pending',NULL,?)",
        params![scope.account,event.event_id,event.revision_id,local_revision_id,event.revision_id,event.entity_id,body,event.created_at],
    ).map_err(database)?;
    Ok(Pending {
        request: request.clone(),
        state: "pending".into(),
        local_revision_id,
        receipt: None,
    })
}

fn validate_receipt(receipt: &Value, event: &Event) -> Result<()> {
    RECEIPT.validate(receipt)?;
    if receipt["event_id"] != event.event_id
        || (receipt["revision_id"] != Value::Null && receipt["revision_id"] != event.revision_id)
        || (receipt["state"] == "accepted"
            && (receipt["revision_id"] != event.revision_id
                || receipt["server_head_revision_id"] != event.revision_id
                || receipt["conflict"] != Value::Null
                || receipt["conflicting_entity_id"] != Value::Null
                || receipt["error_code"] != Value::Null))
    {
        return Err(conflict());
    }
    // Conflict graph context may name the expected head or a parent, rather
    // than this event's new revision. It is advisory and never advances a head.
    Ok(())
}

/// Receipt persistence never copies a push cursor into the pull cursor table.
pub fn record_receipt(transaction: &Transaction<'_>, scope: &Scope, receipt: &Value) -> Result<()> {
    scope.require(transaction)?;
    RECEIPT.validate(receipt)?;
    let event_id = receipt["event_id"].as_str().ok_or_else(invalid)?;
    let mut query = transaction
        .prepare(&format!(
            "SELECT {} FROM sync_event WHERE account_id=? AND event_id=? AND direction='push'",
            columns()
        ))
        .map_err(database)?;
    let mut rows = query
        .query(params![scope.account, event_id])
        .map_err(database)?;
    let held = read(
        transaction,
        rows.next().map_err(database)?.ok_or_else(invalid)?,
        &scope.account,
    )?;
    let event = Event::push(&held.request, &scope.account)?;
    validate_receipt(receipt, &event)?;
    if let Some(previous) = held.receipt {
        if previous != *receipt {
            return Err(conflict());
        }
        return Ok(());
    }
    let changed = transaction.execute(
        "UPDATE sync_event SET state=?,receipt_json=? WHERE account_id=? AND event_id=? AND direction='push' AND state='pending'",
        params![receipt["state"].as_str().ok_or_else(invalid)?,encoded(receipt)?,scope.account,event_id],
    ).map_err(database)?;
    if changed != 1 {
        return Err(invalid());
    }
    if receipt["state"] == "accepted" {
        advance(transaction, scope, &event)?;
    }
    Ok(())
}

fn advance(transaction: &Transaction<'_>, scope: &Scope, incoming: &Event) -> Result<()> {
    let head: Option<String> = transaction
        .query_row(
            "SELECT remote_revision_id FROM sync_remote_head WHERE account_id=? AND entity_id=?",
            params![scope.account, incoming.entity_id],
            |row| row.get(0),
        )
        .optional()
        .map_err(database)?;
    if head.as_ref() == Some(&incoming.revision_id) {
        return Ok(());
    }
    if let Some(head) = head
        && !incoming.parent_revision_ids.contains(&head)
    {
        let mut seen = std::collections::BTreeSet::new();
        let mut pending = vec![head];
        while let Some(revision) = pending.pop() {
            if !seen.insert(revision.clone()) {
                continue;
            }
            if revision == incoming.revision_id {
                return Ok(());
            }
            if seen.len() > 16_384 {
                return Err(Failure::precondition(
                    "the remote sync ancestry exceeds its bound",
                ));
            }
            let body: Option<String> = transaction.query_row(
                &format!("SELECT CASE WHEN length(CAST(request_json AS BLOB))<={MAX_BYTES} THEN request_json ELSE NULL END FROM sync_event WHERE account_id=? AND remote_revision_id=? AND entity_id=?"),
                params![scope.account,revision,incoming.entity_id], |row| row.get(0),
            ).optional().map_err(database)?;
            let Some(body) = body else {
                // An explicitly skipped ancestor does not prove a rewind is safe.
                return Ok(());
            };
            let value = canonical::parse(body.as_bytes())?;
            let event = if value.get("sequence").is_some() {
                Event::stream(&value, &scope.account)?
            } else {
                Event::push(&value, &scope.account)?
            };
            if event.revision_id != revision || event.entity_id != incoming.entity_id {
                return Err(invalid());
            }
            pending.extend(event.parent_revision_ids);
        }
    }
    transaction.execute(
        "INSERT INTO sync_remote_head(account_id,entity_id,remote_revision_id) VALUES (?,?,?) ON CONFLICT(account_id,entity_id) DO UPDATE SET remote_revision_id=excluded.remote_revision_id",
        params![scope.account,incoming.entity_id,incoming.revision_id],
    ).map_err(database)?;
    Ok(())
}
