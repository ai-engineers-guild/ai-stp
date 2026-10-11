//! Deterministic provider bundles published into one new review directory.

use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Selector, inputs, owner, with_provider};
use crate::{
    authoring::{Identity, setups::Source},
    bundle::{self, hosts},
    canonical, digest,
    error::{Failure, Result},
    files::{self, tree},
    objects::Objects,
    projection::Scope,
    selection::graph,
    store::Store,
};

const MAX_PLAN: u64 = 16 * 1024;

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

fn setup(parent: &Path, source: &Source) -> Result<Value> {
    let mut store = Store::planning(parent)?;
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
    identity: &Identity,
    host: &hosts::Root,
    finish: impl FnOnce(bundle::Bundle, Value) -> Result<Value>,
) -> Result<Value> {
    if setup(parent, source)?["harness_id"] != selector.harness_id {
        return Err(invalid());
    }
    let reference = value(source)?;
    with_provider(parent, selector, identity, |provider, artifact, report| {
        let mut store = Store::planning(parent)?;
        store.transaction(|t| {
            let target = selector.target(identity)?;
            let observed = inputs(t, std::slice::from_ref(&reference), target)?;
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
            finish(bundle, report)
        })
    })
}

pub fn plan(
    parent: &Path,
    source: Source,
    scope: Scope,
    provider_version: &str,
    target: Option<&Path>,
    output: &Path,
) -> Result<Value> {
    let state_parent = PathBuf::from(files::location(parent)?);
    let identity = owner(&state_parent)?;
    let document = setup(&state_parent, &source)?;
    let selector = Selector {
        harness_id: field(&document, "harness_id")?.into(),
        scope,
        provider_version: provider_version.into(),
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
        |bundle, provider| {
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
                host: binding.clone(),
                output: output.clone(),
                parent_identity,
                input_digest: field(&bundle.manifest, "input_digest")?.into(),
                bundle_digest: field(&bundle.manifest, "bundle_digest")?.into(),
                artifact_digest: bundle.artifact_digest,
                artifact_bytes: bundle.archive.len() as u64,
            };
            Ok(
                json!({"plan_digest":plan.digest()?,"plan":plan,"manifest":bundle.manifest,
            "assessment":bundle.assessment,"provider":provider,"harness_written":false}),
            )
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
        || plan.identity != owner(&plan.state_parent)?
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
        &plan.identity,
        &host,
        |bundle, _| {
            if bundle.artifact_digest != plan.artifact_digest
                || bundle.archive.len() as u64 != plan.artifact_bytes
                || bundle.manifest["input_digest"] != plan.input_digest
                || bundle.manifest["bundle_digest"] != plan.bundle_digest
                || host.binding()? != plan.host
            {
                return Err(invalid());
            }
            host.outside(output_parent)?;
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
