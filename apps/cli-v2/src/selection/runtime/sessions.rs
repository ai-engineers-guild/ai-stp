//! CLI plans bind the state parent and provider selector. Only the native
//! runtime constructs eligibility inputs; retained terminal outcomes replay offline.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Request, Selector, inputs, invalid, owner, with_provider};
use crate::{
    authoring::Identity,
    canonical, digest,
    error::{Failure, Result},
    files,
    projection::Scope,
    selection::{graph, sessions},
    store::Store,
};

const MAX_PLAN: u64 = 2 * 1024 * 1024;
const POLICY: &str = "native-local-selection/1";

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema_version: u32,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    state_parent: PathBuf,
    selector: Option<Selector>,
    operation: Value,
}

impl Plan {
    fn digest(&self) -> Result<String> {
        let value = value(self)?;
        if canonical::bytes(&value)?.len() as u64 > MAX_PLAN {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }

    fn selector(&self, harness: &str) -> Result<&Selector> {
        let selector = self.selector.as_ref().ok_or_else(invalid)?;
        selector.validate()?;
        if selector.harness_id != harness {
            return Err(invalid());
        }
        Ok(selector)
    }
}

fn value(input: &impl Serialize) -> Result<Value> {
    serde_json::to_value(input).map_err(|_| invalid())
}

fn moment() -> String {
    format!("{:.3}", jiff::Timestamp::now())
}

fn planned(
    parent: &Path,
    selector: Option<Selector>,
    operation: &impl Serialize,
    provider: Value,
) -> Result<Value> {
    let plan = Plan {
        schema_version: 1,
        state_parent: PathBuf::from(files::location(parent)?),
        selector,
        operation: value(operation)?,
    };
    Ok(json!({"plan_digest":plan.digest()?,"plan":plan,"provider":provider}))
}

fn references(members: &[sessions::Member]) -> Result<Vec<Value>> {
    members
        .iter()
        .map(|member| value(&member.reference()))
        .collect()
}

fn preflight(store: &mut Store, roots: &[Value]) -> Result<()> {
    if roots.is_empty() {
        return Ok(());
    }
    let graph = store.transaction(|t| graph::exact(t, roots))?;
    if graph["resolved"] != true {
        return Err(
            Failure::precondition("the exact selection graph is unresolved")
                .with_details([("graph".into(), graph)]),
        );
    }
    Ok(())
}

pub fn propose(parent: &Path, project: &str, path: &Path, empty: bool) -> Result<Value> {
    let request = Request::parse(path, empty)?;
    if request.for_redistribution
        || !crate::passport::stable_id(project, "project")
        || request
            .members
            .iter()
            .any(|member| !crate::passport::stable_id(&member.stable_id, "component"))
    {
        return Err(invalid());
    }
    let identity = owner(parent)?;
    let target = request.target(&identity)?;
    let roots = request
        .members
        .iter()
        .map(value)
        .collect::<Result<Vec<_>>>()?;
    let mut store = Store::planning(parent)?;
    preflight(&mut store, &roots)?;
    drop(store);
    let selector = request.selector();
    with_provider(
        parent,
        &selector,
        &identity,
        |provider, artifact, report| {
            let mut store = Store::planning(parent)?;
            let operation = store.transaction(|t| {
                let observed = inputs(t, &roots, target)?;
                let runtime = sessions::Runtime {
                    identity: &identity,
                    target: &observed.target,
                    evidence: &observed.evidence,
                    provider: Some(provider),
                    policy_version: POLICY,
                };
                let plan =
                    sessions::plan_in(t, project, &request.members, empty, &runtime, &moment())?;
                artifact.executable()?;
                Ok(plan)
            })?;
            planned(parent, Some(selector.clone()), &operation, report)
        },
    )
}

/// Planning a decision records intent. A new confirmation must establish the
/// exact snapshot again during apply; terminal replay does not need a provider.
pub fn decision(parent: &Path, id: &str, target: Option<(Scope, &str)>) -> Result<Value> {
    let identity = owner(parent)?;
    let mut store = Store::planning(parent)?;
    let proposal = sessions::read(&mut store, id)?;
    let selector = target.map(|(scope, version)| Selector {
        harness_id: proposal.harness_id,
        scope,
        provider_version: version.into(),
    });
    if let Some(selector) = &selector {
        selector.validate()?;
    }
    let plan = sessions::decision(&mut store, id, selector.is_none(), &identity, &moment())?;
    planned(parent, selector, &plan, Value::Null)
}

pub fn read(parent: &Path, id: &str) -> Result<Value> {
    let mut store = Store::planning(parent)?;
    let proposal = sessions::read(&mut store, id)?;
    Ok(json!({"proposal":proposal,"state":proposal.state(&moment())?}))
}

pub fn apply(path: &Path, expected: &str) -> Result<Value> {
    let plan: Plan = serde_json::from_value(canonical::parse(&files::read(path, MAX_PLAN)?)?)
        .map_err(|_| invalid())?;
    if plan.schema_version != 1 || !plan.state_parent.is_absolute() || plan.digest()? != expected {
        return Err(invalid());
    }
    let identity = owner(&plan.state_parent)?;
    match plan.operation["action"].as_str().ok_or_else(invalid)? {
        "selection.propose" => apply_proposal(&plan, &identity),
        "selection.confirm" => apply_confirmation(&plan, &identity),
        "selection.cancel" => {
            if plan.selector.is_some() {
                return Err(invalid());
            }
            let operation: sessions::Decision =
                serde_json::from_value(plan.operation).map_err(|_| invalid())?;
            let digest = operation.digest()?;
            operation.validate(&digest, &identity, &moment(), "selection.cancel")?;
            let mut store = Store::open(&plan.state_parent, false)?;
            value(&sessions::cancel(
                &mut store,
                &operation,
                &digest,
                &identity,
                &moment(),
            )?)
        }
        _ => Err(invalid()),
    }
}

fn apply_proposal(plan: &Plan, identity: &Identity) -> Result<Value> {
    let operation: sessions::Plan =
        serde_json::from_value(plan.operation.clone()).map_err(|_| invalid())?;
    let selector = plan.selector(&operation.context.harness_id)?;
    let digest = operation.digest()?;
    let mut store = Store::planning(&plan.state_parent)?;
    if let Some(held) =
        store.transaction(|t| sessions::proposed(t, &operation, &digest, identity, &moment()))?
    {
        return value(&held);
    }
    let roots = references(&operation.members)?;
    preflight(&mut store, &roots)?;
    drop(store);
    with_provider(
        &plan.state_parent,
        selector,
        identity,
        |provider, artifact, _| {
            let mut store = Store::open(&plan.state_parent, false)?;
            store.transaction(|t| {
                // Another invocation may have completed while provider I/O ran.
                if let Some(held) = sessions::proposed(t, &operation, &digest, identity, &moment())?
                {
                    return value(&held);
                }
                let observed = inputs(t, &roots, selector.target(identity)?)?;
                let runtime = sessions::Runtime {
                    identity,
                    target: &observed.target,
                    evidence: &observed.evidence,
                    provider: Some(provider),
                    policy_version: POLICY,
                };
                let result = sessions::propose_in(t, &operation, &digest, &runtime, &moment())?;
                artifact.executable()?;
                value(&result)
            })
        },
    )
}

fn apply_confirmation(plan: &Plan, identity: &Identity) -> Result<Value> {
    let operation: sessions::Decision =
        serde_json::from_value(plan.operation.clone()).map_err(|_| invalid())?;
    let digest = operation.digest()?;
    let mut store = Store::planning(&plan.state_parent)?;
    let proposal = sessions::read(&mut store, &operation.proposal_id)?;
    let selector = plan.selector(&proposal.harness_id)?;
    if let Some(held) =
        store.transaction(|t| sessions::confirmed(t, &operation, &digest, identity, &moment()))?
    {
        return value(&held);
    }
    let roots = references(&proposal.members)?;
    preflight(&mut store, &roots)?;
    drop(store);
    with_provider(
        &plan.state_parent,
        selector,
        identity,
        |provider, artifact, _| {
            let mut store = Store::open(&plan.state_parent, false)?;
            store.transaction(|t| {
                if let Some(held) =
                    sessions::confirmed(t, &operation, &digest, identity, &moment())?
                {
                    return value(&held);
                }
                let observed = inputs(t, &roots, selector.target(identity)?)?;
                let runtime = sessions::Runtime {
                    identity,
                    target: &observed.target,
                    evidence: &observed.evidence,
                    provider: Some(provider),
                    policy_version: POLICY,
                };
                let result = sessions::confirm_in(t, &operation, &digest, &runtime, &moment())?;
                artifact.executable()?;
                value(&result)
            })
        },
    )
}
