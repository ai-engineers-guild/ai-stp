//! Exact publication requests and responses over the existing generated contracts.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Snapshot, text};
use crate::{
    account::access::Binding,
    artifacts, canonical, digest,
    error::{Failure, Result},
    passport,
    wire::Schema,
};

const MAX_REQUEST: usize = 8 * 1024 * 1024;
static CREATE: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/publication-plan-create-request.schema.json"
)));
static RESPONSE: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/publication-plan-response.schema.json"
)));
static CONFIRM: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/publication-confirm-request.schema.json"
)));

pub(crate) fn confirmation_key(key: &str) -> Result<()> {
    CONFIRM.validate(&json!({"schema_version":1,"plan_hash":"plan_confirmation_shape","confirmed":true,"idempotency_key":key}))
}

#[derive(Clone, Copy, Default, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Visibility {
    #[default]
    Private,
    Public,
}

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Options {
    #[serde(default)]
    pub visibility: Visibility,
    pub source_binding_id: Option<String>,
    pub gitlab_source_binding_id: Option<String>,
    #[serde(default)]
    pub attestations: Vec<Value>,
}

/// Retain this exact value before sending it. A retry never generates a new key,
/// re-seals a passport or replaces an unknown request with newly captured bytes.
#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Create {
    pub account: Binding,
    body: Value,
}

fn invalid() -> Failure {
    Failure::precondition(
        "publication request or response differs from its exact account and object",
    )
}

fn nonempty(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::String(v) => !v.trim().is_empty(),
        Value::Array(v) => !v.is_empty(),
        Value::Object(v) => !v.is_empty(),
        _ => true,
    }
}

fn inventory(value: &Value) -> Result<()> {
    let paths = value.as_array().ok_or_else(invalid)?;
    let mut last = None;
    for path in paths {
        let path = path.as_str().ok_or_else(invalid)?;
        if !artifacts::safe_path(path)
            || path.chars().count() > 512
            || last.is_some_and(|previous| previous >= path)
        {
            return Err(invalid());
        }
        last = Some(path);
    }
    Ok(())
}

impl Create {
    pub fn snapshot(&self) -> Result<Snapshot> {
        self.validate()?;
        let document = &self.body["passport"];
        let artifact = super::Artifact::from_value(&document["artifact"])?;
        let projections = self
            .artifacts()?
            .into_iter()
            .filter(|(address, _)| address != &artifact.digest)
            .map(|(digest, size_bytes)| super::Artifact { digest, size_bytes })
            .collect();
        Ok(Snapshot {
            passport: document.clone(),
            passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
            artifact,
            projections,
            artifact_inventory: self.body["artifact_inventory"]
                .as_array()
                .ok_or_else(invalid)?
                .iter()
                .map(|v| v.as_str().map(str::to_owned).ok_or_else(invalid))
                .collect::<Result<_>>()?,
        })
    }

    pub fn new(snapshot: &Snapshot, account: Binding, options: Options, key: &str) -> Result<Self> {
        snapshot.require_owner(&account.account_id)?;
        if snapshot.passport_digest != digest::canonical("ai-stp:passport:v1", &snapshot.passport)?
        {
            return Err(invalid());
        }
        let body = json!({"schema_version":1,"object_kind":snapshot.passport["kind"],
            "stable_id":snapshot.passport["stable_id"],"version":snapshot.passport["version"],
            "content_digest":snapshot.artifact.digest,"artifact_inventory":snapshot.artifact_inventory,
            "visibility":options.visibility,"source_binding_id":options.source_binding_id,
            "gitlab_source_binding_id":options.gitlab_source_binding_id,"policy_version":"safety-3",
            "passport":snapshot.passport,"attestations":options.attestations,
            "idempotency_key":key,"device_id":account.device_id});
        let request = Self { account, body };
        request.validate()?;
        Ok(request)
    }

    pub fn body(&self) -> &Value {
        &self.body
    }

    pub fn bytes(&self) -> Result<Vec<u8>> {
        self.validate()?;
        canonical::bytes(&self.body)
    }

