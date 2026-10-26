//! Explicit isolated account sessions. Authentication does not transfer local ownership.

pub(crate) mod access;
pub(crate) mod adoption;
pub(crate) mod attachment;
pub mod connections;
pub mod contexts;
pub mod corporate;
pub mod enrollment_recovery;
pub mod github;
pub mod grants;
mod journal;
mod model;
pub mod project_links;
pub mod providers;
mod recovery;
pub mod reports;
#[cfg(all(test, unix))]
mod tests;
mod transport;
pub mod visibility;

use journal::{Journal, Pending};
pub use model::{Action, Plan};
use model::{Outcome, Session, State, after};
use transport::{Api, Code, Grant, Reply, Tokens};

use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use serde::Serialize;
use serde_json::{Value, json};
use std::path::Path;
use zeroize::Zeroizing;

use crate::{
    authoring, canonical,
    error::{ErrorKind, Failure, Result},
    files, identity, passport,
};

fn invalid() -> Failure {
    Failure::precondition(
        "the isolated account state, exact intent or server response is inconsistent",
    )
}

fn identity_at(root: &Path) -> Result<identity::Identity> {
    identity::current(root)?.ok_or_else(|| {
        Failure::precondition("initialize the isolated device before connecting an account")
    })
}

fn bind(plan: &Plan) -> Result<identity::Identity> {
    let identity = identity_at(&plan.root)?;
    check_binding(&identity, plan)?;
    Ok(identity)
}

fn check_binding(identity: &identity::Identity, plan: &Plan) -> Result<()> {
    if let Some(connection) = &plan.connection {
        if identity.root_binding() != (plan.root.as_path(), &plan.root_identity)
            || !identity.historical(&plan.identity)
            || identity.storage() != plan.credential_store
        {
            return Err(invalid());
        }
        return connection.check(identity);
    }
    if identity.root_binding() != (plan.root.as_path(), &plan.root_identity)
        || identity.context() != plan.identity
        || identity.storage() != plan.credential_store
        || identity.report()["public_key"] != plan.public_key
        || identity.recovery_binding().map(|e| &e.plan.public_key)
            != plan.revoked_public_key.as_ref()
        || identity
            .recovery_binding()
            .and_then(|e| e.plan.recovery.as_ref())
            .and_then(|r| r.account_id.as_ref())
            != plan.expected_account_id.as_ref()
    {
        return Err(invalid());
    }
    Ok(())
}

// Call only after acquiring the account journal and before opening a registry.
// Holding that journal drains recovery; later revalidation must not recursively
// acquire the registry lock while an authoring/acquisition transaction owns it.
fn check_enrollment_constraints(identity: &identity::Identity, plan: &Plan) -> Result<()> {
    if let Some(connection) = &plan.connection {
        let constraints = enrollment_recovery::constraints(identity, connection)?;
        if constraints.as_ref().map(|v| v.0.as_str()) != plan.expected_account_id.as_deref()
            || constraints.as_ref().map(|v| v.1.as_str()) != plan.revoked_public_key.as_deref()
        {
            return Err(invalid());
        }
    }
    Ok(())
}

fn check_state(state: &State, plan: &Plan) -> Result<()> {
    if state.plan.connection.is_some() || plan.connection.is_some() {
        if state.plan.connection != plan.connection
            || state.plan.expected_account_id != plan.expected_account_id
            || state.plan.revoked_public_key != plan.revoked_public_key
            || state.plan.root != plan.root
            || state.plan.root_identity != plan.root_identity
            || state.plan.identity.account_id != plan.identity.account_id
            || state.plan.credential_store != plan.credential_store
        {
            return Err(invalid());
        }
        return Ok(());
    }
    if state.plan.root != plan.root
        || state.plan.root_identity != plan.root_identity
        || state.plan.identity != plan.identity
        || state.plan.credential_store != plan.credential_store
        || state.plan.public_key != plan.public_key
        || state.plan.expected_account_id != plan.expected_account_id
        || state.plan.revoked_public_key != plan.revoked_public_key
    {
        return Err(invalid());
    }
    Ok(())
}

