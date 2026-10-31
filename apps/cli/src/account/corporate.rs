//! Authenticated corporate observations, never durable installation grants.

mod contract;
#[cfg(test)]
mod tests;

use super::{
    access::Access,
    contexts::{self, Authority},
};
use crate::{
    canonical, digest,
    error::{Failure, Result},
    harnesses, passport,
};
use contract::Contract;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::BTreeSet, path::Path};
use url::Url;

macro_rules! contract {
    ($name:ident, $path:literal) => {
        static $name: Contract =
            Contract::new(include_str!(concat!(env!("CARGO_MANIFEST_DIR"), $path)));
    };
}
contract!(
    TEAMS,
    "/resources/schemas/v1/corporate-team-list.schema.json"
);
contract!(
    PROJECTS,
    "/resources/schemas/v1/corporate-project-list.schema.json"
);
contract!(
    PROJECT,
    "/resources/schemas/v1/corporate-project-view.schema.json"
);
contract!(
    LINK_TARGET,
    "/resources/schemas/v1/project-link-target-response.schema.json"
);
contract!(
    LINK_OUTCOME,
    "/resources/schemas/v1/project-link-plan-outcome.schema.json"
);
contract!(
    LINK_CURRENT,
    "/resources/schemas/v1/project-link-response.schema.json"
);
contract!(
    UNLINK_OUTCOME,
    "/resources/schemas/v1/project-unlink-plan-outcome.schema.json"
);
contract!(
    UNLINK_PLAN,
    "/resources/schemas/v1/project-unlink-plan-response.schema.json"
);
contract!(
    TECHNOLOGIES,
    "/resources/schemas/v1/technology-list.schema.json"
);
contract!(
    MAPPINGS,
    "/resources/schemas/v1/technology-mapping-list.schema.json"
);
contract!(
    MAPPING,
    "/resources/schemas/v1/technology-mapping-view.schema.json"
);
contract!(
    COMPONENTS,
    "/resources/schemas/v1/catalog-component-list.schema.json"
);
contract!(
    SETUPS,
    "/resources/schemas/v1/catalog-setup-list.schema.json"
);
contract!(
    ASSIGNMENTS,
    "/resources/schemas/v1/corporate-assignment-plan.schema.json"
);
contract!(
    HEARTBEAT_POLICY,
    "/resources/schemas/v1/installation-heartbeat-policy.schema.json"
);
contract!(
    HEARTBEAT_STATUS,
    "/resources/schemas/v1/installation-heartbeat-status.schema.json"
);

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ObjectKind {
    Component,
    Setup,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
pub enum Request {
    Teams,
    HeartbeatPolicy,
    HeartbeatStatus,
    Projects {
        membership_only: bool,
    },
    Project {
        project_id: String,
    },
    LinkTarget {
        project_id: String,
    },
    LinkCurrent {
        link_id: String,
    },
    LinkOutcome {
        plan_id: String,
    },
    LinkSettlement {
        plan_id: String,
    },
    LinkRequestOutcome {
        request_key: String,
    },
    UnlinkOutcome {
        plan_id: String,
    },
    UnlinkSettlement {
        plan_id: String,
    },
    UnlinkRequestOutcome {
        request_key: String,
    },
    Technologies {
        query: Option<String>,
        offset: u32,
    },
    Mappings,
    Mapping {
        version: String,
    },
    Catalog {
        object_kind: ObjectKind,
        query: Option<String>,
        harness: Option<String>,
        cursor: Option<String>,
    },
    AssignmentPreview {
        harness: String,
        project_id: Option<String>,
        technology_id: Option<String>,
    },
}

fn invalid() -> Failure {
    Failure::precondition(
        "the corporate request or observation differs from its original authorized context",
    )
}

pub(super) fn unlink_plan(value: &Value) -> Result<Value> {
    UNLINK_PLAN.project(value)
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key].as_str().ok_or_else(invalid)
}

fn query(value: &Option<String>, limit: usize) -> bool {
    value.as_ref().is_none_or(|value| {
        !value.is_empty() && value.len() <= limit && !value.chars().any(char::is_control)
    })
}

