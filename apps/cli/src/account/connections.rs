//! Independent remote enrollment keys under the existing local authority root.

use base64::{Engine, engine::general_purpose::STANDARD};
use cap_fs_ext::DirExt;
use ed25519_dalek::Signer;
use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

use crate::{
    authoring, canonical, digest,
    error::{Failure, Result},
    files::{self, OwnedDirectory},
    identity::{self, credentials::Vault},
    passport,
    store::{PROFILE_SCHEMA, Store, database},
};

#[cfg(all(test, unix))]
#[path = "connections_tests.rs"]
mod tests;

const KIND: &str = "account.connection.create";
const NAMESPACE: &str = "ai-stp-v2-connections";
const OWNER: &[u8] = b"ai-stp native enrollment credentials v1\n";
const LIMIT: usize = 64;
type StoredConnection = (String, String, String, Option<String>, String);
type Admission = (String, String, Option<String>, String);

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Enrollment {
    pub connection_id: String,
    pub device_id: String,
    pub public_key: String,
    pub origin: String,
    pub provider: String,
    pub credential_store: identity::Storage,
    pub credential_namespace: [String; 2],
}

impl Enrollment {
    pub(super) fn validate(&self) -> Result<()> {
        self.credential_store.validate()?;
        let bytes = STANDARD.decode(&self.public_key).map_err(|_| invalid())?;
        if !passport::stable_id(&self.connection_id, "connection")
            || !passport::stable_id(&self.device_id, "device")
            || bytes.len() != 32
            || STANDARD.encode(bytes) != self.public_key
            || self.origin != super::transport::origin(&self.origin)?
            || !super::providers::IDS.contains(&self.provider.as_str())
            || self.credential_namespace.iter().any(|part| {
                !part
                    .parse::<u64>()
                    .is_ok_and(|value| value.to_string() == *part)
            })
        {
            return Err(invalid());
        }
        Ok(())
    }

    pub(super) fn check(&self, identity: &identity::Identity) -> Result<()> {
        self.validate()?;
        identity.revalidate()?;
        check_namespace(identity, &self.credential_namespace)
    }

    pub(super) fn check_record(&self, identity: &identity::Identity) -> Result<()> {
        self.check(identity)?;
        if enrollment(identity, &self.connection_id)? != *self {
            return Err(invalid());
        }
        Ok(())
    }

    pub(super) fn sign(&self, identity: &identity::Identity, payload: &[u8]) -> Result<[u8; 64]> {
        self.check(identity)?;
        if payload.len() > 16 * 1024 * 1024 {
            return Err(Failure::input(
                "the enrollment signing payload exceeds 16 MiB",
            ));
        }
        let directory =
            OwnedDirectory::open_at(identity.root_directory(), NAMESPACE, OWNER, false)?
                .ok_or_else(invalid)?;
        let key = Vault::new(&directory, self.credential_store)?
            .read_key(&self.device_id)?
            .ok_or_else(invalid)?;
        if STANDARD.encode(key.verifying_key().as_bytes()) != self.public_key {
            return Err(invalid());
        }
        check_namespace(identity, &self.credential_namespace)?;
        let signature = key.sign(payload).to_bytes();
        identity.revalidate()?;
        check_namespace(identity, &self.credential_namespace)?;
        Ok(signature)
    }

    pub(super) fn verify_key(&self, identity: &identity::Identity) -> Result<()> {
        self.sign(identity, b"ai-stp:local-enrollment-key-proof:v1")
            .map(|_| ())
    }
}

