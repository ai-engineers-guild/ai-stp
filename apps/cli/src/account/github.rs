//! Selected source authority stays on the server. Plans retain the exact request
//! and idempotency key; a refreshed session requires an explicit new plan.

use super::{access::Access, access::Binding, transport::Code};
use crate::{
    authoring, canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, passport, wire,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

const LIMIT: u64 = 65536;
static REQUEST: wire::Schema = wire::Schema::new(include_str!(
    "../../../../schemas/v1/github-source-prepare-request.schema.json"
));
static PREPARED: wire::Schema = wire::Schema::new(include_str!(
    "../../../../schemas/v1/github-source-prepared.schema.json"
));
static STATUS: wire::Schema = wire::Schema::new(include_str!(
    "../../../../schemas/v1/github-connector-status.schema.json"
));

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    schema_version: u32,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    state_parent: PathBuf,
    account: Binding,
    request: Value,
    created_at: String,
    expires_at: String,
}

fn invalid() -> Failure {
    Failure::input("the selected GitHub source request, plan or response is invalid")
}

pub(super) fn uncertain() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the selected-source response was not confirmed; retain the original request and idempotency key for retry",
    )
}

pub(super) fn refusal(code: Code) -> Failure {
    let (kind, reason) = match code {
        Code::Revoked => (ErrorKind::Precondition, "device_revoked"),
        Code::Unauthorized | Code::Expired => (ErrorKind::Precondition, "account_required"),
        Code::Forbidden => (ErrorKind::Precondition, "permission_denied"),
        Code::Conflict => (ErrorKind::Conflict, "request_conflict"),
        Code::NotFound => (ErrorKind::NotFound, "source_not_found"),
        Code::Invalid => (ErrorKind::Input, "request_rejected"),
        Code::SlowDown => (ErrorKind::Unavailable, "rate_limited"),
        _ => (ErrorKind::Precondition, "source_refused"),
    };
    Failure::new(kind, "the selected-source API refused the request")
        .with_details([("reason".into(), reason.into())])
}

fn relative(path: &str, root: bool) -> bool {
    (root && path == ".")
        || (!path.is_empty()
            && path == path.trim()
            && !path
                .chars()
                .any(|c| c.is_control() || matches!(c, '\\' | ':'))
            && path.split('/').all(|p| !matches!(p, "" | "." | "..")))
}

fn request(value: &Value) -> Result<()> {
    REQUEST.validate(value)?;
    if !value["subpath"].as_str().is_some_and(|p| relative(p, true))
        || canonical::parse(&serde_json::to_vec(value).map_err(|_| invalid())?)? != *value
    {
        return Err(Failure::input(
            "source coordinates must use exact NFC strings and a canonical relative POSIX subpath",
        ));
    }
    Ok(())
}

impl Plan {
    fn validate(&self) -> Result<()> {
        self.account.validate()?;
        request(&self.request)?;
        if self.schema_version != 1
            || !self.state_parent.is_absolute()
            || authoring::expiry(&self.created_at)? != self.expires_at
        {
            return Err(invalid());
        }
        Ok(())
    }

