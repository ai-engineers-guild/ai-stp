//! Parser-free public native configuration workflows.

use super::{
    custody::Custody,
    planning::{self, Operation, Plan, Reviewed},
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
fn read_review(path: &Path, expected: &str) -> Result<Plan> {
    let review = super::custody::Review::parse(&files::read(path, 8 * 1024 * 1024)?, expected)?;
    review.original_plan()?.ok_or_else(invalid)
}
pub fn prepare(root: &Path, input: &Path, expected: &str, at: &str) -> Result<Value> {
    let plan = read_review(input, expected)?;
    let mut custody = Custody::open_user()?;
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
    planning::apply_prepared(root, &mut Custody::open_user()?, operation, digest, at)
}
pub fn status(root: &Path, operation: &str, digest: &str) -> Result<Value> {
    planning::configuration_status(root, &Custody::open_user()?, operation, digest)
}
pub fn cancel(root: &Path, operation: &str, digest: &str, at: &str) -> Result<Value> {
    planning::cancel_preparation(root, &mut Custody::open_user()?, operation, digest, at)
}
pub fn confirm(root: &Path, operation: &str, digest: &str, at: &str) -> Result<Value> {
    planning::confirm_session(root, &Custody::open_user()?, operation, digest, at)
}
