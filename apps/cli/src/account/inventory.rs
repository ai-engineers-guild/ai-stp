//! Explicit owned-inventory consent and exact foreground delivery.

use super::{
    access::{Access, Binding},
    contexts::{self, Authority, Context},
    corporate::{self, Request},
};
use crate::{
    canonical, digest,
    error::{Failure, Result},
    files::{self, OwnedDirectory},
    installation::{custody::Custody, planning},
    passport, wire,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::BTreeSet, path::Path};
const DIRECTORY: &str = "ai-stp-v2-native-inventory";
const OWNER: &[u8] = b"ai-stp native owned inventory v1\n";
const LIMIT: u64 = 5 * 1024 * 1024;
static BATCH: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/installation-inventory-batch.schema.json"
)));
static RECEIPT: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/installation-inventory-receipt.schema.json"
)));
fn invalid() -> Failure {
    Failure::precondition(
        "native inventory changed its original context, consent, policy or exact observation",
    )
}
fn org(context: &Context) -> Result<&str> {
    let Authority::Remote { organization, .. } = &context.authority else {
        return Err(invalid());
    };
    if organization["kind"] != "corporate" {
        return Err(invalid());
    }
    organization["organization_id"]
        .as_str()
        .filter(|id| passport::stable_id(id, "organization"))
        .ok_or_else(invalid)
}
fn expected(context: &Context) -> Result<&Binding> {
    match &context.authority {
        Authority::Remote { account, .. } => Ok(account),
        _ => Err(invalid()),
    }
}
fn same_account(a: &Binding, b: &Binding) -> bool {
    let mut a = a.clone();
    a.revision.clone_from(&b.revision);
    a == *b
}
fn directory(context: &Context, create: bool) -> Result<Option<OwnedDirectory>> {
    let identity = context.bind()?;
    OwnedDirectory::open_at(identity.root_directory(), DIRECTORY, OWNER, create)
}
fn encode(value: &impl Serialize) -> Result<Vec<u8>> {
    let bytes = canonical::bytes(&serde_json::to_value(value).map_err(|_| invalid())?)?;
    if bytes.len() as u64 > LIMIT {
        return Err(invalid());
    }
    Ok(bytes)
}
fn hash(value: &impl Serialize) -> Result<String> {
    digest::canonical(
        "ai-stp:plan:v1",
        &serde_json::to_value(value).map_err(|_| invalid())?,
    )
}
fn online(context: &Context) -> Result<(Access, Value, String)> {
    let identity = context.bind()?;
    context.require_current_native_identity(&identity.context())?;
    let original = expected(context)?;
    let mut access = Access::for_connection(
        &context.root,
        None,
        original
            .connection
            .as_ref()
            .map(|c| c.connection_id.as_str()),
        false,
    )?;
    if !same_account(original, access.binding()) {
        return Err(invalid());
    }
    access.check_local_actor(&context.local_identity)?;
    let organization = org(context)?;
    let (before, observation) = contexts::remote(&mut access, Some(organization))?;
    let authority = corporate::authority(&before, &observation);
    let policy = Request::InventoryPolicy.project(
        &access.corporate(&Request::InventoryPolicy, organization)?,
        organization,
        &original.account_id,
    )?;
    if policy["inventory_scan_enabled"] != true {
        return Err(Failure::precondition(
            "the original company's current policy disables inventory discovery",
        ));
    }
    let (after, observation) = contexts::remote(&mut access, Some(organization))?;
    if authority != corporate::authority(&after, &observation) {
        return Err(invalid());
    }
    Ok((access, policy, hash(&authority)?))
}
fn links(access: &Access, context: &Context, values: &[Value]) -> Result<()> {
    if values.len() > 64 {
        return Err(invalid());
    }
    for link in values {
        let id = link["link_id"].as_str().ok_or_else(invalid)?;
        let project = link["project_id"].as_str().ok_or_else(invalid)?;
        if !passport::stable_id(id, "project_link")
            || !passport::stable_id(project, "remote_project")
        {
            return Err(invalid());
        }
        let request = Request::LinkCurrent { link_id: id.into() };
        let current = request.project(
            &access.corporate(&request, org(context)?)?,
            org(context)?,
            &access.binding().account_id,
        )?;
        if current["link_id"] != id
            || current["remote_project_id"] != project
            || current["organization_id"] != org(context)?
            || current["state"] != "linked"
        {
            return Err(invalid());
        }
    }
    Ok(())
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Pending {
    body: Value,
    links: Vec<Value>,
    digest: String,
    expires_at: String,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Record {
    format: String,
    context: Context,
    account: Binding,
    revision: String,
    enabled: bool,
    policy_version: u64,
    policy_digest: String,
    pending: Option<Pending>,
    outcome: Option<Value>,
}
impl Record {
    fn validate(&self, context: &Context) -> Result<()> {
        self.account.validate()?;
        if self.format != "ai-stp-native-inventory/1"
            || self.context != *context
            || !same_account(&self.account, expected(context)?)
            || !passport::stable_id(&self.revision, "operation")
            || self.policy_version == 0
            || !crate::provider::plan::hash(&self.policy_digest)
            || !self.enabled && self.pending.is_some()
        {
            return Err(invalid());
        }
        if let Some(pending) = &self.pending {
            BATCH.validate(&pending.body)?;
            if pending.digest != hash(&pending.body)? || !passport::timestamp(&pending.expires_at) {
                return Err(invalid());
            }
            validate_body(context, &self.account, &pending.body)?;
        }
        Ok(())
    }
    fn save(&self, dir: &OwnedDirectory) -> Result<()> {
        self.validate(&self.context)?;
        dir.atomic(&format!("{}.json", self.context.context_id), &encode(self)?)
    }
}
fn load(dir: &OwnedDirectory, context: &Context) -> Result<Option<Record>> {
    let Some(bytes) = dir.read_file(&format!("{}.json", context.context_id), LIMIT)? else {
        return Ok(None);
    };
    let record: Record = serde_json::from_value(wire::parse(&bytes)?).map_err(|_| invalid())?;
    record.validate(context)?;
    Ok(Some(record))
}
fn view(context: &Context, record: Option<&Record>) -> Result<Value> {
    Ok(
        json!({"context_id":context.context_id,"organization_id":org(context)?,
    "enabled":record.is_some_and(|r|r.enabled),"coverage":"owned_native_only","complete_discovery":false,"runtime_loading_observed":false,
    "revision":record.map(|r|&r.revision),"pending_digest":record.and_then(|r|r.pending.as_ref().map(|p|&p.digest)),"outcome":record.and_then(|r|r.outcome.as_ref()),
    "scheduler_registered":false}),
    )
}
fn validate_body(context: &Context, account: &Binding, body: &Value) -> Result<()> {
    BATCH.validate(body)?;
    for snapshot in body["snapshots"].as_array().ok_or_else(invalid)? {
        if snapshot["organization_id"] != org(context)?
            || snapshot["employee_id"] != account.account_id
            || snapshot["device_id"] != account.device_id
            || snapshot["complete"] != false
        {
            return Err(invalid());
        }
        for component in snapshot["components"].as_array().ok_or_else(invalid)? {
            if component["source"] != "managed" {
                return Err(invalid());
            }
        }
    }
    Ok(())
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ConsentPlan {
    format: String,
    operation_id: String,
    created_at: String,
    expires_at: String,
    context: Context,
    account: Binding,
    policy: Value,
    expected_revision: Option<String>,
}
impl ConsentPlan {
    pub fn digest(&self) -> Result<String> {
        self.context.digest()?;
        self.account.validate()?;
        if self.format != "ai-stp-native-inventory-consent/1"
            || !passport::stable_id(&self.operation_id, "operation")
            || self.expires_at != crate::authoring::expiry(&self.created_at)?
            || !same_account(expected(&self.context)?, &self.account)
            || self.policy["organization_id"] != org(&self.context)?
            || self.policy["inventory_scan_enabled"] != true
        {
            return Err(invalid());
        }
        hash(self)
    }
}
pub fn consent_plan(root: &Path, context: &str, at: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context))?;
    let (access, policy, _) = online(&context)?;
    let revision = directory(&context, false)?
        .map(|dir| load(&dir, &context))
        .transpose()?
        .flatten()
        .map(|r| r.revision);
    let plan = ConsentPlan {
        format: "ai-stp-native-inventory-consent/1".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at: crate::authoring::expiry(at)?,
        context,
        account: access.binding().clone(),
        policy,
        expected_revision: revision,
    };
    Ok(
        json!({"plan_digest":plan.digest()?,"plan":plan,"disclosure":{"fields":["organization","account","device","project","harness","component coordinates","state","opaque location digest"],"coverage":"owned_native_only","runtime_health":"not_observed","background_service":false}}),
    )
}
pub fn consent_apply(path: &Path, digest: &str, at: &str) -> Result<Value> {
    let plan: ConsentPlan =
        serde_json::from_value(wire::parse(&files::read(path, 131072)?)?).map_err(|_| invalid())?;
    if plan.digest()? != digest {
        return Err(invalid());
    }
    let (access, policy, _) = online(&plan.context)?;
    let dir = directory(&plan.context, true)?.ok_or_else(invalid)?;
    let held = load(&dir, &plan.context)?;
    if held
        .as_ref()
        .is_some_and(|r| r.revision == plan.operation_id)
    {
        return view(&plan.context, held.as_ref());
    }
    if !same_account(&plan.account, access.binding())
        || policy != plan.policy
        || held.as_ref().map(|r| &r.revision) != plan.expected_revision.as_ref()
        || at.parse::<jiff::Timestamp>().map_err(|_| invalid())?
            < plan
                .created_at
                .parse::<jiff::Timestamp>()
                .map_err(|_| invalid())?
        || at.parse::<jiff::Timestamp>().map_err(|_| invalid())?
            >= plan
                .expires_at
                .parse::<jiff::Timestamp>()
                .map_err(|_| invalid())?
    {
        return Err(invalid());
    }
    let record = Record {
        format: "ai-stp-native-inventory/1".into(),
        context: plan.context,
        account: access.binding().clone(),
        revision: plan.operation_id,
        enabled: true,
        policy_version: policy["policy_version"].as_u64().ok_or_else(invalid)?,
        policy_digest: hash(&policy)?,
        pending: None,
        outcome: None,
    };
    record.save(&dir)?;
    view(&record.context, Some(&record))
}
pub fn status(root: &Path, context: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context))?;
    org(&context)?;
    let record = directory(&context, false)?
        .map(|dir| load(&dir, &context))
        .transpose()?
        .flatten();
    view(&context, record.as_ref())
}
pub fn disable(root: &Path, context: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context))?;
    org(&context)?;
    let Some(dir) = directory(&context, false)? else {
        return view(&context, None);
    };
    let Some(mut record) = load(&dir, &context)? else {
        return view(&context, None);
    };
    record.enabled = false;
    record.pending = None;
    record.outcome = Some(json!({"state":"disabled"}));
    record.save(&dir)?;
    view(&context, Some(&record))
}
pub fn scan(root: &Path, context: &str, at: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context))?;
    org(&context)?;
    {
        let dir = directory(&context, false)?.ok_or_else(invalid)?;
        let held = load(&dir, &context)?.ok_or_else(invalid)?;
        if !held.enabled {
            return Err(invalid());
        }
        if held.pending.is_some() {
            return view(&context, Some(&held));
        }
    }
    // Release coordinator and registry locks before taking account/outbox locks.
    let observation = if let Some(custody) = Custody::existing_user()? {
        planning::inventory_observation(root, &custody, &context.context_id, at)?
    } else {
        json!({"snapshots":[]})
    };
    let (access, policy, _) = online(&context)?;
    let dir = directory(&context, false)?.ok_or_else(invalid)?;
    let mut record = load(&dir, &context)?.ok_or_else(invalid)?;
    if !record.enabled
        || record.policy_version != policy["policy_version"].as_u64().ok_or_else(invalid)?
        || record.policy_digest != hash(&policy)?
    {
        return Err(invalid());
    }
    if record.pending.is_some() {
        return view(&context, Some(&record));
    }
    if observation["snapshots"]
        .as_array()
        .ok_or_else(invalid)?
        .is_empty()
    {
        record.outcome = Some(json!({"state":"no_owned_observations"}));
        record.save(&dir)?;
        return view(&context, Some(&record));
    }
    let linked = observation["links"].as_array().ok_or_else(invalid)?.clone();
    links(&access, &context, &linked)?;
    let body = json!({"schema_version":1,"snapshots":observation["snapshots"]});
    validate_body(&context, access.binding(), &body)?;
    if encode(&body)?.len() > 4 * 1024 * 1024 {
        return Err(invalid());
    }
    record.pending = Some(Pending {
        links: linked,
        digest: hash(&body)?,
        body,
        expires_at: super::model::after(at, 86400)?,
    });
    record.outcome = Some(json!({"state":"pending"}));
    record.save(&dir)?;
    view(&context, Some(&record))
}
pub fn flush(root: &Path, context: &str, at: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context))?;
    org(&context)?;
    let snapshot = {
        let dir = directory(&context, false)?.ok_or_else(invalid)?;
        let record = load(&dir, &context)?.ok_or_else(invalid)?;
        if !record.enabled || record.pending.is_none() {
            return view(&context, Some(&record));
        }
        record
    };
    let pending = snapshot.pending.as_ref().ok_or_else(invalid)?;
    if at.parse::<jiff::Timestamp>().map_err(|_| invalid())?
        >= pending
            .expires_at
            .parse::<jiff::Timestamp>()
            .map_err(|_| invalid())?
    {
        let dir = directory(&context, false)?.ok_or_else(invalid)?;
        let mut record = load(&dir, &context)?.ok_or_else(invalid)?;
        if record.revision != snapshot.revision {
            return Err(invalid());
        }
        record.pending = None;
        record.outcome = Some(json!({"state":"expired"}));
        record.save(&dir)?;
        return view(&context, Some(&record));
    }
    let (access, policy, _) = online(&context)?;
    let dir = directory(&context, false)?.ok_or_else(invalid)?;
    let mut record = load(&dir, &context)?.ok_or_else(invalid)?;
    if record.revision != snapshot.revision
        || !record.enabled
        || record.pending.as_ref().map(|p| &p.digest) != Some(&pending.digest)
        || record.policy_version != policy["policy_version"].as_u64().ok_or_else(invalid)?
        || record.policy_digest != hash(&policy)?
        || !same_account(&record.account, access.binding())
    {
        return Err(invalid());
    }
    links(&access, &context, &pending.links)?;
    let bytes = encode(&pending.body)?;
    validate_body(&context, access.binding(), &pending.body)?;
    let reply = access.installation_inventory(org(&context)?, &bytes)?;
    let rejected = acknowledge(&pending.body, &reply)?;
    record.pending = None;
    record.outcome =
        Some(json!({"state":if rejected{"refused"}else{"acknowledged"},"receipt":reply}));
    if rejected {
        record.enabled = false;
    }
    record.save(&dir)?;
    view(&context, Some(&record))
}

