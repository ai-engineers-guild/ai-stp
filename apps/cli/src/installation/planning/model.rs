use super::{invalid, value};
use crate::{
    account::{
        access::Binding,
        contexts::{Authority, Context},
    },
    bundle::reader::Binding as Package,
    digest,
    error::Result,
    files::{self, physical::DirectoryIdentity},
    passport,
    projection::Scope,
    selection::eligibility::{Evidence, Target},
    wire,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    path::PathBuf,
};

const LIMIT: usize = 8 * 1024 * 1024;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Operation {
    Install,
    Replace,
    Remove,
}

/// Caller-established source/eligibility observations, never remote authority.
pub struct Request {
    pub operation: Operation,
    pub setup: Value,
    pub target: Target,
    pub evidence: BTreeMap<String, Evidence>,
    pub roots: BTreeMap<Scope, PathBuf>,
    pub placements: BTreeMap<String, Scope>,
    pub corporate_binding: Option<String>,
}

pub struct Planned {
    pub plan: Plan,
    pub packages: BTreeMap<Scope, Vec<u8>>,
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Directory {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub path: PathBuf,
    pub physical: DirectoryIdentity,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Corporate {
    pub binding_operation_id: String,
    pub binding_digest: String,
    pub original_context: Context,
    pub original_account: Binding,
    pub organization_id: String,
    pub local_project_id: String,
    pub remote_project_id: String,
    pub link_id: String,
    pub link_digest: String,
    pub authorization_digest: String,
    pub assignment_digest: String,
    pub assignment_id: Option<String>,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub checkout_root: PathBuf,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Contribution {
    pub parser_id: String,
    pub ownership_key: String,
    pub host_digest: Option<String>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct File {
    pub before: crate::installation::forward::Observation,
    pub after_digest: Option<String>,
    pub after_bytes: Option<usize>,
    pub after_mode: Option<u32>,
    pub owner: String,
    pub contribution: Option<Contribution>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Root {
    pub directory: Directory,
    pub profile_id: String,
    pub profile_digest: String,
    pub package: Package,
    pub files: BTreeMap<String, File>,
}

#[derive(Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Coordinates {
    pub(super) stable_id: String,
    pub(super) version: String,
    pub(super) passport_digest: String,
}

pub(super) fn coordinates(graph: &Value) -> Result<Vec<Coordinates>> {
    if graph["resolved"] != true {
        return Err(invalid());
    }
    graph["nodes"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(|node| {
            serde_json::from_value(serde_json::json!({"stable_id":node["stable_id"],
            "version":node["version"],"passport_digest":node["passport_digest"]}))
            .map_err(|_| invalid())
        })
        .collect()
}

/// Closed native observation format. Historical external plans cannot parse as
/// this format; parsing never opens a target or changes the selected context.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub(super) schema_version: u32,
    pub(super) format: String,
    pub(super) operation_id: String,
    pub(super) operation: Operation,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(super) source_operation: Option<String>,
    pub(super) created_at: String,
    pub(super) expires_at: String,
    pub(super) state: Directory,
    pub(super) context: Context,
    pub(super) corporate: Option<Corporate>,
    pub(super) engine_digest: String,
    pub(super) target: Target,
    pub(super) setup: Value,
    pub(super) graph_digest: String,
    pub(super) graph_nodes: Vec<Coordinates>,
    pub(super) evidence: BTreeMap<String, Evidence>,
    pub(super) scope_bindings: BTreeMap<String, Scope>,
    pub(super) roots: BTreeMap<Scope, Root>,
}

fn hash(value: &str) -> bool {
    crate::provider::plan::hash(value)
}
fn text(value: &str) -> bool {
    !value.is_empty() && value.len() <= 256 && !value.chars().any(char::is_control)
}

impl Plan {
    pub fn value(&self) -> Result<Value> {
        self.validate()?;
        value(self)
    }
    pub fn digest(&self) -> Result<String> {
        self.validate()?;
        digest::canonical("ai-stp:installation-operation:v1", &value(self)?)
    }
    pub fn parse(bytes: &[u8], expected: &str) -> Result<Self> {
        if bytes.len() > LIMIT || !hash(expected) {
            return Err(invalid());
        }
        let original = wire::parse(bytes)?;
        if digest::canonical("ai-stp:installation-operation:v1", &original)? != expected {
            return Err(invalid());
        }
        let plan: Self = serde_json::from_value(original.clone()).map_err(|_| invalid())?;
        plan.validate()?;
        // Do not lose omitted optional fields or encoded filesystem spellings.
        if value(&plan)? != original {
            return Err(invalid());
        }
        Ok(plan)
    }
    pub(super) fn validate(&self) -> Result<()> {
        self.context.digest()?;
        self.target.validate()?;
        if (self.operation == Operation::Remove) != self.source_operation.is_some()
            || self
                .source_operation
                .as_ref()
                .is_some_and(|id| !passport::stable_id(id, "operation") || id == &self.operation_id)
        {
            return Err(invalid());
        }
        self.state.physical.validate()?;
        let kind_matches = |id: &DirectoryIdentity| {
            matches!(
                (self.target.os.as_str(), id),
                ("linux" | "macos", DirectoryIdentity::Unix { .. })
                    | ("windows", DirectoryIdentity::Windows { .. })
            )
        };
        if !kind_matches(&self.state.physical) {
            return Err(invalid());
        }
        if self.schema_version != 1
            || self.format != "ai-stp-native-installation/1"
            || !passport::stable_id(&self.operation_id, "operation")
            || !passport::timestamp(&self.created_at)
            || self.expires_at != crate::authoring::expiry(&self.created_at)?
            || self.state.path != self.context.root
            || self.target.owner_id != self.context.local_identity.account_id
            || !hash(&self.engine_digest)
            || !hash(&self.graph_digest)
            || !self.roots.contains_key(&self.target.scope)
            || !(1..=3).contains(&self.roots.len())
            || self.graph_nodes.is_empty()
            || self.graph_nodes.len() > 512
            || self
                .setup
                .as_object()
                .is_none_or(|fields| fields.len() != 3)
            || !passport::stable_id(self.setup["stable_id"].as_str().unwrap_or(""), "setup")
        {
            return Err(invalid());
        }
        let setup: Coordinates =
            serde_json::from_value(self.setup.clone()).map_err(|_| invalid())?;
        let mut ids = BTreeSet::new();
        for node in &self.graph_nodes {
            if !(passport::stable_id(&node.stable_id, "component")
                || passport::stable_id(&node.stable_id, "setup"))
                || !passport::version_number(&node.version)
                || !hash(&node.passport_digest)
                || !ids.insert(node.stable_id.as_str())
            {
                return Err(invalid());
            }
        }
        if self.evidence.len() != self.graph_nodes.len()
            || self.graph_nodes.iter().any(|node| {
                self.evidence
                    .get(&node.stable_id)
                    .is_none_or(|e| e.passport_digest != node.passport_digest)
            })
        {
            return Err(invalid());
        }
        if !self.graph_nodes.contains(&setup)
            || self.scope_bindings.iter().any(|(id, scope)| {
                !passport::stable_id(id, "component")
                    || !ids.contains(id.as_str())
                    || !self.roots.contains_key(scope)
            })
            || self.graph_nodes.iter().any(|node| {
                passport::stable_id(&node.stable_id, "component")
                    && !self.scope_bindings.contains_key(&node.stable_id)
            })
        {
            return Err(invalid());
        }
        let (mut count, mut bytes, mut archives, mut before_bytes) =
            (0usize, 0usize, 0usize, 0usize);
        let mut physical = BTreeSet::new();
        for (scope, root) in &self.roots {
            root.directory.physical.validate()?;
            if !kind_matches(&root.directory.physical)
                || !root.directory.path.is_absolute()
                || !physical.insert(crate::canonical::bytes(&value(&root.directory.physical)?)?)
                || !text(&root.profile_id)
                || !hash(&root.profile_digest)
                || root.package.bundle_format != "ai-stp-bundle/2"
                || !hash(&root.package.bundle_digest)
                || !hash(&root.package.artifact_digest)
                || root.package.bundle_size == 0
                || root.files.is_empty()
            {
                return Err(invalid());
            }
            archives = archives
                .checked_add(root.package.bundle_size)
                .ok_or_else(invalid)?;
            count = count.checked_add(root.files.len()).ok_or_else(invalid)?;
            for (path, file) in &root.files {
                before_bytes = before_bytes
                    .checked_add(file.before.byte_length())
                    .ok_or_else(invalid)?;
                if !crate::archive::safe_path(path)
                    || match (
                        self.operation,
                        file.after_digest.as_deref(),
                        file.after_bytes,
                        file.after_mode,
                    ) {
                        (Operation::Remove, None, None, None) => false,
                        (
                            Operation::Install | Operation::Replace,
                            Some(digest),
                            Some(bytes),
                            Some(mode),
                        ) => {
                            !hash(digest)
                                || bytes > 4 * 1024 * 1024
                                || mode & !0o777 != 0
                                || mode & 0o400 == 0
                                || (self.target.os == "windows" && mode != 0o600)
                        }
                        _ => true,
                    }
                    || self.scope_bindings.get(&file.owner) != Some(scope)
                {
                    return Err(invalid());
                }
                if let Some(claim) = &file.contribution
                    && (!matches!(claim.parser_id.as_str(), "toml/1" | "json/1")
                        || !text(&claim.ownership_key)
                        || claim.host_digest.as_deref().is_some_and(|v| !hash(v)))
                {
                    return Err(invalid());
                }
                bytes = bytes
                    .checked_add(file.after_bytes.unwrap_or(0))
                    .ok_or_else(invalid)?;
            }
        }
        if count > 2000
            || bytes > 64 * 1024 * 1024
            || archives > 64 * 1024 * 1024
            || before_bytes > 64 * 1024 * 1024
        {
            return Err(invalid());
        }
        match (&self.context.authority, &self.corporate) {
            (
                Authority::Remote {
                    account,
                    organization,
                    ..
                },
                Some(company),
            ) if organization["kind"] == "corporate" => {
                company.original_context.digest()?;
                company.original_account.validate()?;
                if !passport::stable_id(&company.binding_operation_id, "operation")
                    || !hash(&company.binding_digest)
                    || !hash(&company.link_digest)
                    || !hash(&company.authorization_digest)
                    || !hash(&company.assignment_digest)
                    || company.assignment_id.as_deref().is_some_and(|id| !text(id))
                    || organization["organization_id"] != company.organization_id
                    || account.origin != company.original_account.origin
                    || account.account_id != company.original_account.account_id
                    || !passport::stable_id(&company.local_project_id, "project")
                    || !text(&company.remote_project_id)
                    || !text(&company.link_id)
                    || self
                        .roots
                        .get(&Scope::Project)
                        .is_none_or(|root| root.directory.path != company.checkout_root)
                {
                    return Err(invalid());
                }
            }
            (Authority::Local, None) => (),
            (Authority::Remote { organization, .. }, None)
                if organization["kind"] == "personal" => {}
            _ => return Err(invalid()),
        }
        if crate::canonical::bytes(&value(self)?)?.len() > LIMIT {
            return Err(invalid());
        }
        Ok(())
    }
}
