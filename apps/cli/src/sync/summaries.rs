//! Closed device and account-consent projections, never full local passports.

use super::push::{Capture, Step, absent};
use crate::{
    authoring::Identity,
    canonical, digest,
    error::{Failure, Result},
    passport,
    store::database,
};
use rusqlite::{Connection, params};
use serde_json::{Value, json};

fn invalid() -> Failure {
    Failure::precondition("the local record cannot form a permitted private sync summary")
}

pub(super) fn device(document: &Value, identity: &Identity) -> Result<Capture> {
    if document["stable_id"] != identity.device_id || document["visibility"] != "private" {
        return Err(invalid());
    }
    let at = document["created_at"].as_str().ok_or_else(invalid)?;
    let payload = json!({"schema_version":1,"display_name":"ai-stp Rust CLI",
        "operating_system":document["facts"]["operating_system"]["value"],
        "architecture":document["facts"]["architecture"]["value"],
        "detected_harnesses":[],"toolchain_profile_version":format!("ai-stp-cli-v2/{}",env!("CARGO_PKG_VERSION")),
        "summary_updated_at":at});
    // Only fields this native passport actually observes are projected. An empty
    // harness list is not evidence of an absent harness and triggers no install.
    let result = Capture {
        entity_id: identity.device_id.clone(),
        entity_kind: "device_summary".into(),
        local_revision: document["revision_id"].as_str().ok_or_else(invalid)?.into(),
        steps: vec![Step {
            local_revision: None,
            local_parents: vec![],
            operation: "upsert".into(),
            payload,
            created_at: at.into(),
        }],
        tombstone: None,
    };
    validate(&result, identity)?;
    Ok(result)
}

pub(super) fn consent(connection: &Connection, identity: &Identity, id: &str) -> Result<Capture> {
    if !(id.starts_with("consent_") || id.starts_with("request_")) || id.len() > 128 {
        return Err(absent());
    }
    let mut query=connection.prepare("SELECT consent_id,scope,target,CASE WHEN length(CAST(fingerprint AS BLOB))<=65536 THEN fingerprint ELSE NULL END,CASE WHEN length(CAST(observed AS BLOB))<=65536 THEN observed ELSE NULL END,decided_by,origin,created_at,revoked_at FROM consent WHERE account_id=? ORDER BY consent_id LIMIT 16385").map_err(database)?;
    let mut rows = query
        .query(params![identity.account_id])
        .map_err(database)?;
    let mut result = None;
    let mut count = 0;
    while let Some(row) = rows.next().map_err(database)? {
        count += 1;
        if count > 16384 {
            return Err(invalid());
        }
        let text = |n| row.get::<_, String>(n).map_err(database);
        let scope = text(1)?;
        let target = text(2)?;
        let hash = digest::sha256(format!("{scope}\0{target}").as_bytes());
        let entity = format!("consent_{}", &hash[7..39]);
        if id != text(0)? && id != entity {
            continue;
        }
        if result.is_some() {
            return Err(invalid());
        }
        let revoked: Option<String> = row.get(8).map_err(database)?;
        let at = revoked.clone().unwrap_or(text(7)?);
        if !passport::timestamp(&at) {
            return Err(invalid());
        }
        let payload = if revoked.is_some() {
            json!({"schema_version":1,"scope":scope,"target":target,"revoked_at":at})
        } else {
            json!({"schema_version":1,"scope":scope,"target":target,
                "fingerprint":canonical::parse(text(3)?.as_bytes())?,"observed":canonical::parse(text(4)?.as_bytes())?,
                "decided_by":text(5)?,"origin":text(6)?,"created_at":at})
        };
        result = Some(Capture {
            entity_id: entity,
            entity_kind: "unverified_consent".into(),
            local_revision: passport::revision_id(&payload)?,
            steps: vec![Step {
                local_revision: None,
                local_parents: vec![],
                operation: if revoked.is_some() {
                    "tombstone"
                } else {
                    "upsert"
                }
                .into(),
                payload,
                created_at: at,
            }],
            tombstone: None,
        });
    }
    let result = result.ok_or_else(absent)?;
    validate(&result, identity)?;
    Ok(result)
}

fn validate(capture: &Capture, identity: &Identity) -> Result<()> {
    let step = capture.steps.first().ok_or_else(invalid)?;
    let parents = if step.operation == "tombstone" {
        json!([format!("revision_{}", "0".repeat(64))])
    } else {
        json!([])
    };
    let mut event = json!({"schema_version":1,"entity_id":capture.entity_id,"entity_kind":capture.entity_kind,
        "parent_revision_ids":parents,"operation":step.operation,"payload":step.payload,
        "device_id":identity.device_id,"actor_id":identity.account_id,"created_at":step.created_at});
    event["revision_id"] = passport::revision_id(&event)?.into();
    event["content_digest"] = digest::canonical("ai-stp:revision:v1", &step.payload)?.into();
    event["event_id"] = "event_summary_validation".into();
    event["idempotency_key"] = "summary-validation".into();
    event["expected_head_revision_id"] = Value::Null;
    super::event::Event::push(&event, &identity.account_id)?;
    capture.digest()?;
    Ok(())
}
