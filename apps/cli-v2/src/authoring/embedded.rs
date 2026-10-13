//! Author one exact local source as a private immutable component and setup.

use std::path::PathBuf;

use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use super::{Identity, expiry, freezing, native_identity, setups, source_project};
use crate::{
    artifacts::{self, Member},
    canonical, digest,
    error::{Failure, Result},
    files,
    harnesses::Shape,
    objects::Objects,
    passport,
    projection::{self, Scope, artifact},
    sources,
    store::{Store, database, journal, revisions, versions},
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub directory: PathBuf,
    pub harness_id: String,
    pub component_type: String,
    pub name: String,
    pub license_spdx: String,
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
    pub source_digest: String,
    pub component: Value,
    pub setup: Value,
    pub minted: bool,
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
    Failure::precondition("the author source or exact immutable result is inconsistent")
}

fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str> {
    value[field]
        .as_str()
        .filter(|v| !v.is_empty())
        .ok_or_else(invalid)
}

pub fn kinds(harness: &str) -> Result<Vec<String>> {
    crate::harnesses::definition(harness)?;
    let mut kinds: Vec<_> = projection::routes()?
        .iter()
        .filter(|route| {
            route.harness_id == harness
                && matches!(route.target_scope, Scope::Global | Scope::UserRoot)
        })
        .map(|route| route.component_type.clone())
        .collect();
    kinds.push("cli".into());
    kinds.sort();
    kinds.dedup();
    Ok(kinds)
}

struct Prepared {
    snapshot: Value,
    source_digest: String,
    identity: Value,
    files: Vec<Member>,
    scope: Scope,
    projection_kind: String,
    provider_kind: String,
}

fn capture(request: &Request, owner: &Identity) -> Result<Prepared> {
    if !request.directory.is_absolute()
        || request.name.trim() != request.name
        || request.name.is_empty()
        || request.name.chars().count() > 160
        || !artifacts::safe_path(&request.name)
        || request.name.contains('/')
        || request.license_spdx.trim() != request.license_spdx
        || request.license_spdx.is_empty()
        || request.license_spdx.len() > 256
        || request.license_spdx.chars().any(char::is_control)
    {
        return Err(Failure::input(
            "author requires an absolute directory, one portable name and a nonempty license",
        ));
    }
    if !request.directory.is_dir() {
        return Err(invalid());
    }
    let leaf = request
        .directory
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or_else(invalid)?;
    let root = request.directory.parent().ok_or_else(invalid)?;
    let captured = sources::local::capture(root, leaf)?;
    let bytes = URL_SAFE_NO_PAD
        .decode(text(&captured["artifact"], "bytes_b64")?)
        .map_err(|_| invalid())?;
    let source_digest = text(&captured["artifact"], "digest")?.to_owned();
    let mut members = artifacts::decode_tree(&bytes)?;
    members.retain(|member| member.path.rsplit('/').next() != Some("GENERATED.md"));
    if members.is_empty() {
        return Err(invalid());
    }
    let route = projection::route(&request.component_type, &request.harness_id, Scope::Global)?;
    let (relative, shape, scope) = match route {
        Some(route) => (route.relative.clone(), route.shape, route.target_scope),
        None if request.component_type == "cli" => {
            (format!("bin/{}", request.name), Shape::File, Scope::Global)
        }
        None => {
            return Err(Failure::precondition(
                "this harness has no declared authoring route for that kind",
            ));
        }
    };
    let projection_kind = route
        .map_or("native_files", |r| r.projection_kind.as_str())
        .to_owned();
    let provider_kind = route
        .filter(|r| !r.provider_kind.is_empty())
        .map_or(request.component_type.as_str(), |r| {
            r.provider_kind.as_str()
        })
        .to_owned();
    let named = request.harness_id == "antigravity"
        && matches!(request.component_type.as_str(), "instruction" | "command");
    if (shape == Shape::File || named)
        && (members.len() != 1 || named && !members[0].path.ends_with(".md"))
    {
        return Err(Failure::input(
            "this native surface requires exactly one source file (Markdown for a named document)",
        ));
    }
    for member in &mut members {
        member.path = if named {
            format!("{}/{}.md", relative, request.name)
        } else if shape == Shape::Directory {
            format!("{}/{}/{}", relative, request.name, member.path)
        } else {
            relative.clone()
        };
        if source_project::unfinished(&member.path, &member.bytes) {
            return Err(Failure::precondition(
                "author cannot release unfinished scaffold content",
            ));
        }
    }
    let profile = projection::profile(&request.harness_id, scope)?;
    let identity = json!({"format":"ai-stp-native-author/1", "owner_id":owner.account_id,
        "harness_id":request.harness_id,"component_type":request.component_type,
        "name":request.name,"license_spdx":request.license_spdx,"source_digest":source_digest,
        "profile_id":profile.profile_id,"profile_digest":profile.profile_digest,
        "scope":scope,"projection_kind":projection_kind,"provider_kind":provider_kind,
        "paths":members.iter().map(|v| &v.path).collect::<Vec<_>>()});
    Ok(Prepared {
        snapshot: captured["snapshot"].clone(),
        source_digest,
        identity,
        files: members,
        scope,
        projection_kind,
        provider_kind,
    })
}

