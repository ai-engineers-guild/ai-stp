//! Exact setup installation calls the compiler and configuration coordinator in-process.

use super::{
    journal::{self, Row},
    service,
};
use crate::{
    authoring::{Identity, runtime::Owner, setups::Source},
    canonical, digest,
    error::{Failure, Result},
    files, harnesses, passport,
    projection::Scope,
    provider::{configuration::set, managed, runtime},
    selection::runtime::{access, bundles},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::BTreeMap, path::Path};

static SCHEMA: crate::wire::Schema = crate::wire::Schema::new(include_str!("install.schema.json"));

fn invalid() -> Failure {
    Failure::precondition("the exact native install task input or checkpoint changed")
}
fn encode(value: &impl Serialize) -> Result<Value> {
    serde_json::to_value(value).map_err(|_| invalid())
}
fn source_digest(source: &Source) -> bool {
    passport::stable_id(&source.stable_id, "setup")
        && passport::version_number(&source.version)
        && source
            .passport_digest
            .strip_prefix("sha256:")
            .is_some_and(|value| {
                value.len() == 64
                    && value
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            })
}
fn absolute(path: &str) -> bool {
    !path.contains('\0') && path.len() <= 4096 && Path::new(path).is_absolute()
}
fn version() -> u32 {
    1
}
fn install() -> String {
    "install".into()
}
fn inactive() -> String {
    "inactive".into()
}
fn planning() -> String {
    "planning".into()
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Input {
    #[serde(default = "version")]
    schema_version: u32,
    pub harness_id: String,
    pub source: Option<Source>,
    pub targets: BTreeMap<Scope, String>,
    #[serde(default = "install")]
    pub operation: String,
    #[serde(default = "inactive")]
    pub activation: String,
    pub project_root: Option<String>,
    #[serde(default)]
    pub placements: BTreeMap<String, Scope>,
    pub provider_version: Option<String>,
    pub harness_executable: Option<String>,
    #[serde(default)]
    pub access: access::Request,
}
impl Input {
    pub fn parse(value: Value) -> Result<Self> {
        if canonical::bytes(&value)?.len() > 16 * 1024 {
            return Err(invalid());
        }
        SCHEMA
            .validate(&value)
            .map_err(|_| Failure::input("input does not match the native install task schema"))?;
        let input: Self = serde_json::from_value(value).map_err(|_| {
            Failure::input("install requires a closed exact setup request and explicit roots")
        })?;
        input.validate()?;
        Ok(input)
    }
    pub fn validate(&self) -> Result<()> {
        harnesses::definition(&self.harness_id)?;
        if self.schema_version != 1
            || self.harness_id == "undefined"
            || !matches!(self.activation.as_str(), "inactive" | "handoff")
            || !(1..=3).contains(&self.targets.len())
            || self.targets.values().any(|path| !absolute(path))
            || !matches!(
                (self.operation.as_str(), self.source.is_some()),
                ("install" | "replace", true) | ("remove", false)
            )
            || self
                .source
                .as_ref()
                .is_some_and(|source| !source_digest(source))
            || self
                .harness_executable
                .as_ref()
                .is_some_and(|path| !absolute(path))
            || self
                .project_root
                .as_ref()
                .is_some_and(|path| !absolute(path))
            || self.placements.len() > 512
            || self.placements.iter().any(|(id, scope)| {
                !passport::stable_id(id, "component") || !self.targets.contains_key(scope)
            })
            || self.operation == "remove"
                && (!self.placements.is_empty() || !self.access.is_empty())
            || canonical::bytes(&encode(self)?)?.len() > 16 * 1024
        {
            return Err(invalid());
        }
        managed::version(self.provider_version.as_deref())?;
        self.access.validate()
    }
    pub fn scope(&self) -> &str {
        if self.targets.len() == 1 {
            self.targets
                .keys()
                .next()
                .map_or("", |scope| scope.as_str())
        } else {
            "multiple"
        }
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Reviewed {
    plan: Value,
    plan_digest: String,
}
impl Reviewed {
    fn report(value: Value) -> Result<Self> {
        Ok(Self {
            plan: value.get("plan").cloned().ok_or_else(invalid)?,
            plan_digest: value["plan_digest"].as_str().ok_or_else(invalid)?.into(),
        })
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Checkpoint {
    schema_version: u32,
    action: String,
    identity: Identity,
    #[serde(
        serialize_with = "files::serialize_location",
        deserialize_with = "files::deserialize_location"
    )]
    state_parent: String,
    input_digest: String,
    #[serde(
        serialize_with = "files::serialize_location",
        deserialize_with = "files::deserialize_location"
    )]
    output: String,
    provider_version: String,
    bundle: Option<Reviewed>,
    configuration: Option<Reviewed>,
    #[serde(default = "planning")]
    phase: String,
}
impl Checkpoint {
    pub fn digest(&self) -> Result<String> {
        digest::canonical("ai-stp:plan:v1", &encode(self)?)
    }
    pub fn children(&self) -> Vec<String> {
        self.configuration
            .iter()
            .filter_map(|held| held.plan["operation_id"].as_str().map(str::to_owned))
            .collect()
    }
    pub fn validate(&self, input: &Input, identity: &Identity) -> Result<()> {
        if self.schema_version != 1
            || self.action != "task.install"
            || &self.identity != identity
            || self.input_digest
                != digest::bytes("ai-stp:plan:v1", journal::encode(input)?.as_bytes())?
            || !absolute(&self.state_parent)
            || !absolute(&self.output)
            || input
                .provider_version
                .as_ref()
                .is_some_and(|version| version != &self.provider_version)
            || input.operation == "remove" && self.bundle.is_some()
            || !matches!(
                self.phase.as_str(),
                "planning" | "awaiting_exit" | "awaiting_restart" | "verified" | "cancelled"
            )
            || matches!(self.phase.as_str(), "awaiting_exit" | "awaiting_restart")
                && input.activation != "handoff"
        {
            return Err(invalid());
        }
        managed::sequence(&self.provider_version)?;
        if let Some(bundle) = &self.bundle
            && (bundle.plan_digest != digest::canonical("ai-stp:plan:v1", &bundle.plan)?
                || bundle.plan["action"] != "selection.scoped_bundles"
                || bundle.plan["identity"] != encode(identity)?
                || bundle.plan["inputs"]["source"] != encode(&input.source)?
                || bundle.plan["inputs"]["selector"]["harness_id"] != input.harness_id
                || bundle.plan["inputs"]["selector"]["provider_version"] != self.provider_version)
        {
            return Err(invalid());
        }
        if let Some(held) = &self.configuration {
            let plan = set::Plan::parse(
                &serde_json::to_vec(&held.plan).map_err(|_| invalid())?,
                &held.plan_digest,
            )?;
            let first = plan.first()?;
            if first.harness_id != input.harness_id
                || first.state_parent != self.state_parent
                || first.provider_version != self.provider_version
                || first.operation()? != input.operation
                || plan.children.len() != input.targets.len()
                || input
                    .source
                    .as_ref()
                    .is_some_and(|source| first.setup != encode(source).unwrap_or(Value::Null))
                || input.operation != "remove" && self.bundle.is_none()
                || plan.program.executable != input.harness_executable
                || self.bundle.as_ref().is_some_and(|bundle| {
                    bundle.plan["program_observation_digest"] != plan.program.observation_digest
                })
            {
                return Err(invalid());
            }
            for child in &plan.children {
                let child = child.parsed()?;
                if input.targets.get(&child.target_scope) != Some(&child.target_path) {
                    return Err(invalid());
                }
            }
        }
        Ok(())
    }
    pub fn outcome(&self) -> Result<Value> {
        let held = self.configuration.as_ref().ok_or_else(invalid)?;
        let plan = set::Plan::parse(
            &serde_json::to_vec(&held.plan).map_err(|_| invalid())?,
            &held.plan_digest,
        )?;
        let first = plan.first()?;
        Ok(
            json!({"kind":"install","harness_id":first.harness_id,"setup_id":first.setup["stable_id"].as_str().unwrap_or(""),
            "setup_version":first.setup["version"].as_str().unwrap_or(""),"operation_id":plan.operation_id,
            "state":"verified","verified":true,"operation":first.operation()?,"root_count":plan.children.len()}),
        )
    }
    pub fn handoff(&self) -> Option<Value> {
        let action = match self.phase.as_str() {
            "awaiting_exit" => {
                "Finish sessions using the staged roots, then continue from an external shell before starting the harness."
            }
            "awaiting_restart" => {
                "Start the user-installed harness and continue this task from that new session to confirm activation."
            }
            _ => return None,
        };
        Some(json!({"state":self.phase,"required_action":action}))
    }
}

fn save(owner: &Owner, row: &mut Row, checkpoint: Checkpoint) -> Result<()> {
    row.payload.plan = Some(service::Plan::Install(checkpoint));
    row.payload.plan_digest = Some(row.payload.plan.as_ref().ok_or_else(invalid)?.digest()?);
    super::save(&mut owner.open(false)?, row, "running")
}

pub(super) fn drain(
    parent: &Path,
    output: &Path,
    owner: &Owner,
    mut row: Row,
    cancel: bool,
) -> Result<Value> {
    let service::Input::Install(input) = row.payload.input.clone() else {
        return Err(invalid());
    };
    let mut checkpoint = match &row.payload.plan {
        Some(service::Plan::Install(plan)) => plan.clone(),
        None => Checkpoint {
            schema_version: 1,
            action: "task.install".into(),
            identity: row.payload.identity.clone(),
            state_parent: files::location(parent)?,
            input_digest: digest::bytes("ai-stp:plan:v1", journal::encode(&input)?.as_bytes())?,
            output: output.to_str().ok_or_else(invalid)?.into(),
            provider_version: managed::version(input.provider_version.as_deref())?.into(),
            bundle: None,
            configuration: None,
            phase: "planning".into(),
        },
        _ => return Err(invalid()),
    };
    checkpoint.validate(&input, owner)?;
    if checkpoint.state_parent != files::location(parent)?
        || Path::new(&checkpoint.output) != output
    {
        return Err(invalid());
    }
    if cancel && checkpoint.configuration.is_none() {
        super::save(&mut owner.open(false)?, &mut row, "cancelled")?;
        return row.view();
    }
    if row.payload.plan.is_none() {
        save(owner, &mut row, checkpoint.clone())?;
    }
    if checkpoint.configuration.is_none() {
        if input.operation != "remove" {
            if checkpoint.bundle.is_none() {
                let request = json!({"source":input.source,"targets":input.targets,"placements":input.placements,
                    "output":checkpoint.output,"provider_version":checkpoint.provider_version,
                    "harness_executable":input.harness_executable,"access":input.access});
                checkpoint.bundle = Some(Reviewed::report(bundles::scoped::plan_value(
                    parent, request,
                )?)?);
                checkpoint.validate(&input, owner)?;
                save(owner, &mut row, checkpoint.clone())?;
            }
            let held = checkpoint.bundle.as_ref().ok_or_else(invalid)?;
            bundles::scoped::apply_value(held.plan.clone(), &held.plan_digest)?;
        }
        let targets = input
            .targets
            .iter()
            .map(|(scope, path)| {
                let mut target = json!({"scope":scope,"path":path});
                if input.operation != "remove" {
                    target["bundle"] = json!(output.join(format!("{}.zip", scope.as_str())));
                }
                target
            })
            .collect::<Vec<_>>();
        let request = json!({"harness_id":input.harness_id,"provider_version":checkpoint.provider_version,
            "operation":input.operation,"targets":targets,"project_root":input.project_root,"harness_executable":input.harness_executable});
        checkpoint.configuration = Some(Reviewed::report(runtime::configuration_set_plan(
            parent,
            &serde_json::to_vec(&request).map_err(|_| invalid())?,
        )?)?);
        checkpoint.validate(&input, owner)?;
        save(owner, &mut row, checkpoint.clone())?;
    }
    // No registry connection survives into the provider service. Its durable
    // journal is authoritative if the process dies before this task checkpoint.
    let held = checkpoint.configuration.as_ref().ok_or_else(invalid)?;
    let result = runtime::configuration_set(
        parent,
        &serde_json::to_vec(&held.plan).map_err(|_| invalid())?,
        &held.plan_digest,
        if cancel {
            "cancel"
        } else if input.activation == "handoff" {
            "continue"
        } else {
            "apply"
        },
    )?;
    checkpoint.phase = result["state"].as_str().ok_or_else(invalid)?.into();
    save(owner, &mut row, checkpoint.clone())?;
    let state = match result["state"].as_str() {
        Some("verified") => {
            row.outcome = Some(checkpoint.outcome()?);
            "completed"
        }
        Some("cancelled") => "cancelled",
        Some("awaiting_exit" | "awaiting_restart") => "blocked",
        _ => return Err(invalid()),
    };
    super::save(&mut owner.open(false)?, &mut row, state)?;
    row.view()
}

pub(super) fn schema() -> Result<Value> {
    serde_json::from_str(include_str!("install.schema.json")).map_err(|_| invalid())
}

pub(super) fn descriptor() -> Result<Value> {
    let schema = schema()?;
    let required = schema["required"].as_array().ok_or_else(invalid)?;
    let fields = schema["properties"]
        .as_object()
        .ok_or_else(invalid)?
        .iter()
        .filter(|(name, _)| *name != "schema_version")
        .map(|(name, field)| {
            json!({"name":name,"required":required.iter().any(|value|value==name),
            "value_type":"string","choices":field.get("enum").cloned().unwrap_or_else(||json!([])),
            "json_schema":field})
        })
        .collect::<Vec<_>>();
    Ok(
        json!({"name":"install","when":"Compile and install one exact setup across explicit roots, or replace/remove its configuration, with durable recovery.",
        "input_schema":"cli-task-input-native-install","input_fields":fields}),
    )
}