pub fn plan(
    root: &Path,
    action: Action,
    api: Option<&str>,
    provider: Option<&str>,
    at: &str,
) -> Result<Plan> {
    plan_for_connection(root, action, api, provider, None, at)
}

pub fn plan_for_connection(
    root: &Path,
    action: Action,
    api: Option<&str>,
    provider: Option<&str>,
    connection: Option<&str>,
    at: &str,
) -> Result<Plan> {
    let identity = identity_at(root)?;
    let connection = connection
        .map(|id| connections::enrollment(&identity, id))
        .transpose()?;
    if connection.is_some() && matches!(action, Action::Attach | Action::Recover | Action::Import) {
        return Err(Failure::precondition(
            "this action requires the legacy local-owner session; it cannot replace another connection's identity",
        ));
    }
    let (root, root_identity) = identity.root_binding();
    let (root, root_identity) = (root.to_owned(), root_identity.clone());
    let journal = Journal::for_connection(&identity, connection.as_ref(), false)?;
    let enrollment_constraints = if let Some(connection) = &connection {
        enrollment_recovery::fresh(&identity, connection)?;
        enrollment_recovery::constraints(&identity, connection)?
    } else {
        None
    };
    if journal
        .as_ref()
        .map(Journal::pending)
        .transpose()?
        .flatten()
        .is_some()
    {
        return Err(Failure::precondition(
            "resume the retained account operation before planning another one",
        ));
    }
    let state = journal.as_ref().map(Journal::state).transpose()?.flatten();
    let recovered = if connection.is_none() {
        identity.recovery_binding()
    } else {
        None
    };
    let origin = transport::origin(
        api.or_else(|| connection.as_ref().map(|value| value.origin.as_str()))
            .unwrap_or_else(|| {
                state.as_ref().map_or_else(
                    || recovered.map_or(crate::config::CATALOG_URL, |e| e.plan.origin.as_str()),
                    |s| s.plan.origin.as_str(),
                )
            }),
    )?;
    let provider = provider
        .or_else(|| connection.as_ref().map(|value| value.provider.as_str()))
        .unwrap_or_else(|| {
            state.as_ref().map_or_else(
                || recovered.map_or("github", |e| e.plan.provider.as_str()),
                |s| s.plan.provider.as_str(),
            )
        });
    if recovered.is_some_and(|e| e.plan.origin != origin) {
        return Err(invalid());
    }
    let mut plan = Plan {
        schema_version: 1,
        action,
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        root,
        root_identity,
        identity: identity.context(),
        public_key: identity.report()["public_key"]
            .as_str()
            .ok_or_else(invalid)?
            .into(),
        credential_store: identity.storage(),
        origin,
        provider: provider.into(),
        expected_revision: state.as_ref().map(|s| s.revision.clone()),
        attachment: None,
        recovery: None,
        expected_account_id: enrollment_constraints
            .as_ref()
            .map(|value| value.0.clone())
            .or_else(|| {
                recovered
                    .and_then(|e| e.plan.recovery.as_ref())
                    .and_then(|r| r.account_id.clone())
            }),
        revoked_public_key: enrollment_constraints
            .map(|value| value.1)
            .or_else(|| recovered.map(|e| e.plan.public_key.clone())),
        connection,
    };
    if action == Action::Recover {
        plan.recovery = Some(recovery::selection(
            &identity,
            journal.as_ref().ok_or_else(invalid)?,
            state.as_ref().ok_or_else(invalid)?,
            at,
        )?);
    }
    if action == Action::Attach {
        let state = state.as_ref().ok_or_else(invalid)?;
        let Session::Authorized { account_id, .. } = &state.session else {
            return Err(invalid());
        };
        let store = crate::store::Store::planning_at(identity.root_directory())?;
        plan.attachment = Some(attachment::selection(
            &store.connection,
            &plan.identity,
            account_id,
            at,
        )?);
    }
    plan.validate()?;
    precondition(&plan, state.as_ref(), at)?;
    Ok(plan)
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let value = canonical::parse(&files::read(path, 4 * 1024 * 1024)?)?;
    let plan: Plan = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    plan.validate()?;
    if crate::digest::canonical("ai-stp:plan:v1", &value)? != plan.digest()? {
        return Err(invalid());
    }
    Ok(plan)
}

