//! Exact native sync command plans; terminal replay is local and query-only.

use super::{
    client::{self, Client},
    ledger::Scope,
    push, recovery,
    run::{self, Run},
};
use crate::{
    account::access::{Access, Binding},
    authoring, canonical, digest,
    error::{Failure, Result},
    files, identity, passport,
    store::Store,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

pub use super::interruption::Checkpoint;

#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
pub enum Request {
    Push {
        id: String,
    },
    Pull {
        page_size: u16,
        skip_event_ids: BTreeSet<String>,
    },
    Recover {
        event_id: String,
    },
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    schema_version: u32,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub(super) state_parent: PathBuf,
    pub(super) account: Binding,
    pub(super) operation_id: String,
    request: Request,
    capture: Option<push::Capture>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(super) retirement: Option<recovery::Capture>,
    pub(super) frontier: String,
    pub(super) created_at: String,
    pub(super) expires_at: String,
}

fn invalid() -> Failure {
    Failure::input("the private sync plan or its exact confirmation is invalid")
}

impl Request {
    fn validate(&self) -> Result<()> {
        match self {
            Self::Push { id } => {
                if id.is_empty()
                    || id.len() > 128
                    || !id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
                {
                    return Err(invalid());
                }
            }
            Self::Recover { event_id } => {
                if !(8..=128).contains(&event_id.len())
                    || !event_id.bytes().all(|b| {
                        b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'~' | b'-')
                    })
                {
                    return Err(invalid());
                }
            }
            Self::Pull {
                page_size,
                skip_event_ids,
            } => {
                if !(1..=100).contains(page_size)
                    || skip_event_ids.len() > 100
                    || skip_event_ids.iter().any(|id| {
                        !(8..=128).contains(&id.len())
                            || !id.bytes().all(|b| {
                                b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'~' | b'-')
                            })
                    })
                {
                    return Err(invalid());
                }
            }
        }
        Ok(())
    }
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        self.request.validate()?;
        self.account.validate()?;
        if self.schema_version != 1
            || !self.state_parent.is_absolute()
            || !passport::stable_id(&self.operation_id, "operation")
            || authoring::expiry(&self.created_at)? != self.expires_at
            || matches!(self.request, Request::Push { .. }) != self.capture.is_some()
            || matches!(self.request, Request::Recover { .. }) != self.retirement.is_some()
        {
            return Err(invalid());
        }
        if let (Request::Recover { event_id }, Some(retirement)) = (&self.request, &self.retirement)
        {
            let event = super::event::Event::push(&retirement.request, &self.account.account_id)?;
            if event.event_id != *event_id
                || retirement.replacement_device_id != self.account.device_id
                || event.device_id == retirement.replacement_device_id
            {
                return Err(invalid());
            }
        }
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        if canonical::bytes(&value)?.len() > 16 * 1024 * 1024 {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }
    pub(super) fn entity(&self) -> Option<String> {
        self.capture
            .as_ref()
            .map(|c| c.entity_id.clone())
            .or_else(|| {
                self.retirement
                    .as_ref()
                    .and_then(|c| c.entity().map(str::to_owned))
            })
    }

    pub(super) fn validate_local(
        &self,
        connection: &rusqlite::Connection,
        owner: &authoring::runtime::Owner,
        scope: &Scope,
        at: &str,
    ) -> Result<()> {
        Run::prepare(connection, self, scope, at)?;
        if let (Request::Push { id }, Some(expected)) = (&self.request, &self.capture)
            && push::capture_for_sender(
                connection,
                owner,
                &authoring::Identity {
                    account_id: self.account.account_id.clone(),
                    device_id: self.account.device_id.clone(),
                },
                id,
            )? != *expected
        {
            return Err(Failure::precondition(
                "the private push content changed after planning",
            ));
        }
        if let (Request::Recover { event_id }, Some(expected)) = (&self.request, &self.retirement)
            && recovery::capture(connection, scope, owner, &self.account, event_id)? != *expected
        {
            return Err(Failure::precondition(
                "the retired-device request changed after planning",
            ));
        }
        Ok(())
    }
}