    pub fn digest(&self) -> Result<String> {
        self.validate()?;
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

pub fn plan(root: &Path, origin: Option<&str>, input: &Path, at: &str) -> Result<Plan> {
    let body = wire::parse(&files::read(input, LIMIT)?)?;
    request(&body)?;
    let state_parent = PathBuf::from(files::location(root)?);
    let mut access = Access::for_account(&state_parent, origin)?;
    access.verify()?;
    let plan = Plan {
        schema_version: 1,
        state_parent,
        account: access.binding().clone(),
        request: body,
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
    };
    plan.validate()?;
    Ok(plan)
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let plan: Plan =
        serde_json::from_value(wire::parse(&files::read(path, LIMIT)?)?).map_err(|_| invalid())?;
    plan.validate()?;
    Ok(plan)
}

fn keep(value: &Value, fields: &[&str]) -> Value {
    Value::Object(
        fields
            .iter()
            .filter_map(|k| value.get(*k).map(|v| ((*k).into(), v.clone())))
            .collect(),
    )
}

fn repositories(value: &Value) -> Result<Value> {
    value
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(|v| {
            let mut result = keep(
                v,
                &[
                    "installation_id",
                    "repository_id",
                    "owner_id",
                    "full_name",
                    "html_url",
                    "owner_type",
                    "private",
                    "can_administer",
                    "permission",
                ],
            );
            result["platform_objects"] = v["platform_objects"]
                .as_array()
                .ok_or_else(invalid)?
                .iter()
                .map(|v| {
                    keep(
                        v,
                        &["object_kind", "stable_id", "version", "name", "visibility"],
                    )
                })
                .collect();
            Ok(result)
        })
        .collect()
}

fn observed(access: &Access, response: Value) -> Result<Value> {
    access.revalidate()?;
    Ok(
        json!({"schema_version":1,"account_id":access.binding().account_id,
        "api_origin":access.binding().origin,"source":"online",
        "checked_at":format!("{:.3}",jiff::Timestamp::now()),"response":response}),
    )
}

pub fn status(root: &Path, origin: Option<&str>) -> Result<Value> {
    let mut access = Access::for_account(root, origin)?;
    access.verify()?;
    let value = access.github(None)?;
    STATUS.validate(&value)?;
    let connections: Result<Value> = value["connections"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(|v| {
            let mut connection = keep(
                v,
                &["purpose", "configured", "state", "expires_at", "reason"],
            );
            connection["repositories"] = repositories(&v["repositories"])?;
            connection["installations"] = v["installations"]
                .as_array()
                .ok_or_else(invalid)?
                .iter()
                .map(|v| {
                    let mut installation = keep(
                        v,
                        &[
                            "installation_id",
                            "account_id",
                            "account_login",
                            "account_type",
                            "account_html_url",
                            "repository_selection",
                        ],
                    );
                    installation["repositories"] = repositories(&v["repositories"])?;
                    Ok(installation)
                })
                .collect::<Result<Value>>()?;
            Ok(connection)
        })
        .collect();
    observed(&access, json!({"connections":connections?}))
}

pub fn apply(plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    if plan.digest()? != expected {
        return Err(invalid());
    }
    if !passport::timestamp(at) || at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        return Err(Failure::precondition(
            "the source plan expired; re-plan the original request with its unchanged idempotency key",
        ));
    }
    let mut access = Access::for_account(&plan.state_parent, Some(&plan.account.origin))?;
    if access.binding() != &plan.account {
        return Err(Failure::precondition(
            "the source account, device, session or physical state changed after planning",
        ));
    }
    access.verify()?;
    if format!("{:.3}", jiff::Timestamp::now()) > plan.expires_at {
        return Err(Failure::precondition(
            "the source plan expired during authentication",
        ));
    }
    let bytes = canonical::bytes(&plan.request)?;
    let value = access.github(Some(&bytes))?;
    PREPARED.validate(&value).map_err(|_| uncertain())?;
    let mut paths = std::collections::BTreeSet::new();
    for path in value["artifact_inventory"]
        .as_array()
        .ok_or_else(uncertain)?
    {
        let path = path.as_str().ok_or_else(uncertain)?;
        if !relative(path, false) || !paths.insert(path) {
            return Err(uncertain());
        }
    }
    let response = keep(
        &value,
        &[
            "source_binding_id",
            "content_digest",
            "size_bytes",
            "artifact_inventory",
            "source_visibility",
        ],
    );
    // The machine envelope uses NFC JSON. Refuse rather than silently rewrite
    // an exact source inventory that cannot survive that representation.
    if canonical::parse(&serde_json::to_vec(&response).map_err(|_| uncertain())?)? != response {
        return Err(uncertain());
    }
    observed(&access, response)
}