fn precondition(plan: &Plan, state: Option<&State>, at: &str) -> Result<()> {
    if let Some(state) = state {
        check_state(state, plan)?;
        if at < state.completed_at.as_str() {
            return Err(Failure::precondition(
                "the clock precedes the retained account operation",
            ));
        }
        if plan.action != Action::Start
            && (plan.origin != state.plan.origin || plan.provider != state.plan.provider)
        {
            return Err(invalid());
        }
    }
    if plan.expected_revision.as_deref() != state.map(|s| s.revision.as_str()) {
        return Err(invalid());
    }
    match (plan.action, state.map(|s| &s.session)) {
        (Action::Start, None | Some(Session::Closed { .. })) => Ok(()),
        (Action::Start, Some(Session::Pending { expires_at, .. })) if at >= expires_at.as_str() => {
            Ok(())
        }
        (
            Action::Poll,
            Some(Session::Pending {
                next_poll_at,
                expires_at,
                ..
            }),
        ) if at >= next_poll_at.as_str() || at >= expires_at.as_str() => Ok(()),
        (Action::Refresh, Some(Session::Authorized { .. })) => Ok(()),
        (
            Action::Attach,
            Some(Session::Authorized {
                account_id,
                expires_at,
                ..
            }),
        ) if at < expires_at.as_str()
            && plan
                .attachment
                .as_ref()
                .is_some_and(|s| s.account_id == *account_id) =>
        {
            Ok(())
        }
        (Action::Logout, Some(_)) => Ok(()),
        (Action::Recover, Some(Session::Closed { reason })) if reason == "device_revoked" => Ok(()),
        (Action::Poll, Some(Session::Pending { .. })) => Err(Failure::precondition(
            "the authorization polling interval has not elapsed",
        )),
        _ => Err(Failure::precondition(
            "the current account session does not admit this action; inspect account status",
        )),
    }
}

pub fn status(root: &Path, at: &str) -> Result<Value> {
    status_for_connection(root, None, at)
}

fn qualify_status(mut value: Value, connection: Option<&connections::Enrollment>) -> Value {
    if let Some(connection) = connection {
        value["connection_id"] = connection.connection_id.clone().into();
        value["origin"] = connection.origin.clone().into();
        value["provider"] = connection.provider.clone().into();
        value["device_id"] = connection.device_id.clone().into();
        value["owner_attached"] = false.into();
        if let Some(fields) = value.as_object_mut() {
            fields.remove("effective_owner_id");
        }
    }
    value
}

pub fn status_for_connection(root: &Path, connection: Option<&str>, at: &str) -> Result<Value> {
    if !passport::timestamp(at) {
        return Err(invalid());
    }
    if connection.is_none()
        && let Some(pending) = recovery::pending(root)?
    {
        return Ok(pending);
    }
    let identity = identity_at(root)?;
    let connection = connection
        .map(|id| connections::enrollment(&identity, id))
        .transpose()?;
    let journal = Journal::for_connection(&identity, connection.as_ref(), false)?;
    identity.revalidate()?;
    let store = crate::store::Store::planning_at(identity.root_directory())?;
    let owner = attachment::effective(&store.connection, &identity)?;
    drop(store);
    let Some(journal) = journal else {
        return Ok(qualify_status(
            json!({"schema_version":1,"session":{"state":"absent"},"owner_attached":owner != identity.context(),"effective_owner_id":owner.account_id,"online_verified":false}),
            connection.as_ref(),
        ));
    };
    let state = journal.state()?;
    if let Some(state) = &state {
        check_binding(&identity, &state.plan)?;
        check_enrollment_constraints(&identity, &state.plan)?;
    }
    let pending = journal.pending()?;
    if let Some(pending) = &pending {
        check_binding(&identity, &pending.plan)?;
        check_enrollment_constraints(&identity, &pending.plan)?;
    }
    let mut result=state.map_or_else(||json!({"schema_version":1,"session":{"state":"absent"},"owner_attached":false,"online_verified":false}),|s|s.public(at));
    result["owner_attached"] = (owner != identity.context()).into();
    result["effective_owner_id"] = owner.account_id.into();
    result["pending_operation"] = match pending {
        Some(p) => json!({"plan":p.plan,"plan_digest":p.plan.digest()?}),
        None => Value::Null,
    };
    Ok(qualify_status(result, connection.as_ref()))
}

