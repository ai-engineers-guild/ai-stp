//! Content-addressed writes with explicit head preconditions inside one writer.

use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde_json::{Value, json};

use super::database;
use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    passport,
};

pub enum Write<'a> {
    Advance { expected_heads: &'a [String] },
    Immutable,
}

pub fn seal(document: &Value) -> Result<Value> {
    let mut document = document.clone();
    let fields = document
        .as_object_mut()
        .ok_or_else(|| Failure::input("a passport must be an object"))?;
    for (key, value) in [
        ("schema_version", json!(1)),
        ("parent_revision_ids", json!([])),
        ("visibility", json!("private")),
        ("facts", json!({})),
    ] {
        fields.entry(key).or_insert(value);
    }
    if let Some(facts) = fields.get_mut("facts").and_then(Value::as_object_mut) {
        for fact in facts.values_mut() {
            if let Some(fields) = fact.as_object_mut() {
                for (key, value) in [
                    ("source_refs", json!([])),
                    ("observed_at", Value::Null),
                    ("confirmed_at", Value::Null),
                    ("confidence", Value::Null),
                ] {
                    fields.entry(key).or_insert(value);
                }
            }
        }
    }
    document = canonical::parse(&canonical::bytes(&document)?)?;
    document["revision_id"] = passport::revision_id(&document)?.into();
    passport::validate(&document)?;
    if !passport::stable_id(document["owner_id"].as_str().unwrap_or(""), "account") {
        return Err(Failure::input("passport owner identity is invalid"));
    }
    Ok(document)
}

pub fn heads(transaction: &Transaction<'_>, stable_id: &str) -> Result<Vec<String>> {
    let mut query = transaction
        .prepare("SELECT revision_id FROM head WHERE stable_id = ? ORDER BY revision_id")
        .map_err(database)?;
    query
        .query_map([stable_id], |row| row.get(0))
        .map_err(database)?
        .collect::<std::result::Result<_, _>>()
        .map_err(database)
}

pub fn commit(
    transaction: &Transaction<'_>,
    document: &Value,
    device_id: &str,
    operation_id: Option<&str>,
    write: Write<'_>,
) -> Result<Value> {
    if !passport::stable_id(device_id, "device") {
        return Err(Failure::input("a revision requires a device identity"));
    }
    let document = seal(document)?;
    if matches!(write, Write::Immutable) {
        passport::versions::validate_document(&document)?;
    }
    let text = |field| {
        document[field]
            .as_str()
            .ok_or_else(|| Failure::input("passport identity is incomplete"))
    };
    let id = text("stable_id")?;
    let revision = text("revision_id")?;
    let kind = text("kind")?;
    let created = text("created_at")?;
    if kind == "setup" {
        setup_harness(&document)?;
    }
    let existing: Option<String> = transaction
        .query_row("SELECT kind FROM entity WHERE stable_id = ?", [id], |row| {
            row.get(0)
        })
        .optional()
        .map_err(database)?;
    let current_heads = heads(transaction, id)?;
    if let Some(held) = &existing {
        if held != kind || current_heads.is_empty() {
            return Err(Failure::precondition(
                "the existing entity kind or revision heads are inconsistent",
            ));
        }
        for head in &current_heads {
            let held = Objects {
                connection: transaction,
            }
            .revision(head)?;
            if kind == "setup" && setup_harness(&held)? != setup_harness(&document)? {
                return Err(Failure::precondition(
                    "a setup cannot change its harness after creation",
                ));
            }
            if held["stable_id"] != id || held["owner_id"] != document["owner_id"] {
                return Err(Failure::precondition(
                    "a revision cannot change its entity owner",
                ));
            }
        }
    }
    let known: bool = transaction
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM revision WHERE revision_id = ?)",
            [revision],
            |row| row.get(0),
        )
        .map_err(database)?;
    if known {
        // Replay never rewinds heads. Still verify the bytes at the existing address.
        let held = Objects {
            connection: transaction,
        }
        .revision(revision)?;
        if held != document {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "the stored revision differs from its content address",
            ));
        }
        return Ok(held);
    }
    let parents: Vec<_> = document["parent_revision_ids"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::to_owned)
        .collect();
    match &write {
        Write::Advance { expected_heads } => {
            let mut expected = expected_heads.to_vec();
            expected.sort();
            let mut declared = parents.clone();
            declared.sort();
            if current_heads != expected || declared != expected {
                return Err(Failure::new(
                    ErrorKind::Conflict,
                    "the current heads differ from the planned passport parents",
                ));
            }
        }
        Write::Immutable => {
            if existing.is_none() || !parents.is_empty() {
                return Err(Failure::precondition(
                    "an immutable snapshot requires an existing entity and no draft parents",
                ));
            }
        }
    }
    for parent in &parents {
        let held = Objects {
            connection: transaction,
        }
        .revision(parent)?;
        if held["stable_id"] != id
            || held["owner_id"] != document["owner_id"]
            || held["visibility"] != document["visibility"]
        {
            return Err(Failure::precondition(
                "a draft revision cannot change its entity, owner or visibility",
            ));
        }
    }
    transaction.execute("INSERT INTO entity (stable_id, kind, created_at) VALUES (?, ?, ?) ON CONFLICT (stable_id) DO NOTHING", params![id, kind, created]).map_err(database)?;
    transaction.execute("INSERT INTO revision (revision_id, stable_id, content, device_id, operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?)", params![revision, id, String::from_utf8(canonical::bytes(&document)?).map_err(|_| Failure::input("passport encoding is invalid"))?, device_id, operation_id, created]).map_err(database)?;
    for parent in &parents {
        transaction
            .execute(
                "INSERT INTO revision_parent (revision_id, parent_revision_id) VALUES (?, ?)",
                params![revision, parent],
            )
            .map_err(database)?;
    }
    if matches!(write, Write::Advance { .. }) {
        transaction
            .execute("DELETE FROM head WHERE stable_id = ?", [id])
            .map_err(database)?;
        transaction
            .execute(
                "INSERT INTO head (stable_id, revision_id) VALUES (?, ?)",
                params![id, revision],
            )
            .map_err(database)?;
    }
    Ok(document)
}

