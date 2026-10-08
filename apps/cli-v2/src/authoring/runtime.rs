//! Identity-bound local command execution. Domain services remain parser-free.

use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

use super::{
    Identity, adoption, forks, lifecycle, native_edit, passports, project_binding, releases, setups,
};
use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, identity,
    objects::Objects,
    passport, projects,
    store::Store,
};

const MAX_PLAN: u64 = 16 * 1024 * 1024;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema_version: u32,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    state_parent: PathBuf,
    operation: Value,
}

impl Plan {
    fn digest(&self) -> Result<String> {
        let value = serde_json::to_value(self).map_err(|_| invalid())?;
        if canonical::bytes(&value)?.len() as u64 > MAX_PLAN {
            return Err(Failure::input("the local plan exceeds 16 MiB"));
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }
}

fn invalid() -> Failure {
    Failure::input("the local operation plan is invalid")
}

fn owner(parent: &Path) -> Result<Identity> {
    Ok(identity::current(parent)?.ok_or_else(|| Failure::precondition(
        "initialize the isolated native identity before planning or applying authoring operations"
    ))?.context())
}

fn moment() -> String {
    format!("{:.3}", jiff::Timestamp::now())
}

pub fn plan<T: Serialize>(
    parent: &Path,
    build: impl FnOnce(&mut Store, Identity, &str) -> Result<T>,
) -> Result<Value> {
    let state_parent = PathBuf::from(files::location(parent)?);
    let identity = owner(&state_parent)?;
    let mut store = Store::planning(&state_parent)?;
    let operation =
        serde_json::to_value(build(&mut store, identity, &moment())?).map_err(|_| invalid())?;
    let plan = Plan {
        schema_version: 1,
        state_parent,
        operation,
    };
    Ok(json!({"plan_digest":plan.digest()?, "plan":plan}))
}

type Apply<T> = fn(&mut Store, &T, &str, &Identity, &str) -> Result<Value>;

fn execute<T: DeserializeOwned>(plan: Plan, apply: Apply<T>) -> Result<Value> {
    // Decode the closed domain plan before opening a writable database.
    let operation: T = serde_json::from_value(plan.operation.clone()).map_err(|_| invalid())?;
    let identity = owner(&plan.state_parent)?;
    if plan.operation["identity"] != serde_json::to_value(&identity).map_err(|_| invalid())? {
        return Err(Failure::precondition(
            "the local identity differs from the planned author",
        ));
    }
    let created = plan.operation["created_at"].as_str().ok_or_else(invalid)?;
    let expires = plan.operation["expires_at"].as_str().ok_or_else(invalid)?;
    let operation_id = plan.operation["operation_id"]
        .as_str()
        .ok_or_else(invalid)?;
    if plan.operation["schema_version"] != 1
        || super::expiry(created)? != expires
        || !passport::stable_id(operation_id, "operation")
    {
        return Err(invalid());
    }
    let at = moment();
    let mut store = match Store::open(&plan.state_parent, false) {
        Ok(store) => store,
        Err(error) if matches!(error.kind, ErrorKind::NotFound) => {
            if at.as_str() < created || at.as_str() > expires {
                return Err(Failure::precondition(
                    "an expired plan cannot initialize a registry",
                ));
            }
            Store::open(&plan.state_parent, true)?
        }
        Err(error) => return Err(error),
    };
    let digest = digest::canonical("ai-stp:plan:v1", &plan.operation)?;
    apply(&mut store, &operation, &digest, &identity, &at)
}

pub fn apply(path: &Path, expected_digest: &str) -> Result<Value> {
    let plan: Plan = serde_json::from_value(canonical::parse(&files::read(path, MAX_PLAN)?)?)
        .map_err(|_| invalid())?;
    if plan.schema_version != 1
        || !plan.state_parent.is_absolute()
        || plan.digest()? != expected_digest
    {
        return Err(invalid());
    }
    match plan.operation["action"].as_str().ok_or_else(invalid)? {
        "component.source.bind" => execute(plan, project_binding::apply),
        "component.adopt" => execute(plan, adoption::apply),
        "component.passport.update" => execute(plan, passports::apply),
        "component.adaptation.edit" => execute(plan, native_edit::apply),
        "component.version.release" => execute(plan, releases::apply),
        "component.fork" => execute(plan, forks::apply),
        "component.forget" => execute(plan, lifecycle::apply),
        "project.passport.record" => execute(plan, projects::passports::apply),
        "setup.compose" => execute(plan, setups::apply),
        "setup.fork" | "setup.recast" => execute(plan, setups::copies::apply),
        _ => Err(Failure::input(
            "this operation is not implemented by the local authoring runtime",
        )),
    }
}

/// Inspection needs only the explicit private registry, not a credential session.
pub fn inspect(parent: &Path, kind: &str, id: &str, version: Option<&str>) -> Result<Value> {
    let mut store = Store::planning(parent)?;
    store.transaction(|transaction| {
        let objects = Objects {
            connection: transaction,
        };
        if let Some(version) = version {
            let document = objects.exact_version(id, version, None)?;
            if document["kind"] != kind {
                return Err(invalid());
            }
            Ok(document)
        } else {
            objects.passport(kind, Some(id))
        }
    })
}

pub fn versions(parent: &Path, id: &str) -> Result<Value> {
    let mut store = Store::planning(parent)?;
    store.transaction(|transaction| {
        Objects {
            connection: transaction,
        }
        .versions(id)
    })
}
