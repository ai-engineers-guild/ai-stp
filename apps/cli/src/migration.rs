//! One explicit, resumable transfer of production writer and credential ownership.

use cap_fs_ext::DirExt;
use cap_std::fs::Dir;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::Path;

use crate::{
    account, authoring, canonical, digest,
    error::{Failure, Result},
    files::OwnedDirectory,
    identity, passport, store,
};

const NAMESPACE: &str = "ai-stp-state-transfer";
const OWNER: &[u8] = b"ai-stp production writer transfer v1\n";
const LIMIT: usize = 128 * 1024;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema_version: u32,
    operation_id: String,
    created_at: String,
    expires_at: String,
    identity: identity::adoption::Plan,
    registry: store::migration::Inventory,
    session: Option<account::adoption::Metadata>,
    origin: String,
    provider: String,
}

fn invalid() -> Failure {
    Failure::precondition(
        "the exact production transfer changed or requires recovery; use its retained plan",
    )
}
fn at() -> String {
    format!("{:.3}", jiff::Timestamp::now())
}

fn updater_quiescent(parent: &Dir) -> Result<()> {
    use std::io::Read;
    let mut directory = parent.try_clone().map_err(|_| invalid())?;
    for name in ["self-update", "installations"] {
        directory = match directory.open_dir_nofollow(name) {
            Ok(directory) => directory,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(_) => return Err(invalid()),
        };
    }
    for (index, entry) in directory.entries().map_err(|_| invalid())?.enumerate() {
        if index >= 128 {
            return Err(invalid());
        }
        let entry = entry.map_err(|_| invalid())?;
        let installation = directory
            .open_dir_nofollow(entry.file_name())
            .map_err(|_| invalid())?;
        let file = match crate::files::open_regular(&installation, Path::new("journal.json")) {
            Ok(file) => file,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(_) => return Err(invalid()),
        };
        let mut bytes = Vec::new();
        file.take(LIMIT as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| invalid())?;
        if bytes.len() > LIMIT
            || !matches!(
                canonical::parse(&bytes)?["state"].as_str(),
                Some("idle" | "verified" | "rolled_back" | "failed")
            )
        {
            return Err(Failure::precondition(
                "finish or recover the previous CLI update before transferring production state",
            ));
        }
    }
    Ok(())
}

impl Plan {
    fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
    fn validate(&self) -> Result<()> {
        self.identity.validate()?;
        if self.schema_version != 1
            || self.operation_id != self.identity.identity.operation_id
            || !passport::stable_id(&self.operation_id, "operation")
            || self.expires_at != authoring::expiry(&self.created_at)?
            || self.registry.rows.len() != 51
            || account::adoption::origin(&self.origin)? != self.origin
            || !crate::account::providers::IDS.contains(&self.provider.as_str())
        {
            return Err(invalid());
        }
        if let Some(session) = &self.session
            && (session.device_id != self.identity.identity.device_id
                || !passport::stable_id(&session.account_id, "account")
                || !passport::timestamp(&session.expires_at))
        {
            return Err(invalid());
        }
        Ok(())
    }
    fn root(&self) -> &Path {
        &self.identity.identity.root
    }
    fn report(&self) -> Value {
        json!({"schema_version":1,"operation_id":self.operation_id,"state":"verified","writer":"rust",
            "registry_schema":54,"registry_moved":false,"objects_rewritten":false,"configuration_changed":false,
            "account_id":self.identity.identity.account_id,"device_id":self.identity.identity.device_id,
            "public_key":self.identity.public_key,"preserved_rows":self.registry.rows,
            "session_preserved":self.session.is_some(),"online_verified":false})
    }
}

pub fn plan(
    parent: &Path,
    storage: identity::Storage,
    origin: &str,
    provider: &str,
) -> Result<Value> {
    let operation_id = format!("operation_{}", ulid::Ulid::generate());
    let identity = identity::adoption::plan(parent, storage, &operation_id)?;
    let directory =
        Dir::open_ambient_dir(parent, cap_std::ambient_authority()).map_err(|_| invalid())?;
    updater_quiescent(&directory)?;
    if let Some(journal) = OwnedDirectory::open_at(&directory, NAMESPACE, OWNER, false)?
        && journal.read_file("receipt.json", LIMIT as u64)?.is_some()
    {
        return Err(invalid());
    }
    let created_at = at();
    let plan = Plan {
        schema_version: 1,
        expires_at: authoring::expiry(&created_at)?,
        created_at,
        operation_id,
        session: account::adoption::inspect(&directory, storage, &identity.identity.device_id)?,
        registry: store::migration::inspect(parent)?,
        identity,
        origin: account::adoption::origin(origin)?,
        provider: provider.into(),
    };
    plan.validate()?;
    Ok(json!({"plan_digest":plan.digest()?,"plan":plan}))
}

fn stored(directory: &OwnedDirectory) -> Result<Option<Plan>> {
    directory
        .read_file("plan.json", LIMIT as u64)?
        .map(|bytes| {
            let plan: Plan =
                serde_json::from_value(canonical::parse(&bytes)?).map_err(|_| invalid())?;
            plan.validate()?;
            Ok(plan)
        })
        .transpose()
}

