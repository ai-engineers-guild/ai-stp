//! Durable proposals and atomic confirmation, with runtime-established evidence.

mod context;
mod records;

pub use context::{Context, Member, Runtime};
use context::{context_history, evaluate, owned_head};
use records::{load, replay, require};

use crate::{
    authoring::{Identity, expiry, setups},
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    passport,
    store::Store,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;

const MAX_BYTES: usize = 1024 * 1024;

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub proposal_id: String,
    pub identity: Identity,
    pub context: Context,
    pub members: Vec<Member>,
    pub created_at: String,
    pub expires_at: String,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        plan_digest(self)
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Decision {
    pub schema_version: u32,
    pub action: String,
    pub proposal_id: String,
    pub snapshot: String,
    pub identity: Identity,
    pub created_at: String,
    pub expires_at: String,
}

impl Decision {
    pub fn digest(&self) -> Result<String> {
        plan_digest(self)
    }

    fn validate(&self, expected: &str, identity: &Identity, at: &str, action: &str) -> Result<()> {
        identity.validate()?;
        if self.schema_version != 1
            || self.action != action
            || self.identity != *identity
            || !passport::stable_id(&self.proposal_id, "proposal")
            || !hash(&self.snapshot)
            || !passport::timestamp(at)
            || self.expires_at != expiry(&self.created_at)?
            || self.digest()? != expected
        {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Serialize)]
pub struct Proposal {
    pub proposal_id: String,
    pub project_id: String,
    pub harness_id: String,
    pub snapshot: String,
    pub members: Vec<Member>,
    pub created_at: String,
    pub expires_at: String,
    pub cancelled_at: Option<String>,
    pub confirmed_stable_id: Option<String>,
    pub confirmed_version: Option<String>,
}

impl Proposal {
    pub fn state(&self, at: &str) -> Result<&'static str> {
        if !passport::timestamp(at) {
            return Err(invalid());
        }
        Ok(if self.confirmed_stable_id.is_some() {
            "confirmed"
        } else if self.cancelled_at.is_some() {
            "cancelled"
        } else if at >= self.expires_at.as_str() {
            "expired"
        } else {
            "open"
        })
    }
}

#[derive(Serialize)]
pub struct Confirmation {
    pub passport: Value,
    pub created: bool,
    /// The historical confirmation outcome; current selection may differ.
    pub state: &'static str,
}

fn invalid() -> Failure {
    Failure::input("the selection plan or session record violates its exact contract")
}

fn stale() -> Failure {
    Failure::precondition("the proposal context, policy or exact members changed")
        .with_details([("constraint".into(), "selection_snapshot_changed".into())])
}

fn hash(value: &str) -> bool {
    value.strip_prefix("sha256:").is_some_and(|s| {
        s.len() == 64
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}

fn value<T: Serialize>(input: &T) -> Result<Value> {
    let value = serde_json::to_value(input).map_err(|_| invalid())?;
    if canonical::bytes(&value)?.len() > MAX_BYTES {
        return Err(invalid());
    }
    Ok(value)
}

fn plan_digest<T: Serialize>(input: &T) -> Result<String> {
    digest::canonical("ai-stp:plan:v1", &value(input)?)
}

fn within(at: &str, start: &str, end: &str) -> Result<()> {
    if at < start || at >= end {
        return Err(Failure::precondition(
            "the selection plan is outside its validity interval",
        ));
    }
    Ok(())
}

pub fn plan(
    store: &mut Store,
    project: &str,
    roots: &[setups::Member],
    empty: bool,
    runtime: &Runtime<'_>,
    at: &str,
) -> Result<Plan> {
    if roots.is_empty() != empty {
        return Err(invalid());
    }
    let expires_at = expiry(at)?;
    store.transaction(|t| {
        let (context, members) = evaluate(t, project, roots, runtime)?;
        let plan = Plan {
            schema_version: 1,
            action: "selection.propose".into(),
            proposal_id: format!("proposal_{}", ulid::Ulid::generate()),
            identity: runtime.identity.clone(),
            context,
            members,
            created_at: at.into(),
            expires_at,
        };
        plan.digest()?;
        Ok(plan)
    })
}

pub fn read(store: &mut Store, id: &str) -> Result<Proposal> {
    store.transaction(|t| require(t, id))
}

pub fn propose(
    store: &mut Store,
    plan: &Plan,
    expected_digest: &str,
    runtime: &Runtime<'_>,
    at: &str,
) -> Result<Proposal> {
    runtime.identity.validate()?;
    if plan.schema_version != 1
        || plan.action != "selection.propose"
        || plan.identity != *runtime.identity
        || !passport::stable_id(&plan.proposal_id, "proposal")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected_digest
    {
        return Err(invalid());
    }
    let snapshot = plan.context.snapshot(&plan.members)?;
    store.transaction(|t| {
        if let Some(held) = load(t, &plan.proposal_id)? {
            if held.project_id != plan.context.project_id
                || held.harness_id != plan.context.harness_id
                || held.snapshot != snapshot
                || held.members != plan.members
                || held.created_at != plan.created_at
                || held.expires_at != plan.expires_at
            {
                return Err(Failure::new(
                    ErrorKind::Conflict,
                    "the proposal identity already belongs to another plan",
                ));
            }
            context_history(t, &plan.context, runtime.identity)?;
            return Ok(held);
        }
        within(at, &plan.created_at, &plan.expires_at)?;
        let roots = plan
            .members
            .iter()
            .map(Member::reference)
            .collect::<Vec<_>>();
        let (context, members) = evaluate(t, &plan.context.project_id, &roots, runtime)?;
        if context != plan.context || members != plan.members {
            return Err(stale());
        }
        records::insert(t, plan, &snapshot)
    })
}

pub fn decision(
    store: &mut Store,
    id: &str,
    cancel: bool,
    identity: &Identity,
    at: &str,
) -> Result<Decision> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    store.transaction(|t| {
        let proposal = require(t, id)?;
        owned_head(t, "project", &proposal.project_id, identity)?;
        Ok(Decision {
            schema_version: 1,
            action: if cancel {
                "selection.cancel"
            } else {
                "selection.confirm"
            }
            .into(),
            proposal_id: id.into(),
            snapshot: proposal.snapshot,
            identity: identity.clone(),
            created_at: at.into(),
            expires_at,
        })
    })
}

fn matches(proposal: &Proposal, decision: &Decision) -> Result<()> {
    if proposal.snapshot != decision.snapshot {
        return Err(stale());
    }
    Ok(())
}

pub fn cancel(
    store: &mut Store,
    plan: &Decision,
    expected_digest: &str,
    identity: &Identity,
    at: &str,
) -> Result<Proposal> {
    plan.validate(expected_digest, identity, at, "selection.cancel")?;
    store.transaction(|t| {
        let held = require(t, &plan.proposal_id)?;
        matches(&held, plan)?;
        owned_head(t, "project", &held.project_id, identity)?;
        if held.confirmed_stable_id.is_some() {
            return Err(Failure::precondition(
                "a confirmed proposal cannot be cancelled",
            ));
        }
        if held.cancelled_at.is_some() {
            return Ok(held);
        }
        within(at, &plan.created_at, &plan.expires_at)?;
        if at < held.created_at.as_str() {
            return Err(invalid());
        }
        records::cancel(t, &held, at)
    })
}

pub fn confirm(
    store: &mut Store,
    plan: &Decision,
    expected_digest: &str,
    runtime: &Runtime<'_>,
    at: &str,
) -> Result<Confirmation> {
    plan.validate(expected_digest, runtime.identity, at, "selection.confirm")?;
    store.transaction(|t| {
        let held = require(t, &plan.proposal_id)?;
        matches(&held, plan)?;
        // Read terminal state under the same writer as creation. Replay neither
        // rechecks mutable context nor overwrites a more recently selected pair.
        if let (Some(id), Some(version)) = (&held.confirmed_stable_id, &held.confirmed_version) {
            return replay(t, &held, id, version, runtime.identity);
        }
        if held.state(at)? != "open" {
            return Err(Failure::precondition(
                "the proposal is cancelled or expired",
            ));
        }
        within(at, &held.created_at, &held.expires_at)?;
        within(at, &plan.created_at, &plan.expires_at)?;
        let roots = held
            .members
            .iter()
            .map(Member::reference)
            .collect::<Vec<_>>();
        let (context, members) = evaluate(t, &held.project_id, &roots, runtime)?;
        if context.harness_id != held.harness_id
            || members != held.members
            || context.snapshot(&members)? != held.snapshot
        {
            return Err(stale());
        }
        records::freeze(t, &held, context, runtime.identity, expected_digest, at)
    })
}