    pub fn validate(&self) -> Result<()> {
        if canonical::bytes(&self.body)?.len() > MAX_REQUEST {
            return Err(invalid());
        }
        CREATE.validate(&self.body)?;
        self.account.validate()?;
        let document = &self.body["passport"];
        passport::validate(document)?;
        passport::versions::validate_document(document)?;
        if self.body["schema_version"] != 1
            || self.body["device_id"] != self.account.device_id
            || document["owner_id"] != self.account.account_id
            || self.body["object_kind"] != document["kind"]
            || self.body["stable_id"] != document["stable_id"]
            || self.body["version"] != document["version"]
            || self.body["content_digest"] != document["artifact"]["digest"]
            || (!self.body["source_binding_id"].is_null()
                && !self.body["gitlab_source_binding_id"].is_null())
        {
            return Err(invalid());
        }
        inventory(&self.body["artifact_inventory"])?;
        for key in ["name", "version", "license", "tags", "artifact"] {
            if !nonempty(&document[key]) {
                return Err(invalid());
            }
        }
        if !nonempty(&document["license"]["spdx_id"]) {
            return Err(invalid());
        }
        if document["kind"] == "component"
            && self.body["source_binding_id"].is_null()
            && self.body["gitlab_source_binding_id"].is_null()
            && ["repository", "commit", "path"]
                .iter()
                .any(|k| !nonempty(&document["source"][k]))
        {
            return Err(Failure::precondition(
                "component publication requires sealed source coordinates or an explicit source binding",
            ));
        }
        self.artifacts()?;
        attestations(&self.body, &self.account)
    }

    /// Original artifact and unique projections only; source captures are not
    /// additional upload routes on this API.
    pub fn artifacts(&self) -> Result<BTreeMap<String, usize>> {
        let document = &self.body["passport"];
        let mut result = BTreeMap::new();
        let mut add = |value: &Value| -> Result<()> {
            let address = text(value, "digest")?.to_owned();
            let size = value["size_bytes"]
                .as_u64()
                .filter(|v| *v <= 64 * 1024 * 1024)
                .ok_or_else(invalid)? as usize;
            if let Some(previous) = result.insert(address, size)
                && previous != size
            {
                return Err(invalid());
            }
            Ok(())
        };
        add(&document["artifact"])?;
        if document["kind"] == "component" {
            for adaptation in document["adaptations"].as_array().ok_or_else(invalid)? {
                for scope in adaptation["scope_adaptations"]
                    .as_array()
                    .ok_or_else(invalid)?
                {
                    add(&scope["projection_artifact"])?;
                }
            }
        }
        Ok(result)
    }

    pub fn response(&self, value: &Value, previous: Option<&Value>) -> Result<()> {
        self.validate()?;
        RESPONSE.validate(value)?;
        inventory(&value["artifact_inventory"])?;
        if value["actor_id"] != self.account.account_id
            || value["device_id"] != self.account.device_id
        {
            return Err(invalid());
        }
        for key in [
            "schema_version",
            "object_kind",
            "stable_id",
            "version",
            "content_digest",
            "artifact_inventory",
            "visibility",
            "source_binding_id",
            "gitlab_source_binding_id",
            "policy_version",
        ] {
            if value[key] != self.body[key] {
                return Err(invalid());
            }
        }
        if let Some(previous) = previous {
            self.response(previous, None)?;
            for key in ["plan_id", "plan_hash", "expires_at"] {
                if previous[key] != value[key] {
                    return Err(invalid());
                }
            }
        }
        Ok(())
    }

    pub fn confirmation(&self, plan: &Value, key: &str) -> Result<Value> {
        self.response(plan, None)?;
        let value = json!({"schema_version":1,"plan_hash":plan["plan_hash"],"confirmed":true,"idempotency_key":key});
        CONFIRM.validate(&value)?;
        Ok(value)
    }
}

fn attestations(request: &Value, account: &Binding) -> Result<()> {
    let mut seen = BTreeSet::new();
    for record in request["attestations"].as_array().ok_or_else(invalid)? {
        let hash = crate::attestation::contract::verify(record, &account.public_key)?;
        crate::attestation::contract::bind(record, &request["passport"], account)?;
        if record["policy_version"] != request["policy_version"] || !seen.insert(hash) {
            return Err(invalid());
        }
    }
    Ok(())
}
