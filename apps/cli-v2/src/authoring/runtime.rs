//! Identity-bound local command execution. Domain services remain parser-free.

use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

use super::{
    Identity, adoption, derivation, forks, importing, lifecycle, materialization, native_edit,
    passports, project_binding, releases, setups,
};
use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, identity,
    objects::Objects,
    passport::{self, developer, device},
    projects,
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

/// An author and the physical root from which that authority was loaded.
/// Every associated registry connection keeps the same root capability.
pub(crate) struct Owner {
    device: identity::Identity,
    context: Identity,
}

impl std::ops::Deref for Owner {
    type Target = Identity;
    fn deref(&self) -> &Identity {
        &self.context
    }
}

impl Owner {
    fn checked(&self, store: Store) -> Result<Store> {
        self.device.revalidate()?;
        if crate::account::attachment::effective(&store.connection, &self.device)? != self.context {
            return Err(Failure::precondition(
                "the registry owner changed after this author was loaded",
            ));
        }
        Ok(store)
    }

    pub(crate) fn planning(&self) -> Result<Store> {
        self.checked(Store::planning_at(self.device.root_directory())?)
    }

    pub(crate) fn open(&self, create: bool) -> Result<Store> {
        self.checked(Store::open_at(self.device.root_directory(), create)?)
    }

    pub(crate) fn historical(&self, identity: &Identity) -> bool {
        self.device.historical(identity)
    }
}

pub(crate) fn owner(parent: &Path) -> Result<Owner> {
    let device = identity::current(parent)?.ok_or_else(|| Failure::precondition(
        "initialize the isolated native identity before planning or applying authoring operations"
    ))?;
    let store = Store::planning_at(device.root_directory())?;
    device.revalidate()?;
    let context = crate::account::attachment::effective(&store.connection, &device)?;
    Ok(Owner { context, device })
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
    let mut store = identity.planning()?;
    let operation = serde_json::to_value(build(&mut store, identity.clone(), &moment())?)
        .map_err(|_| invalid())?;
    let plan = Plan {
        schema_version: 1,
        state_parent,
        operation,
    };
    Ok(json!({"plan_digest":plan.digest()?, "plan":plan}))
}

fn execute<T: DeserializeOwned>(
    plan: Plan,
    apply: impl FnOnce(&mut Store, &T, &str, &Identity, &str) -> Result<Value>,
) -> Result<Value> {
    // Decode the closed domain plan before opening a writable database.
    let operation: T = serde_json::from_value(plan.operation.clone()).map_err(|_| invalid())?;
    let identity = owner(&plan.state_parent)?;
    let planned: Identity =
        serde_json::from_value(plan.operation["identity"].clone()).map_err(|_| invalid())?;
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
    let digest = digest::canonical("ai-stp:plan:v1", &plan.operation)?;
    if planned != *identity {
        // Historical replay is query-only and must identify the exact completed
        // effect. An unexecuted old plan cannot recover former owner authority.
        if !identity.historical(&planned) {
            return Err(Failure::precondition(
                "the local identity differs from the planned author",
            ));
        }
        let mut store = identity.planning()?;
        if !crate::store::journal::finished(
            &store.connection,
            operation_id,
            plan.operation["action"].as_str().ok_or_else(invalid)?,
        )? {
            return Err(Failure::precondition(
                "the local identity differs from the unexecuted planned author",
            ));
        }
        return apply(&mut store, &operation, &digest, &planned, &at);
    }
    let mut store = match identity.open(false) {
        Ok(store) => store,
        Err(error) if matches!(error.kind, ErrorKind::NotFound) => {
            if at.as_str() < created || at.as_str() > expires {
                return Err(Failure::precondition(
                    "an expired plan cannot initialize a registry",
                ));
            }
            identity.open(true)?
        }
        Err(error) => return Err(error),
    };
    apply(&mut store, &operation, &digest, &identity, &at)
}

fn acquire(plan: Plan) -> Result<Value> {
    let operation: crate::catalog::acquisition::Plan =
        serde_json::from_value(plan.operation.clone()).map_err(|_| invalid())?;
    let Some(binding) = &operation.access else {
        return execute(plan, crate::catalog::acquisition::apply);
    };
    binding.validate()?;
    // Terminal history is local and remains replayable after logout or session
    // refresh. The domain rechecks its exact digest and immutable content.
    let identity = owner(&plan.state_parent)?;
    let store = identity.planning()?;
    let finished = crate::store::journal::finished(
        &store.connection,
        &operation.operation_id,
        &operation.action,
    )?;
    drop(store);
    if finished {
        return execute(plan, crate::catalog::acquisition::apply);
    }
    // Acquire the account lock before execute opens a writable registry.
    let mut access =
        crate::account::access::Access::load(&plan.state_parent, &binding.origin, false)?;
    if access.binding() != binding {
        return Err(Failure::precondition(
            "the planned private acquisition session changed",
        ));
    }
    access.verify()?;
    execute(plan, |store, operation, digest, identity, at| {
        crate::catalog::acquisition::apply_with_access(
            store,
            operation,
            digest,
            identity,
            at,
            Some(&access),
        )
    })
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
        "component.adaptation.derive" => execute(plan, derivation::apply),
        "component.materialize" => execute(plan, materialization::apply),
        "component.version.release" => execute(plan, releases::apply),
        "component.fork" => execute(plan, forks::apply),
        "component.forget" => execute(plan, lifecycle::apply),
        "project.passport.record" => execute(plan, projects::passports::apply),
        "project.technology.record" => execute(plan, projects::technology::retained::apply),
        "passport.developer.record" => execute(plan, developer::apply),
        "passport.device.record" => execute(plan, device::apply),
        "setup.compose" => execute(plan, setups::apply),
        "setup.passport.update" => execute(plan, setups::drafts::apply),
        "setup.version.release" => execute(plan, setups::releases::apply),
        "setup.import" => execute(plan, importing::apply),
        "catalog.setup.acquire" => acquire(plan),
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

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use crate::store::revisions::{self, Write};

    #[test]
    fn an_author_keeps_the_same_registry_parent_across_path_replacement()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let sandbox = tempfile::tempdir()?;
        let root = sandbox.path().join("state");
        let displaced = sandbox.path().join("displaced");
        std::fs::create_dir(&root)?;
        let at = moment();
        let initialization = identity::plan(&root, identity::Storage::File, &at)?;
        identity::apply(&initialization, &initialization.digest()?, &at)?;
        let author = owner(&root)?;
        drop(author.planning()?);
        assert!(!root.join("ai-stp-v2-state").exists());

        std::fs::rename(&root, &displaced)?;
        std::fs::create_dir(&root)?;
        let id = format!("project_{}", ulid::Ulid::generate());
        let mut store = author.open(true)?;
        let recorded = store.transaction(|t| revisions::commit(t,
            &json!({"kind":"project","stable_id":id,"owner_id":author.account_id,"created_at":at}),
            &author.device_id, None, Write::Advance { expected_heads: &[] }))?;
        drop(store);
        assert!(std::fs::read_dir(&root)?.next().is_none());
        assert!(displaced.join("ai-stp-v2-state/registry.sqlite3").is_file());

        for planning in [false, true] {
            let mut store = if planning {
                author.planning()?
            } else {
                author.open(false)?
            };
            let document = store.transaction(|t| Objects { connection: t }.head("project", &id))?;
            assert_eq!(document, recorded);
        }
        std::fs::remove_dir(&root)?;
        std::fs::rename(&displaced, &root)?;
        assert_eq!(
            inspect(&root, "project", &id, None)?["revision_id"],
            recorded["revision_id"]
        );
        Ok(())
    }
}