fn acknowledge(body: &Value, reply: &Value) -> Result<bool> {
    RECEIPT.validate(reply)?;
    let wanted = body["snapshots"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(|s| s["scan_id"].as_str().ok_or_else(invalid))
        .collect::<Result<BTreeSet<_>>>()?;
    let mut seen = BTreeSet::new();
    let mut rejected = false;
    for field in ["accepted_ids", "duplicate_ids", "rejected_ids"] {
        for id in reply[field].as_array().ok_or_else(invalid)? {
            let id = id.as_str().ok_or_else(invalid)?;
            if !wanted.contains(id) || !seen.insert(id) {
                return Err(invalid());
            }
            if field == "rejected_ids" {
                rejected = true;
            }
        }
    }
    if seen != wanted {
        return Err(invalid());
    }
    Ok(rejected)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn body() -> Value {
        json!({"snapshots":[{"scan_id":"native_inventory_original"}]})
    }
    #[test]
    fn inventory_receipts_acknowledge_only_the_exact_original_partition() -> Result<()> {
        let body = body();
        for field in ["accepted_ids", "duplicate_ids"] {
            let mut reply =
                json!({"schema_version":1,"accepted_ids":[],"duplicate_ids":[],"rejected_ids":[]});
            reply[field] = json!(["native_inventory_original"]);
            assert!(!acknowledge(&body, &reply)?);
        }
        assert!(acknowledge(
            &body,
            &json!({"schema_version":1,"accepted_ids":[],"duplicate_ids":[],"rejected_ids":["native_inventory_original"]})
        )?);
        for reply in [
            json!({"schema_version":1,"accepted_ids":[],"duplicate_ids":[],"rejected_ids":[]}),
            json!({"schema_version":1,"accepted_ids":["native_inventory_other"],"duplicate_ids":[],"rejected_ids":[]}),
            json!({"schema_version":1,"accepted_ids":["native_inventory_original"],"duplicate_ids":["native_inventory_original"],"rejected_ids":[]}),
        ] {
            assert!(acknowledge(&body, &reply).is_err());
        }
        Ok(())
    }
    #[test]
    fn wire_inventory_has_no_fields_for_paths_payloads_prompts_or_unmanaged_coordinates()
    -> Result<()> {
        let mut item = json!({"location_digest":format!("sha256:{}","a".repeat(64)),"kind":"instruction","harness":"codex","source":"managed","state":"present","stable_id":"component_fixture","version":"1.0","setup_stable_id":null,"setup_version":null});
        let snapshot = |item: Value| json!({"schema_version":1,"snapshots":[{"schema_version":1,"scan_id":"native_inventory_fixture","organization_id":"organization_01ARZ3NDEKTSV4RRFFQ69G5FAV","employee_id":"account_01ARZ3NDEKTSV4RRFFQ69G5FAV","device_id":"fixture-device","project_id":null,"scope":"global","scanned_at":"2026-11-03T00:00:00Z","complete":false,"components":[item]}]});
        BATCH.validate(&snapshot(item.clone()))?;
        for key in ["path", "prompt", "content", "arguments", "api_key"] {
            let mut bad = item.clone();
            bad[key] = "private-canary".into();
            assert!(BATCH.validate(&snapshot(bad)).is_err());
        }
        item["source"] = "external".into();
        assert!(BATCH.validate(&snapshot(item)).is_err());
        Ok(())
    }
}