pub fn apply(plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    plan.validate()?;
    if !passport::timestamp(at) || plan.digest()? != expected {
        return Err(invalid());
    }
    if plan.action == Action::Recover {
        return recovery::apply(plan, at);
    }
    let identity = identity_at(&plan.root)?;
    if check_binding(&identity, plan).is_err() {
        if plan.connection.is_some() {
            return Err(invalid());
        }
        identity.historical_account(plan)?;
        if plan.action == Action::Attach {
            return attachment::apply(plan, &identity, at);
        }
        let journal = Journal::at(
            identity.root_directory(),
            plan.credential_store,
            &plan.identity.device_id,
            false,
        )?
        .ok_or_else(invalid)?;
        return Ok(journal.receipt(plan)?.ok_or_else(invalid)?.public());
    }
    if plan.action == Action::Attach {
        return attachment::apply(plan, &identity, at);
    }
    let existing = Journal::for_connection(&identity, plan.connection.as_ref(), false)?;
    if existing.is_none() && (at < plan.created_at.as_str() || at > plan.expires_at.as_str()) {
        return Err(Failure::precondition(
            "the account plan expired before admission",
        ));
    }
    let journal = match existing {
        Some(v) => v,
        None => Journal::for_connection(&identity, plan.connection.as_ref(), true)?
            .ok_or_else(invalid)?,
    };
    check_enrollment_constraints(&identity, plan)?;
    if let Some(receipt) = journal.receipt(plan)? {
        if journal.pending()?.is_some_and(|p| p.plan == *plan) {
            journal.clear_pending(plan)?;
        }
        enrollment_recovery::confirm(&identity, &receipt)?;
        return Ok(receipt.public());
    }
    let state = journal.state()?;
    if let Some(state) = &state {
        check_state(state, plan)?;
        if state.plan == *plan {
            let receipt = journal.complete(state)?;
            enrollment_recovery::confirm(&identity, &receipt)?;
            return Ok(receipt.public());
        }
    }
    if let Some(connection) = &plan.connection {
        enrollment_recovery::fresh(&identity, connection)?;
    }
    let pending = journal.pending()?;
    let resumed = pending.is_some();
    if (!resumed || plan.action == Action::Start)
        && matches!(plan.action, Action::Start | Action::Poll | Action::Refresh)
        && let Some(connection) = &plan.connection
    {
        connection.verify_key(&identity)?;
    }
    let pending = match pending {
        Some(p) if p.plan == *plan => p,
        Some(_) => {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "another account operation must complete first",
            ));
        }
        None => {
            if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
                return Err(Failure::precondition(
                    "the account plan expired before admission",
                ));
            }
            precondition(plan, state.as_ref(), at)?;
            let pending = Pending {
                plan: plan.clone(),
                requested_at: at.into(),
            };
            journal.admit(&pending)?;
            pending
        }
    };
    precondition(plan, state.as_ref(), at)?;
    let (session, outcome) = if resumed && plan.action != Action::Start {
        // Exchange is single use. A crash after send cannot be distinguished from
        // a committed response that never reached the credential store.
        let state = state.ok_or_else(invalid)?;
        if plan.action == Action::Poll {
            (
                Session::Closed {
                    reason: "exchange_response_unknown".into(),
                },
                Outcome::ExchangeUnknown,
            )
        } else if plan.action == Action::Logout {
            closed("remote_revocation_unconfirmed", Outcome::LogoutUnconfirmed)
        } else {
            (state.session, Outcome::RequestUnknown)
        }
    } else {
        execute(
            plan,
            state.map(|s| s.session),
            &identity,
            &pending.requested_at,
            at,
        )?
    };
    bind(plan)?;
    let state = State {
        plan: plan.clone(),
        revision: plan.operation_id.clone(),
        session,
        outcome,
        completed_at: now_after(at),
    };
    journal.write(&state)?;
    let receipt = journal.complete(&state)?;
    enrollment_recovery::confirm(&identity, &receipt)?;
    Ok(receipt.public())
}

