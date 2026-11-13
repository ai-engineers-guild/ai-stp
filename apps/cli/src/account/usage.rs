//! Corporate runtime observations and a private, retryable foreground outbox.

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
use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

const DIRECTORY: &str = "ai-stp-v2-runtime-usage";
const OWNER: &[u8] = b"ai-stp native runtime usage v1\n";
const LIMIT: u64 = 262144;
const QUEUE_LIMIT: usize = 4096;
const SEND_LIMIT: usize = 64;
static BATCH: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/runtime-usage-event-batch.schema.json"
)));
static RECEIPT: wire::Schema = wire::Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/runtime-usage-ingest-result.schema.json"
)));

fn invalid() -> Failure {
    Failure::precondition("the original runtime usage context, consent or observation changed")
}

fn organization(context: &Context) -> Result<&str> {
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

fn account(context: &Context) -> Result<&Binding> {
    let Authority::Remote { account, .. } = &context.authority else {
        return Err(invalid());
    };
    organization(context)?;
    Ok(account)
}

fn same_account(left: &Binding, right: &Binding) -> bool {
    let mut left = left.clone();
    left.revision.clone_from(&right.revision);
    left == *right
}

fn directory_name(context_id: &str) -> String {
    format!("{DIRECTORY}-{context_id}")
}

fn directory(context: &Context, create: bool) -> Result<Option<OwnedDirectory>> {
    let identity = context.bind()?;
    OwnedDirectory::open_at(
        identity.root_directory(),
        &directory_name(&context.context_id),
        OWNER,
        create,
    )
}

fn bytes(value: &impl Serialize) -> Result<Vec<u8>> {
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

fn online(context: &Context) -> Result<(Access, Value)> {
    let identity = context.bind()?;
    context.require_current_native_identity(&identity.context())?;
    let original = account(context)?;
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
    let organization = organization(context)?;
    let (before, observation) = contexts::remote(&mut access, Some(organization))?;
    let authority = corporate::authority(&before, &observation);
    let policy = Request::InventoryPolicy.project(
        &access.corporate(&Request::InventoryPolicy, organization)?,
        organization,
        &original.account_id,
    )?;
    if policy["usage_collection_enabled"] != true {
        return Err(Failure::precondition(
            "the original company's current policy disables runtime usage collection",
        ));
    }
    let (after, observation) = contexts::remote(&mut access, Some(organization))?;
    if authority != corporate::authority(&after, &observation) {
        return Err(invalid());
    }
    Ok((access, policy))
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Record {
    format: String,
    context: Context,
    account: Binding,
    revision: String,
    enabled: bool,
    policy_digest: String,
    outcome: Option<String>,
}

impl Record {
    fn validate(&self, context: &Context) -> Result<()> {
        self.account.validate()?;
        if self.format != "ai-stp-native-runtime-usage/1"
            || self.context != *context
            || !same_account(&self.account, account(context)?)
            || !passport::stable_id(&self.revision, "operation")
            || !crate::provider::plan::hash(&self.policy_digest)
        {
            return Err(invalid());
        }
        Ok(())
    }

    fn save(&self, dir: &OwnedDirectory) -> Result<()> {
        self.validate(&self.context)?;
        dir.atomic(&format!("{}.json", self.context.context_id), &bytes(self)?)
    }
}

fn load(dir: &OwnedDirectory, context: &Context) -> Result<Option<Record>> {
    let Some(content) = dir.read_file(&format!("{}.json", context.context_id), LIMIT)? else {
        return Ok(None);
    };
    let record: Record = serde_json::from_value(wire::parse(&content)?).map_err(|_| invalid())?;
    record.validate(context)?;
    Ok(Some(record))
}

fn pending_names(dir: &OwnedDirectory) -> Result<Vec<String>> {
    let mut names = Vec::new();
    for entry in dir.directory.entries().map_err(|_| invalid())? {
        let entry = entry.map_err(|_| invalid())?;
        let name = entry.file_name().into_string().map_err(|_| invalid())?;
        if name.starts_with("event_") && name.ends_with(".json") {
            if name.len() != 43 || !name[6..38].bytes().all(|b| b.is_ascii_hexdigit()) {
                return Err(invalid());
            }
            names.push(name);
        }
    }
    names.sort();
    if names.len() > QUEUE_LIMIT {
        return Err(invalid());
    }
    Ok(names)
}

fn view(context: &Context, record: Option<&Record>, pending: usize) -> Result<Value> {
    Ok(
        json!({"context_id":context.context_id,"organization_id":organization(context)?,
        "enabled":record.is_some_and(|r|r.enabled),"revision":record.map(|r|&r.revision),
        "pending":pending,"outcome":record.and_then(|r|r.outcome.as_deref()),
        "coverage":"agent_reported_owned_signals","background_service":false}),
    )
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
        if self.format != "ai-stp-native-runtime-usage-consent/1"
            || !passport::stable_id(&self.operation_id, "operation")
            || self.expires_at != crate::authoring::expiry(&self.created_at)?
            || !same_account(account(&self.context)?, &self.account)
            || self.policy["organization_id"] != organization(&self.context)?
            || self.policy["usage_collection_enabled"] != true
        {
            return Err(invalid());
        }
        hash(self)
    }
}

pub fn consent_plan(root: &Path, context: &str, at: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context))?;
    let (access, policy) = online(&context)?;
    let expected_revision = directory(&context, false)?
        .map(|dir| load(&dir, &context))
        .transpose()?
        .flatten()
        .map(|r| r.revision);
    let plan = ConsentPlan {
        format: "ai-stp-native-runtime-usage-consent/1".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at: crate::authoring::expiry(at)?,
        context,
        account: access.binding().clone(),
        policy,
        expected_revision,
    };
    Ok(json!({"plan_digest":plan.digest()?,"plan":plan,
        "disclosure":{"fields":["organization","employee","device","project","harness",
            "exact setup and component coordinates","invocation time","outcome"],
            "coverage":"agent_reported_owned_signals","background_service":false}}))
}

