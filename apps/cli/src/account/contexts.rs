//! Context selection is a local preference. Remote observations grant no authority.

use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

use super::access::{Access, Binding};
use crate::{
    authoring, canonical, digest,
    error::{Failure, Result},
    files, identity, passport,
    store::{
        CHECKOUT_LINK_SCHEMA, ENROLLMENT_RECOVERY_SCHEMA, PROFILE_SCHEMA, Store, database,
        profile_schema_after,
    },
    wire,
};

#[cfg(all(test, unix))]
mod tests;

const LIMIT: usize = 256;
const MAX_PLAN: u64 = 131072;
static ACTIVE: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/active-context.schema.json"
)));
static ORGANIZATIONS: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/organization-list.schema.json"
)));

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Authority {
    Local,
    Remote {
        account: Box<Binding>,
        organization: Value,
        observation: Value,
    },
}

enum SessionSource<'a> {
    Local,
    Legacy,
    Connection(&'a str),
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Context {
    pub schema_version: u32,
    pub context_id: String,
    pub label: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub root: PathBuf,
    pub root_identity: [String; 2],
    pub local_identity: authoring::Identity,
    pub observed_at: String,
    pub authority: Authority,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Selection {
    pub revision: String,
    pub context_id: String,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
pub enum Change {
    Create {
        context: Box<Context>,
        registry_schema_before: u32,
    },
    Select {
        context: Box<Context>,
        expected: Option<Selection>,
    },
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub registry_schema_after: u32,
    pub operation_id: String,
    pub created_at: String,
    pub expires_at: String,
    pub change: Change,
}

fn invalid() -> Failure {
    Failure::precondition("the context, selection revision or retained operation changed")
}
fn fields(value: &Value, names: &[&str]) -> Value {
    Value::Object(
        names
            .iter()
            .filter_map(|name| value.get(*name).map(|v| ((*name).to_owned(), v.clone())))
            .collect(),
    )
}
pub(super) fn organizations_projection(value: &Value) -> Result<Value> {
    ORGANIZATIONS.validate(value)?;
    let mut ids = std::collections::BTreeSet::new();
    let mut items = Vec::new();
    for item in value["items"].as_array().ok_or_else(invalid)? {
        if !ids.insert(item["organization_id"].as_str().ok_or_else(invalid)?) {
            return Err(invalid());
        }
        items.push(fields(
            item,
            &[
                "schema_version",
                "organization_id",
                "kind",
                "display_name",
                "membership_revision",
            ],
        ));
    }
    Ok(json!({"schema_version":1,"items":items}))
}
pub(super) fn active_projection(value: &Value) -> Result<Value> {
    ACTIVE.validate(value)?;
    let mut active = fields(
        value,
        &["schema_version", "mode", "organization_id", "capabilities"],
    );
    active["capabilities"] = fields(
        &value["capabilities"],
        &[
            "schema_version",
            "registry_version",
            "mode",
            "context_kind",
            "organization_id",
            "authorization_revision",
            "issued_at",
            "generated_at",
            "expires_at",
            "capabilities",
            "unavailable",
        ],
    );
    let projection = &active["capabilities"];
    let caps = projection["capabilities"].as_array().ok_or_else(invalid)?;
    if canonical::bytes(projection)?.len() > 16384
        || caps
            .windows(2)
            .any(|pair| pair[0].as_str() >= pair[1].as_str())
        || caps.iter().any(|cap| {
            cap.as_str()
                .is_none_or(|key| projection["unavailable"].get(key).is_some())
        })
        || ["issued_at", "generated_at", "expires_at"]
            .iter()
            .any(|key| {
                projection[*key]
                    .as_str()
                    .is_none_or(|at| !passport::timestamp(at))
            })
        || projection["mode"] != active["mode"]
        || projection["context_kind"] != active["mode"]
        || projection["organization_id"] != active["organization_id"]
    {
        return Err(invalid());
    }
    Ok(active)
}
fn encode(value: &impl Serialize) -> Result<String> {
    let bytes = canonical::bytes(&serde_json::to_value(value).map_err(|_| invalid())?)?;
    if bytes.len() as u64 > MAX_PLAN {
        return Err(invalid());
    }
    String::from_utf8(bytes).map_err(|_| invalid())
}

impl Context {
    pub fn digest(&self) -> Result<String> {
        self.validate()?;
        Ok(digest::sha256(&canonical::bytes(&json!([
            "ai-stp-native-context/1",
            self
        ]))?))
    }

    fn validate(&self) -> Result<()> {
        self.local_identity.validate()?;
        if self.schema_version != 1
            || !passport::stable_id(&self.context_id, "context")
            || !self.root.is_absolute()
            || !passport::timestamp(&self.observed_at)
            || self.label.is_empty()
            || self.label.len() > 120
            || self.label.trim() != self.label
            || self.label.chars().any(char::is_control)
            || self
                .root_identity
                .iter()
                .any(|v| !v.parse::<u64>().is_ok_and(|n| n.to_string() == *v))
        {
            return Err(invalid());
        }
        if let Authority::Remote {
            account,
            organization,
            observation,
        } = &self.authority
        {
            account.validate()?;
            if active_projection(observation)? != *observation {
                return Err(invalid());
            }
            ORGANIZATIONS.validate(&json!({"schema_version":1,"items":[organization]}))?;
            let projection = &observation["capabilities"];
            if account.root_identity != self.root_identity
                || organization["organization_id"] != observation["organization_id"]
                || organization["kind"] != observation["mode"]
                || projection["mode"] != observation["mode"]
                || projection["context_kind"] != observation["mode"]
                || projection["organization_id"] != observation["organization_id"]
                || !matches!(observation["mode"].as_str(), Some("personal" | "corporate"))
            {
                return Err(invalid());
            }
        }
        Ok(())
    }

    fn check(&self, id: &identity::Identity) -> Result<()> {
        self.validate()?;
        if id.root_binding() != (self.root.as_path(), &self.root_identity)
            || !id.historical(&self.local_identity)
        {
            return Err(invalid());
        }
        id.revalidate()
    }

    pub(super) fn bind(&self) -> Result<identity::Identity> {
        let id = super::identity_at(&self.root)?;
        self.check(&id)?;
        Ok(id)
    }

    pub(crate) fn connection_id(&self) -> Option<&str> {
        match &self.authority {
            Authority::Local => None,
            Authority::Remote { account, .. } => account
                .connection
                .as_ref()
                .map(|v| v.connection_id.as_str()),
        }
    }

    fn public(&self) -> Result<Value> {
        Ok(
            json!({"context":self,"context_digest":self.digest()?,"online_verified":false,
            "observation_only":true,"selection_changes_harness_files":false}),
        )
    }
}

impl Plan {
    fn context(&self) -> &Context {
        match &self.change {
            Change::Create { context, .. } | Change::Select { context, .. } => context,
        }
    }
    fn kind(&self) -> &'static str {
        match self.change {
            Change::Create { .. } => "context.create",
            Change::Select { .. } => "context.select",
        }
    }
    fn validate(&self) -> Result<()> {
        self.context().validate()?;
        if self.schema_version != 1
            || ![
                PROFILE_SCHEMA,
                ENROLLMENT_RECOVERY_SCHEMA,
                CHECKOUT_LINK_SCHEMA,
            ]
            .contains(&self.registry_schema_after)
            || !passport::stable_id(&self.operation_id, "operation")
            || !passport::timestamp(&self.created_at)
            || self.expires_at != authoring::expiry(&self.created_at)?
        {
            return Err(invalid());
        }
        match &self.change {
            Change::Create {
                context,
                registry_schema_before,
            } => {
                if profile_schema_after(*registry_schema_before)? != self.registry_schema_after
                    || context.observed_at != self.created_at
                {
                    return Err(invalid());
                }
            }
            Change::Select {
                expected: Some(selection),
                ..
            } => validate_selection(selection)?,
            _ => {}
        }
        Ok(())
    }
    pub fn digest(&self) -> Result<String> {
        self.validate()?;
        digest::canonical(
            "ai-stp:plan:v1",
            &serde_json::to_value(self).map_err(|_| invalid())?,
        )
    }
}

fn validate_selection(value: &Selection) -> Result<()> {
    if !passport::stable_id(&value.revision, "operation")
        || !passport::stable_id(&value.context_id, "context")
    {
        return Err(invalid());
    }
    Ok(())
}

fn selection(connection: &Connection) -> Result<Option<Selection>> {
    let result = connection
        .query_row(
            "SELECT revision,context_id FROM native_context_selection WHERE singleton=1",
            [],
            |row| {
                Ok(Selection {
                    revision: row.get(0)?,
                    context_id: row.get(1)?,
                })
            },
        )
        .optional()
        .map_err(database)?;
    if let Some(value) = &result {
        validate_selection(value)?;
        let (kind,state,finished,detail):(String,String,Option<String>,String)=connection.query_row(
            "SELECT kind,state,finished_at,coalesce(detail,'') FROM operation WHERE operation_id=?",[&value.revision],
            |row|Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?))).map_err(database)?;
        if detail.len() as u64 > MAX_PLAN {
            return Err(invalid());
        }
        let plan: Plan =
            serde_json::from_value(canonical::parse(detail.as_bytes())?).map_err(|_| invalid())?;
        plan.validate()?;
        if kind != "context.select"
            || state != "verified"
            || finished
                .as_ref()
                .is_none_or(|at| !passport::timestamp(at) || at < &plan.created_at)
            || plan.operation_id != value.revision
            || !matches!(plan.change, Change::Select { .. })
            || plan.context().context_id != value.context_id
            || encode(&plan)? != detail
        {
            return Err(invalid());
        }
    }
    Ok(result)
}

