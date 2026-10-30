//! Explicit local consent and bounded foreground heartbeat delivery.
//!
//! No service, startup registration, harness invocation or installation inventory.

mod contract;
#[cfg(test)]
mod tests;

use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;

use super::{
    access::{Access, Binding},
    contexts::{self, Authority, Context},
    corporate::{self, Request},
};
use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files::{self, OwnedDirectory},
    passport, wire,
};
use contract::{Pending, at, time};

const DIRECTORY: &str = "ai-stp-v2-heartbeats";
const OWNER: &[u8] = b"ai-stp-cli-v2 foreground heartbeat v1\n";
const LIMIT: u64 = 65536;

pub(super) fn invalid() -> Failure {
    Failure::precondition("the original heartbeat context, consent or retained observation changed")
}
pub(super) fn uncertain() -> Failure {
    Failure::new(
        ErrorKind::Unavailable,
        "heartbeat delivery is unconfirmed; retain the original observation until retry or expiry",
    )
}
pub(super) fn signature_message(organization: &str, value: &Value) -> Result<Vec<u8>> {
    contract::message(organization, value)
}
pub(super) fn write_body(
    organization: &str,
    account: &str,
    device: &str,
    bytes: &[u8],
) -> Result<()> {
    let body = contract::request(bytes)?;
    if !passport::stable_id(organization, "organization")
        || body["account_id"] != account
        || body["device_id"] != device
    {
        return Err(invalid());
    }
    Ok(())
}
fn moment() -> String {
    format!("{:.3}", jiff::Timestamp::now())
}
fn encode(value: &impl Serialize) -> Result<Vec<u8>> {
    let bytes = serde_json::to_vec(value).map_err(|_| invalid())?;
    if bytes.len() as u64 > LIMIT {
        return Err(invalid());
    }
    Ok(bytes)
}
fn organization(context: &Context) -> Result<&str> {
    let Authority::Remote { organization, .. } = &context.authority else {
        return Err(invalid());
    };
    if organization["kind"] != "corporate" {
        return Err(invalid());
    }
    let id = organization["organization_id"]
        .as_str()
        .ok_or_else(invalid)?;
    if !passport::stable_id(id, "organization") {
        return Err(invalid());
    }
    Ok(id)
}
fn binding(context: &Context) -> Result<&Binding> {
    let Authority::Remote { account, .. } = &context.authority else {
        return Err(invalid());
    };
    organization(context)?;
    Ok(account)
}
fn directory(context: &Context, create: bool) -> Result<Option<OwnedDirectory>> {
    let identity = context.bind()?;
    OwnedDirectory::open_at(identity.root_directory(), DIRECTORY, OWNER, create)
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Record {
    schema_version: u32,
    context: Context,
    account: Binding,
    enabled: bool,
    consent_revision: String,
    consent_plan_id: String,
    consent_plan_digest: String,
    policy_version: u64,
    pending: Option<Pending>,
    authority_retry_at: Option<String>,
    next_observation_at: Option<String>,
    last_attempt_at: Option<String>,
    last_success_at: Option<String>,
    outcome: Option<String>,
}
impl Record {
    fn validate(&self, context: &Context) -> Result<()> {
        self.account.validate()?;
        let original = binding(context)?;
        if self.schema_version != 1
            || self.context != *context
            || self.consent_revision.parse::<ulid::Ulid>().is_err()
            || !passport::stable_id(&self.consent_plan_id, "plan")
            || !contract::hash(&self.consent_plan_digest)
            || self.account.origin != original.origin
            || self.account.account_id != original.account_id
            || self.account.device_id != original.device_id
            || self.account.public_key != original.public_key
            || self.account.root_identity != original.root_identity
            || self.account.credential_store != original.credential_store
            || self.account.connection != original.connection
            || !self.enabled && self.pending.is_some()
            || self.outcome.as_deref().is_some_and(|v| {
                !matches!(
                    v,
                    "acknowledged"
                        | "superseded"
                        | "unconfirmed"
                        | "expired"
                        | "interrupted"
                        | "policy_changed"
                        | "authority_unavailable"
                        | "refused"
                )
            })
        {
            return Err(invalid());
        }
        for value in [
            &self.next_observation_at,
            &self.last_attempt_at,
            &self.last_success_at,
            &self.authority_retry_at,
        ]
        .into_iter()
        .flatten()
        {
            time(value)?;
        }
        if let Some(pending) = &self.pending {
            let request = pending.request()?;
            if request["account_id"] != self.account.account_id
                || request["device_id"] != self.account.device_id
                || request["policy_version"] != self.policy_version
            {
                return Err(invalid());
            }
        }
        Ok(())
    }
    fn save(&self, dir: &OwnedDirectory) -> Result<()> {
        self.validate(&self.context)?;
        dir.atomic(&format!("{}.json", self.context.context_id), &encode(self)?)
    }
    fn stop(&mut self, outcome: &str) {
        self.enabled = false;
        self.pending = None;
        self.authority_retry_at = None;
        self.consent_revision = ulid::Ulid::generate().to_string();
        self.outcome = Some(outcome.into());
    }
}
fn load(dir: &OwnedDirectory, context: &Context) -> Result<Option<Record>> {
    let Some(bytes) = dir.read_file(&format!("{}.json", context.context_id), LIMIT)? else {
        return Ok(None);
    };
    let record: Record = serde_json::from_value(wire::parse(&bytes)?).map_err(|_| invalid())?;
    record.validate(context)?;
    Ok(Some(record))
}
fn view(context: &Context, record: Option<&Record>) -> Result<Value> {
    let pending = record.and_then(|v| v.pending.as_ref());
    Ok(
        json!({"schema_version":1,"context_id":context.context_id,"context_digest":context.digest()?,
        "organization_id":organization(context)?,"enabled":record.is_some_and(|v|v.enabled),
        "consent_revision":record.map(|v|&v.consent_revision),"policy_version":record.map(|v|v.policy_version),
        "pending":pending.is_some(),"pending_checked_at":pending.map(|v|&v.checked_at),
        "pending_expires_at":pending.map(|v|&v.expires_at),"next_attempt_at":pending.map(|v|&v.next_attempt_at),
        "attempts":pending.map_or(0,|v|v.attempts),"next_observation_at":record.and_then(|v|v.next_observation_at.as_ref()),
        "authority_retry_at":record.and_then(|v|v.authority_retry_at.as_ref()),
        "last_attempt_at":record.and_then(|v|v.last_attempt_at.as_ref()),"last_success_at":record.and_then(|v|v.last_success_at.as_ref()),
        "last_outcome":record.and_then(|v|v.outcome.as_ref()),"scheduler_registered":false,
        "scheduling_owner":"foreground_client","coverage":"cli_foreground_liveness_only",
        "harness_runtime_coverage":"unknown","managed_inventory":"none"}),
    )
}

/// The held access serializes this original enrollment; Store is never held over HTTP.
fn online(context: &Context, account: &Binding) -> Result<(Access, Value, String)> {
    let identity = context.bind()?;
    context.require_current_native_identity(&identity.context())?;
    let mut access = Access::for_binding(&context.root, account, false)?;
    access.check_local_actor(&context.local_identity)?;
    let org = organization(context)?;
    let (before, observation) = contexts::remote(&mut access, Some(org))?;
    let authority = corporate::authority(&before, &observation);
    let data = access.corporate(&Request::HeartbeatPolicy, org)?;
    let policy = Request::HeartbeatPolicy.project(&data, org, &account.account_id)?;
    let (after, observation) = contexts::remote(&mut access, Some(org))?;
    if authority != corporate::authority(&after, &observation) {
        return Err(invalid());
    }
    Ok((
        access,
        policy,
        digest::sha256(&canonical::bytes(&authority)?),
    ))
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ConsentPlan {
    schema_version: u32,
    action: String,
    plan_id: String,
    created_at: String,
    expires_at: String,
    context: Context,
    account: Binding,
    policy_version: u64,
    policy: Value,
    expected_revision: Option<String>,
}
impl ConsentPlan {
    pub fn digest(&self) -> Result<String> {
        self.context.digest()?;
        self.account.validate()?;
        let original = binding(&self.context)?;
        let policy = Request::HeartbeatPolicy.project(
            &self.policy,
            organization(&self.context)?,
            &self.account.account_id,
        )?;
        if self.schema_version != 1
            || self.action != "corporate.heartbeat.consent"
            || !passport::stable_id(&self.plan_id, "plan")
            || time(&self.expires_at)? - time(&self.created_at)? != 600
            || policy != self.policy
            || policy["policy_version"] != self.policy_version
            || policy["enabled"] != true
            || self.account.origin != original.origin
            || self.account.account_id != original.account_id
            || self.account.device_id != original.device_id
            || self.account.public_key != original.public_key
            || self.account.root_identity != original.root_identity
            || self.account.credential_store != original.credential_store
            || self.account.connection != original.connection
            || self
                .expected_revision
                .as_ref()
                .is_some_and(|v| v.parse::<ulid::Ulid>().is_err())
        {
            return Err(invalid());
        }
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

pub fn consent_plan(root: &Path, context_id: &str, now: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context_id))?;
    let (access, policy, _) = online(&context, binding(&context)?)?;
    if policy["enabled"] != true {
        return Err(Failure::precondition(
            "company heartbeat reporting is disabled",
        ));
    }
    let dir = directory(&context, false)?;
    let previous = dir
        .as_ref()
        .map(|d| load(d, &context))
        .transpose()?
        .flatten();
    let plan = ConsentPlan {
        schema_version: 1,
        action: "corporate.heartbeat.consent".into(),
        plan_id: format!("plan_{}", ulid::Ulid::generate()),
        created_at: now.into(),
        expires_at: at(time(now)? + 600)?,
        account: access.binding().clone(),
        policy_version: policy["policy_version"].as_u64().ok_or_else(invalid)?,
        policy,
        expected_revision: previous.as_ref().map(|v| v.consent_revision.clone()),
        context,
    };
    Ok(
        json!({"context_digest":plan.context.digest()?,"plan_digest":plan.digest()?,"plan":plan,"disclosure":{
        "coverage":"cli_foreground_liveness_only","fields":["account_id","device_id","cli_version","capabilities","last_sync_at","health_state","checked_at","policy_version","signature"],
        "harness_runtime_coverage":"unknown","managed_inventory":"none","startup_service_installed":false}}),
    )
}
pub fn read_plan(path: &Path) -> Result<ConsentPlan> {
    let plan: ConsentPlan =
        serde_json::from_value(wire::parse(&files::read(path, LIMIT)?)?).map_err(|_| invalid())?;
    plan.digest()?;
    Ok(plan)
}
pub fn consent_apply(plan: &ConsentPlan, expected: &str, now: &str) -> Result<Value> {
    if plan.digest()? != expected {
        return Err(invalid());
    }
    let context = contexts::resolve(&plan.context.root, Some(&plan.context.context_id))?;
    if context != plan.context {
        return Err(invalid());
    }
    // Read-only replay cannot re-enable consent after a later local disable.
    if let Some(dir) = directory(&context, false)?
        && let Some(record) = load(&dir, &context)?
        && record.consent_plan_id == plan.plan_id
        && record.consent_plan_digest == expected
    {
        return view(&context, Some(&record));
    }
    if time(now)? < time(&plan.created_at)? || time(now)? >= time(&plan.expires_at)? {
        return Err(invalid());
    }
    let (access, policy, _) = online(&context, &plan.account)?;
    if access.binding() != &plan.account
        || policy["enabled"] != true
        || policy["policy_version"] != plan.policy_version
        || policy != plan.policy
    {
        return Err(invalid());
    }
    let dir = directory(&context, true)?.ok_or_else(invalid)?;
    let previous = load(&dir, &context)?;
    if let Some(record) = &previous
        && record.consent_plan_id == plan.plan_id
        && record.consent_plan_digest == expected
    {
        return view(&context, Some(record));
    }
    if previous.as_ref().map(|v| &v.consent_revision) != plan.expected_revision.as_ref() {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "local heartbeat consent changed; review it again",
        ));
    }
    let record = Record {
        schema_version: 1,
        context: context.clone(),
        account: plan.account.clone(),
        enabled: true,
        consent_revision: ulid::Ulid::generate().to_string(),
        consent_plan_id: plan.plan_id.clone(),
        consent_plan_digest: expected.into(),
        policy_version: plan.policy_version,
        pending: None,
        authority_retry_at: None,
        next_observation_at: None,
        last_attempt_at: None,
        last_success_at: None,
        outcome: previous
            .filter(|v| v.pending.is_some())
            .map(|_| "interrupted".into()),
    };
    record.save(&dir)?;
    view(&context, Some(&record))
}
pub fn status(root: &Path, context_id: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context_id))?;
    organization(&context)?;
    let dir = directory(&context, false)?;
    let record = dir
        .as_ref()
        .map(|d| load(d, &context))
        .transpose()?
        .flatten();
    view(&context, record.as_ref())
}
pub fn disable(root: &Path, context_id: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context_id))?;
    organization(&context)?;
    let Some(dir) = directory(&context, false)? else {
        return view(&context, None);
    };
    let Some(mut record) = load(&dir, &context)? else {
        return view(&context, None);
    };
    if record.enabled {
        record.stop("interrupted");
        record.save(&dir)?;
    }
    view(&context, Some(&record))
}

