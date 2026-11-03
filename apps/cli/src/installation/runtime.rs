//! Parser-free public native configuration workflows.

use super::{
    custody::Custody,
    planning::{self, Operation, Reviewed},
};
use crate::{
    account::contexts,
    authoring::runtime::owner,
    error::{Failure, Result},
    files,
    projection::Scope,
    selection::{
        graph,
        runtime::native::{self, Decisions},
    },
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Coordinates {
    stable_id: String,
    version: String,
    passport_digest: String,
}
#[derive(Default, Deserialize)]
#[serde(rename_all = "snake_case")]
enum Trust {
    #[default]
    Pinned,
    ExactSetup,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    schema_version: u32,
    setup: Coordinates,
    harness_id: String,
    operation: Operation,
    roots: BTreeMap<Scope, Location>,
    #[serde(default)]
    placements: BTreeMap<String, Scope>,
    #[serde(default)]
    corporate_binding: Option<String>,
    #[serde(default)]
    trust: Trust,
    #[serde(default)]
    trust_pins: BTreeSet<String>,
    #[serde(default)]
    permissions: BTreeSet<String>,
}
struct Location(PathBuf);
impl<'de> Deserialize<'de> for Location {
    fn deserialize<D: serde::Deserializer<'de>>(
        deserializer: D,
    ) -> std::result::Result<Self, D::Error> {
        let value = Value::deserialize(deserializer)?;
        match value {
            Value::String(path) => Ok(Self(path.into())),
            value => files::deserialize_path(value)
                .map(Self)
                .map_err(serde::de::Error::custom),
        }
    }
}
fn invalid() -> Failure {
    Failure::input("native configuration requires a closed bounded exact setup request")
}
fn coordinates(value: &Coordinates) -> Value {
    json!({"stable_id":value.stable_id,"version":value.version,"passport_digest":value.passport_digest})
}

pub fn plan(root: &Path, context: Option<&str>, input: &Path, at: &str) -> Result<Value> {
    let input: Input =
        serde_json::from_value(crate::wire::parse(&files::read(input, 128 * 1024)?)?)
            .map_err(|_| invalid())?;
    if input.schema_version != 1
        || input.operation == Operation::Remove
        || !(1..=3).contains(&input.roots.len())
        || input.placements.len() > 512
        || input.trust_pins.len() > 512
        || input.permissions.len() > 512
    {
        return Err(invalid());
    }
    let context = contexts::resolve(root, context)?;
    let setup = coordinates(&input.setup);
    let mut pins = input.trust_pins;
    if matches!(input.trust, Trust::ExactSetup) {
        let owner = owner(root)?;
        let mut store = owner.planning()?;
        let graph = store
            .transaction(|connection| graph::exact(connection, std::slice::from_ref(&setup)))?;
        if graph["resolved"] != true {
            return Err(invalid());
        }
        for node in graph["nodes"].as_array().ok_or_else(invalid)? {
            pins.insert(node["passport_digest"].as_str().ok_or_else(invalid)?.into());
        }
    }
    let scope = *input.roots.keys().next().ok_or_else(invalid)?;
    let (target, evidence) = native::observe(
        root,
        &context,
        &setup,
        Decisions {
            harness_id: input.harness_id,
            scope,
            pins,
            permissions: input.permissions,
        },
    )?;
    let request = planning::Request {
        operation: input.operation,
        setup,
        target,
        evidence,
        roots: input
            .roots
            .into_iter()
            .map(|(scope, path)| (scope, path.0))
            .collect(),
        placements: input.placements,
        corporate_binding: input.corporate_binding,
    };
    let planned = planning::create(root, &context.context_id, &request, at)?;
    let custody = Custody::open_user()?;
    let reviewed = Reviewed::create(root, &planned.plan, &custody, at)?;
    Ok(
        json!({"plan":reviewed.value()?,"plan_digest":reviewed.digest()?,"configuration_changed":false,"execution_authorized":false}),
    )
}
pub fn prepare(root: &Path, input: &Path, expected: &str, at: &str) -> Result<Value> {
    let review = planning::retirement::read(input, expected)?;
    let mut custody = Custody::open_user()?;
    if review.retirement().is_some() {
        return planning::retirement::prepare(root, &mut custody, &review, expected, at);
    }
    let plan = review.original_plan()?.ok_or_else(invalid)?;
    let operation = plan.value()?["operation_id"]
        .as_str()
        .ok_or_else(invalid)?
        .to_owned();
    if let Some(retained) = custody.retained(&operation)? {
        if retained.digest()? != expected
            || retained.original_plan()?.ok_or_else(invalid)?.value()? != plan.value()?
        {
            return Err(invalid());
        }
        let status = planning::configuration_status(root, &custody, &operation, expected)?;
        let phase = status["custody"]["state"].as_str().ok_or_else(invalid)?;
        return Ok(
            json!({"kind":"native.configuration.preparation","operation_id":operation,"plan_digest":expected,
            "state":if phase=="completed"{status["state"].as_str().unwrap_or("configured")}else{phase},"custody":status["custody"],
            "configuration_changed":false,"execution_authorized":false}),
        );
    }
    let reviewed = Reviewed::create(root, &plan, &custody, at)?;
    if reviewed.digest()? != expected {
        return Err(Failure::precondition(
            "native review changed before preparation; review the current exact effects",
        ));
    }
    reviewed.prepare(root, &mut custody, expected, at)
}
pub fn remove_plan(root: &Path, operation: &str, expected: &str, at: &str) -> Result<Value> {
    let custody = Custody::open_user()?;
    let plan = planning::create_removal(root, &custody, operation, expected, at)?;
    let reviewed = Reviewed::create(root, &plan, &custody, at)?;
    Ok(
        json!({"plan":reviewed.value()?,"plan_digest":reviewed.digest()?,"configuration_changed":false,"execution_authorized":false}),
    )
}
pub fn apply(root: &Path, operation: &str, digest: &str, at: &str) -> Result<Value> {
    let mut custody = Custody::open_user()?;
    if let Some(review) = retained_retirement(&custody, operation, digest)? {
        return planning::retirement::apply(root, &mut custody, &review);
    }
    planning::apply_prepared(root, &mut custody, operation, digest, at)
}
pub fn status(root: &Path, operation: &str, digest: &str) -> Result<Value> {
    let custody = existing()?;
    if let Some(review) = retained_retirement(&custody, operation, digest)? {
        return planning::retirement::status(root, &custody, &review);
    }
    planning::configuration_status(root, &custody, operation, digest)
}
pub fn cancel(root: &Path, operation: &str, digest: &str, at: &str) -> Result<Value> {
    let mut custody = Custody::open_user()?;
    if let Some(review) = retained_retirement(&custody, operation, digest)? {
        return planning::retirement::cancel(root, &mut custody, &review);
    }
    planning::cancel_preparation(root, &mut custody, operation, digest, at)
}
pub fn confirm(root: &Path, operation: &str, digest: &str, at: &str) -> Result<Value> {
    planning::confirm_session(root, &existing()?, operation, digest, at)
}

