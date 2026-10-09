//! An explicitly selected native source graph becomes one private draft atomically.

use std::{
    collections::BTreeSet,
    path::PathBuf,
    time::{Duration, Instant},
};

use rusqlite::{Connection, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Identity, adoption, discovery, expiry};
use crate::{
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    files,
    harnesses::{Root, Scope},
    objects::Objects,
    passport,
    store::{
        Store, database, journal,
        revisions::{self, Write},
    },
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub root: PathBuf,
    pub harness_id: String,
    pub scope: Scope,
    pub root_kind: Root,
    pub candidates: Vec<String>,
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
    pub request: Request,
    pub components: Vec<adoption::Plan>,
    pub passport: Value,
}

fn invalid() -> Failure {
    Failure::input("the native import plan violates its explicit draft graph contract")
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        let bytes = canonical::bytes(&serde_json::to_value(self).map_err(|_| invalid())?)?;
        if bytes.len() > 8 * 1024 * 1024 {
            return Err(invalid());
        }
        digest::bytes("ai-stp:plan:v1", &bytes)
    }
}

fn prepare(request: &Request) -> Result<Vec<(adoption::Source, adoption::Prepared)>> {
    if request.harness_id == "undefined"
        || request.candidates.is_empty()
        || request.candidates.len() > 128
        || request.candidates.windows(2).any(|pair| pair[0] >= pair[1])
        || request.candidates.iter().any(|id| id.len() != 71)
    {
        return Err(invalid());
    }
    let started = Instant::now();
    let report = discovery::at(
        &request.root,
        &request.harness_id,
        request.scope,
        request.root_kind,
    )?;
    if !report.complete {
        return Err(Failure::precondition(
            "native import requires complete bounded discovery at the selected root",
        ));
    }
    let mut selected = report
        .components
        .into_iter()
        .filter(|candidate| {
            request
                .candidates
                .binary_search(&candidate.candidate_id)
                .is_ok()
        })
        .collect::<Vec<_>>();
    selected.sort_by(|a, b| a.candidate_id.cmp(&b.candidate_id));
    if selected.len() != request.candidates.len() {
        return Err(Failure::new(
            ErrorKind::NotFound,
            "a selected native import candidate is absent",
        ));
    }
    let mut bytes = 0;
    selected
        .into_iter()
        .map(|candidate| {
            let source = adoption::Source {
                root: request.root.clone(),
                harness_id: request.harness_id.clone(),
                scope: request.scope,
                root_kind: request.root_kind,
                candidate_id: candidate.candidate_id.clone(),
            };
            let prepared = adoption::prepare_candidate(&source, &request.harness_id, candidate)?;
            bytes += prepared.content.bytes.len();
            if bytes > 64 * 1024 * 1024 || started.elapsed() > Duration::from_secs(30) {
                return Err(Failure::precondition(
                    "native import exceeds its aggregate capture budget",
                ));
            }
            Ok((source, prepared))
        })
        .collect()
}

fn rebuild(
    transaction: &Transaction<'_>,
    plan: &Plan,
    prepared: &[(adoption::Source, adoption::Prepared)],
) -> Result<Plan> {
    if plan.components.len() != prepared.len() {
        return Err(invalid());
    }
    let mut plan = plan.clone();
    for (component, (source, prepared)) in plan.components.iter_mut().zip(prepared) {
        *component = adoption::build(
            transaction,
            prepared,
            source,
            &plan.identity,
            &plan.created_at,
            &plan.operation_id,
            &component.binding.stable_id,
        )?;
    }
    finish(plan)
}