fn id(kind: &str, identity: &Value) -> Result<String> {
    let bytes = canonical::bytes(&json!({"kind":kind,"source":identity}))?;
    let hash = Sha256::digest(bytes);
    let bytes: [u8; 16] = hash[..16].try_into().map_err(|_| invalid())?;
    Ok(format!("{kind}_{}", ulid::Ulid::from_bytes(bytes)))
}

fn component(
    request: &Request,
    prepared: &Prepared,
    identity: &Identity,
    at: &str,
) -> Result<(Value, Vec<u8>)> {
    let names = native_identity::projection_names(
        &request.component_type,
        &request.harness_id,
        &prepared.files,
    )?;
    let members = prepared.files.iter().map(|file| Ok(json!({"path":file.path,"object_type":"file","mode":file.mode,
        "content_artifact":{"digest":digest::bytes("ai-stp:artifact:v1",&file.bytes)?,"size_bytes":file.bytes.len()},
        "native_ids":names[&file.path],"content_format":"application/octet-stream","parser_id":null,
        "ownership":"whole","ownership_key":null,"write_semantics":"replace","withdrawal_semantics":"remove_path"})))
        .collect::<Result<Vec<_>>>()?;
    native_identity::verify_files(
        &request.component_type,
        &request.harness_id,
        &members,
        &prepared.files,
    )?;
    let bytes = artifact::build_members(&members, &prepared.files)?;
    let reference =
        json!({"digest":digest::bytes("ai-stp:artifact:v1",&bytes)?,"size_bytes":bytes.len()});
    let profile = projection::profile(&request.harness_id, prepared.scope)?;
    let adaptation = passport::versions::seal_adaptation(&json!({
    "harness_id":request.harness_id,"implementation_mode":"native","source_artifact":null,"transform":null,
    "logical_component_type":request.component_type,"scope_adaptations":[{
        "scope":prepared.scope,"projection_format":artifact::FORMAT,"projection_artifact":reference,
            "provider_component_kind":prepared.provider_kind,"projection_kind":prepared.projection_kind,
        "required_surface":{"profile_id":profile.profile_id,"profile_digest":profile.profile_digest,"bundle_format":profile.bundle_format},
        "permissions":{"filesystem":[],"network":[],"process":[]},"members":members,
        "supported_harness_versions":[],"supported_os":[],"supported_arch":[],
        "technical_support":"experimental","technical_support_reason":"locally authored embedded component","semantic_losses":[]
    }]}))?;
    let values = json!({"name":request.name,"description":format!("Local {} {}.",request.component_type,request.name),
        "tags":["authored"],"license":{"spdx_id":request.license_spdx,"redistribution_allowed":false},
        "component_type":request.component_type,"harness_id":request.harness_id});
    let document = freezing::complete(
        json!({"kind":"component","stable_id":id("component",&prepared.identity)?,
        "version":"1.0","owner_id":identity.account_id,"created_at":at,"visibility":"private","parent_revision_ids":[],
        "facts":{"author_source":{"value":prepared.identity,"origin":"derived","confirmation":"none","observed_at":at}}}),
        &values,
        vec![adaptation],
    )?;
    Ok((document, bytes))
}

fn setup(
    request: &Request,
    prepared: &Prepared,
    identity: &Identity,
    at: &str,
    component: &Value,
    artifact: &[u8],
) -> Result<(Value, Vec<u8>)> {
    let reference = setups::Member {
        stable_id: text(component, "stable_id")?.into(),
        version: "1.0".into(),
        passport_digest: digest::canonical("ai-stp:passport:v1", component)?,
    };
    let composition = setups::Request {
        harness_id: request.harness_id.clone(),
        name: request.name.clone(),
        description: format!("Local {} {}.", request.component_type, request.name),
        purpose: format!("Use the local {} {}.", request.component_type, request.name),
        members: vec![reference.clone()],
        requirements: None,
    };
    let (mut document, definition) = setups::assemble(
        &composition,
        prepared.identity.clone(),
        &id("setup", &prepared.identity)?,
        identity,
        at,
        std::slice::from_ref(component),
    )?;
    let mut definition = canonical::parse(&definition)?;
    definition["schema_version"] = 2.into();
    definition["format"] = "ai-stp-setup-definition/2".into();
    definition["embedded"] = json!([{"ref":reference,"passport":component,"snapshot":prepared.snapshot,
        "artifact_b64":URL_SAFE_NO_PAD.encode(artifact),"artifact_digest":component["artifact"]["digest"],
        "artifact_size_bytes":artifact.len(),"passport_digest":digest::canonical("ai-stp:passport:v1",component)?,
        "passport_size_bytes":canonical::bytes(component)?.len()}]);
    document["artifact_format"] = definition["format"].clone();
    let (document, bytes) = setups::seal(document, canonical::bytes(&definition)?)?;
    setups::verify_definition(&document, &bytes)?;
    Ok((document, bytes))
}