pub(super) fn enrollment(identity: &identity::Identity, connection_id: &str) -> Result<Enrollment> {
    let store = Store::planning_at(identity.root_directory())?;
    if !store.profiles_enabled()? {
        return Err(Failure::precondition(
            "create the retained connection before using its session",
        ));
    }
    let held = record(&store.connection, connection_id)?.ok_or_else(invalid)?;
    held.plan.belongs(identity)?;
    let public_key = held.public_key.ok_or_else(|| {
        Failure::precondition("resume the retained connection creation before signing in")
    })?;
    let result = Enrollment {
        connection_id: held.plan.connection_id,
        device_id: held.plan.device_id,
        public_key,
        origin: held.plan.origin,
        provider: held.plan.provider,
        credential_store: held.plan.credential_store,
        credential_namespace: held.credential_namespace,
    };
    result.validate()?;
    check_namespace(identity, &result.credential_namespace)?;
    identity.revalidate()?;
    Ok(result)
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub root: PathBuf,
    pub root_identity: [String; 2],
    pub local_identity: authoring::Identity,
    pub credential_store: identity::Storage,
    pub connection_id: String,
    pub device_id: String,
    pub label: String,
    pub origin: String,
    pub provider: String,
    pub registry_schema_before: u32,
    pub registry_schema_after: u32,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Record {
    pub plan: Plan,
    pub plan_digest: String,
    pub public_key: Option<String>,
    pub credential_namespace: [String; 2],
}

fn invalid() -> Failure {
    Failure::precondition(
        "the retained connection, enrollment key or exact operation binding changed",
    )
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }

    fn validate(&self) -> Result<()> {
        self.local_identity.validate()?;
        self.credential_store.validate()?;
        if self.schema_version != 1
            || self.action != KIND
            || !passport::stable_id(&self.operation_id, "operation")
            || !passport::stable_id(&self.connection_id, "connection")
            || !passport::stable_id(&self.device_id, "device")
            || self.device_id == self.local_identity.device_id
            || !self.root.is_absolute()
            || self.expires_at != authoring::expiry(&self.created_at)?
            || self.origin.len() > 4096
            || self.origin != super::transport::origin(&self.origin)?
            || !super::providers::IDS.contains(&self.provider.as_str())
            || self.label.is_empty()
            || self.label.len() > 120
            || self.label.trim() != self.label
            || self.label.chars().any(char::is_control)
            || ![53, 54, PROFILE_SCHEMA].contains(&self.registry_schema_before)
            || self.registry_schema_after != PROFILE_SCHEMA
        {
            return Err(invalid());
        }
        Ok(())
    }

    fn bind(&self) -> Result<identity::Identity> {
        let id = super::identity_at(&self.root)?;
        self.belongs(&id)?;
        Ok(id)
    }

    fn belongs(&self, id: &identity::Identity) -> Result<()> {
        if id.root_binding() != (self.root.as_path(), &self.root_identity)
            || !id.historical(&self.local_identity)
            || id.storage() != self.credential_store
        {
            return Err(invalid());
        }
        Ok(())
    }
}

impl Record {
    fn validate(&self) -> Result<()> {
        self.plan.validate()?;
        if self.plan.digest()? != self.plan_digest {
            return Err(invalid());
        }
        if self.credential_namespace.iter().any(|part| {
            !part
                .parse::<u64>()
                .is_ok_and(|value| value.to_string() == *part)
        }) {
            return Err(invalid());
        }
        if let Some(key) = &self.public_key {
            let bytes = STANDARD.decode(key).map_err(|_| invalid())?;
            if bytes.len() != 32 || STANDARD.encode(bytes) != *key {
                return Err(invalid());
            }
        }
        Ok(())
    }

    fn public(&self) -> Value {
        json!({"connection_id":self.plan.connection_id,"label":self.plan.label,
            "origin":self.plan.origin,"provider":self.plan.provider,"device_id":self.plan.device_id,
            "public_key":self.public_key,"state":if self.public_key.is_some(){"ready"}else{"creating"},
            "credential_store":self.plan.credential_store,"created_at":self.plan.created_at,
            "online_verified":false,"account_id":null,"operation_id":self.plan.operation_id,
            "pending_operation":if self.public_key.is_none(){Some(json!({"plan":self.plan,"plan_digest":self.plan_digest}))}else{None}})
    }
}

pub fn plan(root: &Path, label: &str, origin: &str, provider: &str, at: &str) -> Result<Plan> {
    let id = super::identity_at(root)?;
    let store = Store::planning_at(id.root_directory())?;
    let version = store
        .connection
        .query_row("PRAGMA user_version", [], |row| row.get(0))
        .map_err(database)?;
    let result = Plan {
        schema_version: 1,
        action: KIND.into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        root: id.root_binding().0.to_owned(),
        root_identity: id.root_binding().1.clone(),
        local_identity: id.context(),
        credential_store: id.storage(),
        connection_id: format!("connection_{}", ulid::Ulid::generate()),
        device_id: format!("device_{}", ulid::Ulid::generate()),
        label: label.into(),
        origin: super::transport::origin(origin)?,
        provider: provider.into(),
        registry_schema_before: version,
        registry_schema_after: PROFILE_SCHEMA,
    };
    result.validate()?;
    id.revalidate()?;
    Ok(result)
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let value = canonical::parse(&files::read(path, 65536)?)?;
    let plan: Plan = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    plan.validate()?;
    if digest::canonical("ai-stp:plan:v1", &value)? != plan.digest()? {
        return Err(invalid());
    }
    Ok(plan)
}