fn finish(mut plan: Plan) -> Result<Plan> {
    let mut ids = BTreeSet::new();
    let mut sources = BTreeSet::new();
    if plan.components.iter().any(|item| {
        !ids.insert(&item.binding.stable_id) || !sources.insert(&item.binding.source_key)
    }) {
        return Err(Failure::new(
            ErrorKind::Conflict,
            "selected sources have conflicting component bindings",
        ));
    }
    let members: Vec<_> = plan.components.iter().map(|component| json!({
        "stable_id":component.passport["stable_id"],"revision_id":component.passport["revision_id"],
        "candidate_id":component.source.candidate_id,
        "content_digest":component.passport["facts"]["content_digest"]["value"],
    })).collect();
    let fact = |value: Value, origin: &str| json!({"value":value,"origin":origin,"confirmation":"none","observed_at":plan.created_at});
    plan.passport = revisions::seal(&json!({
        "kind":"setup","stable_id":plan.passport["stable_id"],"owner_id":plan.identity.account_id,
        "created_at":plan.created_at,"visibility":"private","parent_revision_ids":[],
        "facts":{
            "harness_id":fact(plan.request.harness_id.clone().into(),"declared"),
            "origin":fact("imported".into(),"derived"),"capture_mode":fact("selected_components".into(),"declared"),
            "components":fact(json!(members),"derived"),"scope":fact(json!(plan.request.scope),"declared"),
            "root_kind":fact(json!(plan.request.root_kind),"declared"),
            "capture_tool_version":fact(concat!("ai-stp-cli-v2=",env!("CARGO_PKG_VERSION")).into(),"observed"),
        }
    }))?;
    plan.digest()?;
    Ok(plan)
}

pub fn plan(store: &mut Store, mut request: Request, identity: Identity, at: &str) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    request.root = PathBuf::from(files::location(&request.root)?);
    request.candidates.sort();
    let prepared = prepare(&request)?;
    let operation_id = format!("operation_{}", ulid::Ulid::generate());
    // Allocate identities only in this plan, then reuse those exact identities
    // when rebuilding under the apply transaction's writer lock.
    store.transaction(|transaction| {
        let components = prepared
            .iter()
            .map(|(source, prepared)| {
                adoption::build(
                    transaction,
                    prepared,
                    source,
                    &identity,
                    at,
                    &operation_id,
                    &format!("component_{}", ulid::Ulid::generate()),
                )
            })
            .collect::<Result<Vec<_>>>()?;
        finish(Plan {
            schema_version: 1,
            action: "setup.import".into(),
            operation_id,
            created_at: at.into(),
            expires_at,
            identity,
            request,
            components,
            passport: json!({"stable_id":format!("setup_{}",ulid::Ulid::generate())}),
        })
    })
}

fn replay(connection: &Connection, plan: &Plan) -> Result<Value> {
    let held = Objects { connection }
        .revision(plan.passport["revision_id"].as_str().ok_or_else(invalid)?)?;
    if held != plan.passport {
        return Err(invalid());
    }
    for component in &plan.components {
        adoption::replay(connection, component)?;
    }
    Ok(held)
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
        || plan.action != "setup.import"
        || plan.identity != *identity
        || plan.digest()? != expected
        || !plan.request.root.is_absolute()
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::stable_id(plan.passport["stable_id"].as_str().unwrap_or(""), "setup")
        || plan.expires_at != expiry(&plan.created_at)?
        || !passport::timestamp(at)
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
            replay(&store.connection, plan)
        } else {
            Err(invalid())
        };
    }
    if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        return Err(Failure::precondition(
            "the import plan is not within its validity interval",
        ));
    }
    let prepared = prepare(&plan.request)?;
    store.transaction(|transaction| {
        if let Some(state) = journal::state(transaction,&plan.operation_id,&plan.action,expected)? {
            return if state == "verified" { replay(transaction,plan) } else { Err(invalid()) };
        }
        if rebuild(transaction,plan,&prepared)?.digest()? != expected {
            return Err(Failure::new(ErrorKind::Conflict,"native import sources, bindings or revision heads changed after planning"));
        }
        transaction.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",params![plan.operation_id,plan.action,at,at,expected]).map_err(database)?;
        for (component, (_, prepared)) in plan.components.iter().zip(&prepared) {
            adoption::persist(transaction,component,prepared,identity,at)?;
        }
        revisions::commit(transaction,&plan.passport,&identity.device_id,Some(&plan.operation_id),Write::Advance { expected_heads:&[] })
    })
}