pub fn plan(
    root: &Path,
    origin: Option<&str>,
    configuration: Option<&Path>,
    request: Request,
    at: &str,
) -> Result<Plan> {
    plan_for_connection(root, origin, None, configuration, request, at)
}

pub fn plan_for_connection(
    root: &Path,
    origin: Option<&str>,
    connection: Option<&str>,
    configuration: Option<&Path>,
    request: Request,
    at: &str,
) -> Result<Plan> {
    request.validate()?;
    client::enabled(configuration)?;
    let state_parent = PathBuf::from(files::location(root)?);
    let mut account = Access::for_connection(&state_parent, origin, connection, false)?;
    account.verify()?;
    let owner = authoring::runtime::owner(&state_parent)?;
    let store = owner.planning()?;
    account.check_registry_owner(&store.connection)?;
    let scope = Scope::new(&account.binding().account_id, &account.binding().origin)?;
    scope.inspect(&store.connection)?;
    let capture = match &request {
        Request::Push { id } => Some(push::capture_for_sender(
            &store.connection,
            &owner,
            &authoring::Identity {
                account_id: account.binding().account_id.clone(),
                device_id: account.binding().device_id.clone(),
            },
            id,
        )?),
        Request::Pull { .. } | Request::Recover { .. } => None,
    };
    let retirement = match &request {
        Request::Recover { event_id } => Some(recovery::capture(
            &store.connection,
            &scope,
            &owner,
            account.binding(),
            event_id,
        )?),
        _ => None,
    };
    let frontier = run::frontier(
        &store.connection,
        &scope,
        capture
            .as_ref()
            .map(|c| c.entity_id.as_str())
            .or_else(|| retirement.as_ref().and_then(recovery::Capture::entity)),
    )?;
    let plan = Plan {
        schema_version: 1,
        state_parent,
        account: account.binding().clone(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        request,
        capture,
        retirement,
        frontier,
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
    };
    plan.digest()?;
    account.revalidate()?;
    Ok(plan)
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let plan: Plan =
        serde_json::from_value(canonical::parse(&files::read(path, 16 * 1024 * 1024)?)?)
            .map_err(|_| invalid())?;
    plan.digest()?;
    Ok(plan)
}

pub fn apply(plan: &Plan, expected: &str, configuration: Option<&Path>, at: &str) -> Result<Value> {
    if plan.digest()? != expected {
        return Err(invalid());
    }
    // The original physical root and identity history own terminal evidence,
    // even after logout. No session or network is needed to replay that result.
    let identity = identity::current(&plan.state_parent)?.ok_or_else(invalid)?;
    if identity.root_binding().1 != &plan.account.root_identity {
        return Err(invalid());
    }
    let store = Store::planning_at(identity.root_directory())?;
    let previous = Run::load(&store.connection, plan)?;
    identity.revalidate()?;
    if let Some(run) = &previous
        && run.result.is_some()
    {
        return run.output(plan);
    }
    drop(store);
    drop(identity);
    if previous.is_none()
        && (!passport::timestamp(at)
            || at < plan.created_at.as_str()
            || at > plan.expires_at.as_str())
    {
        return Err(invalid());
    }
    let mut client = Client::for_plan(&plan.state_parent, configuration, plan)?;
    client.run = Some(client.store.transaction(|t| {
        let at = format!("{:.3}", jiff::Timestamp::now());
        client.scope.bind(t, &at)?;
        Run::admit(t, plan, &client.scope, &at)
    })?);
    let result = match &plan.request {
        Request::Push { .. } => {
            let capture = plan.capture.as_ref().ok_or_else(invalid)?;
            client.push(capture, &capture.digest()?)?
        }
        Request::Pull {
            page_size,
            skip_event_ids,
        } => client.pull(*page_size, skip_event_ids)?,
        Request::Recover { .. } => client.recover(
            plan.retirement.as_ref().ok_or_else(invalid)?,
            &plan.operation_id,
            expected,
        )?,
    };
    let run = client.run.as_mut().ok_or_else(invalid)?;
    if run.result.is_none() {
        client.store.transaction(|t| {
            run.check(t, &client.scope)?;
            run.save(
                t,
                &client.scope,
                Some(result),
                &format!("{:.3}", jiff::Timestamp::now()),
            )
        })?;
    }
    run.output(plan)
}