pub fn effective(root: &Path, context: Option<&str>) -> Result<Value> {
    let context = contexts::resolve(root, context)?;
    let Some(custody) = Custody::existing_user()? else {
        return Ok(
            json!({"context_id":context.context_id,"setups":[],"authorization_granted":false}),
        );
    };
    planning::effective(root, &custody, &context)
}
pub fn pending(root: &Path) -> Result<Value> {
    let Some(custody) = Custody::existing_user()? else {
        return Ok(json!({"pending":null,"other_state_pending":false}));
    };
    planning::pending(root, &custody)
}

fn existing() -> Result<Custody> {
    Custody::existing_user()?.ok_or_else(|| {
        Failure::new(
            crate::error::ErrorKind::NotFound,
            "this OS user has no native configuration operations",
        )
    })
}

fn retained_retirement(
    custody: &Custody,
    operation: &str,
    expected: &str,
) -> Result<Option<super::custody::Review>> {
    let Some(review) = custody.retained(operation)? else {
        return Ok(None);
    };
    if review.digest()? != expected {
        return Err(invalid());
    }
    Ok(review.retirement().is_some().then_some(review))
}
pub fn retire_plan(root: &Path, operation: &str, expected: &str, at: &str) -> Result<Value> {
    planning::retirement::plan(root, &existing()?, operation, expected, at)
}

/// Explicit local OS-user metadata read, including original state directories
/// that are gone. No account session or source authorization is inferred.
pub fn custody() -> Result<Value> {
    let Some(custody) = Custody::existing_user()? else {
        return Ok(json!({"operations":[],"pending":null,"authorization_granted":false}));
    };
    let mut operations = Vec::new();
    for operation in custody.current_operations()? {
        let review = custody.retained(&operation)?.ok_or_else(invalid)?;
        let Some(plan) = review.original_plan()? else {
            continue;
        };
        let document = plan.value()?;
        let current = custody.current_scopes(&operation)?;
        let mut roots = Vec::new();
        for (scope, held) in document["roots"].as_object().ok_or_else(invalid)? {
            let scope_value: Scope = serde_json::from_value(json!(scope)).map_err(|_| invalid())?;
            if !current.contains(&scope_value) {
                continue;
            }
            let path = files::deserialize_path(held["directory"]["path"].clone())
                .map_err(|_| invalid())?;
            let state = if crate::files::absence::Parent::observe(&path).is_ok() {
                "missing"
            } else {
                "present_or_unavailable"
            };
            roots.push(json!({"scope":scope,"directory":held["directory"],"state":state}));
        }
        operations.push(
            json!({"operation_id":operation,"plan_digest":review.digest()?,
            "original_context":document["context"],"setup":document["setup"],
            "harness_id":document["target"]["harness_id"],"roots":roots}),
        );
    }
    let pending = if let Some(review) = custody.pending()? {
        let document = review.value()?;
        let metadata = document["missing_retirement"].is_object();
        let original = if metadata {
            &document["missing_retirement"]["original_plan"]
        } else {
            &document["native_plan"]
        };
        let controller = if metadata {
            &document["missing_retirement"]["controller"]
        } else {
            &original["state"]
        };
        json!({"operation_id":review.operation_id(),"plan_digest":review.digest()?,
            "metadata_only":metadata,"controller_state":controller["path"],"original_context":original["context"],
            "state":custody.status(&review)?["state"]})
    } else {
        Value::Null
    };
    Ok(json!({"operations":operations,"pending":pending,"authorization_granted":false}))
}
