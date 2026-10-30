//! One content-free observation retains its original signature and deadline.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::invalid;
use crate::{canonical, digest, error::Result, passport, wire::Schema};

static REQUEST: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/installation-heartbeat-request.schema.json"
)));
static RESPONSE: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/installation-heartbeat.schema.json"
)));

pub(super) fn request(bytes: &[u8]) -> Result<Value> {
    if bytes.len() > 4096 {
        return Err(invalid());
    }
    let body = crate::wire::parse(bytes)?;
    REQUEST.validate(&body).map_err(|_| invalid())?;
    Ok(body)
}

pub(super) const LIFETIME: i64 = 240;

pub(super) fn hash(value: &str) -> bool {
    value.strip_prefix("sha256:").is_some_and(|value| {
        value.len() == 64
            && value
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}

pub(super) fn time(value: &str) -> Result<i64> {
    if !passport::timestamp(value) {
        return Err(invalid());
    }
    value
        .parse::<jiff::Timestamp>()
        .map(|v| v.as_second())
        .map_err(|_| invalid())
}

pub(super) fn at(value: i64) -> Result<String> {
    jiff::Timestamp::from_second(value)
        .map(|v| format!("{v:.3}"))
        .map_err(|_| invalid())
}

pub(super) fn unsigned(account: &str, device: &str, policy: u64, now: &str) -> Value {
    json!({"schema_version":1,"account_id":account,"device_id":device,
        "cli_version":crate::registry::VERSION,"capabilities":["cli.foreground-liveness"],
        "last_sync_at":null,"health_state":"active","checked_at":now,"policy_version":policy})
}

pub(super) fn message(organization: &str, unsigned: &Value) -> Result<Vec<u8>> {
    if !passport::stable_id(organization, "organization") {
        return Err(invalid());
    }
    let mut checked = unsigned.clone();
    checked["signature"] = "A".repeat(86).into();
    REQUEST.validate(&checked).map_err(|_| invalid())?;
    // This sender emits fixed ASCII capability/version/identity fields. These
    // bytes therefore equal the server's sorted, ASCII-escaped JSON preimage.
    let bytes = canonical::bytes(unsigned)?;
    if !bytes.is_ascii() || unsigned.get("signature").is_some() {
        return Err(invalid());
    }
    let mut message = format!("ai-stp:installation-heartbeat:v1\n{organization}\n").into_bytes();
    message.extend(bytes);
    Ok(message)
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Pending {
    pub body: String,
    pub sha256: String,
    pub session_revision: String,
    pub authority_digest: String,
    pub checked_at: String,
    pub expires_at: String,
    pub next_attempt_at: String,
    pub attempts: u32,
}

impl Pending {
    pub fn request(&self) -> Result<Value> {
        if self.body.len() > 4096 || self.sha256 != digest::sha256(self.body.as_bytes()) {
            return Err(invalid());
        }
        let body = crate::wire::parse(self.body.as_bytes())?;
        REQUEST.validate(&body).map_err(|_| invalid())?;
        if body["checked_at"] != self.checked_at
            || body["capabilities"] != json!(["cli.foreground-liveness"])
            || !body["last_sync_at"].is_null()
            || body["health_state"] != "active"
            || body["policy_version"].as_u64().is_none()
            || self.session_revision.is_empty()
            || !hash(&self.authority_digest)
            || time(&self.expires_at)? - time(&self.checked_at)? != LIFETIME
            || time(&self.next_attempt_at)? > time(&self.expires_at)?
            || time(&self.next_attempt_at)? < time(&self.checked_at)?
            || self.attempts > 8
        {
            return Err(invalid());
        }
        Ok(body)
    }

    pub fn ready(&self, now: &str) -> Result<bool> {
        self.request()?;
        let now = time(now)?;
        Ok(now >= time(&self.next_attempt_at)?
            && now < time(&self.expires_at)?
            && now >= time(&self.checked_at)?
            && self.attempts < 8)
    }

    pub fn attempted(&mut self, now: &str, base: u64, maximum: u64) -> Result<()> {
        if !self.ready(now)? || base == 0 || maximum < base {
            return Err(invalid());
        }
        self.attempts += 1;
        let delay = base
            .saturating_mul(1u64 << (self.attempts - 1))
            .min(maximum);
        self.next_attempt_at = at(time(now)?
            .saturating_add(delay.min(i64::MAX as u64) as i64)
            .min(time(&self.expires_at)?))?;
        Ok(())
    }

    pub fn acknowledge(&self, organization: &str, response: &Value) -> Result<&'static str> {
        let request = self.request()?;
        RESPONSE.validate(response).map_err(|_| invalid())?;
        if response["organization_id"] != organization
            || response["account_id"] != request["account_id"]
            || response["device_id"] != request["device_id"]
        {
            return Err(invalid());
        }
        let checked = response["checked_at"]
            .as_str()
            .ok_or_else(invalid)?
            .parse::<jiff::Timestamp>()
            .map_err(|_| invalid())?;
        if checked
            > self
                .checked_at
                .parse::<jiff::Timestamp>()
                .map_err(|_| invalid())?
        {
            return Ok("superseded");
        }
        if response["checked_at"] != request["checked_at"]
            || response["cli_version"] != request["cli_version"]
            || response["capabilities"] != request["capabilities"]
            || response["last_sync_at"] != request["last_sync_at"]
            || response["reported_state"] != request["health_state"]
        {
            return Err(invalid());
        }
        Ok("acknowledged")
    }
}