fn existing(connection: &Connection, prepared: &Prepared) -> Result<Option<(Value, Value)>> {
    let stable_id = id("setup", &prepared.identity)?;
    let found: bool = connection
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM object_version WHERE stable_id=? AND version='1.0')",
            [&stable_id],
            |row| row.get(0),
        )
        .map_err(database)?;
    if !found {
        return Ok(None);
    }
    let objects = Objects { connection };
    objects.require_active(&stable_id)?;
    objects.require_active(&id("component", &prepared.identity)?)?;
    let setup = objects.exact_version(&stable_id, "1.0", None)?;
    setups::verify(connection, &setup)?;
    let component = objects.exact_version(&id("component", &prepared.identity)?, "1.0", None)?;
    if component["facts"]["author_source"]["value"] != prepared.identity {
        return Err(invalid());
    }
    Ok(Some((component, setup)))
}

pub fn plan(store: &mut Store, request: Request, identity: Identity, at: &str) -> Result<Plan> {
    identity.validate()?;
    let expires_at = expiry(at)?;
    let prepared = capture(&request, &identity)?;
    let (component, setup, minted) =
        if let Some((component, setup)) = existing(&store.connection, &prepared)? {
            (component, setup, false)
        } else {
            let (component, bytes) = component(&request, &prepared, &identity, at)?;
            let (setup, _) = setup(&request, &prepared, &identity, at, &component, &bytes)?;
            (component, setup, true)
        };
    Ok(Plan {
        schema_version: 1,
        action: "author.local".into(),
        operation_id: format!("operation_{}", ulid::Ulid::generate()),
        created_at: at.into(),
        expires_at,
        identity,
        request,
        source_digest: prepared.source_digest,
        component,
        setup,
        minted,
    })
}

pub fn outcome(plan: &Plan) -> Value {
    json!({"kind":"author","harness_id":plan.request.harness_id,"directory":plan.request.directory,
        "component_type":plan.request.component_type,"name":plan.request.name,
        "component_id":plan.component["stable_id"],"component_version":"1.0",
        "setup_id":plan.setup["stable_id"],"setup_version":"1.0","minted":plan.minted})
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
        || plan.action != "author.local"
        || plan.identity != *identity
        || !passport::stable_id(&plan.operation_id, "operation")
        || !passport::timestamp(at)
        || plan.expires_at != expiry(&plan.created_at)?
        || plan.digest()? != expected
    {
        return Err(invalid());
    }
    if let Some(state) = journal::state(
        &store.connection,
        &plan.operation_id,
        &plan.action,
        expected,
    )? {
        if state != "verified" {
            return Err(invalid());
        }
        let objects = Objects {
            connection: &store.connection,
        };
        if objects.exact_version(text(&plan.component, "stable_id")?, "1.0", None)?
            != plan.component
            || objects.exact_version(text(&plan.setup, "stable_id")?, "1.0", None)? != plan.setup
        {
            return Err(invalid());
        }
        setups::verify(&store.connection, &plan.setup)?;
        return Ok(outcome(plan));
    }
    if at < plan.created_at.as_str() || at > plan.expires_at.as_str() {
        return Err(Failure::precondition(
            "the author plan expired before effects; cancel and start from current source",
        ));
    }
    let prepared = capture(&plan.request, identity)?;
    if prepared.source_digest != plan.source_digest {
        return Err(Failure::precondition(
            "the author source changed after planning",
        ));
    }
    let (component, artifact) = component(&plan.request, &prepared, identity, &plan.created_at)?;
    let (setup, definition) = setup(
        &plan.request,
        &prepared,
        identity,
        &plan.created_at,
        &component,
        &artifact,
    )?;
    store.transaction(|t| {
        if let Some((component,setup)) = existing(t,&prepared)? {
            if component != plan.component || setup != plan.setup { return Err(invalid()); }
        } else {
            if !plan.minted || component != plan.component || setup != plan.setup { return Err(invalid()); }
            revisions::content(t,&artifact,at)?;
            revisions::commit(t, &component, &identity.device_id, Some(&plan.operation_id),
                revisions::Write::Advance { expected_heads: &[] })?;
            versions::record(t,&component,&identity.device_id,Some(&plan.operation_id),at)?;
            setups::persist(t, &setup, &definition, identity, &plan.operation_id, at)?;
            setups::verify(t,&setup)?;
        }
        t.execute("INSERT INTO operation(operation_id,kind,state,started_at,finished_at,detail) VALUES (?,?,'verified',?,?,?)",
            params![plan.operation_id,plan.action,at,at,expected]).map_err(database)?;
        Ok(outcome(plan))
    })
}
