//! Deterministic provider bundles published into one new review directory.

use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Owner, Selector, access, inputs, owner, program, with_provider};
use crate::{
    authoring::{Identity, setups::Source},
    bundle::{self, hosts},
    canonical, digest,
    error::{Failure, Result},
    files::{self, tree},
    objects::Objects,
    projection::Scope,
    selection::graph,
};

const MAX_PLAN: u64 = 64 * 1024;

pub struct Request<'a> {
    pub source: Source,
    pub scope: Scope,
    pub provider_version: &'a str,
    pub target: Option<&'a Path>,
    pub output: &'a Path,
    pub harness_executable: Option<&'a Path>,
    pub access: Option<&'a Path>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema_version: u32,
    action: String,
    identity: Identity,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    state_parent: PathBuf,
    source: Source,
    selector: Selector,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    program_observation_digest: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    access: Option<access::Plan>,
    host: Option<hosts::Binding>,
    #[serde(
        serialize_with = "files::serialize_location",
        deserialize_with = "files::deserialize_location"
    )]
    output: String,
    parent_identity: [String; 2],
    input_digest: String,
    bundle_digest: String,
    artifact_digest: String,
    artifact_bytes: u64,
}

fn invalid() -> Failure {
    Failure::precondition("the exact bundle plan, source, host inputs or destination changed")
}

fn value(input: &impl Serialize) -> Result<Value> {
    serde_json::to_value(input).map_err(|_| invalid())
}

fn field<'a>(input: &'a Value, name: &str) -> Result<&'a str> {
    input[name].as_str().ok_or_else(invalid)
}