pub fn status(parent: &Path) -> Result<Value> {
    let directory =
        Dir::open_ambient_dir(parent, cap_std::ambient_authority()).map_err(|_| invalid())?;
    let Some(journal) = OwnedDirectory::open_at(&directory, NAMESPACE, OWNER, false)? else {
        return Ok(json!({"schema_version":1,"state":"not_started"}));
    };
    let Some(plan) = stored(&journal)? else {
        return Ok(json!({"schema_version":1,"state":"not_started"}));
    };
    if identity::root(parent)?
        != (
            plan.root().to_path_buf(),
            plan.identity.identity.root_identity.clone(),
        )
    {
        return Err(invalid());
    }
    if let Some(bytes) = journal.read_file("receipt.json", LIMIT as u64)? {
        let receipt = canonical::parse(&bytes)?;
        if receipt != plan.report() {
            return Err(invalid());
        }
        return Ok(receipt);
    }
    Ok(json!({"schema_version":1,"state":"pending","plan_digest":plan.digest()?,"plan":plan}))
}

pub fn apply(bytes: &[u8], expected: &str) -> Result<Value> {
    if bytes.len() > LIMIT {
        return Err(invalid());
    }
    let plan: Plan = serde_json::from_value(canonical::parse(bytes)?).map_err(|_| invalid())?;
    plan.validate()?;
    if plan.digest()? != expected {
        return Err(invalid());
    }
    let parent =
        Dir::open_ambient_dir(plan.root(), cap_std::ambient_authority()).map_err(|_| invalid())?;
    if identity::physical_root(&parent)? != plan.identity.identity.root_identity {
        return Err(invalid());
    }
    let existing = OwnedDirectory::open_at(&parent, NAMESPACE, OWNER, false)?;
    if existing.is_none() && (at() < plan.created_at || at() > plan.expires_at) {
        return Err(invalid());
    }
    let journal = match existing {
        Some(journal) => journal,
        None => OwnedDirectory::open_at(&parent, NAMESPACE, OWNER, true)?.ok_or_else(invalid)?,
    };
    match stored(&journal)? {
        Some(held) if held == plan => (),
        Some(_) | None => {
            // A failed precondition or connection drain has not transferred
            // ownership. Schema 53 and the absent native identity permit a
            // newly reviewed plan; admitted schema-54 work can only resume.
            if at() < plan.created_at
                || at() > plan.expires_at
                || store::migration::inspect(plan.root())? != plan.registry
                || identity::adoption::plan(
                    plan.root(),
                    plan.identity.identity.credential_store,
                    &plan.operation_id,
                )? != plan.identity
            {
                return Err(invalid());
            }
            plan.identity.revalidate(&parent)?;
            if account::adoption::inspect(
                &parent,
                plan.identity.identity.credential_store,
                &plan.identity.identity.device_id,
            )? != plan.session
            {
                return Err(invalid());
            }
            journal.atomic(
                "plan.json",
                &canonical::bytes(&serde_json::to_value(&plan).map_err(|_| invalid())?)?,
            )?;
        }
    }
    if let Some(bytes) = journal.read_file("receipt.json", LIMIT as u64)? {
        let receipt = canonical::parse(&bytes)?;
        if receipt != plan.report() {
            return Err(invalid());
        }
        return Ok(receipt);
    }
    // The VFS drains standard SQLite connections before retaining its byte-range
    // lock. No second main-file descriptor is opened while that lock is held.
    let mut store = store::migration::open(&parent)?;
    if store::migration::phase(&store, &plan.operation_id, expected)?.is_none() {
        if at() < plan.created_at || at() > plan.expires_at {
            return Err(invalid());
        }
        updater_quiescent(&parent)?;
        store::migration::verify(&store, &plan.registry, None)?;
        store::migration::admit(&mut store, &plan.operation_id, expected, &at())?;
    }
    let committed = store::migration::receipt(&store, &plan.operation_id, expected)?;
    if committed.is_none() {
        store::migration::verify(&store, &plan.registry, Some(&plan.operation_id))?;
    }
    let owner = identity::adoption::apply(&plan.identity, &parent)?;
    if committed.is_none() {
        account::adoption::apply(
            &owner,
            &plan.session,
            &plan.operation_id,
            &plan.origin,
            &plan.provider,
            &plan.created_at,
        )?;
        plan.identity.revalidate(&parent)?;
        store::migration::verify(&store, &plan.registry, Some(&plan.operation_id))?;
        store::migration::commit(
            &mut store,
            &plan.operation_id,
            expected,
            &plan.report(),
            &at(),
        )?;
    } else if committed != Some(plan.report()) {
        return Err(invalid());
    }
    // Only exact credential slots that were copied and read back are retired.
    // A crash after the SQLite fence resumes here using the retained native key.
    account::adoption::retire_source(&owner, &plan.session)?;
    identity::adoption::retire_source(&plan.identity, &parent)?;
    store::migration::publish(&store)?;
    if store::migration::receipt(&store, &plan.operation_id, expected)? != Some(plan.report()) {
        return Err(invalid());
    }
    journal.atomic("receipt.json", &canonical::bytes(&plan.report())?)?;
    Ok(plan.report())
}