fn now_after(at: &str) -> String {
    format!("{:.3}", jiff::Timestamp::now()).max(at.into())
}

fn execute(
    plan: &Plan,
    session: Option<Session>,
    identity: &identity::Identity,
    requested_at: &str,
    at: &str,
) -> Result<(Session, Outcome)> {
    let api = Api::new(&plan.origin)?;
    match plan.action {
        Action::Attach | Action::Recover | Action::Import => Err(invalid()),
        Action::Start => {
            // Preserve the first attempt's deadline across idempotent start retries.
            if at >= after(requested_at, 1800)?.as_str() {
                return Ok(closed("authorization_expired", Outcome::Expired));
            }
            let body=serde_json::to_vec(&json!({"schema_version":1,"provider":plan.provider,"idempotency_key":plan.operation_id})).map_err(|_|invalid())?;
            match api.post::<Grant>("device", &body, None)? {
                Reply::Resource(grant) => {
                    validate_grant(&grant, &plan.origin)?;
                    let expires_at = after(requested_at, grant.expires_in)?;
                    if now_after(at) >= expires_at {
                        return Ok(closed("authorization_expired", Outcome::Expired));
                    }
                    Ok((
                        Session::Pending {
                            device_code: grant.device_code,
                            user_code: grant.user_code,
                            verification_uri: grant.verification_uri,
                            verification_uri_complete: grant.verification_uri_complete,
                            expires_at,
                            interval: grant.interval,
                            next_poll_at: after(&now_after(at), grant.interval)?,
                        },
                        Outcome::Pending,
                    ))
                }
                Reply::Refused(Code::Expired) => {
                    Ok(closed("authorization_expired", Outcome::Expired))
                }
                Reply::Refused(_) => Ok(closed("authorization_refused", Outcome::Refused)),
            }
        }
        Action::Poll => poll(&api, plan, session.ok_or_else(invalid)?, at),
        Action::Refresh => {
            let session = session.ok_or_else(invalid)?;
            match refresh(&api, plan, &session, identity, at)? {
                Reply::Resource(tokens) => Ok((authorized(tokens, at)?, Outcome::Authorized)),
                Reply::Refused(Code::Revoked) => Ok(closed("device_revoked", Outcome::Revoked)),
                Reply::Refused(Code::Unauthorized | Code::Forbidden) => {
                    Ok(closed("credentials_rejected", Outcome::Refused))
                }
                Reply::Refused(_) => Ok((session, Outcome::Refused)),
            }
        }
        Action::Logout => {
            let session = session.ok_or_else(invalid)?;
            if !matches!(session, Session::Authorized { .. }) {
                return Ok(closed(
                    "local_authorization_discarded",
                    Outcome::LocallyClosed,
                ));
            }
            Ok(match remote_logout(&api, plan, &session, identity, at) {
                Ok(true) => closed("remote_sessions_revoked", Outcome::Closed),
                Ok(false) => closed("remote_credentials_unavailable", Outcome::LocallyClosed),
                Err(_) => closed("remote_revocation_unconfirmed", Outcome::LogoutUnconfirmed),
            })
        }
    }
}

fn closed(reason: &str, outcome: Outcome) -> (Session, Outcome) {
    (
        Session::Closed {
            reason: reason.into(),
        },
        outcome,
    )
}

