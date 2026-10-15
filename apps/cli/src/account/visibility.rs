//! Exact distribution visibility plans. The server owns authority and replay;
//! neither planning nor historical confirmation changes immutable passports.

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
    "../../../../schemas/v1/visibility-plan-create-request.schema.json"
));
static RESPONSE: wire::Schema = wire::Schema::new(include_str!(
    "../../../../schemas/v1/visibility-plan-response.schema.json"
));
static CONFIRM: wire::Schema = wire::Schema::new(include_str!(
    "../../../../schemas/v1/publication-confirm-request.schema.json"
));
const FIELDS: &[&str] = &[
    "schema_version",
    "plan_id",
    "plan_hash",
    "state",
    "object_kind",
    "stable_id",
    "version",
    "passport_digest",
    "previous_visibility",
    "visibility",
    "actor_id",
    "device_id",
    "expires_at",
    "effects",
];

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
    remote: Value,
    created_at: String,
    expires_at: String,
}

pub(super) fn invalid() -> Failure {
    Failure::input("the visibility request, plan or response is invalid")
}

pub(super) fn uncertain() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the visibility result was not confirmed; retain the original request, idempotency key and server plan for reconciliation",
    )
}

pub(super) fn refusal(code: Code) -> Failure {
    let (kind, reason) = match code {
        Code::Revoked => (ErrorKind::Precondition, "device_revoked"),
        Code::Unauthorized | Code::Expired => (ErrorKind::Precondition, "account_required"),
        Code::Forbidden => (ErrorKind::Precondition, "permission_denied"),
        Code::Conflict => (ErrorKind::Conflict, "request_conflict"),
        Code::NotFound => (ErrorKind::NotFound, "visibility_plan_or_version_not_found"),
        Code::Invalid => (ErrorKind::Input, "request_rejected"),
        Code::SlowDown => (ErrorKind::Unavailable, "rate_limited"),
        _ => (ErrorKind::Precondition, "visibility_refused"),
    };
    Failure::new(kind, "the visibility API refused the request")
        .with_details([("reason".into(), reason.into())])
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key].as_str().ok_or_else(invalid)
}

fn coordinates(value: &Value) -> Result<()> {
    if !passport::stable_id(text(value, "stable_id")?, text(value, "object_kind")?) {
        return Err(invalid());
    }
    Ok(())
}

fn request(value: &Value, account: &Binding) -> Result<()> {
    REQUEST.validate(value)?;
    coordinates(value)?;
    if value["schema_version"] != 1 || value["device_id"] != account.device_id {
        return Err(invalid());
    }
    Ok(())
}

fn response(value: &Value, account: &Binding) -> Result<Value> {
    RESPONSE.validate(value)?;
    coordinates(value)?;
    if value["schema_version"] != 1
        || value["actor_id"] != account.account_id
        || !passport::stable_id(text(value, "plan_id")?, "plan")
        || !passport::timestamp(text(value, "expires_at")?)
        || value["previous_visibility"] == value["visibility"]
        || value["effects"]
            != json!([format!(
                "set distribution visibility to {}",
                text(value, "visibility")?
            )])
    {
        return Err(invalid());
    }
    Ok(Value::Object(
        FIELDS
            .iter()
            .map(|key| ((*key).into(), value[*key].clone()))
            .collect(),
    ))
}

fn bound(value: &Value, body: &Value, account: &Binding) -> Result<Value> {
    let value = response(value, account)?;
    for key in [
        "object_kind",
        "stable_id",
        "version",
        "visibility",
        "device_id",
    ] {
        if value[key] != body[key] {
            return Err(invalid());
        }
    }
    Ok(value)
}

fn unchanged(value: &Value, previous: &Value) -> Result<()> {
    if FIELDS
        .iter()
        .any(|key| *key != "state" && value[*key] != previous[*key])
        || (previous["state"] != "planned" && value["state"] != previous["state"])
    {
        return Err(uncertain());
    }
    Ok(())
}