fn harness(value: &str) -> Result<()> {
    if value == "undefined" {
        return Err(invalid());
    }
    harnesses::definition(value).map(|_| ())
}

impl Request {
    pub(crate) fn validate(&self) -> Result<()> {
        match self {
            Self::Project { project_id } | Self::LinkTarget { project_id }
                if !passport::stable_id(project_id, "remote_project") =>
            {
                Err(invalid())
            }
            Self::LinkOutcome { plan_id } | Self::LinkSettlement { plan_id }
                if !passport::stable_id(plan_id, "link_plan") =>
            {
                Err(invalid())
            }
            Self::LinkCurrent { link_id } if !passport::stable_id(link_id, "project_link") => {
                Err(invalid())
            }
            Self::UnlinkOutcome { plan_id } | Self::UnlinkSettlement { plan_id }
                if !passport::stable_id(plan_id, "unlink_plan") =>
            {
                Err(invalid())
            }
            Self::LinkRequestOutcome { request_key }
            | Self::UnlinkRequestOutcome { request_key }
                if !(16..=128).contains(&request_key.len())
                    || !request_key
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"._~-".contains(&b)) =>
            {
                Err(invalid())
            }
            Self::Technologies {
                query: value,
                offset,
            } if !query(value, 200) || *offset > 1_000_000 => Err(invalid()),
            Self::Mapping { version }
                if version.is_empty()
                    || version.len() > 128
                    || matches!(version.as_str(), "." | "..")
                    || !version
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || b"._+-".contains(&byte)) =>
            {
                Err(invalid())
            }
            Self::Catalog {
                query: value,
                harness: target,
                cursor,
                ..
            } => {
                if !query(value, 200) || !query(cursor, 512) {
                    return Err(invalid());
                }
                target.as_deref().map(harness).transpose().map(|_| ())
            }
            Self::AssignmentPreview {
                harness: target,
                project_id,
                technology_id,
            } => {
                if project_id
                    .as_ref()
                    .is_some_and(|id| !passport::stable_id(id, "remote_project"))
                    || technology_id
                        .as_ref()
                        .is_some_and(|id| !passport::stable_id(id, "technology"))
                {
                    return Err(invalid());
                }
                harness(target)
            }
            _ => Ok(()),
        }
    }

    pub(crate) fn wire(
        &self,
        origin: &str,
        organization: &str,
        account: &str,
    ) -> Result<(Url, Option<Value>)> {
        self.validate()?;
        if !passport::stable_id(organization, "organization")
            || !passport::stable_id(account, "account")
        {
            return Err(invalid());
        }
        let mut url = Url::parse(origin).map_err(|_| invalid())?;
        let base = format!("/v1/corporate/organizations/{organization}");
        let route = match self {
            Self::Teams => format!("{base}/teams"),
            Self::HeartbeatPolicy => format!("{base}/telemetry/heartbeat/policy"),
            Self::HeartbeatStatus => format!("{base}/telemetry/heartbeat"),
            Self::Projects {
                membership_only: true,
            } => format!("{base}/members/{account}/projects"),
            Self::Projects {
                membership_only: false,
            } => format!("{base}/projects"),
            Self::Project { project_id } => format!("{base}/projects/{project_id}"),
            Self::LinkTarget { project_id } => {
                format!("/v1/organizations/{organization}/project-link-targets/{project_id}")
            }
            Self::LinkCurrent { link_id } => format!("/v1/projects/links/{link_id}"),
            Self::LinkOutcome { plan_id } => {
                format!("/v1/organizations/{organization}/project-link-plans/{plan_id}/outcome")
            }
            Self::LinkSettlement { plan_id } => {
                format!("/v1/organizations/{organization}/project-link-plans/{plan_id}/settlement")
            }
            Self::LinkRequestOutcome { request_key } => {
                format!("/v1/organizations/{organization}/project-link-plan-requests/{request_key}")
            }
            Self::UnlinkOutcome { plan_id } => {
                format!("/v1/organizations/{organization}/project-unlink-plans/{plan_id}/outcome")
            }
            Self::UnlinkSettlement { plan_id } => {
                format!(
                    "/v1/organizations/{organization}/project-unlink-plans/{plan_id}/settlement"
                )
            }
            Self::UnlinkRequestOutcome { request_key } => {
                format!(
                    "/v1/organizations/{organization}/project-unlink-plan-requests/{request_key}"
                )
            }
            Self::Technologies { .. } => format!("{base}/technologies"),
            Self::Mappings => format!("{base}/technology-mappings"),
            Self::Mapping { version } => format!("{base}/technology-mappings/{version}"),
            Self::Catalog { object_kind, .. } => format!(
                "/v1/catalog/{}",
                match object_kind {
                    ObjectKind::Component => "components",
                    ObjectKind::Setup => "setups",
                }
            ),
            Self::AssignmentPreview { .. } => format!("{base}/catalog-assignments/plan"),
        };
        url.set_path(&route);
        match self {
            Self::Technologies { query, offset } => {
                let mut params = url.query_pairs_mut();
                params
                    .append_pair("limit", "128")
                    .append_pair("offset", &offset.to_string());
                if let Some(query) = query {
                    params.append_pair("query", query);
                }
            }
            Self::Catalog {
                query,
                harness,
                cursor,
                ..
            } => {
                let mut params = url.query_pairs_mut();
                params
                    .append_pair("organization_id", organization)
                    .append_pair("page_size", "50");
                for (key, value) in [("q", query), ("harness_id", harness), ("cursor", cursor)] {
                    if let Some(value) = value {
                        params.append_pair(key, value);
                    }
                }
            }
            _ => (),
        }
        let body = if let Self::AssignmentPreview {
            harness,
            project_id,
            technology_id,
        } = self
        {
            Some(
                json!({"schema_version":1,"account_id":account,"harness":harness,
                "project_id":project_id,"technology_id":technology_id,"materialized":[]}),
            )
        } else {
            None
        };
        Ok((url, body))
    }

    pub(super) fn project(
        &self,
        value: &Value,
        organization: &str,
        account: &str,
    ) -> Result<Value> {
        let schema = match self {
            Self::Teams => &TEAMS,
            Self::HeartbeatPolicy => &HEARTBEAT_POLICY,
            Self::HeartbeatStatus => &HEARTBEAT_STATUS,
            Self::Projects { .. } => &PROJECTS,
            Self::Project { .. } => &PROJECT,
            Self::LinkTarget { .. } => &LINK_TARGET,
            Self::LinkCurrent { .. } => &LINK_CURRENT,
            Self::LinkOutcome { .. }
            | Self::LinkSettlement { .. }
            | Self::LinkRequestOutcome { .. } => &LINK_OUTCOME,
            Self::UnlinkOutcome { .. }
            | Self::UnlinkSettlement { .. }
            | Self::UnlinkRequestOutcome { .. } => &UNLINK_OUTCOME,
            Self::Technologies { .. } => &TECHNOLOGIES,
            Self::Mappings => &MAPPINGS,
            Self::Mapping { .. } => &MAPPING,
            Self::Catalog {
                object_kind: ObjectKind::Component,
                ..
            } => &COMPONENTS,
            Self::Catalog {
                object_kind: ObjectKind::Setup,
                ..
            } => &SETUPS,
            Self::AssignmentPreview { .. } => &ASSIGNMENTS,
        };
        let value = schema.project(value)?;
        if matches!(
            self,
            Self::Project { .. }
                | Self::HeartbeatPolicy
                | Self::HeartbeatStatus
                | Self::LinkTarget { .. }
                | Self::LinkCurrent { .. }
                | Self::Mappings
                | Self::Mapping { .. }
                | Self::AssignmentPreview { .. }
        ) && value["organization_id"] != organization
        {
            return Err(invalid());
        }
        if matches!(self, Self::HeartbeatPolicy) && value["policy_version"].as_u64().is_none() {
            return Err(Failure::precondition(
                "the server does not report the required heartbeat policy revision",
            ));
        }
        if matches!(self, Self::HeartbeatStatus) {
            let heartbeat = &value["heartbeat"];
            if heartbeat.is_null() {
                if value["health_state"] != "unknown" {
                    return Err(invalid());
                }
            } else if heartbeat["organization_id"] != organization
                || heartbeat["account_id"] != account
                || heartbeat["device_id"] != value["device_id"]
                || heartbeat["health_state"] != value["health_state"]
                || heartbeat["stale_after_seconds"] != value["stale_after_seconds"]
            {
                return Err(invalid());
            }
        }
        if let Self::Project { project_id } = self
            && value["project_id"] != *project_id
        {
            return Err(invalid());
        }
        if let Self::LinkCurrent { link_id } = self
            && value["link_id"] != *link_id
        {
            return Err(invalid());
        }
        if let Self::LinkTarget { project_id } = self {
            if value["remote_project_id"] != *project_id {
                return Err(invalid());
            }
            let mut providers = BTreeSet::new();
            for provider in value["providers"].as_array().ok_or_else(invalid)? {
                let id = text(provider, "provider_project_id")?;
                if !passport::stable_id(id, "provider_project") || !providers.insert(id) {
                    return Err(invalid());
                }
            }
        }
        if let Self::LinkOutcome { plan_id } | Self::LinkSettlement { plan_id } = self
            && value["plan"]["plan_id"] != *plan_id
        {
            return Err(invalid());
        }
        if let Self::UnlinkOutcome { plan_id } | Self::UnlinkSettlement { plan_id } = self
            && value["plan"]["plan_id"] != *plan_id
        {
            return Err(invalid());
        }
        if matches!(
            self,
            Self::UnlinkOutcome { .. }
                | Self::UnlinkSettlement { .. }
                | Self::UnlinkRequestOutcome { .. }
        ) {
            let plan = &value["plan"];
            let link = &value["link"];
            if plan["organization_id"] != organization
                || (value["state"] == "applied") == link.is_null()
            {
                return Err(invalid());
            }
            if !link.is_null() {
                for field in [
                    "link_id",
                    "organization_id",
                    "local_project_id",
                    "remote_project_id",
                    "provider_project_id",
                    "local_revision",
                    "remote_revision",
                    "provider_revision",
                ] {
                    if link[field] != plan[field] {
                        return Err(invalid());
                    }
                }
                let expected = plan["expected_link_revision"]
                    .as_u64()
                    .and_then(|revision| revision.checked_add(1));
                if link["state"] != "unlinked"
                    || expected.is_none()
                    || link["revision"].as_u64() != expected
                {
                    return Err(invalid());
                }
            }
        }
        if matches!(
            self,
            Self::LinkOutcome { .. }
                | Self::LinkSettlement { .. }
                | Self::LinkRequestOutcome { .. }
        ) {
            let plan = &value["plan"];
            let link = &value["link"];
            if plan["organization_id"] != organization
                || (value["state"] == "applied") == link.is_null()
            {
                return Err(invalid());
            }
            if !link.is_null() {
                for field in [
                    "plan_id",
                    "plan_digest",
                    "organization_id",
                    "local_project_id",
                    "remote_project_id",
                    "provider_project_id",
                ] {
                    if link[field] != plan[field] {
                        return Err(invalid());
                    }
                }
            }
        }
        if let Self::Mapping { version } = self
            && value["version"] != *version
        {
            return Err(invalid());
        }
        if let Self::AssignmentPreview {
            harness,
            project_id,
            technology_id,
        } = self
            && (value["account_id"] != account
                || value["harness"] != *harness
                || value["project_id"] != json!(project_id)
                || value["technology_id"] != json!(technology_id)
                || value["total"].as_u64()
                    != value["items"].as_array().map(|items| items.len() as u64))
        {
            return Err(invalid());
        }
        if let Some(items) = value["items"].as_array() {
            if items.len() > 1024 {
                return Err(invalid());
            }
            let key = match self {
                // Team IDs are opaque in the canonical DTO; the current server
                // mints operation IDs for them, not a separate team namespace.
                Self::Teams => Some(("team_id", None)),
                Self::Projects { .. } => Some(("project_id", Some("remote_project"))),
                Self::Technologies { .. } => Some(("technology_id", Some("technology"))),
                _ => None,
            };
            if let Some((field, kind)) = key {
                let mut ids = BTreeSet::new();
                for item in items {
                    let id = text(item, field)?;
                    if item["organization_id"] != organization
                        || id.is_empty()
                        || id.len() > 128
                        || id.chars().any(char::is_control)
                        || kind.is_some_and(|kind| !passport::stable_id(id, kind))
                        || !ids.insert(id)
                    {
                        return Err(invalid());
                    }
                }
            }
        }
        Ok(value)
    }
}