pub(crate) fn record(connection: &Connection, id: &str) -> Result<Option<Record>> {
    if !passport::stable_id(id, "connection") {
        return Err(invalid());
    }
    let held:Option<StoredConnection> = connection.query_row(
        "SELECT detail,device_id,origin,public_key,state FROM native_connection WHERE connection_id=?",[id],
        |row| Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?,row.get(4)?))).optional().map_err(database)?;
    held.map(|(detail, device, origin, key, state)| {
        if detail.len() > 65536 {
            return Err(invalid());
        }
        let value: Record =
            serde_json::from_value(canonical::parse(detail.as_bytes())?).map_err(|_| invalid())?;
        value.validate()?;
        if value.plan.connection_id != id
            || value.plan.device_id != device
            || value.plan.origin != origin
            || value.public_key != key
            || state != if key.is_some(){"ready"}else{"creating"}
        {
            return Err(invalid());
        }
        let admitted:Admission=connection.query_row(
            "SELECT kind,state,finished_at,coalesce(detail,'') FROM operation WHERE operation_id=?",
            [&value.plan.operation_id],|row|Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?))).map_err(database)?;
        if admitted.3.len()>65536 {return Err(invalid());}
        let intent:Record=serde_json::from_value(canonical::parse(admitted.3.as_bytes())?).map_err(|_|invalid())?;
        intent.validate()?;
        if intent.plan!=value.plan || intent.plan_digest!=value.plan_digest || intent.credential_namespace!=value.credential_namespace || intent.public_key.is_some() || admitted.0!=KIND
            || admitted.1!=if key.is_some(){"verified"}else{"applying"}
            || admitted.2.is_some()!=key.is_some()
            || admitted.2.as_ref().is_some_and(|at|!passport::timestamp(at)||at<&value.plan.created_at)
        {return Err(invalid());}
        Ok(value)
    })
    .transpose()
}

fn detail(record: &Record) -> Result<String> {
    let bytes = canonical::bytes(&serde_json::to_value(record).map_err(|_| invalid())?)?;
    if bytes.len() > 65536 {
        return Err(invalid());
    }
    String::from_utf8(bytes).map_err(|_| invalid())
}

fn check_namespace(identity: &identity::Identity, expected: &[String; 2]) -> Result<()> {
    let directory = identity
        .root_directory()
        .open_dir_nofollow(NAMESPACE)
        .map_err(|_| invalid())?;
    if identity::physical_root(&directory)? != *expected {
        return Err(invalid());
    }
    Ok(())
}

