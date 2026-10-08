//! Deterministic provider packages from exact local versions and explicit evidence.

mod composition;
mod package;

use std::collections::BTreeMap;

use rusqlite::Connection;
use serde_json::{Value, json};

use crate::{
    artifacts::Member,
    canonical, digest,
    error::{Failure, Result},
    objects::Objects,
    passport, projection,
    provider::Info,
    selection::eligibility::{self, Evidence, Target},
    store::{Store, revisions},
};

const MAX_FILES: usize = 2000;
const MAX_FILE_BYTES: usize = 4 * 1024 * 1024;
const MAX_BYTES: usize = 64 * 1024 * 1024;

/// Exact observed host bytes, or an explicitly observed absence. Missing keys
/// mean unknown, never an empty configuration. The runtime must capture these
/// without credentials and revalidate their identity before provider execution.
pub type Hosts = BTreeMap<String, Option<Vec<u8>>>;

pub struct Bundle {
    pub manifest: Value,
    pub archive: Vec<u8>,
    pub artifact_digest: String,
    pub assessment: Value,
}

struct File {
    member: Member,
    owner: String,
}

fn invalid(message: &str) -> Failure {
    Failure::precondition(message)
}

fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str> {
    value[field]
        .as_str()
        .ok_or_else(|| invalid("an exact bundle input is incomplete"))
}

fn exact(connection: &Connection, reference: &Value) -> Result<Value> {
    Objects { connection }.exact_version(
        text(reference, "stable_id")?,
        text(reference, "version")?,
        Some(text(reference, "passport_digest")?),
    )
}

/// This reads one consistent database snapshot and returns no partial package.
/// It neither stores a plan nor authorizes execution against a harness target.
pub fn compile(
    store: &mut Store,
    setup: &Value,
    target: &Target,
    evidence: &BTreeMap<String, Evidence>,
    provider: &Info,
    hosts: &Hosts,
) -> Result<Bundle> {
    store.transaction(|connection| {
        compile_snapshot(connection, setup, target, evidence, provider, hosts)
    })
}