impl Plan {
    fn digest(&self) -> Result<String> {
        let value = value(self)?;
        if canonical::bytes(&value)?.len() as u64 > MAX_PLAN {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }
}

fn setup(identity: &Owner, source: &Source) -> Result<Value> {
    let mut store = identity.planning()?;
    store.transaction(|t| {
        let document = Objects { connection: t }.exact_version(
            &source.stable_id,
            &source.version,
            Some(&source.passport_digest),
        )?;
        if document["kind"] != "setup" {
            return Err(invalid());
        }
        let graph = graph::exact(t, &[value(source)?])?;
        if graph["resolved"] != true {
            return Err(invalid().with_details([("graph".into(), graph)]));
        }
        Ok(document)
    })
}

/// Network work precedes the registry lock. The read transaction and held
/// target survive compilation and publication, so local writers cannot change
/// registry evidence between verification and this artifact's creation.
fn with_bundle(
    parent: &Path,
    source: &Source,
    selector: &Selector,
    identity: &Owner,
    host: &hosts::Root,
    access: access::Intent<'_>,
    finish: impl FnOnce(bundle::Bundle, Value, Option<String>, &access::Observed) -> Result<Value>,
) -> Result<Value> {
    if setup(identity, source)?["harness_id"] != selector.harness_id {
        return Err(invalid());
    }
    let reference = value(source)?;
    with_provider(parent, selector, identity, |provider, artifact, report| {
        let access =
            access::Observed::capture(parent, identity, &[vec![reference.clone()]], access)?;
        let mut store = identity.planning()?;
        store.transaction(|t| {
            let (target, program) = selector.observe(t, parent, identity)?;
            let mut observed = inputs(t, std::slice::from_ref(&reference), target)?;
            access.apply(&mut observed)?;
            let paths = hosts::paths(t, &reference, &selector.harness_id, selector.scope)?;
            let before = host.read(&paths)?;
            let bundle = bundle::compile_snapshot(
                t,
                &reference,
                &observed.target,
                &observed.evidence,
                provider,
                &before,
            )?;
            if host.read(&paths)? != before {
                return Err(invalid());
            }
            artifact.executable()?;
            access.revalidate()?;
            finish(bundle, report, program, &access)
        })
    })
}

pub fn plan(parent: &Path, request: Request<'_>) -> Result<Value> {
    let Request {
        source,
        scope,
        provider_version,
        target,
        output,
        harness_executable,
        access,
    } = request;
    let access_request = access::Request::read(access)?;
    let state_parent = PathBuf::from(files::location(parent)?);
    let identity = owner(&state_parent)?;
    let document = setup(&identity, &source)?;
    let selector = Selector {
        harness_id: field(&document, "harness_id")?.into(),
        scope,
        provider_version: provider_version.into(),
        harness_executable: harness_executable.map(|p| program::Executable(p.into())),
    };
    selector.validate()?;
    let (output, parent_identity) = tree::destination(output)?;
    match Path::new(&output).symlink_metadata() {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
        _ => {
            return Err(Failure::precondition(
                "the bundle output directory must be unused",
            ));
        }
    }
    let output_parent = Path::new(&output).parent().ok_or_else(invalid)?;
    let host = hosts::Root::open(target, &state_parent, output_parent)?;
    let binding = host.binding()?;
    with_bundle(
        &state_parent,
        &source,
        &selector,
        &identity,
        &host,
        access::Intent::Review(&access_request),
        |bundle, provider, program, access| {
            if host.binding()? != binding {
                return Err(invalid());
            }
            host.outside(output_parent)?;
            let plan = Plan {
                schema_version: 1,
                action: "selection.bundle".into(),
                identity: identity.clone(),
                state_parent: state_parent.clone(),
                source: source.clone(),
                selector: selector.clone(),
                program_observation_digest: program,
                access: access.plan()?,
                host: binding.clone(),
                output: output.clone(),
                parent_identity,
                input_digest: field(&bundle.manifest, "input_digest")?.into(),
                bundle_digest: field(&bundle.manifest, "bundle_digest")?.into(),
                artifact_digest: bundle.artifact_digest,
                artifact_bytes: bundle.archive.len() as u64,
            };
            let mut result = json!({"plan_digest":plan.digest()?,"plan":plan,"manifest":bundle.manifest,
                "assessment":bundle.assessment,"provider":provider,"harness_written":false});
            if let Some(observation) = access.report()? {
                result["access_observation"] = observation;
            }
            Ok(result)
        },
    )
}

pub fn apply(path: &Path, expected: &str) -> Result<Value> {
    let plan: Plan = serde_json::from_value(canonical::parse(&files::read(path, MAX_PLAN)?)?)
        .map_err(|_| Failure::input("the bundle plan is not a closed bounded document"))?;
    if plan.schema_version != 1
        || plan.action != "selection.bundle"
        || !plan.state_parent.is_absolute()
        || plan.digest()? != expected
    {
        return Err(invalid());
    }
    let identity = owner(&plan.state_parent)?;
    if plan.identity != *identity
        || tree::destination(Path::new(&plan.output))?
            != (plan.output.clone(), plan.parent_identity.clone())
    {
        return Err(invalid());
    }
    plan.selector.validate()?;
    let output_parent = Path::new(&plan.output).parent().ok_or_else(invalid)?;
    let host = hosts::Root::open(
        plan.host.as_ref().map(|b| b.path.as_path()),
        &plan.state_parent,
        output_parent,
    )?;
    if host.binding()? != plan.host {
        return Err(invalid());
    }
    with_bundle(
        &plan.state_parent,
        &plan.source,
        &plan.selector,
        &identity,
        &host,
        access::Intent::Apply(plan.access.as_ref()),
        |bundle, _, program, access| {
            program::matches(&program, &plan.program_observation_digest)?;
            if bundle.artifact_digest != plan.artifact_digest
                || bundle.archive.len() as u64 != plan.artifact_bytes
                || bundle.manifest["input_digest"] != plan.input_digest
                || bundle.manifest["bundle_digest"] != plan.bundle_digest
                || host.binding()? != plan.host
            {
                return Err(invalid());
            }
            host.outside(output_parent)?;
            access.revalidate()?;
            let files = BTreeMap::from([("bundle.zip".into(), bundle.archive)]);
            let (created, cleanup_pending) = tree::publish(
                &tree::Tree {
                    output: &plan.output,
                    parent_identity: &plan.parent_identity,
                    files: &files,
                    purpose: tree::Purpose::ProviderBundle,
                },
                expected,
            )?;
            Ok(
                json!({"schema_version":1,"plan_digest":expected,"output":value(&plan)?["output"],
            "filename":"bundle.zip","artifact_digest":plan.artifact_digest,"artifact_bytes":plan.artifact_bytes,
            "bundle_digest":plan.bundle_digest,"input_digest":plan.input_digest,
            "outcome":if created {"created"} else {"already_matches"},
            "staging_cleanup_pending":cleanup_pending,"installation_authorized":false,"harness_written":false}),
            )
        },
    )
}