pub(super) fn authority(organization: &Value, observation: &Value) -> Value {
    let capabilities = &observation["capabilities"];
    json!([
        organization["organization_id"],
        organization["kind"],
        organization["membership_revision"],
        capabilities["registry_version"],
        capabilities["authorization_revision"],
        capabilities["mode"],
        capabilities["context_kind"],
        capabilities["organization_id"],
        capabilities["capabilities"],
        capabilities["unavailable"]
    ])
}

fn heartbeat_device(value: &Value, device: &str) -> Result<()> {
    if value["device_id"] != device {
        return Err(invalid());
    }
    Ok(())
}

pub fn observe(root: &Path, context: Option<&str>, request: Request) -> Result<Value> {
    request.validate()?;
    let context = contexts::resolve(root, context)?;
    let Authority::Remote {
        account,
        organization,
        ..
    } = &context.authority
    else {
        return Err(Failure::precondition(
            "corporate reads require an authenticated corporate context",
        ));
    };
    if organization["kind"] != "corporate" {
        return Err(invalid());
    }
    let mut access = Access::for_binding(root, account, false)?;
    let organization_id = text(organization, "organization_id")?;
    let (organization, observation) = contexts::remote(&mut access, Some(organization_id))?;
    if organization["kind"] != "corporate" {
        return Err(invalid());
    }
    if matches!(
        request,
        Request::LinkCurrent { .. }
            | Request::UnlinkOutcome { .. }
            | Request::UnlinkSettlement { .. }
            | Request::UnlinkRequestOutcome { .. }
    ) && !observation["capabilities"]["capabilities"]
        .as_array()
        .is_some_and(|values| values.iter().any(|value| value == "project.unlink"))
    {
        return Err(invalid());
    }
    let data = access.corporate(&request, organization_id)?;
    let data = request.project(&data, organization_id, &access.binding().account_id)?;
    if matches!(request, Request::HeartbeatStatus) {
        heartbeat_device(&data, &access.binding().device_id)?;
    }
    let (current, current_observation) = contexts::remote(&mut access, Some(organization_id))?;
    if authority(&organization, &observation) != authority(&current, &current_observation) {
        return Err(Failure::precondition(
            "corporate membership or capabilities changed during the observation; read the original context again",
        ));
    }
    if matches!(
        request,
        Request::LinkTarget { .. }
            | Request::LinkOutcome { .. }
            | Request::LinkSettlement { .. }
            | Request::LinkRequestOutcome { .. }
            | Request::UnlinkOutcome { .. }
            | Request::UnlinkSettlement { .. }
            | Request::UnlinkRequestOutcome { .. }
    ) && data["authorization_revision"]
        != current_observation["capabilities"]["authorization_revision"]
    {
        return Err(Failure::precondition(
            "project link observation policy differs from the current corporate context",
        ));
    }
    context.bind()?.revalidate()?;
    access.revalidate()?;
    let result = json!({"schema_version":1,"context":context,"context_digest":context.digest()?,
        "account":access.binding(),"organization":current,"observation":current_observation,
        "request":request,"data":data,"online_verified":true,"observation_only":true,
        "installation_authority":false,"materialized_inventory":"none"});
    Ok(
        json!({"observation_digest":digest::sha256(&canonical::bytes(&json!(["ai-stp-native-corporate-observation/1",result]))?),
        "observation":result}),
    )
}