fn compile_snapshot(
    connection: &Connection,
    setup: &Value,
    target: &Target,
    evidence: &BTreeMap<String, Evidence>,
    provider: &Info,
    hosts: &Hosts,
) -> Result<Bundle> {
    if !passport::stable_id(text(setup, "stable_id")?, "setup")
        || setup.as_object().is_none_or(|fields| fields.len() != 3)
        || canonical::bytes(setup)?.len() > 4096
    {
        return Err(invalid("a bundle requires one exact setup version"));
    }
    let mut host_bytes = 0usize;
    let mut host_identities = BTreeMap::new();
    for (path, bytes) in hosts {
        let size = bytes.as_ref().map_or(0, Vec::len);
        host_bytes = host_bytes
            .checked_add(size)
            .ok_or_else(|| invalid("host inputs exceed their bounds"))?;
        if hosts.len() > MAX_FILES
            || !crate::artifacts::safe_path(path)
            || size > MAX_FILE_BYTES
            || host_bytes > MAX_BYTES
        {
            return Err(invalid("host inputs exceed their path or size bounds"));
        }
        host_identities.insert(path, bytes.as_ref().map(|bytes| digest::sha256(bytes)));
    }
    let assessment = eligibility::assess_connection(
        connection,
        std::slice::from_ref(setup),
        target,
        evidence,
        Some(provider),
    )?;
    if assessment["admissible"] != true {
        return Err(
            invalid("the exact setup graph is not mechanically admissible")
                .with_details([("eligibility".into(), assessment)]),
        );
    }
    let document = exact(connection, setup)?;
    let setup_bytes = revisions::read_content(connection, text(&document["artifact"], "digest")?)?;
    if document["artifact"]["size_bytes"] != setup_bytes.len() {
        return Err(invalid(
            "the setup artifact size does not match its passport",
        ));
    }
    drop(setup_bytes);
    let mut composition = composition::Composition::default();
    let mut files = Vec::new();
    let mut bindings = Vec::new();
    let mut remaining_hosts: BTreeMap<_, _> = hosts
        .iter()
        .map(|(path, bytes)| (path.as_str(), bytes.as_deref()))
        .collect();
    let mut projection_bytes = 0u64;
    let mut output_bytes = 0usize;
    let nodes = assessment["graph"]["nodes"]
        .as_array()
        .ok_or_else(|| invalid("graph nodes are missing"))?;
    for node in nodes {
        let component = exact(connection, node)?;
        if component["kind"] == "setup" {
            continue;
        }
        let id = text(&component, "stable_id")?;
        let (adaptation, scope) =
            projection::adaptation(&component, &target.harness_id, target.scope)
                .ok_or_else(|| invalid("an exact scope adaptation disappeared"))?;
        if scope["required_surface"]["bundle_format"] != "ai-stp-bundle/2" {
            return Err(invalid(
                "native bundle compilation requires adaptation-bound format v2",
            ));
        }
        // Bound aggregate allocation before loading any selected projection.
        projection_bytes = projection_bytes
            .checked_add(
                scope["projection_artifact"]["size_bytes"]
                    .as_u64()
                    .ok_or_else(|| invalid("projection size missing"))?,
            )
            .ok_or_else(|| invalid("projection inputs exceed their bounds"))?;
        if projection_bytes > (2 * MAX_BYTES) as u64 {
            return Err(invalid("the selected projection archives exceed 128 MiB"));
        }
        let payload =
            revisions::read_content(connection, text(&scope["projection_artifact"], "digest")?)?;
        let members = projection::artifact::verify(scope, &payload)?;
        drop(payload);
        let declared = scope["members"]
            .as_array()
            .ok_or_else(|| invalid("projection members are missing"))?;
        if members.is_empty()
            || declared
                .iter()
                .any(|member| member["object_type"] != "file")
        {
            return Err(invalid(
                "bundle v2 requires a file for every component and cannot preserve explicit directory members",
            ));
        }
        crate::authoring::native_identity::verify_members(
            text(&component, "component_type")?,
            &target.harness_id,
            scope,
            &members,
        )?;
        composition.include(&component, scope, &assessment)?;
        let declared: BTreeMap<_, _> = declared
            .iter()
            .map(|value| Ok((text(value, "path")?, value)))
            .collect::<Result<_>>()?;
        let mut member_paths = Vec::new();
        for mut member in members {
            let declaration = declared
                .get(member.path.as_str())
                .ok_or_else(|| invalid("a projection file has no declaration"))?;
            composition.claim(id, &member.path)?;
            if secret(&member.path)
                || member.bytes.len() > MAX_FILE_BYTES
                || !matches!(member.mode, 0o644 | 0o755)
            {
                return Err(invalid(
                    "a bundle file violates its credential, size or mode boundary",
                ));
            }
            if declaration["ownership"] == "contribution" {
                let host = remaining_hosts.remove(member.path.as_str()).ok_or_else(|| {
                    invalid(
                        "a configuration contribution needs exact observed host bytes or absence",
                    )
                })?;
                let format = crate::authoring::contribution::Format::for_path(&member.path)?;
                let parser = if format == crate::authoring::contribution::Format::Toml {
                    "toml/1"
                } else {
                    "json/1"
                };
                if declaration["parser_id"] != parser {
                    return Err(invalid(
                        "the configuration parser does not match its host format",
                    ));
                }
                member.bytes = crate::authoring::contribution::assemble(
                    format,
                    host,
                    text(declaration, "ownership_key")?,
                    &member.bytes,
                )?;
            }
            output_bytes = output_bytes
                .checked_add(member.bytes.len())
                .ok_or_else(|| invalid("bundle files exceed their bounds"))?;
            if files.len() >= MAX_FILES
                || output_bytes > MAX_BYTES
                || member.bytes.len() > MAX_FILE_BYTES
            {
                return Err(invalid("bundle files exceed their count or byte bounds"));
            }
            member_paths.push(member.path.clone());
            files.push(File {
                member,
                owner: id.into(),
            });
        }
        member_paths.sort();
        bindings.push(json!({"stable_id":id,"version":component["version"],
            "passport_digest":node["passport_digest"],"adaptation_id":adaptation["adaptation_id"],
            "projection_artifact":scope["projection_artifact"],"provider_component_kind":scope["provider_component_kind"],
            "projection_kind":scope["projection_kind"],"member_paths":member_paths}));
    }
    if bindings.is_empty() {
        return Err(invalid(
            "the declared empty setup has no installable bundle under provider protocol v3",
        ));
    }
    if !remaining_hosts.is_empty() {
        return Err(invalid(
            "host inputs must cover exactly the configuration contributions",
        ));
    }
    composition.validate()?;
    let profile = provider
        .profile(target.scope)
        .ok_or_else(|| invalid("provider profile missing"))?;
    if files.len() as u64 > profile["max_files"].as_u64().unwrap_or(0)
        || output_bytes as u64 > profile["max_bytes"].as_u64().unwrap_or(0)
    {
        return Err(invalid(
            "the whole bundle exceeds the selected provider profile limits",
        ));
    }
    files.sort_by(|a, b| a.member.path.cmp(&b.member.path));
    bindings.sort_by(|a, b| a["stable_id"].as_str().cmp(&b["stable_id"].as_str()));
    let input = json!({"setup":setup,"target":target,"provider_digest":digest::sha256(&canonical::bytes(provider.document())?),
        "hosts":host_identities,"assessment":assessment});
    let input_digest = digest::canonical("ai-stp:plan:v1", &input)?;
    let (manifest, archive) = package::build(
        &document,
        target,
        profile,
        &input_digest,
        bindings,
        &files,
        composition,
    )?;
    Ok(Bundle {
        artifact_digest: digest::sha256(&archive),
        manifest,
        archive,
        assessment,
    })
}

/// The public provider's credential filename boundary; no content inspection.
fn secret(path: &str) -> bool {
    let name = path.rsplit('/').next().unwrap_or("");
    [
        ".env",
        ".netrc",
        ".npmrc",
        "credentials",
        "id_rsa",
        "id_ed25519",
        ".pgpass",
    ]
    .contains(&name)
        || name.starts_with(".env.")
        || [".pem", ".key", ".p12", ".pfx", ".keystore"]
            .iter()
            .any(|suffix| name.ends_with(suffix))
}