pub fn consent_apply(path: &Path, digest: &str, at: &str) -> Result<Value> {
    let plan: ConsentPlan =
        serde_json::from_value(wire::parse(&files::read(path, LIMIT)?)?).map_err(|_| invalid())?;
    if plan.digest()? != digest {
        return Err(invalid());
    }
    let (access, policy) = online(&plan.context)?;
    let dir = directory(&plan.context, true)?.ok_or_else(invalid)?;
    let held = load(&dir, &plan.context)?;
    if held
        .as_ref()
        .is_some_and(|r| r.revision == plan.operation_id)
    {
        return view(&plan.context, held.as_ref(), pending_names(&dir)?.len());
    }
    if !same_account(&plan.account, access.binding())
        || policy != plan.policy
        || held.as_ref().map(|r| &r.revision) != plan.expected_revision.as_ref()
        || !pending_names(&dir)?.is_empty()
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
        format: "ai-stp-native-runtime-usage/1".into(),
        context: plan.context,
        account: access.binding().clone(),
        revision: plan.operation_id,
        enabled: true,
        policy_digest: hash(&policy)?,
        outcome: None,
    };
    record.save(&dir)?;
    view(&record.context, Some(&record), pending_names(&dir)?.len())
}

pub fn status(root: &Path, context: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context))?;
    organization(&context)?;
    let Some(dir) = directory(&context, false)? else {
        return view(&context, None, 0);
    };
    view(
        &context,
        load(&dir, &context)?.as_ref(),
        pending_names(&dir)?.len(),
    )
}

pub fn disable(root: &Path, context: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context))?;
    organization(&context)?;
    let Some(dir) = directory(&context, false)? else {
        return view(&context, None, 0);
    };
    let Some(mut record) = load(&dir, &context)? else {
        return view(&context, None, 0);
    };
    record.enabled = false;
    record.outcome = Some("disabled".into());
    record.save(&dir)?;
    for name in pending_names(&dir)? {
        dir.directory.remove_file(name).map_err(|_| invalid())?;
    }
    dir.sync()?;
    view(&context, Some(&record), 0)
}

