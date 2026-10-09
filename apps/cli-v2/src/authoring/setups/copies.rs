//! Private exact setup copies, including atomic owned graph derivation.

use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    Member, Request, Source, aggregate::Aggregate, compile, exact, finish_from, recast, verify,
};

pub use super::recast::{Derivation, DerivedMember};
use crate::{
    authoring::{Identity, expiry, freezing},
    canonical, digest,
    error::{ErrorKind, Failure, Result},
    harnesses,
    objects::Objects,
    passport,
    provider::Info,
    selection::graph,
    store::{
        Store, database, journal,
        revisions::{self, Write},
        versions,
    },
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub action: String,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub identity: Identity,
    pub source: Source,
    pub target_harness: String,
    pub passport: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub derivation: Option<Derivation>,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

fn invalid() -> Failure {
    Failure::precondition(
        "the setup copy violates its exact source, lineage or complete graph contract",
    )
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(invalid)
}

struct Built {
    passport: Value,
    bytes: Vec<u8>,
    derived: Option<recast::Built>,
}

fn copy(
    connection: &Connection,
    plan: &Plan,
    original: Value,
    derived: Option<recast::Built>,
) -> Result<Built> {
    let same = original["harness_id"] == plan.target_harness;
    if !matches!(
        (plan.action.as_str(), same),
        ("setup.fork", true) | ("setup.recast", false)
    ) || plan.target_harness == "undefined"
        || original["stable_id"] == plan.passport["stable_id"]
    {
        return Err(invalid());
    }
    harnesses::definition(&plan.target_harness)?;
    let mut members = Vec::new();
    let mut unavailable = Vec::new();
    if let Some(derived) = &derived {
        for document in &derived.documents {
            members.push(Member {
                stable_id: text(document, "stable_id")?.into(),
                version: text(document, "version")?.into(),
                passport_digest: digest::canonical("ai-stp:passport:v1", document)?,
            });
        }
    } else {
        for reference in original["components"].as_array().ok_or_else(invalid)? {
            if !reference["variant_id"].is_null() {
                return Err(invalid());
            }
            let member = Member {
                stable_id: text(reference, "stable_id")?.into(),
                version: text(reference, "version")?.into(),
                passport_digest: text(reference, "passport_digest")?.into(),
            };
            let held = Objects { connection }.exact_version(
                &member.stable_id,
                &member.version,
                Some(&member.passport_digest),
            )?;
            if !held["adaptations"]
                .as_array()
                .ok_or_else(invalid)?
                .iter()
                .any(|a| a["harness_id"] == plan.target_harness)
            {
                unavailable.push(serde_json::to_value(&member).map_err(|_| invalid())?);
            }
            members.push(member);
        }
    }
    if !unavailable.is_empty() {
        return Err(Failure::precondition("every exact setup member needs an explicit target adaptation; author and release missing adaptations before selecting new coordinates")
            .with_details([("constraint".into(),"adaptation_unavailable".into()),("members".into(),json!(unavailable))]));
    }
    let request = Request {
        harness_id: plan.target_harness.clone(),
        name: text(&original, "name")?.into(),
        description: text(&original, "description")?.into(),
        purpose: text(&original, "purpose")?.into(),
        members,
        requirements: None,
    };
    let id = text(&plan.passport, "stable_id")?;
    let (mut document, _) = if let Some(derived) = &derived {
        super::assemble(
            &request,
            super::input(&request, id)?,
            id,
            &plan.identity,
            &plan.created_at,
            &derived.documents,
        )?
    } else {
        let result = compile(connection, &request, id, &plan.identity, &plan.created_at)?;
        let mut expected_members = original["components"].clone();
        passport::versions::normalize_component_refs(&mut expected_members)?;
        if result.0["components"] != expected_members {
            return Err(invalid());
        }
        result
    };
    // Source declarations may add requirements, but cannot weaken requirements
    // rebuilt from the exact members. Keep one explanation per environment name.
    let mut environment = std::collections::BTreeMap::new();
    for value in [&document, &original] {
        for requirement in value["required_env"].as_array().ok_or_else(invalid)? {
            environment.insert(text(requirement, "name")?.to_owned(), requirement.clone());
        }
    }
    let mut requirements = Aggregate::default();
    requirements.include(&document)?;
    requirements.include(&original)?;
    requirements.apply(&mut document);
    document["required_env"] = environment.into_values().collect::<Vec<_>>().into();
    // Keep content declarations and conservative requirements. Evidence, account
    // authority and source-harness version claims do not transfer to a new setup.
    for field in [
        "tags",
        "target_role",
        "posture",
        "supported_tasks",
        "supported_os",
        "supported_arch",
    ] {
        if let Some(value) = original.get(field) {
            document[field] = value.clone();
        }
    }
    if same {
        document["supported_harness_versions"] = original["supported_harness_versions"].clone();
    } else {
        document["ported_from"] = serde_json::to_value(&plan.source).map_err(|_| invalid())?;
    }
    document["related_setup_ids"] = json!([plan.source.stable_id]);
    document["facts"]["source_setup"] = json!({"value":plan.source,"origin":"derived","confirmation":"none","observed_at":plan.created_at});
    if !same
        && original["supported_harness_versions"]
            .as_array()
            .is_some_and(|v| !v.is_empty())
    {
        document["facts"]["source_harness_version_constraints"] = json!({"value":{
            "harness_id":original["harness_id"],"constraints":original["supported_harness_versions"],"transferred":false},
            "origin":"derived","confirmation":"none","observed_at":plan.created_at});
    }
    let (passport, bytes) = finish_from(connection, &original, document)?;
    Ok(Built {
        passport,
        bytes,
        derived,
    })
}

fn build(connection: &Connection, plan: &Plan, original: Value) -> Result<Built> {
    let derived = if let Some(declaration) = &plan.derivation {
        let provider = Info::parse(&canonical::bytes(&declaration.provider)?)?;
        if plan.action != "setup.recast" || provider.document()["harness_id"] != plan.target_harness
        {
            return Err(invalid());
        }
        Some(recast::build(
            connection,
            &original,
            &provider,
            &plan.identity,
            &plan.created_at,
            Some(&declaration.members),
        )?)
    } else {
        None
    };
    copy(connection, plan, original, derived)
}

/// An absent target means a same-harness fork; an explicit target means recast.
pub fn plan(
    store: &mut Store,
    reference: Source,
    target: Option<&str>,
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    create_plan(store, reference, target, None, identity, at)
}

/// A declaration enables only the implemented lossless native transformations.
pub fn plan_with_provider(
    store: &mut Store,
    reference: Source,
    provider: &Info,
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    create_plan(
        store,
        reference,
        Some(text(provider.document(), "harness_id")?),
        Some(provider),
        identity,
        at,
    )
}

fn create_plan(
    store: &mut Store,
    reference: Source,
    target: Option<&str>,
    provider: Option<&Info>,
    identity: Identity,
    at: &str,
) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    store.transaction(|t| {
        let original = exact(t, &reference)?;
        let mut plan = Plan {
            schema_version: 1,
            action: if target.is_some() {
                "setup.recast"
            } else {
                "setup.fork"
            }
            .into(),
            operation_id: format!("operation_{}", ulid::Ulid::generate()),
            created_at: at.into(),
            expires_at,
            identity,
            source: reference,
            target_harness: target.unwrap_or(text(&original, "harness_id")?).into(),
            passport: json!({"stable_id":format!("setup_{}",ulid::Ulid::generate())}),
            derivation: None,
        };
        let prepared = if let Some(provider) = provider {
            let prepared = recast::build(t, &original, provider, &plan.identity, at, None)?;
            plan.derivation = Some(prepared.derivation.clone());
            Some(prepared)
        } else {
            None
        };
        plan.passport = copy(t, &plan, original, prepared)?.passport;
        Ok(plan)
    })
}

