//! Exact public acquisition. Network observation precedes one atomic local write.

use std::{
    collections::{BTreeMap, BTreeSet, VecDeque},
    path::Path,
    time::{Duration, Instant},
};

use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Kind, validate};
use crate::{
    authoring::{Identity, expiry, native_identity, setups},
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    http::{Endpoint, MAX_BODY},
    objects::Objects,
    passport,
    projection::artifact,
    selection::graph,
    store::{Store, database, journal, revisions, versions},
    wire,
};

const MAX_BYTES: usize = 128 * 1024 * 1024;
const MAX_METADATA: usize = 8 * 1024 * 1024;
const MAX_COMPONENTS: usize = 512;
const MAX_EDGES: usize = 8192;
static RESULT: wire::Schema = wire::Schema::new(include_str!(
    "../../../../schemas/v1/cli-catalog-setup-acquisition.schema.json"
));

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Observation {
    passport: Value,
    passport_digest: String,
    lifecycle: String,
    trust: Value,
    published_at: String,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub identity: Identity,
    pub endpoint: String,
    pub setup: Observation,
    pub components: BTreeMap<String, Observation>,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        let bytes = canonical::bytes(&serde_json::to_value(self).map_err(|_| invalid())?)?;
        if bytes.len() > MAX_METADATA {
            return Err(invalid());
        }
        digest::bytes("ai-stp:plan:v1", &bytes)
    }
}

fn invalid() -> Failure {
    Failure::precondition(
        "catalog acquisition requires a complete, bounded and unchanged exact graph",
    )
}

fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str> {
    value[field].as_str().ok_or_else(invalid)
}

struct Capture {
    endpoint: Endpoint,
    started: Instant,
    metadata_bytes: usize,
    bytes: usize,
    verified_bytes: usize,
    payloads: BTreeMap<String, Vec<u8>>,
}

impl Capture {
    fn new(endpoint: Endpoint) -> Self {
        Self {
            endpoint,
            started: Instant::now(),
            metadata_bytes: 0,
            bytes: 0,
            verified_bytes: 0,
            payloads: BTreeMap::new(),
        }
    }

    fn remaining(&self) -> Result<Duration> {
        Duration::from_secs(30)
            .checked_sub(self.started.elapsed())
            .filter(|d| !d.is_zero())
            .ok_or_else(|| Failure::precondition("catalog graph capture exceeded thirty seconds"))
    }

    fn observation(&mut self, kind: Kind, id: &str, version: &str) -> Result<Observation> {
        if !passport::stable_id(id, kind.name()) || !passport::version_number(version) {
            return Err(invalid());
        }
        let url = self
            .endpoint
            .route(&[kind.route(), id, "versions", version], &[])?;
        let bytes = self.endpoint.read(
            &url,
            "application/json",
            MAX_BODY.min((MAX_METADATA - self.metadata_bytes) as u64),
            self.remaining()?,
        )?;
        self.metadata_bytes += bytes.len();
        let response = wire::parse(&bytes)?;
        validate(kind, id, Some(version), &response)?;
        passport::validate(&response["passport"])?;
        if !matches!(
            response["lifecycle"].as_str(),
            Some("active" | "deprecated")
        ) {
            return Err(Failure::precondition(
                "catalog acquisition refuses blocked or hidden versions",
            ));
        }
        Ok(Observation {
            passport: response["passport"].clone(),
            passport_digest: text(&response, "passport_digest")?.into(),
            lifecycle: text(&response, "lifecycle")?.into(),
            trust: response["trust"].clone(),
            published_at: text(&response, "published_at")?.into(),
        })
    }

    fn artifact(&mut self, document: &Value, reference: &Value) -> Result<()> {
        let address = text(reference, "digest")?;
        let size = reference["size_bytes"]
            .as_u64()
            .filter(|size| *size <= 64 * 1024 * 1024)
            .ok_or_else(invalid)?;
        if let Some(bytes) = self.payloads.get(address) {
            return if bytes.len() as u64 == size {
                Ok(())
            } else {
                Err(invalid())
            };
        }
        if size > (MAX_BYTES - self.bytes) as u64 {
            return Err(invalid());
        }
        let kind = Kind::parse(text(document, "kind")?)?;
        let query = if document["artifact"] == *reference {
            vec![]
        } else {
            vec![("digest", address)]
        };
        let url = self.endpoint.route(
            &[
                kind.route(),
                text(document, "stable_id")?,
                "versions",
                text(document, "version")?,
                "artifact",
            ],
            &query,
        )?;
        let bytes =
            self.endpoint
                .read(&url, "application/octet-stream", size, self.remaining()?)?;
        if bytes.len() as u64 != size || digest::bytes("ai-stp:artifact:v1", &bytes)? != address {
            return Err(invalid());
        }
        self.bytes += bytes.len();
        self.payloads.insert(address.into(), bytes);
        Ok(())
    }

