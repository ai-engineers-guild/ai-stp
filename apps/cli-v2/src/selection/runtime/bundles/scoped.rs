//! Publish all scope packages from one qualified graph and one review plan.

use super::{
    Identity, Owner, Selector, Source, access, bundle, canonical, digest, files, hosts, inputs,
    owner, program, setup, tree, value, with_provider,
};
use crate::{
    error::{Failure, Result},
    projection::Scope,
    provider::managed,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

const LIMIT: u64 = 256 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    source: Source,
    targets: BTreeMap<Scope, PathBuf>,
    #[serde(default)]
    placements: BTreeMap<String, Scope>,
    output: PathBuf,
    provider_version: Option<String>,
    harness_executable: Option<program::Executable>,
    #[serde(default)]
    access: access::Request,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Inputs {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    state_parent: PathBuf,
    source: Source,
    selector: Selector,
    targets: BTreeMap<Scope, hosts::Binding>,
    placements: BTreeMap<String, Scope>,
    #[serde(
        serialize_with = "files::serialize_location",
        deserialize_with = "files::deserialize_location"
    )]
    output: String,
    parent_identity: [String; 2],
}

#[derive(Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct Package {
    input_digest: String,
    bundle_digest: String,
    artifact_digest: String,
    artifact_bytes: u64,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema_version: u32,
    action: String,
    identity: Identity,
    inputs: Inputs,
    program_observation_digest: Option<String>,
    access: Option<access::Plan>,
    packages: BTreeMap<Scope, Package>,
}

fn invalid() -> Failure {
    Failure::precondition("the complete scoped bundle plan, graph, roots or output changed")
}

impl Plan {
    fn digest(&self) -> Result<String> {
        let value = value(self)?;
        if canonical::bytes(&value)?.len() as u64 > LIMIT {
            return Err(invalid());
        }
        digest::canonical("ai-stp:plan:v1", &value)
    }
}

fn package(bundle: &bundle::Bundle) -> Result<Package> {
    let field = |key| {
        bundle.manifest[key]
            .as_str()
            .map(str::to_owned)
            .ok_or_else(invalid)
    };
    Ok(Package {
        input_digest: field("input_digest")?,
        bundle_digest: field("bundle_digest")?,
        artifact_digest: bundle.artifact_digest.clone(),
        artifact_bytes: bundle.archive.len() as u64,
    })
}

fn open(inputs: &Inputs) -> Result<BTreeMap<Scope, hosts::Root>> {
    if !(1..=3).contains(&inputs.targets.len())
        || inputs.placements.len() > 512
        || !inputs.state_parent.is_absolute()
        || !Path::new(&inputs.output).is_absolute()
        || tree::destination(Path::new(&inputs.output))?
            != (inputs.output.clone(), inputs.parent_identity.clone())
        || inputs.targets.keys().next().copied() != Some(inputs.selector.scope)
    {
        return Err(invalid());
    }
    inputs.selector.validate()?;
    let output_parent = Path::new(&inputs.output).parent().ok_or_else(invalid)?;
    let mut roots = BTreeMap::new();
    for (scope, binding) in &inputs.targets {
        if !binding.path.is_absolute() {
            return Err(invalid());
        }
        let root = hosts::Root::open(Some(&binding.path), &inputs.state_parent, output_parent)?;
        if root.binding()?.as_ref() != Some(binding) {
            return Err(invalid());
        }
        for (other_scope, other) in &inputs.targets {
            if other_scope != scope {
                root.outside(&other.path).map_err(|_| invalid())?;
            }
        }
        roots.insert(*scope, root);
    }
    Ok(roots)
}

fn compile<T>(
    input: &Inputs,
    identity: &Owner,
    roots: &BTreeMap<Scope, hosts::Root>,
    access_intent: access::Intent<'_>,
    finish: impl FnOnce(bundle::scopes::Compiled, Value, Option<String>, &access::Observed) -> Result<T>,
) -> Result<T> {
    if setup(identity, &input.source)?["harness_id"] != input.selector.harness_id {
        return Err(invalid());
    }
    let reference = value(&input.source)?;
    with_provider(
        &input.state_parent,
        &input.selector,
        identity,
        |provider, artifact, report| {
            let access = access::Observed::capture(
                &input.state_parent,
                identity,
                &[vec![reference.clone()]],
                access_intent,
            )?;
            let mut store = identity.planning()?;
            store.transaction(|connection| {
                let (target, program) =
                    input
                        .selector
                        .observe(connection, &input.state_parent, identity)?;
                let mut observed = inputs(connection, std::slice::from_ref(&reference), target)?;
                access.apply(&mut observed)?;
                let paths = bundle::scopes::paths(
                    connection,
                    &reference,
                    &input.selector.harness_id,
                    &roots.keys().copied().collect(),
                    &input.placements,
                )?;
                let mut before = BTreeMap::new();
                for (scope, root) in roots {
                    before.insert(*scope, root.read(paths.get(scope).ok_or_else(invalid)?)?);
                }
                let built = bundle::scopes::compile_snapshot(
                    connection,
                    &reference,
                    &observed.target,
                    &observed.evidence,
                    provider,
                    &before,
                    &input.placements,
                )?;
                for (scope, root) in roots {
                    if root.read(paths.get(scope).ok_or_else(invalid)?)?
                        != *before.get(scope).ok_or_else(invalid)?
                        || root.binding()?.as_ref() != input.targets.get(scope)
                    {
                        return Err(invalid());
                    }
                    root.outside(Path::new(&input.output).parent().ok_or_else(invalid)?)?;
                }
                artifact.executable()?;
                access.revalidate()?;
                finish(built, report, program, &access)
            })
        },
    )
}