pub fn content(transaction: &Transaction<'_>, payload: &[u8], at: &str) -> Result<String> {
    if payload.len() > 64 * 1024 * 1024 || !passport::timestamp(at) {
        return Err(Failure::input(
            "content exceeds its size bound or has an invalid timestamp",
        ));
    }
    let address = digest::bytes("ai-stp:artifact:v1", payload)?;
    transaction.execute("INSERT INTO content (digest, bytes, byte_length, stored_at) VALUES (?, ?, ?, ?) ON CONFLICT (digest) DO NOTHING", params![address, payload, payload.len() as i64, at]).map_err(database)?;
    if read_content(transaction, &address)? != payload {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "the stored content differs from its address",
        ));
    }
    Ok(address)
}

pub fn read_content(connection: &Connection, address: &str) -> Result<Vec<u8>> {
    let row: Option<(Vec<u8>, i64, i64)> = connection
        .query_row(
            "SELECT substr(bytes,1,67108865),byte_length,length(bytes) FROM content WHERE digest=?",
            [address],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .map_err(database)?;
    let (bytes, declared, actual) =
        row.ok_or_else(|| Failure::new(ErrorKind::NotFound, "the component content is absent"))?;
    if bytes.len() > 64 * 1024 * 1024
        || declared != actual
        || actual != bytes.len() as i64
        || digest::bytes("ai-stp:artifact:v1", &bytes)? != address
    {
        return Err(Failure::precondition(
            "the stored component content differs from its address or length",
        ));
    }
    Ok(bytes)
}

fn setup_harness(document: &Value) -> Result<&str> {
    let top = document.get("harness_id");
    let fact = document["facts"]
        .get("harness_id")
        .map(|fact| &fact["value"]);
    if top.is_some() && fact.is_some() && top != fact {
        return Err(Failure::precondition("setup harness declarations disagree"));
    }
    let harness = top
        .or(fact)
        .and_then(Value::as_str)
        .ok_or_else(|| Failure::precondition("a setup requires its harness at creation"))?;
    if harness == "undefined" {
        return Err(Failure::input("a setup requires a concrete harness"));
    }
    crate::harnesses::definition(harness)?;
    Ok(harness)
}
