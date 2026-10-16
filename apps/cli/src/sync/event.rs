//! Existing sync wire identities. Transport receipts never replace local validation.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{
    digest,
    error::{Failure, Result},
    passport,
    wire::Schema,
};

static PUSH: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/sync-event.schema.json"
)));
static STREAM: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/sync-stream-event.schema.json"
)));
static SUMMARY: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/identity-device-summary.schema.json"
)));
static CONSENT: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/sync-consent-upsert.schema.json"
)));
static REVOCATION: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/sync-consent-tombstone.schema.json"
)));

pub(super) fn invalid() -> Failure {
    Failure::input("the private sync event fails its content, account or entity binding")
}

#[derive(Clone, Deserialize, Serialize)]
pub struct Event {
    pub schema_version: u32,
    pub event_id: String,
    pub entity_id: String,
    pub entity_kind: String,
    pub revision_id: String,
    pub parent_revision_ids: Vec<String>,
    pub device_id: String,
    pub actor_id: String,
    pub operation: String,
    pub content_digest: String,
    pub created_at: String,
    pub payload: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sequence: Option<u64>,
}

impl Event {
    pub fn stream(value: &Value, account: &str) -> Result<Self> {
        STREAM.validate(value)?;
        Self::read(value, account)
    }

    pub fn push(value: &Value, account: &str) -> Result<Self> {
        PUSH.validate(value)?;
        Self::read(value, account)
    }

    fn read(value: &Value, account: &str) -> Result<Self> {
        let event: Self = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
        event.validate(account)?;
        Ok(event)
    }

    pub fn sealed(&self) -> Value {
        json!({"schema_version":1,"entity_id":self.entity_id,"entity_kind":self.entity_kind,
            "parent_revision_ids":self.parent_revision_ids,"operation":self.operation,
            "payload":self.payload,"device_id":self.device_id,"actor_id":self.actor_id,
            "created_at":self.created_at})
    }

    pub fn passport_kind(&self) -> Option<&'static str> {
        match self.entity_kind.as_str() {
            "developer_passport" => Some("developer"),
            "component_private" => Some("component"),
            "setup_private" => Some("setup"),
            _ => None,
        }
    }

    /// Keep the original content address; version closure is outside the passport.
    pub fn passport(&self) -> Result<Value> {
        let kind = self.passport_kind().ok_or_else(invalid)?;
        let mut document = self.payload.clone();
        document
            .as_object_mut()
            .ok_or_else(invalid)?
            .remove("sync_released_versions");
        passport::validate(&document)?;
        if document["stable_id"] != self.entity_id
            || document["kind"] != kind
            || document["visibility"] != "private"
        {
            return Err(invalid());
        }
        Ok(document)
    }

    fn validate(&self, account: &str) -> Result<()> {
        if self.schema_version != 1
            || !passport::stable_id(account, "account")
            || self.actor_id != account
            || !passport::stable_id(&self.device_id, "device")
            || !passport::timestamp(&self.created_at)
            || !matches!(self.operation.as_str(), "upsert" | "tombstone")
            || self.parent_revision_ids.len() > 2
            || (self.parent_revision_ids.len() == 2
                && self.parent_revision_ids[0] == self.parent_revision_ids[1])
            || (self.operation == "tombstone" && self.parent_revision_ids.is_empty())
            || self.revision_id != passport::revision_id(&self.sealed())?
            || self.content_digest != digest::canonical("ai-stp:revision:v1", &self.payload)?
        {
            return Err(invalid());
        }
        super::payload::check(&self.payload)?;
        match self.entity_kind.as_str() {
            "developer_passport" | "component_private" | "setup_private" => {
                let kind = self.passport_kind().ok_or_else(invalid)?;
                if !passport::stable_id(&self.entity_id, kind) {
                    return Err(invalid());
                }
                if self.operation == "upsert" {
                    self.passport()?;
                }
                super::versions::bindings(&self.payload, &self.entity_id, kind)?;
            }
            "device_summary" => {
                if self.entity_id != self.device_id {
                    return Err(invalid());
                }
                if self.operation == "upsert" {
                    SUMMARY.validate(&self.payload)?;
                }
                super::versions::bindings(&self.payload, &self.entity_id, "device")?;
            }
            "unverified_consent" => {
                if !passport::stable_id(&self.entity_id, "account")
                    && !self.entity_id.starts_with("consent_")
                {
                    return Err(invalid());
                }
                if self.operation == "upsert" {
                    CONSENT.validate(&self.payload)?;
                } else {
                    REVOCATION.validate(&self.payload)?;
                }
                if self.payload["scope"] == "task" && self.payload["target"] != "full-auto" {
                    return Err(invalid());
                }
                super::versions::bindings(&self.payload, &self.entity_id, "consent")?;
            }
            _ => return Err(invalid()),
        }
        Ok(())
    }
}