pub fn plan(parent: &Path, path: &Path) -> Result<Value> {
    plan_value(parent, crate::wire::parse(&files::read(path, LIMIT)?)?)
}

pub(crate) fn plan_value(parent: &Path, value: Value) -> Result<Value> {
    if canonical::bytes(&value)?.len() as u64 > LIMIT {
        return Err(invalid());
    }
    let request: Request = serde_json::from_value(value).map_err(|_| invalid())?;
    request.access.validate()?;
    if !(1..=3).contains(&request.targets.len())
        || request.targets.values().any(|path| !path.is_absolute())
    {
        return Err(invalid());
    }
    let state_parent = PathBuf::from(files::location(parent)?);
    let identity = owner(&state_parent)?;
    let document = setup(&identity, &request.source)?;
    let (output, parent_identity) = tree::destination(&request.output)?;
    match Path::new(&output).symlink_metadata() {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
        _ => {
            return Err(Failure::precondition(
                "the scoped bundle output must be unused",
            ));
        }
    }
    let output_parent = Path::new(&output).parent().ok_or_else(invalid)?;
    let mut targets = BTreeMap::new();
    for (scope, path) in &request.targets {
        let root = hosts::Root::open(Some(path), &state_parent, output_parent)?;
        targets.insert(*scope, root.binding()?.ok_or_else(invalid)?);
    }
    let inputs = Inputs {
        state_parent,
        source: request.source,
        selector: Selector {
            harness_id: document["harness_id"].as_str().ok_or_else(invalid)?.into(),
            scope: *targets.keys().next().ok_or_else(invalid)?,
            provider_version: managed::version(request.provider_version.as_deref())?.into(),
            harness_executable: request.harness_executable,
        },
        targets,
        placements: request.placements,
        output,
        parent_identity,
    };
    let roots = open(&inputs)?;
    compile(
        &inputs,
        &identity,
        &roots,
        access::Intent::Review(&request.access),
        |built, provider, program, access| {
            let packages = built
                .bundles
                .iter()
                .map(|(scope, bundle)| Ok((*scope, package(bundle)?)))
                .collect::<Result<_>>()?;
            let manifests: BTreeMap<_, _> = built
                .bundles
                .iter()
                .map(|(scope, b)| (*scope, &b.manifest))
                .collect();
            let plan = Plan {
                schema_version: 1,
                action: "selection.scoped_bundles".into(),
                identity: identity.clone(),
                inputs: inputs.clone(),
                program_observation_digest: program,
                access: access.plan()?,
                packages,
            };
            let mut result = json!({"plan":plan,"plan_digest":plan.digest()?,"manifests":manifests,
            "assessment":built.assessment,"provider":provider,"harness_written":false});
            if let Some(observation) = access.report()? {
                result["access_observation"] = observation;
            }
            Ok(result)
        },
    )
}

pub fn apply(path: &Path, expected: &str) -> Result<Value> {
    apply_value(crate::wire::parse(&files::read(path, LIMIT)?)?, expected)
}

pub(crate) fn apply_value(document: Value, expected: &str) -> Result<Value> {
    if canonical::bytes(&document)?.len() as u64 > LIMIT {
        return Err(invalid());
    }
    let plan: Plan = serde_json::from_value(document).map_err(|_| invalid())?;
    if plan.schema_version != 1
        || plan.action != "selection.scoped_bundles"
        || plan.digest()? != expected
    {
        return Err(invalid());
    }
    let identity = owner(&plan.inputs.state_parent)?;
    if plan.identity != *identity {
        return Err(invalid());
    }
    let roots = open(&plan.inputs)?;
    compile(
        &plan.inputs,
        &identity,
        &roots,
        access::Intent::Apply(plan.access.as_ref()),
        |built, _, program, access| {
            program::matches(&program, &plan.program_observation_digest)?;
            let packages: BTreeMap<_, _> = built
                .bundles
                .iter()
                .map(|(scope, bundle)| Ok((*scope, package(bundle)?)))
                .collect::<Result<_>>()?;
            if packages != plan.packages {
                return Err(invalid());
            }
            let files: BTreeMap<_, _> = built
                .bundles
                .into_iter()
                .map(|(scope, bundle)| (format!("{}.zip", scope.as_str()), bundle.archive))
                .collect();
            access.revalidate()?;
            let (created, cleanup_pending) = tree::publish(
                &tree::Tree {
                    output: &plan.inputs.output,
                    parent_identity: &plan.inputs.parent_identity,
                    files: &files,
                    purpose: tree::Purpose::ProviderBundle,
                },
                expected,
            )?;
            Ok(
                json!({"schema_version":1,"plan_digest":expected,"output":value(&plan.inputs)?["output"],"packages":packages,
            "outcome":if created {"created"} else {"already_matches"},"staging_cleanup_pending":cleanup_pending,
            "installation_authorized":false,"harness_written":false}),
            )
        },
    )
}