pub fn apply(plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    plan.validate()?;
    if expected != plan.digest()? || !passport::timestamp(at) || at < plan.created_at.as_str() {
        return Err(invalid());
    }
    let id = plan.bind()?;
    let observed = {
        let store = Store::planning_at(id.root_directory())?;
        let held = if store.profiles_enabled()? {
            record(&store.connection, &plan.connection_id)?
        } else {
            None
        };
        if held.as_ref().is_some_and(|held| held.plan != *plan) {
            return Err(invalid());
        }
        if held.is_none() && (at < plan.created_at.as_str() || at >= plan.expires_at.as_str()) {
            return Err(Failure::precondition(
                "the connection plan expired; plan a new connection",
            ));
        }
        held
    };
    // Credential directory, then registry: no registry lock crosses vault I/O.
    let directory = OwnedDirectory::open_at(id.root_directory(), NAMESPACE, OWNER, true)?
        .ok_or_else(invalid)?;
    let namespace = identity::physical_root(&directory.directory)?;
    if observed
        .as_ref()
        .is_some_and(|record| record.credential_namespace != namespace)
    {
        return Err(invalid());
    }
    check_namespace(&id, &namespace)?;
    let vault = Vault::new(&directory, plan.credential_store)?;
    let retained_key = vault.read_key(&plan.device_id)?;
    if retained_key.is_some() {
        let store = Store::planning_at(id.root_directory())?;
        let owned =
            store.profiles_enabled()? && record(&store.connection, &plan.connection_id)?.is_some();
        if !owned {
            return Err(Failure::precondition(
                "the planned enrollment credential slot is already owned",
            ));
        }
    }
    let admitted = {
        let mut store = Store::open_at(id.root_directory(), true)?;
        let held = if store.profiles_enabled()? {
            record(&store.connection, &plan.connection_id)?
        } else {
            None
        };
        if let Some(held) = held {
            if held.plan != *plan || held.credential_namespace != namespace {
                return Err(invalid());
            }
            held
        } else {
            if at < plan.created_at.as_str() || at >= plan.expires_at.as_str() {
                return Err(Failure::precondition(
                    "the connection plan expired; plan a new connection",
                ));
            }
            if retained_key.is_some() {
                return Err(Failure::precondition(
                    "the planned enrollment credential slot is already owned",
                ));
            }
            let version: u32 = store
                .connection
                .query_row("PRAGMA user_version", [], |row| row.get(0))
                .map_err(database)?;
            if version != plan.registry_schema_before {
                return Err(Failure::precondition(
                    "the registry format changed; plan this new connection again",
                ));
            }
            let value = Record {
                plan: plan.clone(),
                plan_digest: expected.into(),
                public_key: None,
                credential_namespace: namespace.clone(),
            };
            let detail = detail(&value)?;
            store.profile_transaction(|transaction| {
                let count:i64=transaction.query_row("SELECT count(*) FROM native_connection",[],|row|row.get(0)).map_err(database)?;
                if count>=LIMIT as i64 {return Err(Failure::precondition("the retained connection limit has been reached"));}
                transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,detail) VALUES (?1,?2,'applying',?3,?4)",params![plan.operation_id,KIND,at,detail]).map_err(database)?;
                transaction.execute("INSERT INTO native_connection(connection_id,device_id,origin,state,detail) VALUES (?1,?2,?3,'creating',?4)",params![plan.connection_id,plan.device_id,plan.origin,detail]).map_err(database)?;
                Ok(())
            })?;
            value
        }
    };
    id.revalidate()?;
    check_namespace(&id, &namespace)?;
    let key = match retained_key {
        Some(key) => key,
        None if admitted.public_key.is_none() => {
            let key = identity::generate()?;
            vault.create_key(&plan.device_id, &key)?;
            key
        }
        None => {
            return Err(Failure::precondition(
                "the retained enrollment key is missing; it cannot be replaced by replay",
            ));
        }
    };
    let public_key = STANDARD.encode(key.verifying_key().as_bytes());
    if admitted
        .public_key
        .as_ref()
        .is_some_and(|held| held != &public_key)
    {
        return Err(invalid());
    }
    let mut completed = admitted;
    completed.public_key = Some(public_key.clone());
    let detail = detail(&completed)?;
    let mut store = Store::open_at(id.root_directory(), false)?;
    id.revalidate()?;
    check_namespace(&id, &namespace)?;
    store.transaction(|transaction| {
        let held=record(transaction,&plan.connection_id)?.ok_or_else(invalid)?;
        if held.plan!=*plan || held.public_key.as_ref().is_some_and(|held|held!=&public_key) {return Err(invalid());}
        transaction.execute("UPDATE native_connection SET public_key=?1,state='ready',detail=?2 WHERE connection_id=?3",params![public_key,detail,plan.connection_id]).map_err(database)?;
        transaction.execute("UPDATE operation SET state='verified',finished_at=coalesce(finished_at,?1) WHERE operation_id=?2 AND kind=?3",params![at,plan.operation_id,KIND]).map_err(database)?;
        Ok(())
    })?;
    check_namespace(&id, &namespace)?;
    Ok(
        json!({"schema_version":1,"connection":completed.public(),"registry_schema_version":PROFILE_SCHEMA}),
    )
}

pub fn list(root: &Path) -> Result<Value> {
    let id = super::identity_at(root)?;
    let store = Store::planning_at(id.root_directory())?;
    let mut records = Vec::new();
    if store.profiles_enabled()? {
        let mut statement = store
            .connection
            .prepare("SELECT connection_id FROM native_connection ORDER BY connection_id LIMIT 65")
            .map_err(database)?;
        let ids = statement
            .query_map([], |row| row.get::<_, String>(0))
            .map_err(database)?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(database)?;
        if ids.len() > LIMIT {
            return Err(invalid());
        }
        for connection in ids {
            let held = record(&store.connection, &connection)?.ok_or_else(invalid)?;
            held.plan.belongs(&id)?;
            records.push(held.public());
        }
    }
    id.revalidate()?;
    Ok(json!({"schema_version":1,"connections":records,"online_verified":false}))
}