/// Expired payload bytes are retired on the next foreground maintenance pass.
/// This is local-only and also runs while a personal view is selected.
pub fn maintain(root: &Path) -> Result<Value> {
    maintain_at(root, &moment())
}
pub(super) fn maintain_at(root: &Path, now: &str) -> Result<Value> {
    let contexts = contexts::list(root)?;
    let contexts = contexts["contexts"].as_array().ok_or_else(invalid)?;
    let now = time(now)?;
    let mut expired = 0;
    for item in contexts {
        let context: Context =
            serde_json::from_value(item["context"].clone()).map_err(|_| invalid())?;
        if organization(&context).is_err() {
            continue;
        }
        let Some(dir) = directory(&context, false)? else {
            continue;
        };
        let Some(mut record) = load(&dir, &context)? else {
            continue;
        };
        if record
            .pending
            .as_ref()
            .is_some_and(|v| time(&v.expires_at).is_ok_and(|v| now >= v))
        {
            record.pending = None;
            record.outcome = Some("expired".into());
            record.save(&dir)?;
            expired += 1;
        }
    }
    Ok(
        json!({"schema_version":1,"expired_payloads_retired":expired,"network_requests":0,"scheduler_registered":false}),
    )
}

pub fn flush(root: &Path, context_id: &str) -> Result<Value> {
    flush_with_clock(root, context_id, moment)
}
pub(super) fn flush_with_clock(
    root: &Path,
    context_id: &str,
    clock: impl Fn() -> String,
) -> Result<Value> {
    let context = contexts::resolve(root, Some(context_id))?;
    organization(&context)?;
    // Snapshot before account access; never acquire account while retaining the
    // local outbox lock (all writers follow account -> outbox).
    let snapshot = {
        let Some(dir) = directory(&context, false)? else {
            return view(&context, None);
        };
        let Some(mut record) = load(&dir, &context)? else {
            return view(&context, None);
        };
        if !record.enabled {
            return view(&context, Some(&record));
        }
        let now = clock();
        let seconds = time(&now)?;
        if record.pending.as_ref().is_some_and(|p| {
            time(&p.expires_at).is_ok_and(|v| seconds >= v)
                || time(&p.checked_at).is_ok_and(|v| seconds < v)
        }) {
            record.pending = None;
            record.outcome = Some("expired".into());
            record.save(&dir)?;
            return view(&context, Some(&record));
        }
        if record
            .authority_retry_at
            .as_ref()
            .is_some_and(|v| time(v).is_ok_and(|v| seconds < v))
        {
            return view(&context, Some(&record));
        }
        let due = record
            .pending
            .as_ref()
            .map(|v| &v.next_attempt_at)
            .or(record.next_observation_at.as_ref());
        if due.is_some_and(|v| time(v).is_ok_and(|v| time(&now).is_ok_and(|now| now < v))) {
            return view(&context, Some(&record));
        }
        record
    };
    let current = online(&context, &snapshot.account);
    let (access, policy, authority) = match current {
        Ok(value) => value,
        Err(error) => {
            let dir = directory(&context, false)?.ok_or_else(invalid)?;
            let mut record = load(&dir, &context)?.ok_or_else(invalid)?;
            if record.consent_revision != snapshot.consent_revision {
                return view(&context, Some(&record));
            }
            if matches!(error.kind, ErrorKind::Unavailable) {
                // Discovery failure cannot replace or resign a retained payload.
                record.authority_retry_at = Some(at(time(&clock())? + 60)?);
                record.outcome = Some("authority_unavailable".into());
            } else {
                record.stop("authority_unavailable");
            }
            record.save(&dir)?;
            return view(&context, Some(&record));
        }
    };
    let dir = directory(&context, false)?.ok_or_else(invalid)?;
    let mut record = load(&dir, &context)?.ok_or_else(invalid)?;
    if !record.enabled || record.consent_revision != snapshot.consent_revision {
        return view(&context, Some(&record));
    }
    record.authority_retry_at = None;
    if policy["enabled"] != true || policy["policy_version"] != record.policy_version {
        record.stop("policy_changed");
        record.save(&dir)?;
        return view(&context, Some(&record));
    }
    let now = clock();
    if let Some(pending) = &record.pending {
        if time(&now)? >= time(&pending.expires_at)? || time(&now)? < time(&pending.checked_at)? {
            record.pending = None;
            record.outcome = Some("expired".into());
            record.save(&dir)?;
            return view(&context, Some(&record));
        }
        if pending.session_revision != access.binding().revision
            || pending.authority_digest != authority
        {
            record.pending = None;
            record.outcome = Some("interrupted".into());
            record.save(&dir)?;
            return view(&context, Some(&record));
        }
        if !pending.ready(&now)? {
            return view(&context, Some(&record));
        }
    } else {
        if record
            .next_observation_at
            .as_ref()
            .is_some_and(|v| time(v).is_ok_and(|v| time(&now).is_ok_and(|now| now < v)))
        {
            return view(&context, Some(&record));
        }
        let mut body = contract::unsigned(
            &record.account.account_id,
            &record.account.device_id,
            record.policy_version,
            &now,
        );
        let signature = access.sign_heartbeat(organization(&context)?, &body)?;
        body["signature"] = URL_SAFE_NO_PAD.encode(signature).into();
        let body = String::from_utf8(canonical::bytes(&body)?).map_err(|_| invalid())?;
        record.pending = Some(Pending {
            sha256: digest::sha256(body.as_bytes()),
            body,
            session_revision: access.binding().revision.clone(),
            authority_digest: authority.clone(),
            checked_at: now.clone(),
            expires_at: at(time(&now)? + contract::LIFETIME)?,
            next_attempt_at: now.clone(),
            attempts: 0,
        });
        let interval = policy["interval_seconds"].as_u64().ok_or_else(invalid)?;
        record.next_observation_at = Some(at(time(&now)?
            .checked_add(interval.try_into().map_err(|_| invalid())?)
            .ok_or_else(invalid)?)?);
    }
    let send_at = clock();
    let pending = record.pending.as_mut().ok_or_else(invalid)?;
    if !pending.ready(&send_at)? {
        record.save(&dir)?;
        return view(&context, Some(&record));
    }
    pending.attempted(
        &send_at,
        policy["retry_base_seconds"].as_u64().ok_or_else(invalid)?,
        policy["retry_max_seconds"].as_u64().ok_or_else(invalid)?,
    )?;
    let body = pending.body.clone();
    record.last_attempt_at = Some(send_at);
    record.outcome = Some("unconfirmed".into());
    record.save(&dir)?; // Retain exact signed bytes and pacing before any PUT.
    let result = access.heartbeat(organization(&context)?, body.as_bytes());
    match result {
        Ok(response) => {
            let outcome = record
                .pending
                .as_ref()
                .ok_or_else(invalid)?
                .acknowledge(organization(&context)?, &response);
            if let Ok(outcome) = outcome {
                record.outcome = Some(outcome.into());
                if outcome == "acknowledged" {
                    record.last_success_at = Some(clock());
                }
                record.pending = None;
            }
        }
        Err(error) if !matches!(error.kind, ErrorKind::Unavailable) => record.stop("refused"),
        Err(_) => (),
    }
    // A lost or invalid reply remains unconfirmed. It never creates new bytes.
    record.save(&dir)?;
    context.bind()?.revalidate()?;
    view(&context, Some(&record))
}