fn remote_logout(
    api: &Api,
    plan: &Plan,
    session: &Session,
    identity: &identity::Identity,
    at: &str,
) -> Result<bool> {
    let Session::Authorized {
        access_token,
        expires_at,
        ..
    } = session
    else {
        return Err(invalid());
    };
    if at < expires_at.as_str() {
        match api.post::<transport::Logout>("logout", b"{}", Some(access_token))? {
            Reply::Resource(result) if result.schema_version == 1 && result.revoked => {
                return Ok(true);
            }
            Reply::Refused(Code::Unauthorized | Code::Forbidden) => {}
            Reply::Refused(Code::Revoked) => return Ok(false),
            _ => return Err(invalid()),
        }
    }
    let tokens = match refresh(api, plan, session, identity, at)? {
        Reply::Resource(tokens) => tokens,
        Reply::Refused(Code::Unauthorized | Code::Forbidden | Code::Revoked) => return Ok(false),
        _ => return Err(invalid()),
    };
    match api.post::<transport::Logout>("logout", b"{}", Some(&tokens.access_token))? {
        Reply::Resource(result) if result.schema_version == 1 && result.revoked => Ok(true),
        _ => Err(invalid()),
    }
}

fn poll(api: &Api, plan: &Plan, session: Session, at: &str) -> Result<(Session, Outcome)> {
    let Session::Pending {
        device_code,
        user_code,
        verification_uri,
        verification_uri_complete,
        expires_at,
        mut interval,
        ..
    } = session
    else {
        return Err(invalid());
    };
    if at >= expires_at.as_str() {
        return Ok(closed("authorization_expired", Outcome::Expired));
    }
    #[derive(Serialize)]
    struct Request<'a> {
        schema_version: u32,
        device_code: &'a model::Secret,
        device_id: &'a str,
        public_key: &'a str,
        display_name: &'a str,
        #[serde(skip_serializing_if = "Option::is_none")]
        expected_account_id: Option<&'a str>,
        #[serde(skip_serializing_if = "Option::is_none")]
        revoked_public_key: Option<&'a str>,
    }
    let body = Zeroizing::new(
        serde_json::to_vec(&Request {
            schema_version: 1,
            device_code: &device_code,
            device_id: plan.device_id(),
            public_key: plan.enrollment_public_key(),
            display_name: "ai-stp Rust CLI",
            expected_account_id: plan.expected_account_id.as_deref(),
            revoked_public_key: plan.revoked_public_key.as_deref(),
        })
        .map_err(|_| invalid())?,
    );
    let outcome = match api.post::<Tokens>("device/token", &body, None)? {
        Reply::Resource(tokens) => {
            validate_tokens(&tokens, plan, plan.expected_account_id.as_deref())?;
            return Ok((authorized(tokens, at)?, Outcome::Authorized));
        }
        Reply::Refused(Code::Expired) => {
            return Ok(closed("authorization_expired", Outcome::Expired));
        }
        Reply::Refused(Code::Declined) => {
            return Ok(closed("authorization_declined", Outcome::Declined));
        }
        Reply::Refused(Code::Revoked) => {
            return Ok(closed("device_revoked", Outcome::Revoked));
        }
        Reply::Refused(Code::Pending) => Outcome::Pending,
        Reply::Refused(Code::SlowDown) => {
            interval = interval.checked_add(5).ok_or_else(invalid)?;
            Outcome::RateLimited
        }
        Reply::Refused(_) => return Ok(closed("authorization_refused", Outcome::Refused)),
    };
    Ok((
        Session::Pending {
            device_code,
            user_code,
            verification_uri,
            verification_uri_complete,
            expires_at,
            interval,
            next_poll_at: after(&now_after(at), interval)?,
        },
        outcome,
    ))
}

fn refresh(
    api: &Api,
    plan: &Plan,
    session: &Session,
    identity: &identity::Identity,
    at: &str,
) -> Result<Reply<Tokens>> {
    let Session::Authorized {
        account_id,
        refresh_token,
        ..
    } = session
    else {
        return Err(invalid());
    };
    let checked_at = now_after(at);
    let message = format!(
        "ai-stp:device-refresh:v1\n{}\n{checked_at}",
        plan.device_id()
    );
    let signature = URL_SAFE_NO_PAD.encode(plan.sign(identity, message.as_bytes())?);
    let body=serde_json::to_vec(&json!({"schema_version":1,"device_id":plan.device_id(),"checked_at":checked_at,"signature":signature})).map_err(|_|invalid())?;
    let reply = api.post::<Tokens>("device/refresh", &body, Some(refresh_token))?;
    if let Reply::Resource(tokens) = &reply {
        validate_tokens(tokens, plan, Some(account_id))?;
    }
    Ok(reply)
}