fn record(connection: &Connection, id: &str) -> Result<Context> {
    if !passport::stable_id(id, "context") {
        return Err(invalid());
    }
    let (detail, connection_id): (String, Option<String>) = connection
        .query_row(
            "SELECT detail,connection_id FROM native_context WHERE context_id=?",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()
        .map_err(database)?
        .ok_or_else(invalid)?;
    if detail.len() as u64 > MAX_PLAN {
        return Err(invalid());
    }
    let plan: Plan =
        serde_json::from_value(canonical::parse(detail.as_bytes())?).map_err(|_| invalid())?;
    plan.validate()?;
    if !matches!(plan.change, Change::Create { .. })
        || plan.context().context_id != id
        || plan.context().connection_id() != connection_id.as_deref()
    {
        return Err(invalid());
    }
    let held: (String, String, Option<String>, String) = connection
        .query_row(
            "SELECT kind,state,finished_at,coalesce(detail,'') FROM operation WHERE operation_id=?",
            [&plan.operation_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .map_err(database)?;
    if held.0 != plan.kind()
        || held.1 != "verified"
        || held
            .2
            .as_ref()
            .is_none_or(|at| !passport::timestamp(at) || at < &plan.created_at)
        || held.3 != detail
        || encode(&plan)? != detail
    {
        return Err(invalid());
    }
    Ok(plan.context().clone())
}

pub fn organizations(root: &Path, connection: &str) -> Result<Value> {
    organizations_with_access(Access::for_connection(root, None, Some(connection), false)?)
}

pub fn legacy_organizations(root: &Path) -> Result<Value> {
    organizations_with_access(Access::for_account(root, None)?)
}

fn organizations_with_access(mut access: Access) -> Result<Value> {
    access.verify()?;
    let items = organizations_projection(&access.context_read("/v1/organizations", None)?)?;
    Ok(json!({"account":access.binding(),"organizations":items,"online_verified":true}))
}

pub(super) fn remote(access: &mut Access, organization: Option<&str>) -> Result<(Value, Value)> {
    if organization.is_some_and(|id| !passport::stable_id(id, "organization")) {
        return Err(invalid());
    }
    access.verify()?;
    let observation = active_projection(&access.context_read("/v1/context", organization)?)?;
    let now = format!("{:.3}", jiff::Timestamp::now());
    let projection = &observation["capabilities"];
    if projection["expires_at"]
        .as_str()
        .is_none_or(|at| at <= now.as_str())
        || ["issued_at", "generated_at"]
            .iter()
            .any(|key| projection[*key].as_str().is_none_or(|at| at > now.as_str()))
    {
        return Err(Failure::precondition(
            "the server returned a stale or future context observation",
        ));
    }
    if organization.is_some_and(|id| observation["organization_id"] != id) {
        return Err(invalid());
    }
    let items = organizations_projection(&access.context_read("/v1/organizations", None)?)?;
    let matches = items["items"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .filter(|item| item["organization_id"] == observation["organization_id"])
        .collect::<Vec<_>>();
    if matches.len() != 1 || matches[0]["kind"] != observation["mode"] {
        return Err(invalid());
    }
    Ok((matches[0].clone(), observation))
}

pub fn create_plan(
    root: &Path,
    label: &str,
    connection: Option<&str>,
    organization: Option<&str>,
    at: &str,
) -> Result<Plan> {
    create_with_source(
        root,
        label,
        connection.map_or(SessionSource::Local, SessionSource::Connection),
        organization,
        at,
    )
}

pub fn create_legacy_plan(
    root: &Path,
    label: &str,
    organization: Option<&str>,
    at: &str,
) -> Result<Plan> {
    create_with_source(root, label, SessionSource::Legacy, organization, at)
}

fn create_with_source(
    root: &Path,
    label: &str,
    source: SessionSource<'_>,
    organization: Option<&str>,
    at: &str,
) -> Result<Plan> {
    if matches!(source, SessionSource::Local) && organization.is_some() {
        return Err(Failure::input(
            "a remote organization requires an explicit retained connection",
        ));
    }
    let id = super::identity_at(root)?;
    let authority = if !matches!(source, SessionSource::Local) {
        let mut access = match source {
            SessionSource::Legacy => Access::for_account(root, None)?,
            SessionSource::Connection(connection) => {
                Access::for_connection(root, None, Some(connection), false)?
            }
            SessionSource::Local => return Err(invalid()),
        };
        let (organization, observation) = remote(&mut access, organization)?;
        Authority::Remote {
            account: Box::new(access.binding().clone()),
            organization,
            observation,
        }
    } else {
        Authority::Local
    };
    let (root, physical) = id.root_binding();
    let context = Context {
        schema_version: 1,
        context_id: format!("context_{}", ulid::Ulid::generate()),
        label: label.into(),
        root: root.to_owned(),
        root_identity: physical.clone(),
        local_identity: id.context(),
        observed_at: at.into(),
        authority,
    };
    let store = Store::planning_at(id.root_directory())?;
    let version = store
        .connection
        .query_row("PRAGMA user_version", [], |row| row.get(0))
        .map_err(database)?;
    let plan = Plan {
        schema_version: 1,
        registry_schema_after: profile_schema_after(version)?,
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        change: Change::Create {
            context: Box::new(context),
            registry_schema_before: version,
        },
    };
    plan.validate()?;
    id.revalidate()?;
    Ok(plan)
}

pub fn select_plan(root: &Path, context: &str, at: &str) -> Result<Plan> {
    let id = super::identity_at(root)?;
    let store = Store::planning_at(id.root_directory())?;
    if !store.profiles_enabled()? {
        return Err(invalid());
    }
    let context = record(&store.connection, context)?;
    context.check(&id)?;
    let plan = Plan {
        schema_version: 1,
        registry_schema_after: store.version()?,
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at: authoring::expiry(at)?,
        change: Change::Select {
            context: Box::new(context),
            expected: selection(&store.connection)?,
        },
    };
    plan.validate()?;
    id.revalidate()?;
    Ok(plan)
}

pub fn read_plan(path: &Path) -> Result<Plan> {
    let value = canonical::parse(&files::read(path, MAX_PLAN)?)?;
    let plan: Plan = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    if digest::canonical("ai-stp:plan:v1", &value)? != plan.digest()? {
        return Err(invalid());
    }
    Ok(plan)
}

fn replay(connection: &Connection, plan: &Plan, detail: &str) -> Result<bool> {
    let held: Option<(String, String, Option<String>, String)> = connection
        .query_row(
            "SELECT kind,state,finished_at,coalesce(detail,'') FROM operation WHERE operation_id=?",
            [&plan.operation_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .optional()
        .map_err(database)?;
    if let Some(held) = held {
        if held.0 != plan.kind()
            || held.1 != "verified"
            || held.3 != detail
            || held
                .2
                .as_ref()
                .is_none_or(|at| !passport::timestamp(at) || at < &plan.created_at)
        {
            return Err(invalid());
        }
        return Ok(true);
    }
    Ok(false)
}

pub fn apply(plan: &Plan, expected: &str, at: &str) -> Result<Value> {
    plan.validate()?;
    if plan.digest()? != expected || !passport::timestamp(at) || at < plan.created_at.as_str() {
        return Err(invalid());
    }
    let id = plan.context().bind()?;
    let detail = encode(plan)?;
    let context_digest = plan.context().digest()?;
    let receipt = || {
        json!({"schema_version":1,"operation_id":plan.operation_id,"action":plan.kind(),
        "context_id":plan.context().context_id,"context_digest":context_digest,
        "plan_digest":expected,"harness_files_changed":false})
    };
    {
        let store = Store::planning_at(id.root_directory())?;
        if replay(&store.connection, plan, &detail)? {
            if !store.profiles_enabled()?
                || record(&store.connection, &plan.context().context_id)? != *plan.context()
            {
                return Err(invalid());
            }
            return Ok(receipt());
        }
    }
    if at >= plan.expires_at.as_str() {
        return Err(Failure::precondition(
            "the context plan expired; review a new plan",
        ));
    }
    // Never hold the registry lock while acquiring a session journal or vault.
    let _access = if let Change::Create { context, .. } = &plan.change {
        if let Authority::Remote {
            account,
            organization,
            observation,
        } = &context.authority
        {
            let mut access = Access::for_binding(&context.root, account, false)?;
            let (current, projection) =
                remote(&mut access, organization["organization_id"].as_str())?;
            if current != *organization
                || projection["capabilities"]["authorization_revision"]
                    != observation["capabilities"]["authorization_revision"]
            {
                return Err(Failure::precondition(
                    "organization membership or policy changed; review a new context plan",
                ));
            }
            Some(access)
        } else {
            None
        }
    } else {
        None
    };
    let mut store = Store::open_at(id.root_directory(), true)?;
    if profile_schema_after(store.version()?)? != plan.registry_schema_after {
        return Err(Failure::precondition(
            "the registry format changed; review a new context plan",
        ));
    }
    if let Change::Create {
        registry_schema_before,
        ..
    } = &plan.change
    {
        let version: u32 = store
            .connection
            .query_row("PRAGMA user_version", [], |row| row.get(0))
            .map_err(database)?;
        if version != *registry_schema_before && !replay(&store.connection, plan, &detail)? {
            return Err(Failure::precondition(
                "the registry format changed; review a new context plan",
            ));
        }
    }
    store.profile_transaction(|tx| {
        if replay(tx,plan,&detail)? {return Ok(());}
        match &plan.change {
            Change::Create {context,registry_schema_before}=>{
                // profile_transaction performs the explicit format upgrade in this commit.
                if profile_schema_after(*registry_schema_before)? != plan.registry_schema_after {return Err(invalid());}
                let count:i64=tx.query_row("SELECT count(*) FROM native_context",[],|row|row.get(0)).map_err(database)?;
                if count>=LIMIT as i64 {return Err(Failure::precondition("the retained context limit has been reached"));}
                tx.execute("INSERT INTO native_context(context_id,connection_id,detail) VALUES (?1,?2,?3)",
                    params![context.context_id,context.connection_id(),detail]).map_err(database)?;
            }
            Change::Select {context,expected}=>{
                if record(tx,&context.context_id)?!=**context || selection(tx)?!=*expected {return Err(invalid());}
                tx.execute("INSERT INTO native_context_selection(singleton,revision,context_id) VALUES (1,?1,?2) ON CONFLICT(singleton) DO UPDATE SET revision=excluded.revision,context_id=excluded.context_id",
                    params![plan.operation_id,context.context_id]).map_err(database)?;
            }
        }
        tx.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?1,?2,'verified',?3,?3,?4)",
            params![plan.operation_id,plan.kind(),at,detail]).map_err(database)?;
        Ok(())
    })?;
    id.revalidate()?;
    Ok(receipt())
}

pub fn list(root: &Path) -> Result<Value> {
    let id = super::identity_at(root)?;
    let store = Store::planning_at(id.root_directory())?;
    let mut contexts = Vec::new();
    let selected = if store.profiles_enabled()? {
        let mut statement = store
            .connection
            .prepare("SELECT context_id FROM native_context ORDER BY context_id LIMIT 257")
            .map_err(database)?;
        let ids = statement
            .query_map([], |row| row.get::<_, String>(0))
            .map_err(database)?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(database)?;
        if ids.len() > LIMIT {
            return Err(invalid());
        }
        for key in ids {
            let held = record(&store.connection, &key)?;
            held.check(&id)?;
            contexts.push(held.public()?);
        }
        let selected = selection(&store.connection)?;
        if let Some(value) = &selected {
            record(&store.connection, &value.context_id)?.check(&id)?;
        }
        selected
    } else {
        None
    };
    id.revalidate()?;
    Ok(
        json!({"schema_version":1,"contexts":contexts,"selected":selected,"online_verified":false,
        "selection_changes_harness_files":false}),
    )
}

pub fn show(root: &Path, context: &str, refresh: bool) -> Result<Value> {
    let id = super::identity_at(root)?;
    let context = {
        let store = Store::planning_at(id.root_directory())?;
        if !store.profiles_enabled()? {
            return Err(invalid());
        }
        record(&store.connection, context)?
    };
    context.check(&id)?;
    let mut result = context.public()?;
    if refresh
        && let Authority::Remote {
            account,
            organization,
            ..
        } = &context.authority
    {
        let mut access = Access::for_binding(root, account, false)?;
        let (current, observation) = remote(&mut access, organization["organization_id"].as_str())?;
        result["current_organization"] = current;
        result["current_observation"] = observation;
        result["online_verified"] = json!(true);
    }
    id.revalidate()?;
    Ok(result)
}

/// Resolve a new command's preference once; retained commands carry their own
/// context. Loading a view never creates membership or installation authority.
pub(super) fn resolve(root: &Path, context: Option<&str>) -> Result<Context> {
    let id = super::identity_at(root)?;
    let held = {
        let store = Store::planning_at(id.root_directory())?;
        if !store.profiles_enabled()? {
            return Err(Failure::precondition(
                "create an explicit native context first",
            ));
        }
        let context = match context {
            Some(context) => context.to_owned(),
            None => selection(&store.connection)?
                .map(|value| value.context_id)
                .ok_or_else(|| {
                    Failure::precondition("select a context or supply its exact identifier")
                })?,
        };
        record(&store.connection, &context)?
    };
    held.check(&id)?;
    Ok(held)
}
