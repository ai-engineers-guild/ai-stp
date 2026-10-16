//! The two existing sync routes, bound to one authenticated account and device.

use std::collections::BTreeMap;

use serde_json::Value;

use crate::{
    error::{ErrorKind, Failure, Result},
    wire::Schema,
};

use super::event::Event;

static PUSH: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/sync-push-request.schema.json"
)));
static PUSH_RESPONSE: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/sync-push-response.schema.json"
)));
static PULL_RESPONSE: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/sync-pull-response.schema.json"
)));

pub(crate) enum Request<'a> {
    Push(&'a Value),
    Pull {
        cursor: Option<&'a str>,
        page_size: u16,
    },
}

pub(super) fn invalid() -> Failure {
    Failure::input(
        "the private sync request or response does not match its bounded account contract",
    )
}

pub(crate) fn uncertain() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the private sync response was not received; retain the original events, keys and head preconditions for retry",
    )
}

pub(super) fn cursor(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 512
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'))
}

impl Request<'_> {
    pub(crate) fn validate(&self, account: &str, device: &str) -> Result<()> {
        match self {
            Self::Push(body) => {
                PUSH.validate(body)?;
                let mut ids = std::collections::BTreeSet::new();
                let mut keys = std::collections::BTreeSet::new();
                for value in body["events"].as_array().ok_or_else(invalid)? {
                    let event = Event::push(value, account)?;
                    if event.device_id != device
                        || !ids.insert(event.event_id)
                        || !keys.insert(value["idempotency_key"].as_str().ok_or_else(invalid)?)
                    {
                        return Err(invalid());
                    }
                }
            }
            Self::Pull {
                cursor: value,
                page_size,
            } => {
                if !(1..=100).contains(page_size) || value.is_some_and(|v| !cursor(v)) {
                    return Err(invalid());
                }
            }
        }
        Ok(())
    }

    pub(crate) fn response(&self, value: Value, account: &str) -> Result<Value> {
        match self {
            Self::Push(body) => {
                PUSH_RESPONSE.validate(&value)?;
                let mut pending = body["events"]
                    .as_array()
                    .ok_or_else(invalid)?
                    .iter()
                    .map(|v| {
                        let event = Event::push(v, account)?;
                        Ok((event.event_id.clone(), event))
                    })
                    .collect::<Result<BTreeMap<_, _>>>()?;
                for receipt in value["receipts"].as_array().ok_or_else(invalid)? {
                    let id = receipt["event_id"].as_str().ok_or_else(invalid)?;
                    let event = pending.remove(id).ok_or_else(invalid)?;
                    super::ledger::validate_receipt(receipt, &event)?;
                }
                if !pending.is_empty() {
                    return Err(invalid());
                }
            }
            Self::Pull { page_size, .. } => {
                PULL_RESPONSE.validate(&value)?;
                let events = value["items"].as_array().ok_or_else(invalid)?;
                if value["page"]["page_size"] != *page_size
                    || events.len() > usize::from(*page_size)
                {
                    return Err(invalid());
                }
                let mut previous = 0;
                let mut ids = std::collections::BTreeSet::new();
                for event in events {
                    let sequence = event["sequence"].as_u64().ok_or_else(invalid)?;
                    if sequence <= previous
                        || event["actor_id"] != account
                        || !ids.insert(event["event_id"].as_str().ok_or_else(invalid)?)
                    {
                        return Err(invalid());
                    }
                    previous = sequence;
                }
                // Per-event semantic validation belongs to page application,
                // where an explicitly named abandoned event can be recognized.
            }
        }
        Ok(value)
    }
}
