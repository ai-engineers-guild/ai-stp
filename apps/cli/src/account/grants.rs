//! Account-bound remote grants. The API owns idempotency; plans retain intent,
//! never refreshed mutation preconditions or a second local authorization store.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use zeroize::Zeroizing;

use super::{
    access::{Access, Binding},
    transport::Code,
};
use crate::{
    authoring, canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, passport, wire,
};

const MAX_REQUEST: u64 = 65536;
static DIRECT: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/grant-direct-create-request.schema.json"
)));
static INVITE: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/grant-invitation-create-request.schema.json"
)));
static ACCEPT: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/grant-accept-request.schema.json"
)));
static REVOKE: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/grant-revoke-request.schema.json"
)));
static GRANT: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/grant-access-response.schema.json"
)));
static INVITATION: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/grant-invitation-response.schema.json"
)));
static LIST: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/grant-list-response.schema.json"
)));
static REVOKED: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/grant-revoke-response.schema.json"
)));

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    Direct,
    Invite,
    Accept,
    Revoke,
    RevokeInvitation,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    action: Action,
    body: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    target_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    token_env: Option<String>,
}

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
    request: Request,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    token_sha256: Option<String>,
    created_at: String,
    expires_at: String,
}

pub(super) fn invalid() -> Failure {
    Failure::input("the grant request, plan or exact response identity is invalid")
}

pub(super) fn uncertain() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "the grant response was not received; retry the original request and idempotency key without refreshing its preconditions",
    )
}

pub(super) fn refusal(code: Code) -> Failure {
    let kind = match code {
        Code::Conflict => ErrorKind::Conflict,
        Code::NotFound => ErrorKind::NotFound,
        Code::Invalid => ErrorKind::Input,
        Code::SlowDown => ErrorKind::Unavailable,
        _ => ErrorKind::Precondition,
    };
    let reason = match code {
        Code::Revoked => "device_revoked",
        Code::Unauthorized | Code::Expired => "account_required",
        Code::Forbidden => "permission_denied",
        Code::Conflict => "request_conflict",
        Code::Precondition => "grant_precondition_changed",
        Code::NotFound => "grant_or_recipient_not_found",
        Code::Invalid => "request_rejected",
        Code::SlowDown => "rate_limited",
        _ => "remote_refusal",
    };
    Failure::new(
        kind,
        "the grant API refused the request; no local result replaces its answer",
    )
    .with_details([("reason".into(), reason.into())])
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key].as_str().ok_or_else(invalid)
}

fn object(value: &Value) -> Result<()> {
    let kind = text(value, "object_kind")?;
    if !matches!(kind, "component" | "setup")
        || !passport::stable_id(text(value, "stable_id")?, kind)
        || !value["major"].as_u64().is_some_and(|v| v <= 9999)
    {
        return Err(invalid());
    }
    Ok(())
}

fn variable(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .enumerate()
            .all(|(i, b)| b == b'_' || b.is_ascii_alphabetic() || (i > 0 && b.is_ascii_digit()))
}

impl Request {
    fn validate(&self) -> Result<()> {
        if self.body.get("token").is_some() || self.body["mutation_contract"] != 1 {
            return Err(invalid());
        }
        match self.action {
            Action::Direct => {
                DIRECT.validate(&self.body)?;
                object(&self.body)?;
                let id = self.body["expected_grant_id"].as_str();
                let revision = self.body["expected_revision"].as_u64();
                if id.is_some() != revision.is_some()
                    || id.is_some_and(|id| !passport::stable_id(id, "grant"))
                    || (self.body["recipient_kind"] == "user_id"
                        && !passport::stable_id(text(&self.body, "recipient")?, "account"))
                {
                    return Err(invalid());
                }
            }
            Action::Invite => {
                INVITE.validate(&self.body)?;
                object(&self.body)?;
            }
            Action::Accept => {
                // Validate the public body through the same generated contract,
                // with a non-secret shape witness in place of the withheld token.
                let mut body = self.body.clone();
                body.as_object_mut()
                    .ok_or_else(invalid)?
                    .insert("token".into(), "xxxxxxxxxxxxxxxx".into());
                ACCEPT.validate(&body)?;
            }
            Action::Revoke | Action::RevokeInvitation => {
                REVOKE.validate(&self.body)?;
                if (self.action == Action::Revoke
                    && self.body["expected_revision"].as_u64().is_none())
                    || (self.action == Action::RevokeInvitation
                        && !self.body["expected_revision"].is_null())
                {
                    return Err(invalid());
                }
            }
        }
        match self.action {
            Action::Direct | Action::Invite if self.target_id.is_none() => {}
            Action::Accept | Action::RevokeInvitation
                if self
                    .target_id
                    .as_deref()
                    .is_some_and(|id| passport::stable_id(id, "invite")) => {}
            Action::Revoke
                if self
                    .target_id
                    .as_deref()
                    .is_some_and(|id| passport::stable_id(id, "grant")) => {}
            _ => return Err(invalid()),
        }
        match (self.action, self.token_env.as_deref()) {
            (Action::Accept, Some(name)) if variable(name) => {}
            (Action::Accept, _) | (_, Some(_)) => return Err(invalid()),
            (_, None) => {}
        }
        Ok(())
    }