fn replay(connection: &Connection, plan: &Plan) -> Result<Value> {
    let id = text(&plan.passport, "stable_id")?;
    let document = Objects { connection }.exact_version(id, "1.0", None)?;
    let origin: Option<(String,String,String,String)> = connection.query_row(
        "SELECT source_stable_id,source_version,source_digest,created_at FROM fork_origin WHERE stable_id=?",
        [id],|r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).optional().map_err(database)?;
    let expected = (
        plan.source.stable_id.clone(),
        plan.source.version.clone(),
        plan.source.passport_digest.clone(),
        plan.created_at.clone(),
    );
    if document != plan.passport || origin.as_ref() != Some(&expected) {
        return Err(invalid());
    }
    verify(connection, &document)?;
    if let Some(derived) = &plan.derivation {
        for member in &derived.members {
            let held = Objects { connection }.exact_version(
                text(&member.passport, "stable_id")?,
                "1.0",
                None,
            )?;
            if held != member.passport {
                return Err(invalid());
            }
            freezing::verify(connection, &held)?;
            let origin: (String,String,String,String) = connection.query_row(
                "SELECT source_stable_id,source_version,source_digest,created_at FROM fork_origin WHERE stable_id=?",
                [text(&held,"stable_id")?],|r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).map_err(database)?;
            if origin
                != (
                    member.source.stable_id.clone(),
                    member.source.version.clone(),
                    member.source.passport_digest.clone(),
                    plan.created_at.clone(),
                )
            {
                return Err(invalid());
            }
        }
    }
    Ok(document)
}