    fn content(&mut self, document: &Value) -> Result<()> {
        self.artifact(document, &document["artifact"])?;
        if document["kind"] == "component" {
            for adaptation in document["adaptations"].as_array().ok_or_else(invalid)? {
                for scope in adaptation["scope_adaptations"]
                    .as_array()
                    .ok_or_else(invalid)?
                {
                    self.artifact(document, &scope["projection_artifact"])?;
                    let bytes = self
                        .payloads
                        .get(text(&scope["projection_artifact"], "digest")?)
                        .ok_or_else(invalid)?;
                    self.verified_bytes = self
                        .verified_bytes
                        .checked_add(bytes.len())
                        .filter(|size| *size <= MAX_BYTES)
                        .ok_or_else(invalid)?;
                    let files = artifact::verify(scope, bytes)?;
                    native_identity::verify_files(
                        text(document, "component_type")?,
                        text(adaptation, "harness_id")?,
                        scope["members"].as_array().ok_or_else(invalid)?,
                        &files,
                    )?;
                }
            }
        } else {
            setups::verify_definition(
                document,
                self.payloads
                    .get(text(&document["artifact"], "digest")?)
                    .ok_or_else(invalid)?,
            )?;
        }
        Ok(())
    }
}

fn reference(value: &Value) -> Result<(String, String, String)> {
    let id = text(value, "stable_id")?;
    let version = text(value, "version")?;
    let address = text(value, "passport_digest")?;
    if !passport::stable_id(id, "component")
        || !passport::version_number(version)
        || address.len() != 71
        || !address.starts_with("sha256:")
        || !address[7..]
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        || !value["variant_id"].is_null()
    {
        return Err(invalid());
    }
    Ok((id.into(), version.into(), address.into()))
}

fn capture(
    endpoint: Endpoint,
    id: &str,
    version: &str,
) -> Result<(Observation, BTreeMap<String, Observation>, Capture)> {
    let mut capture = Capture::new(endpoint);
    let setup = capture.observation(Kind::Setup, id, version)?;
    capture.content(&setup.passport)?;
    let mut pending = VecDeque::from(
        setup.passport["components"]
            .as_array()
            .ok_or_else(invalid)?
            .clone(),
    );
    let mut edges = pending.len();
    let mut found: BTreeMap<String, Observation> = BTreeMap::new();
    while let Some(item) = pending.pop_front() {
        if edges > MAX_EDGES {
            return Err(invalid());
        }
        let (id, version, address) = reference(&item)?;
        if let Some(held) = found.get(&id) {
            if held.passport["version"] != version || held.passport_digest != address {
                return Err(invalid());
            }
            continue;
        }
        if found.len() >= MAX_COMPONENTS {
            return Err(invalid());
        }
        let observed = capture.observation(Kind::Component, &id, &version)?;
        if observed.passport_digest != address
            || !observed.passport["adaptations"]
                .as_array()
                .ok_or_else(invalid)?
                .iter()
                .any(|a| a["harness_id"] == setup.passport["harness_id"])
        {
            return Err(invalid());
        }
        capture.content(&observed.passport)?;
        if let Some(required) = observed.passport["requires_components"].as_array() {
            edges += required.len();
            pending.extend(required.iter().cloned());
        }
        found.insert(id, observed);
    }
    // Resolve a DAG before creating a plan; a cyclic graph is never a successful capture.
    let mut ordered = BTreeSet::new();
    while ordered.len() < found.len() {
        let before = ordered.len();
        for (id, observation) in &found {
            let dependencies = observation.passport["requires_components"].as_array();
            if dependencies.is_none_or(|items| {
                items.iter().all(|item| {
                    item["stable_id"]
                        .as_str()
                        .is_some_and(|id| ordered.contains(id))
                })
            }) {
                ordered.insert(id.clone());
            }
        }
        if before == ordered.len() {
            return Err(invalid());
        }
    }
    capture.remaining()?;
    Ok((setup, found, capture))
}

pub fn plan(
    config: Option<&Path>,
    id: &str,
    version: &str,
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    let endpoint = Endpoint::configured(config)?;
    let url = endpoint.base.to_string();
    let (setup, components, _) = capture(endpoint, id, version)?;
    let plan = Plan {
        schema_version: 1,
        action: "catalog.setup.acquire".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
        endpoint: url,
        setup,
        components,
    };
    plan.digest()?;
    Ok(plan)
}