impl Plan {
    fn validate(&self) -> Result<()> {
        self.account.validate()?;
        request(&self.request, &self.account)?;
        if self.schema_version != 1
            || !self.state_parent.is_absolute()
            || authoring::expiry(&self.created_at)? != self.expires_at
            || bound(&self.remote, &self.request, &self.account)? != self.remote
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
    let mut body = wire::parse(&files::read(input, LIMIT)?)?;
    let object = body.as_object_mut().ok_or_else(invalid)?;
    // Identity is supplied exclusively by the retained isolated account session.
    if object.contains_key("device_id") || object.contains_key("schema_version") {
        return Err(invalid());
    }
    let state_parent = PathBuf::from(files::location(root)?);
    let mut access = Access::for_account(&state_parent, origin)?;
    object.insert("schema_version".into(), 1.into());
    object.insert(
        "device_id".into(),
        access.binding().device_id.clone().into(),
    );
    request(&body, access.binding())?;
    let expires_at = authoring::expiry(at)?;
    access.verify()?;
    let remote = access.visibility("", Some(&canonical::bytes(&body)?))?;
    let remote = bound(&remote, &body, access.binding()).map_err(|_| uncertain())?;
    let plan = Plan {
        schema_version: 1,
        state_parent,
        account: access.binding().clone(),
        request: body,
        remote,
        created_at: at.into(),
        expires_at,
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

fn observed(access: &Access, response: Value) -> Result<Value> {
    access.revalidate()?;
    Ok(
        json!({"schema_version":1,"account_id":access.binding().account_id,
        "api_origin":access.binding().origin,"source":"online",
        "checked_at":format!("{:.3}",jiff::Timestamp::now()),"response":response}),
    )
}

pub fn status(root: &Path, origin: Option<&str>, id: &str) -> Result<Value> {
    if !passport::stable_id(id, "plan") {
        return Err(invalid());
    }
    let mut access = Access::for_account(root, origin)?;
    access.verify()?;
    let value = response(&access.visibility(id, None)?, access.binding())?;
    if value["plan_id"] != id {
        return Err(invalid());
    }
    observed(&access, value)
}

pub fn apply(plan: &Plan, expected: &str, confirmed: bool, at: &str) -> Result<Value> {
    if !confirmed {
        return Err(Failure::precondition(
            "visibility requires an explicit --confirm decision",
        ));
    }
    if plan.digest()? != expected {
        return Err(invalid());
    }
    if !passport::timestamp(at) || at < plan.created_at.as_str() || at >= plan.expires_at.as_str() {
        return Err(Failure::precondition(
            "the visibility plan expired; re-plan the original request with its unchanged idempotency key",
        ));
    }
    let mut access = Access::for_account(&plan.state_parent, Some(&plan.account.origin))?;
    if access.binding() != &plan.account {
        return Err(Failure::precondition(
            "the visibility account, device, session or physical state changed after planning",
        ));
    }
    access.verify()?;
    let id = text(&plan.remote, "plan_id")?;
    let current =
        response(&access.visibility(id, None)?, &plan.account).map_err(|_| uncertain())?;
    unchanged(&current, &plan.remote)?;
    if current["state"] != "planned" {
        return observed(&access, current);
    }
    let now = format!("{:.3}", jiff::Timestamp::now());
    if now >= plan.expires_at || now.as_str() >= text(&current, "expires_at")? {
        return Err(Failure::precondition(
            "the visibility plan expired during revalidation",
        ));
    }
    let body = json!({"schema_version":1,"plan_hash":current["plan_hash"],
        "confirmed":true,"idempotency_key":plan.request["idempotency_key"]});
    CONFIRM.validate(&body)?;
    let value = access.visibility(&format!("{id}/confirm"), Some(&canonical::bytes(&body)?))?;
    let value = response(&value, &plan.account).map_err(|_| uncertain())?;
    unchanged(&value, &current)?;
    if value["state"] == "planned" {
        return Err(uncertain());
    }
    observed(&access, value)
}