pub fn record(root: &Path, context_id: &str, signal: &planning::UsageSignal<'_>) -> Result<Value> {
    let context = contexts::resolve(root, Some(context_id))?;
    let revision = {
        let dir = directory(&context, false)?.ok_or_else(invalid)?;
        let held = load(&dir, &context)?.ok_or_else(invalid)?;
        if !held.enabled {
            return Err(invalid());
        }
        held.revision
    };
    let custody = Custody::existing_user()?.ok_or_else(invalid)?;
    let observation = planning::usage_observation(root, &custody, context_id, signal)?;
    drop(custody);
    let event = &observation["event"];
    BATCH.validate(&json!({"schema_version":1,"events":[event]}))?;
    let event_id = event["event_id"].as_str().ok_or_else(invalid)?;
    let name = format!("{event_id}.json");
    let dir = directory(&context, false)?.ok_or_else(invalid)?;
    let held = load(&dir, &context)?.ok_or_else(invalid)?;
    if !held.enabled || held.revision != revision {
        return Err(invalid());
    }
    if let Some(existing) = dir.read_file(&name, LIMIT)? {
        let previous = wire::parse(&existing)?;
        if previous != observation {
            return Err(invalid());
        }
        return view(&context, Some(&held), pending_names(&dir)?.len());
    }
    if pending_names(&dir)?.len() >= QUEUE_LIMIT {
        return Err(Failure::precondition("runtime usage outbox is full"));
    }
    dir.atomic(&name, &bytes(&observation)?)?;
    view(&context, Some(&held), pending_names(&dir)?.len())
}

/// Queue native hook load signals for the owned components of the harness
/// session that called the hook. A hook never fails its harness: a missing
/// consent, installation or identifier records nothing and still succeeds.
pub fn hook(root: &Path, harness: &str, payload: &[u8], at: &str) -> Value {
    let Some((session, directory)) = hook_payload(harness, payload) else {
        return json!({"recorded":0,"skipped":0,"session_identified":false});
    };
    let components = Custody::existing_user()
        .ok()
        .flatten()
        .and_then(|custody| planning::hook_components(root, &custody, harness, &directory).ok())
        .unwrap_or_default();
    let mut recorded = 0;
    for (context, operation, component) in &components {
        let signal = planning::UsageSignal {
            operation,
            component,
            signal_id: &session,
            activity_kind: "load",
            outcome: "succeeded",
            at,
            source: "native_hook",
        };
        if record(root, context, &signal).is_ok() {
            recorded += 1;
        }
    }
    json!({"recorded":recorded,"skipped":components.len() - recorded,"session_identified":true})
}

/// Reads only the session identifier and working directory of a hook event.
fn hook_payload(harness: &str, payload: &[u8]) -> Option<(String, PathBuf)> {
    let event: Value = serde_json::from_slice(payload).ok()?;
    let session = match harness {
        "grok-build" => event["sessionId"].as_str(),
        "cursor" => event["session_id"]
            .as_str()
            .or_else(|| event["conversation_id"].as_str()),
        "claude-code" | "codex" => event["session_id"].as_str(),
        _ => None,
    }?;
    let directory = event["cwd"]
        .as_str()
        .or_else(|| event["workspaceRoot"].as_str())
        .or_else(|| event["workspace_roots"][0].as_str())
        .map(PathBuf::from)
        .or_else(|| std::env::current_dir().ok())?;
    Some((session.to_owned(), directory))
}

fn acknowledge(events: &[Value], reply: &Value) -> Result<(BTreeSet<String>, bool)> {
    RECEIPT.validate(reply)?;
    let wanted = events
        .iter()
        .map(|event| {
            event["event_id"]
                .as_str()
                .ok_or_else(invalid)
                .map(str::to_owned)
        })
        .collect::<Result<BTreeSet<_>>>()?;
    let mut seen = BTreeSet::new();
    let mut acknowledged = BTreeSet::new();
    let mut rejected = false;
    for field in ["accepted_ids", "duplicate_ids", "rejected_ids"] {
        for id in reply[field].as_array().ok_or_else(invalid)? {
            let id = id.as_str().ok_or_else(invalid)?;
            if !wanted.contains(id) || !seen.insert(id.to_owned()) {
                return Err(invalid());
            }
            if field == "rejected_ids" {
                rejected = true;
            } else {
                acknowledged.insert(id.to_owned());
            }
        }
    }
    if seen != wanted
        || reply["accepted"].as_u64()
            != Some(reply["accepted_ids"].as_array().ok_or_else(invalid)?.len() as u64)
        || reply["duplicates"].as_u64()
            != Some(reply["duplicate_ids"].as_array().ok_or_else(invalid)?.len() as u64)
        || reply["rejected"].as_u64()
            != Some(reply["rejected_ids"].as_array().ok_or_else(invalid)?.len() as u64)
    {
        return Err(invalid());
    }
    Ok((acknowledged, rejected))
}