fn verify_local(connection: &Connection, plan: &Plan) -> Result<Value> {
    let objects = Objects { connection };
    let mut verified_bytes = 0usize;
    for observation in plan.components.values().chain(std::iter::once(&plan.setup)) {
        let document = &observation.passport;
        let held = objects.exact_version(
            text(document, "stable_id")?,
            text(document, "version")?,
            Some(&observation.passport_digest),
        )?;
        if held != *document {
            return Err(invalid());
        }
        let (address,lane,author,component,observed): (String,String,i64,i64,String) = connection.query_row(
            "SELECT passport_digest,trust_lane,author_verified,component_verified,acquired_at FROM acquired_trust WHERE stable_id=? AND version=?",
            [text(document,"stable_id")?,text(document,"version")?],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?))).map_err(database)?;
        if address != observation.passport_digest
            || !matches!(lane.as_str(), "authoritative" | "experimental")
            || !matches!(author, 0 | 1)
            || !matches!(component, 0 | 1)
            || (lane == "authoritative" && (author != 1 || component != 1))
            || !passport::timestamp(&observed)
        {
            return Err(invalid());
        }
        let payload = revisions::read_content(connection, text(&document["artifact"], "digest")?)?;
        if document["artifact"]["size_bytes"] != payload.len() {
            return Err(invalid());
        }
        if document["kind"] == "component" {
            for adaptation in document["adaptations"].as_array().ok_or_else(invalid)? {
                for scope in adaptation["scope_adaptations"]
                    .as_array()
                    .ok_or_else(invalid)?
                {
                    let bytes = revisions::read_content(
                        connection,
                        text(&scope["projection_artifact"], "digest")?,
                    )?;
                    verified_bytes = verified_bytes
                        .checked_add(bytes.len())
                        .filter(|size| *size <= MAX_BYTES)
                        .ok_or_else(invalid)?;
                    artifact::verify(scope, &bytes)?;
                }
            }
        } else {
            setups::verify_definition(document, &payload)?;
        }
    }
    let setup = &plan.setup;
    let result = json!({"schema_version":1,"source":"online","stable_id":setup.passport["stable_id"],"version":setup.passport["version"],
        "passport_digest":setup.passport_digest,"artifact_digest":setup.passport["artifact"]["digest"],
        "harness_id":setup.passport["harness_id"],"checked_at":plan.created_at,
        "components":plan.components.values().map(|item|json!({"stable_id":item.passport["stable_id"],"version":item.passport["version"],"passport_digest":item.passport_digest,"artifact_digest":item.passport["artifact"]["digest"]})).collect::<Vec<_>>() });
    RESULT.validate(&result)?;
    Ok(result)
}

pub fn apply(
    store: &mut Store,
    plan: &Plan,
    expected: &str,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    identity.validate()?;
    if plan.schema_version != 1
        || plan.action != "catalog.setup.acquire"
        || plan.identity != *identity
        || plan.digest()? != expected
        || plan.expires_at != expiry(&plan.created_at)?
        || !passport::timestamp(at)
        || !passport::stable_id(&plan.operation_id, "operation")
    {
        return Err(invalid());
    }
    if let Some(state) = journal::state(
        &store.connection,
        &plan.operation_id,
        &plan.action,
        expected,
    )? {
        return if state == "verified" {
            store.transaction(|transaction| verify_local(transaction, plan))
        } else {
            Err(invalid())
        };
    }
    if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        return Err(Failure::precondition(
            "the acquisition plan is outside its validity interval",
        ));
    }
    let (setup, components, capture) = capture(
        Endpoint::new(&plan.endpoint)?,
        text(&plan.setup.passport, "stable_id")?,
        text(&plan.setup.passport, "version")?,
    )?;
    if setup != plan.setup || components != plan.components {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "catalog passports, access or trust changed after planning",
        ));
    }
    let started = at.parse::<jiff::Timestamp>().map_err(|_| invalid())?;
    let expires = plan
        .expires_at
        .parse::<jiff::Timestamp>()
        .map_err(|_| invalid())?;
    if started
        .checked_add(capture.started.elapsed())
        .map_err(|_| invalid())?
        > expires
    {
        return Err(Failure::precondition(
            "the acquisition plan expired during catalog capture",
        ));
    }
    store.transaction(|transaction| {
        if let Some(state) = journal::state(transaction,&plan.operation_id,&plan.action,expected)? {
            return if state == "verified" { verify_local(transaction,plan) } else { Err(invalid()) };
        }
        transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",params![plan.operation_id,plan.action,at,at,expected]).map_err(database)?;
        for (address,bytes) in &capture.payloads {
            if revisions::content(transaction,bytes,at)? != *address { return Err(invalid()); }
        }
        for observation in components.values().chain(std::iter::once(&setup)) {
            let document = &observation.passport;
            Objects {connection:transaction}.require_active(text(document,"stable_id")?)?;
            versions::acquire(transaction,document,&identity.device_id,&plan.operation_id,at)?;
            transaction.execute("INSERT INTO acquired_trust(stable_id,version,passport_digest,trust_lane,author_verified,component_verified,acquired_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(stable_id,version) DO UPDATE SET passport_digest=excluded.passport_digest,trust_lane=excluded.trust_lane,author_verified=excluded.author_verified,component_verified=excluded.component_verified,acquired_at=excluded.acquired_at",
                params![text(document,"stable_id")?,text(document,"version")?,observation.passport_digest,text(&observation.trust,"trust_lane")?,observation.trust["author_verified"].as_bool().ok_or_else(invalid)?,observation.trust["component_verified"].as_bool().ok_or_else(invalid)?,at]).map_err(database)?;
        }
        if graph::exact(transaction,setup.passport["components"].as_array().ok_or_else(invalid)?)?["resolved"] != true { return Err(invalid()); }
        verify_local(transaction,plan)
    })
}