pub fn apply(
    store: &mut Store,
    plan: &Plan,
    expected_digest: &str,
    identity: &Identity,
    at: &str,
) -> Result<Value> {
    identity.validate()?;
    if plan.schema_version != 1
        || !["setup.fork", "setup.recast"].contains(&plan.action.as_str())
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected_digest
    {
        return Err(invalid());
    }
    let id = text(&plan.passport, "stable_id")?;
    store.transaction(|t| {
        if let Some(state) = journal::state(t,&plan.operation_id,&plan.action,expected_digest)? {
            if state != "verified" { return Err(invalid()); }
            return replay(t,plan);
        }
        if at < plan.created_at.as_str() || at > plan.expires_at.as_str() { return Err(invalid()); }
        let exists: bool = t.query_row("SELECT EXISTS(SELECT 1 FROM entity WHERE stable_id=?)",[id],|r|r.get(0)).map_err(database)?;
        if exists { return Err(Failure::new(ErrorKind::Conflict,"the planned setup identity already exists")); }
        let built = build(t,plan,exact(t,&plan.source)?)?;
        let document = built.passport;
        if document != plan.passport { return Err(invalid()); }
        if let Some(derived) = built.derived {
            for member in &derived.derivation.members {
                let exists: bool = t.query_row("SELECT EXISTS(SELECT 1 FROM entity WHERE stable_id=?)",[text(&member.passport,"stable_id")?],|r|r.get(0)).map_err(database)?;
                if exists { return Err(Failure::new(ErrorKind::Conflict,"a planned recast component identity already exists")); }
            }
            for bytes in derived.artifacts.values() { revisions::content(t,bytes,at)?; }
            for member in &derived.derivation.members {
                freezing::verify(t,&member.passport)?;
                revisions::commit(t,&member.passport,&identity.device_id,Some(&plan.operation_id),Write::Advance { expected_heads:&[] })?;
                versions::record(t,&member.passport,&identity.device_id,Some(&plan.operation_id),at)?;
                t.execute("INSERT INTO fork_origin(stable_id,source_stable_id,source_version,source_digest,created_at) VALUES (?,?,?,?,?)",
                    params![text(&member.passport,"stable_id")?,member.source.stable_id,member.source.version,member.source.passport_digest,plan.created_at]).map_err(database)?;
            }
        }
        revisions::content(t,&built.bytes,at)?;
        revisions::commit(t,&document,&identity.device_id,Some(&plan.operation_id),Write::Advance {expected_heads:&[]})?;
        versions::record(t,&document,&identity.device_id,Some(&plan.operation_id),at)?;
        t.execute("INSERT INTO fork_origin(stable_id,source_stable_id,source_version,source_digest,created_at) VALUES (?,?,?,?,?)",
            params![id,plan.source.stable_id,plan.source.version,plan.source.passport_digest,plan.created_at]).map_err(database)?;
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,plan.action,at,at,expected_digest]).map_err(database)?;
        if graph::exact(t,document["components"].as_array().ok_or_else(invalid)?)?["resolved"] != true { return Err(invalid()); }
        verify(t,&document)?;
        Ok(document)
    })
}