    fn token(&self) -> Result<Option<Zeroizing<String>>> {
        self.token_env
            .as_ref()
            .map(|name| {
                let value = Zeroizing::new(std::env::var(name).map_err(|_| {
                    Failure::precondition("the invitation token variable is unavailable")
                })?);
                if !(16..=256).contains(&value.chars().count()) {
                    return Err(Failure::precondition(
                        "the invitation token does not meet the supported bounds",
                    ));
                }
                Ok(value)
            })
            .transpose()
    }

    fn route(&self) -> Result<String> {
        self.validate()?;
        Ok(match self.action {
            Action::Direct => "direct".into(),
            Action::Invite => "invitations".into(),
            Action::Accept => format!(
                "invitations/{}/accept",
                self.target_id.as_deref().ok_or_else(invalid)?
            ),
            Action::RevokeInvitation => format!(
                "invitations/{}/revoke",
                self.target_id.as_deref().ok_or_else(invalid)?
            ),
            Action::Revoke => format!("{}/revoke", self.target_id.as_deref().ok_or_else(invalid)?),
        })
    }
}

impl Plan {
    fn validate(&self) -> Result<()> {
        self.account.validate()?;
        self.request.validate()?;
        if self.schema_version != 1
            || !self.state_parent.is_absolute()
            || authoring::expiry(&self.created_at)? != self.expires_at
            || (self.request.action == Action::Accept) != self.token_sha256.is_some()
            || self.token_sha256.as_deref().is_some_and(|s| {
                !s.strip_prefix("sha256:").is_some_and(|h| {
                    h.len() == 64
                        && h.bytes()
                            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                })
            })
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

pub fn plan(root: &Path, origin: Option<&str>, request: &Path, at: &str) -> Result<Plan> {
    let mut request: Request =
        serde_json::from_value(canonical::parse(&files::read(request, MAX_REQUEST)?)?)
            .map_err(|_| invalid())?;
    request
        .body
        .as_object_mut()
        .ok_or_else(invalid)?
        .entry("mutation_contract")
        .or_insert(json!(1));
    request.validate()?;
    let token = request.token()?;
    let state_parent = PathBuf::from(files::location(root)?);
    let mut access = Access::for_account(&state_parent, origin)?;
    access.verify()?;
    let plan = Plan {
        schema_version: 1,
        state_parent,
        account: access.binding().clone(),
        request,
        token_sha256: token.as_ref().map(|s| digest::sha256(s.as_bytes())),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
    };
    plan.validate()?;
    Ok(plan)
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let plan: Plan = serde_json::from_value(canonical::parse(&files::read(path, MAX_REQUEST)?)?)
        .map_err(|_| invalid())?;
    plan.validate()?;
    Ok(plan)
}

fn keep(value: &Value, fields: &[&str]) -> Value {
    Value::Object(
        fields
            .iter()
            .filter_map(|name| value.get(*name).map(|v| ((*name).into(), v.clone())))
            .collect(),
    )
}

fn grant(value: &Value, account: &str) -> Result<Value> {
    GRANT.validate(value)?;
    object(value)?;
    if !passport::stable_id(text(value, "grant_id")?, "grant")
        || (value["owner_account_id"] != account && value["grantee_account_id"] != account)
    {
        return Err(invalid());
    }
    Ok(keep(
        value,
        &[
            "schema_version",
            "grant_id",
            "object_kind",
            "stable_id",
            "major",
            "grantee_account_id",
            "owner_account_id",
            "state",
            "revision",
            "created_at",
            "revoked_at",
            "recipient_kind",
            "recipient",
        ],
    ))
}

fn invitation(value: &Value) -> Result<Value> {
    INVITATION.validate(value)?;
    object(value)?;
    if !passport::stable_id(text(value, "invitation_id")?, "invite") {
        return Err(invalid());
    }
    Ok(keep(
        value,
        &[
            "schema_version",
            "invitation_id",
            "object_kind",
            "stable_id",
            "major",
            "state",
            "expires_at",
            "created_at",
        ],
    ))
}

fn observed(access: &Access, response: Value) -> Result<Value> {
    access.revalidate()?;
    Ok(
        json!({"schema_version":1, "account_id":access.binding().account_id,
        "api_origin":access.binding().origin, "source":"online", "checked_at":format!("{:.3}", jiff::Timestamp::now()), "response":response}),
    )
}

pub fn list(root: &Path, origin: Option<&str>) -> Result<Value> {
    let mut access = Access::for_account(root, origin)?;
    access.verify()?;
    let value = access.grants("", None)?;
    LIST.validate(&value)?;
    let grants = value["grants"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(|v| grant(v, &access.binding().account_id))
        .collect::<Result<Vec<_>>>()?;
    let invitations = value["invitations"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(invitation)
        .collect::<Result<Vec<_>>>()?;
    observed(
        &access,
        json!({"schema_version":1,"grants":grants,"invitations":invitations}),
    )
}

pub fn apply(plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    if plan.digest()? != expected {
        return Err(invalid());
    }
    if !passport::timestamp(at) || at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        return Err(Failure::precondition(
            "the grant plan expired; review the original request and key before creating a new plan",
        ));
    }
    let token = plan.request.token()?;
    if token.as_ref().map(|s| digest::sha256(s.as_bytes())) != plan.token_sha256 {
        return Err(Failure::precondition(
            "the invitation token changed after planning",
        ));
    }
    let mut access = Access::for_account(&plan.state_parent, Some(&plan.account.origin))?;
    if access.binding() != &plan.account {
        return Err(Failure::precondition(
            "the grant account, device, session or physical state changed after planning",
        ));
    }
    access.verify()?;
    if format!("{:.3}", jiff::Timestamp::now()) > plan.expires_at {
        return Err(Failure::precondition(
            "the grant plan expired during authentication",
        ));
    }
    // Serialize the secret directly into zeroizing transport memory. It never
    // becomes part of a retained Value, public plan, response or error detail.
    let mut body = Zeroizing::new(serde_json::to_vec(&plan.request.body).map_err(|_| invalid())?);
    if let Some(token) = &token {
        // Reserve the worst-case JSON escaping space before introducing any
        // secret bytes, so Vec growth cannot leave a freed token fragment.
        body.reserve(token.len() * 6 + 16);
        if body.pop() != Some(b'}') {
            return Err(invalid());
        }
        body.extend_from_slice(b",\"token\":");
        serde_json::to_writer(&mut *body, token.as_str()).map_err(|_| invalid())?;
        body.push(b'}');
    }
    let value = access.grants(&plan.request.route()?, Some(&body))?;
    let response = match plan.request.action {
        Action::Direct | Action::Accept => {
            let response = grant(&value, &plan.account.account_id)?;
            let role = if plan.request.action == Action::Direct {
                "owner_account_id"
            } else {
                "grantee_account_id"
            };
            if value[role] != plan.account.account_id {
                return Err(invalid());
            }
            if plan.request.action == Action::Direct {
                for field in ["object_kind", "stable_id", "major"] {
                    if value[field] != plan.request.body[field] {
                        return Err(invalid());
                    }
                }
                if plan.request.body["expected_grant_id"]
                    .as_str()
                    .is_some_and(|id| value["grant_id"] != id)
                    || (plan.request.body["recipient_kind"] == "user_id"
                        && value["grantee_account_id"] != plan.request.body["recipient"])
                {
                    return Err(invalid());
                }
            }
            response
        }
        Action::Invite => {
            let response = invitation(&value)?;
            for field in ["object_kind", "stable_id", "major"] {
                if value[field] != plan.request.body[field] {
                    return Err(invalid());
                }
            }
            response
        }
        Action::Revoke | Action::RevokeInvitation => {
            REVOKED.validate(&value)?;
            if value["local_bytes_retained"] != true {
                return Err(invalid());
            }
            keep(
                &value,
                &["schema_version", "revoked", "local_bytes_retained"],
            )
        }
    };
    let mut observed = observed(&access, response)?;
    observed["action"] = serde_json::to_value(plan.request.action).map_err(|_| invalid())?;
    observed["plan_digest"] = expected.into();
    Ok(observed)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn id(kind: &str) -> String {
        format!("{kind}_{}", ulid::Ulid::generate())
    }

    #[test]
    fn exact_grant_intents_reject_missing_revisions_tokens_and_cross_kind_targets() -> Result<()> {
        let account = id("account");
        let mut direct: Request = serde_json::from_value(json!({"action":"direct", "body":{
            "object_kind":"component", "stable_id":id("component"), "major":1,
            "recipient_kind":"user_id", "recipient":account, "mutation_contract":1,"idempotency_key":"native-grant-proof-01"}})).map_err(|_| invalid())?;
        direct.validate()?;
        let mut plan = Plan {
            schema_version: 1,
            state_parent: std::env::current_dir().map_err(|_| invalid())?,
            account: Binding {
                origin: "https://example.test".into(),
                account_id: account.clone(),
                device_id: id("device"),
                revision: id("operation"),
                root_identity: ["volume".into(), "directory".into()],
                public_key: "fixture".into(),
                credential_store: crate::identity::Storage::File,
            },
            request: direct.clone(),
            token_sha256: None,
            created_at: "2026-10-13T00:00:00.000Z".into(),
            expires_at: "2026-10-13T00:15:00.000Z".into(),
        };
        let encoded = serde_json::to_value(&plan).map_err(|_| invalid())?;
        let expected = digest::canonical("ai-stp:plan:v1", &encoded)?;
        let restored: Plan = serde_json::from_value(encoded).map_err(|_| invalid())?;
        assert_eq!(restored.digest()?, expected);
        plan.request.body["idempotency_key"] = "different-grant-intent".into();
        assert_ne!(plan.digest()?, expected);
        plan.request = direct.clone();
        plan.account.revision = id("operation");
        assert_ne!(plan.digest()?, expected);
        direct.body["expected_grant_id"] = id("grant").into();
        assert!(direct.validate().is_err());
        direct.body["expected_revision"] = 2.into();
        direct.validate()?;
        direct.body["expected_revision"] = 0.into();
        assert!(direct.validate().is_err());
        let mut revoke: Request =
            serde_json::from_value(json!({"action":"revoke", "target_id":id("grant"),
            "body":{"mutation_contract":1,"idempotency_key":"native-revoke-proof-01"}}))
            .map_err(|_| invalid())?;
        assert!(revoke.validate().is_err());
        revoke.body["expected_revision"] = 3.into();
        revoke.validate()?;
        revoke.target_id = Some(id("invite"));
        assert!(revoke.validate().is_err());
        revoke.action = Action::RevokeInvitation;
        assert!(revoke.validate().is_err());
        revoke
            .body
            .as_object_mut()
            .ok_or_else(invalid)?
            .remove("expected_revision");
        revoke.validate()?;
        let mut accept: Request =
            serde_json::from_value(json!({"action":"accept", "target_id":id("invite"),
            "token_env":"NATIVE_PROOF_TOKEN", "body":{"mutation_contract":1,"idempotency_key":"native-accept-proof-01"}}))
            .map_err(|_| invalid())?;
        accept.validate()?;
        accept.body["token"] = "a token must never enter public request JSON".into();
        assert!(accept.validate().is_err());
        assert!(
            serde_json::from_value::<Request>(
                json!({"action":"accept", "body":{}, "unknown":true})
            )
            .is_err()
        );
        Ok(())
    }

    #[test]
    fn remote_grants_keep_unknown_revision_and_never_invent_trust_or_other_accounts() -> Result<()>
    {
        let account = id("account");
        let mut value = json!({"schema_version":1,"grant_id":id("grant"),"object_kind":"component",
            "stable_id":id("component"),"major":1,"grantee_account_id":account,"owner_account_id":id("account"),
            "state":"revoked","created_at":"2026-10-13T00:00:00.000Z","revoked_at":"2026-10-13T00:00:01.000Z",
            "recipient_kind":null,"recipient":null,"author_verified":true,"unexpected_token":"not a credential"});
        let projected = grant(&value, &account)?;
        assert!(projected.get("revision").is_none());
        assert!(projected.get("author_verified").is_none());
        assert!(projected.get("unexpected_token").is_none());
        assert_eq!(projected["state"], "revoked");
        assert!(grant(&value, &id("account")).is_err());
        value["revision"] = 0.into();
        assert!(grant(&value, &account).is_err());
        value["revision"] = 2.into();
        assert_eq!(grant(&value, &account)?["revision"], 2);
        value["stable_id"] = id("setup").into();
        assert!(grant(&value, &account).is_err());
        Ok(())
    }
}