pub fn flush(root: &Path, context_id: &str) -> Result<Value> {
    let context = contexts::resolve(root, Some(context_id))?;
    let (snapshot, pending) = {
        let dir = directory(&context, false)?.ok_or_else(invalid)?;
        let record = load(&dir, &context)?.ok_or_else(invalid)?;
        if !record.enabled {
            return view(&context, Some(&record), pending_names(&dir)?.len());
        }
        let pending = pending_names(&dir)?
            .into_iter()
            .take(SEND_LIMIT)
            .map(|name| {
                let content = dir.read_file(&name, LIMIT)?.ok_or_else(invalid)?;
                let observation = wire::parse(&content)?;
                BATCH.validate(&json!({"schema_version":1,"events":[&observation["event"]]}))?;
                if observation
                    .as_object()
                    .is_none_or(|fields| fields.len() != 2)
                    || observation["event"]["organization_id"] != organization(&context)?
                    || observation["event"]["employee_id"] != account(&context)?.account_id
                    || observation["event"]["device_id"] != account(&context)?.device_id
                    || !passport::stable_id(
                        observation["link_id"].as_str().ok_or_else(invalid)?,
                        "project_link",
                    )
                {
                    return Err(invalid());
                }
                Ok((name, content, observation))
            })
            .collect::<Result<Vec<_>>>()?;
        (record, pending)
    };
    if pending.is_empty() {
        return status(root, context_id);
    }
    let (access, policy) = online(&context)?;
    if snapshot.policy_digest != hash(&policy)?
        || !same_account(&snapshot.account, access.binding())
    {
        return Err(invalid());
    }
    let mut links = BTreeSet::new();
    for (_, _, observation) in &pending {
        let link = observation["link_id"].as_str().ok_or_else(invalid)?;
        if links.insert(link) {
            let request = Request::LinkCurrent {
                link_id: link.into(),
            };
            let current = request.project(
                &access.corporate(&request, organization(&context)?)?,
                organization(&context)?,
                &access.binding().account_id,
            )?;
            if current["link_id"] != link
                || current["state"] != "linked"
                || current["organization_id"] != organization(&context)?
                || pending.iter().any(|(_, _, item)| {
                    item["link_id"] == link
                        && item["event"]["project_id"] != current["remote_project_id"]
                })
            {
                return Err(invalid());
            }
        }
    }
    let events = pending
        .iter()
        .map(|(_, _, item)| item["event"].clone())
        .collect::<Vec<_>>();
    let body = json!({"schema_version":1,"events":events});
    BATCH.validate(&body)?;
    let reply = access.runtime_usage(organization(&context)?, &bytes(&body)?)?;
    let (acknowledged, rejected) = acknowledge(&events, &reply)?;
    let dir = directory(&context, false)?.ok_or_else(invalid)?;
    let mut held = load(&dir, &context)?.ok_or_else(invalid)?;
    if !held.enabled || held.revision != snapshot.revision {
        return Err(invalid());
    }
    for (name, original, _) in &pending {
        if dir.read_file(name, LIMIT)?.as_deref() != Some(original.as_slice()) {
            return Err(invalid());
        }
    }
    for (name, _, observation) in &pending {
        if acknowledged.contains(
            observation["event"]["event_id"]
                .as_str()
                .ok_or_else(invalid)?,
        ) {
            dir.directory.remove_file(name).map_err(|_| invalid())?;
        }
    }
    dir.sync()?;
    held.outcome = Some(if rejected { "refused" } else { "acknowledged" }.into());
    if rejected {
        held.enabled = false;
    }
    held.save(&dir)?;
    view(&context, Some(&held), pending_names(&dir)?.len())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn contexts_have_separate_outboxes() -> Result<()> {
        let root = tempfile::tempdir().map_err(|_| invalid())?;
        let first = OwnedDirectory::open(root.path(), &directory_name("context_a"), OWNER, true)?
            .ok_or_else(invalid)?;
        let second = OwnedDirectory::open(root.path(), &directory_name("context_b"), OWNER, true)?
            .ok_or_else(invalid)?;
        let name = "event_0123456789abcdef0123456789abcdef.json";
        first.atomic(name, b"first")?;
        second.atomic(name, b"second")?;
        for pending in pending_names(&first)? {
            first
                .directory
                .remove_file(pending)
                .map_err(|_| invalid())?;
        }
        assert!(pending_names(&first)?.is_empty());
        assert_eq!(second.read_file(name, LIMIT)?, Some(b"second".to_vec()));
        Ok(())
    }

    #[test]
    fn receipt_requires_an_exact_partition() -> Result<()> {
        let events = vec![json!({"event_id":"event_0123456789abcdef0123456789abcdef"})];
        let reply = json!({"schema_version":1,"accepted":1,"duplicates":0,"rejected":0,
            "accepted_ids":["event_0123456789abcdef0123456789abcdef"],
            "duplicate_ids":[],"rejected_ids":[]});
        assert_eq!(acknowledge(&events, &reply)?.0.len(), 1);
        let mut duplicate = reply.clone();
        duplicate["duplicate_ids"] = duplicate["accepted_ids"].clone();
        assert!(acknowledge(&events, &duplicate).is_err());
        Ok(())
    }

    #[test]
    fn usage_wire_refuses_payload_and_paths() -> Result<()> {
        let digest = format!("sha256:{}", "a".repeat(64));
        let event = json!({
            "schema_version":1,
            "event_id":"event_0123456789abcdef0123456789abcdef",
            "organization_id":"organization_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "employee_id":"account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "device_id":"fixture-device",
            "project_id":"remote_project_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "harness":"codex",
            "setup":{"stable_id":"setup_fixture","version":"1.0","passport_digest":digest},
            "component":{"kind":"mcp","stable_id":"component_fixture","version":"1.0","passport_digest":digest},
            "invoked_at":"2026-11-05T00:00:00.000Z",
            "outcome":"succeeded","source":"native_hook","activity_kind":"invocation"
        });
        BATCH.validate(&json!({"schema_version":1,"events":[event]}))?;
        for key in ["prompt", "arguments", "path", "content", "api_key"] {
            let mut forbidden = event.clone();
            forbidden[key] = "private-canary".into();
            assert!(
                BATCH
                    .validate(&json!({"schema_version":1,"events":[forbidden]}))
                    .is_err()
            );
        }
        Ok(())
    }

    #[test]
    fn hook_payload_reads_only_each_vendor_session_and_directory() {
        let cases = [
            (
                "claude-code",
                json!({"session_id":"claude-1","cwd":"/w","hook_event_name":"SessionStart","prompt":"x"}),
            ),
            (
                "codex",
                json!({"session_id":"codex-1","cwd":"/w","hook_event_name":"SessionStart"}),
            ),
            (
                "cursor",
                json!({"session_id":"cursor-1","workspace_roots":["/w"]}),
            ),
            (
                "cursor",
                json!({"conversation_id":"cursor-1","workspace_roots":["/w"]}),
            ),
            (
                "grok-build",
                json!({"sessionId":"grok-1","workspaceRoot":"/w"}),
            ),
        ];
        for (harness, event) in cases {
            let (session, directory) =
                hook_payload(harness, event.to_string().as_bytes()).expect(harness);
            assert!(session.ends_with("-1"));
            assert_eq!(directory, PathBuf::from("/w"));
        }
        assert!(
            hook_payload("grok-build", br#"{"session_id":"wrong-field","cwd":"/w"}"#).is_none()
        );
        assert!(hook_payload("antigravity", br#"{"session_id":"s","cwd":"/w"}"#).is_none());
        assert!(hook_payload("codex", b"not json").is_none());
    }

    #[test]
    fn hook_without_session_records_nothing_and_succeeds() {
        let root = tempfile::tempdir().expect("root");
        let reply = hook(root.path(), "codex", b"{}", "2026-11-14T00:00:00.000Z");
        assert_eq!(reply["recorded"], 0);
        assert_eq!(reply["session_identified"], false);
    }
}
