//! One reviewed publication graph, resumed with fresh authority and original keys.

use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{
    Snapshot,
    client::Client,
    contract::{Create, Options, Visibility},
    journal::Attempt,
    readback::Observation,
    set::{Run, Terminal},
    text,
};
use crate::{
    account::access::Binding,
    authoring, canonical, digest,
    error::{ErrorKind, Failure, Result},
    files, identity, passport,
    store::Store,
};

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Evidence {
    pub source_binding_id: Option<String>,
    pub gitlab_source_binding_id: Option<String>,
    #[serde(default)]
    pub attestations: Vec<Value>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub stable_id: String,
    pub version: String,
    #[serde(default)]
    pub visibility: Visibility,
    pub component_root: Option<String>,
    #[serde(default)]
    pub evidence: BTreeMap<String, Evidence>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "delivery", rename_all = "snake_case", deny_unknown_fields)]
pub(super) enum Member {
    Available {
        snapshot: Snapshot,
        catalog: Observation,
    },
    Publish {
        attempt: Attempt,
    },
}

impl Member {
    pub(super) fn snapshot(&self) -> Result<Snapshot> {
        match self {
            Self::Available { snapshot, .. } => Ok(snapshot.clone()),
            Self::Publish { attempt } => attempt.request.snapshot(),
        }
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Intent {
    pub operation_id: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub state_parent: PathBuf,
    pub account: Binding,
    pub visibility: Visibility,
    pub component_root: Option<String>,
    pub members: Vec<Member>,
}

pub(super) fn invalid() -> Failure {
    Failure::precondition(
        "the publication group differs from its exact intent, session or progress",
    )
}

pub(super) fn encode(value: &impl Serialize) -> Result<String> {
    let bytes = canonical::bytes(&serde_json::to_value(value).map_err(|_| invalid())?)?;
    if bytes.len() > 16 * 1024 * 1024 {
        return Err(invalid());
    }
    String::from_utf8(bytes).map_err(|_| invalid())
}

impl Intent {
    pub fn digest(&self) -> Result<String> {
        self.account.validate()?;
        if !passport::stable_id(&self.operation_id, "operation")
            || !self.state_parent.is_absolute()
            || self.members.is_empty()
            || self.members.len() > 513
            || self
                .component_root
                .as_ref()
                .is_some_and(|p| !Path::new(p).is_absolute())
        {
            return Err(invalid());
        }
        let mut ids = BTreeSet::new();
        let mut operations = BTreeSet::from([self.operation_id.as_str()]);
        for (index, member) in self.members.iter().enumerate() {
            let snapshot = member.snapshot()?;
            let document = &snapshot.passport;
            if !ids.insert(text(document, "stable_id")?.to_owned())
                || index + 1 < self.members.len() && document["kind"] != "component"
                || self.members.len() > 1
                    && index + 1 == self.members.len()
                    && document["kind"] != "setup"
            {
                return Err(invalid());
            }
            match member {
                Member::Available { catalog, .. } => {
                    catalog.validate(&snapshot, self.visibility, &self.account)?
                }
                Member::Publish { attempt } => {
                    attempt.digest()?;
                    if attempt.request.account != self.account
                        || !operations.insert(&attempt.operation_id)
                        || serde_json::to_value(self.visibility).map_err(|_| invalid())?
                            != attempt.request.body()["visibility"]
                    {
                        return Err(invalid());
                    }
                }
            }
        }
        digest::bytes("ai-stp:plan:v1", encode(self)?.as_bytes())
    }

    pub(super) fn local(&self, store: &mut Store) -> Result<()> {
        let target = self.members.last().ok_or_else(invalid)?.snapshot()?;
        let actual = super::prepare(
            store,
            text(&target.passport, "stable_id")?,
            text(&target.passport, "version")?,
            Some(&target.passport_digest),
            self.component_root.as_deref().map(Path::new),
        )?;
        if actual.len() != self.members.len() {
            return Err(invalid());
        }
        for (actual, expected) in actual.iter().zip(&self.members) {
            if let Member::Available { snapshot, .. } = expected
                && actual != snapshot
            {
                return Err(invalid());
            }
            let expected = expected.snapshot()?;
            if actual.passport != expected.passport
                || actual.passport_digest != expected.passport_digest
                || actual.artifact_inventory != expected.artifact_inventory
            {
                return Err(invalid());
            }
        }
        Ok(())
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    schema_version: u32,
    pub(super) intent: Intent,
    pub(super) account: Binding,
    pub(super) position: String,
    pub(super) created_at: String,
    pub(super) expires_at: String,
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        self.intent.digest()?;
        self.account.validate()?;
        let mut original = self.intent.account.clone();
        original.revision.clone_from(&self.account.revision);
        if self.schema_version != 1
            || original != self.account
            || authoring::expiry(&self.created_at)? != self.expires_at
            || !super::interruption::hash(&self.position)
        {
            return Err(invalid());
        }
        digest::bytes("ai-stp:plan:v1", encode(self)?.as_bytes())
    }
}

fn bound(intent: Intent, client: &Client, store: &Store, at: &str) -> Result<Plan> {
    let plan = Plan {
        schema_version: 1,
        position: Run::position(&store.connection, &intent)?,
        intent,
        account: client.binding().clone(),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
    };
    plan.digest()?;
    Ok(plan)
}

fn catalog(
    client: &mut Client,
    snapshot: &Snapshot,
    visibility: Visibility,
) -> Result<Option<Observation>> {
    // Publication cannot change an existing version's distribution visibility.
    // Check the private route after a public miss before admitting a new write.
    let observed = client.catalog(snapshot, Visibility::Private)?;
    if visibility == Visibility::Public
        && observed
            .as_ref()
            .is_some_and(|v| v.distribution_visibility == Visibility::Private)
    {
        return Err(Failure::precondition(
            "this exact version is already private; public distribution requires a separate explicit visibility change",
        ));
    }
    Ok(observed)
}

pub fn plan(root: &Path, origin: Option<&str>, request: Request, at: &str) -> Result<Plan> {
    plan_for_connection(root, origin, None, request, at)
}

pub fn plan_for_connection(
    root: &Path,
    origin: Option<&str>,
    connection: Option<&str>,
    request: Request,
    at: &str,
) -> Result<Plan> {
    let state_parent = PathBuf::from(files::location(root)?);
    let mut client = Client::for_connection(&state_parent, origin, connection)?;
    let mut store = client.registry()?;
    let component_root = request
        .component_root
        .as_deref()
        .map(|p| files::location(Path::new(p)))
        .transpose()?;
    let snapshots = super::prepare(
        &mut store,
        &request.stable_id,
        &request.version,
        None,
        component_root.as_deref().map(Path::new),
    )?;
    let ids: BTreeSet<_> = snapshots
        .iter()
        .map(|s| text(&s.passport, "stable_id"))
        .collect::<Result<_>>()?;
    if request.evidence.keys().any(|id| !ids.contains(id.as_str())) {
        return Err(invalid());
    }
    Run::unoccupied(&store.connection, snapshots.last().ok_or_else(invalid)?)?;
    let mut members = Vec::new();
    for snapshot in snapshots {
        let id = text(&snapshot.passport, "stable_id")?;
        let evidence = request.evidence.get(id);
        if let Some(catalog) = catalog(&mut client, &snapshot, request.visibility)? {
            if evidence.is_some() {
                return Err(Failure::input(
                    "publication evidence cannot be submitted for an already readable version",
                ));
            }
            members.push(Member::Available { snapshot, catalog });
        } else {
            let evidence = evidence.cloned().unwrap_or_default();
            let options = Options {
                visibility: request.visibility,
                source_binding_id: evidence.source_binding_id,
                gitlab_source_binding_id: evidence.gitlab_source_binding_id,
                attestations: evidence.attestations,
            };
            let request = Create::new(
                &snapshot,
                client.binding().clone(),
                options,
                &format!("publication-create-{}", ulid::Ulid::generate()),
            )?;
            members.push(Member::Publish {
                attempt: Attempt::new(request)?,
            });
        }
    }
    let intent = Intent {
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        state_parent,
        account: client.binding().clone(),
        visibility: request.visibility,
        component_root,
        members,
    };
    bound(intent, &client, &store, at)
}

pub fn resume(root: &Path, origin: Option<&str>, operation_id: &str, at: &str) -> Result<Plan> {
    // Resolve the durable intent before acquiring its account journal. The
    // selected view and unrelated legacy session cannot retarget continuation.
    let identity = identity::current(root)?.ok_or_else(invalid)?;
    let intent = {
        let store = Store::planning_at(identity.root_directory())?;
        Run::intent(&store.connection, operation_id)?
    };
    if origin.is_some_and(|origin| origin != intent.account.origin) {
        return Err(invalid());
    }
    let mut client = Client::for_binding(root, &intent.account)?;
    client.verify()?;
    let mut store = client.registry()?;
    if intent.state_parent != Path::new(&files::location(root)?) {
        return Err(invalid());
    }
    let held = Run::load(&store.connection, &intent)?.ok_or_else(invalid)?;
    if held.terminal.is_some() {
        return Err(Failure::precondition(
            "the publication group already has a historical result",
        ));
    }
    intent.local(&mut store)?;
    bound(intent, &client, &store, at)
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let plan: Plan =
        serde_json::from_value(canonical::parse(&files::read(path, 16 * 1024 * 1024)?)?)
            .map_err(|_| invalid())?;
    plan.digest()?;
    Ok(plan)
}

pub fn read_request(path: &Path) -> Result<Request> {
    serde_json::from_value(canonical::parse(&files::read(path, 16 * 1024 * 1024)?)?)
        .map_err(|_| Failure::input("the publication request violates its closed contract"))
}

pub fn apply(plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    if plan.digest()? != expected {
        return Err(invalid());
    }
    apply_confirmed(plan, at).map_err(|mut failure| {
        failure
            .details
            .entry("operation_id".into())
            .or_insert_with(|| plan.intent.operation_id.clone().into());
        failure
    })
}

fn apply_confirmed(plan: &Plan, at: &str) -> Result<Value> {
    let intent = &plan.intent;
    let identity = identity::current(&intent.state_parent)?.ok_or_else(invalid)?;
    if identity.root_binding().1 != &intent.account.root_identity {
        return Err(invalid());
    }
    let store = Store::planning_at(identity.root_directory())?;
    if let Some(run) = Run::load(&store.connection, intent)?
        && run.terminal.is_some()
    {
        identity.revalidate()?;
        return run.view(intent);
    }
    drop(store);
    drop(identity);
    if !passport::timestamp(at) || at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        return Err(invalid());
    }
    let mut client = Client::for_binding(&intent.state_parent, &plan.account)?;
    if client.binding() != &plan.account {
        return Err(invalid());
    }
    let mut store = client.registry()?;
    if Run::position(&store.connection, intent)? != plan.position {
        return Err(invalid());
    }
    intent.local(&mut store)?;
    // All retained reuse decisions need fresh access before any group write.
    let mut catalogs = Vec::new();
    for member in &intent.members {
        let snapshot = member.snapshot()?;
        let observed = catalog(&mut client, &snapshot, intent.visibility)?;
        if matches!(member, Member::Available { .. }) && observed.is_none() {
            return Err(Failure::precondition(
                "a reused publication member is no longer readable",
            ));
        }
        catalogs.push(observed);
    }
    let mut run = store.transaction(|t| Run::confirm(t, plan, at))?;
    for (index, member) in intent.members.iter().enumerate() {
        if let Member::Publish { attempt } = member {
            let existing = attempt.inspect(&store.connection)?;
            // A new remote observation can avoid an unstarted duplicate. Once an
            // attempt is admitted, only that original attempt settles its outcome.
            if existing.is_none() && catalogs[index].is_some() {
                continue;
            }
            let result = attempt.advance_in(&mut client, &mut store)?;
            match result["state"].as_str() {
                Some("published") => {
                    if existing.as_ref().is_some_and(|v| v["state"] == "published") {
                        if catalogs[index].is_none() {
                            return Err(Failure::precondition(
                                "a published dependency is no longer readable",
                            ));
                        }
                    } else {
                        // advance_in just obtained this exact fresh observation.
                        catalogs[index] = Some(
                            serde_json::from_value(result["outcome"]["catalog"].clone())
                                .map_err(|_| invalid())?,
                        );
                    }
                }
                Some("refused") => {
                    let accepted = catalogs[..index]
                        .iter()
                        .cloned()
                        .map(|v| v.ok_or_else(invalid))
                        .collect::<Result<Vec<_>>>()?;
                    store.transaction(|t| {
                        run.finish(
                            t,
                            intent,
                            Terminal::Refused {
                                index,
                                catalogs: accepted,
                            },
                        )
                    })?;
                    return run.view(intent);
                }
                Some("waiting") => {
                    return Ok(
                        json!({"schema_version":1,"operation_id":intent.operation_id,
                    "intent_digest":intent.digest()?,"state":"waiting","member_index":index,"member":result}),
                    );
                }
                _ => return Err(invalid()),
            }
        }
    }
    let catalogs = catalogs
        .into_iter()
        .map(|v| v.ok_or_else(invalid))
        .collect::<Result<Vec<_>>>()?;
    store.transaction(|t| run.finish(t, intent, Terminal::Published { catalogs }))?;
    run.view(intent)
}

/// Local journal evidence only. With no id, discover unfinished groups without
/// returning their complete passports or loading account credentials.
pub fn status(root: &Path, operation_id: Option<&str>) -> Result<Value> {
    if operation_id.is_some_and(|id| !passport::stable_id(id, "operation")) {
        return Err(Failure::input("invalid publication operation identifier"));
    }
    let identity = identity::current(root)?.ok_or_else(invalid)?;
    let store = Store::planning_at(identity.root_directory())?;
    let mut query = store.connection.prepare(
        "SELECT operation_id FROM operation WHERE kind='publication.set' AND ((?1 IS NULL AND finished_at IS NULL) OR operation_id=?1) ORDER BY operation_id LIMIT 129"
    ).map_err(crate::store::database)?;
    let ids = query
        .query_map([operation_id], |r| r.get::<_, String>(0))
        .map_err(crate::store::database)?
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(crate::store::database)?;
    if ids.len() > 128 {
        return Err(invalid());
    }
    if operation_id.is_some() && ids.is_empty() {
        return Err(Failure::new(
            ErrorKind::NotFound,
            "the publication operation was not admitted",
        ));
    }
    let mut operations = Vec::new();
    for id in ids {
        let intent = Run::intent(&store.connection, &id)?;
        if intent.account.root_identity != *identity.root_binding().1 {
            return Err(invalid());
        }
        let run = Run::load(&store.connection, &intent)?.ok_or_else(invalid)?;
        let target = intent.members.last().ok_or_else(invalid)?.snapshot()?;
        let mut view = if run.terminal.is_some() {
            run.view(&intent)?
        } else {
            json!({"schema_version":1,"operation_id":id,"intent_digest":intent.digest()?,"state":"waiting"})
        };
        view["stable_id"] = target.passport["stable_id"].clone();
        view["version"] = target.passport["version"].clone();
        if operation_id.is_some() {
            let mut members = Vec::new();
            for member in &intent.members {
                let snapshot = member.snapshot()?;
                let delivery = match member {
                    Member::Publish { attempt } => {
                        attempt.inspect(&store.connection)?.unwrap_or_else(
                            || json!({"operation_id":attempt.operation_id,"state":"not_started"}),
                        )
                    }
                    Member::Available { .. } => json!({"state":"reuse_planned"}),
                };
                members.push(json!({"stable_id":snapshot.passport["stable_id"],"version":snapshot.passport["version"],"delivery":delivery}));
            }
            view["members"] = members.into();
        }
        operations.push(view);
    }
    identity.revalidate()?;
    Ok(json!({"schema_version":1,"observation":"local_journal","operations":operations}))
}

/// Read current remote evidence through the replacement account, preserving the
/// stopped group's historical receipt and all original per-object requests.
pub fn reconcile(root: &Path, origin: Option<&str>, operation_id: &str) -> Result<Value> {
    let mut client = Client::connect(root, origin)?;
    let store = client.registry()?;
    let intent = Run::intent(&store.connection, operation_id)?;
    let run = Run::load(&store.connection, &intent)?.ok_or_else(invalid)?;
    let Some(Terminal::Interrupted { recovery }) = &run.terminal else {
        return Err(invalid());
    };
    client.recovered_binding(&intent.account, recovery)?;
    let mut members = Vec::new();
    for member in &intent.members {
        let interrupted = match member {
            Member::Publish { attempt } => attempt
                .inspect(&store.connection)?
                .is_some_and(|v| v["state"] == "interrupted"),
            _ => false,
        };
        members.push((member.clone(), interrupted));
    }
    drop(store);
    let mut observations = Vec::new();
    for (member, interrupted) in members {
        if let Member::Publish { attempt } = &member
            && interrupted
        {
            observations.push(attempt.reconcile(&mut client)?);
        } else {
            let snapshot = member.snapshot()?;
            observations.push(json!({"stable_id":snapshot.passport["stable_id"],
                "version":snapshot.passport["version"],"catalog":client.catalog(&snapshot,intent.visibility)?}));
        }
    }
    Ok(
        json!({"schema_version":1,"operation_id":operation_id,"intent_digest":intent.digest()?,"members":observations}),
    )
}