fn authorized(tokens: Tokens, at: &str) -> Result<Session> {
    Ok(Session::Authorized {
        account_id: tokens.account_id,
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token,
        expires_at: after(at, tokens.expires_in)?,
    })
}

fn validate_tokens(tokens: &Tokens, plan: &Plan, account: Option<&str>) -> Result<()> {
    if tokens.schema_version != 1
        || tokens.token_type != "Bearer"
        || tokens.device_id != plan.device_id()
        || !passport::stable_id(&tokens.account_id, "account")
        || account.is_some_and(|v| v != tokens.account_id)
        || !(60..=86400).contains(&tokens.expires_in)
    {
        return Err(invalid());
    }
    Ok(())
}

fn validate_grant(grant: &Grant, origin: &str) -> Result<()> {
    if grant.schema_version != 1
        || !(60..=1800).contains(&grant.expires_in)
        || !(1..=60).contains(&grant.interval)
        || !(32..=256).contains(&grant.device_code.0.len())
        || !grant
            .device_code
            .0
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
    {
        return Err(invalid());
    }
    validate_browser(
        &grant.user_code,
        &grant.verification_uri,
        &grant.verification_uri_complete,
        origin,
    )
}

fn validate_browser(code: &str, plain: &str, complete: &str, origin: &str) -> Result<()> {
    if code.len() != 9
        || code.as_bytes()[4] != b'-'
        || !code
            .bytes()
            .enumerate()
            .all(|(i, b)| i == 4 || b"0123456789ABCDEFGHJKMNPQRSTVWXYZ".contains(&b))
    {
        return Err(invalid());
    }
    for (uri, filled) in [(plain, false), (complete, true)] {
        if uri.len() > 2048
            || uri
                .chars()
                .any(|c| c.is_control() || c.is_whitespace() || c == '\\')
        {
            return Err(invalid());
        }
        let url = url::Url::parse(uri).map_err(|_| invalid())?;
        if url.origin().ascii_serialization() != origin
            || !url.username().is_empty()
            || url.password().is_some()
            || url.fragment().is_some()
            || !matches!(url.path(), "/en/device-login" | "/ru/device-login")
        {
            return Err(invalid());
        }
        let query = url.query_pairs().collect::<Vec<_>>();
        if filled {
            if query.len() != 1 || query[0].0 != "user_code" || query[0].1 != code {
                return Err(invalid());
            }
        } else if !query.is_empty() {
            return Err(invalid());
        }
    }
    Ok(())
}

fn validate_session(state: &State) -> Result<()> {
    match &state.session {
        Session::Pending {
            device_code,
            user_code,
            verification_uri,
            verification_uri_complete,
            expires_at,
            interval,
            next_poll_at,
        } => {
            if !(32..=256).contains(&device_code.0.len())
                || !device_code
                    .0
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
                || !(1..=1800).contains(interval)
                || !passport::timestamp(expires_at)
                || !passport::timestamp(next_poll_at)
            {
                return Err(invalid());
            }
            validate_browser(
                user_code,
                verification_uri,
                verification_uri_complete,
                &state.plan.origin,
            )?;
        }
        Session::Authorized {
            account_id,
            expires_at,
            ..
        } => {
            if !passport::stable_id(account_id, "account") || !passport::timestamp(expires_at) {
                return Err(invalid());
            }
        }
        Session::Closed { reason } => {
            if !matches!(
                reason.as_str(),
                "exchange_response_unknown"
                    | "device_revoked"
                    | "authorization_expired"
                    | "authorization_refused"
                    | "authorization_declined"
                    | "credentials_rejected"
                    | "local_authorization_discarded"
                    | "remote_credentials_unavailable"
                    | "remote_sessions_revoked"
                    | "remote_revocation_unconfirmed"
            ) {
                return Err(invalid());
            }
        }
    }
    Ok(())
}
