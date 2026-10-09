//! Exact setup review trees. Export reads retained state and writes one new directory.

use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Source, exact};
use crate::{
    canonical, digest,
    error::{Failure, Result},
    files::{self, tree},
    store::{Store, revisions},
};

const MAX_PLAN: u64 = 8 * 1024 * 1024;

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u8,
    pub action: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub state_parent: PathBuf,
    pub source: Source,
    #[serde(
        serialize_with = "files::serialize_location",
        deserialize_with = "files::deserialize_location"
    )]
    pub output: String,
    pub parent_identity: [String; 2],
    pub files: BTreeMap<String, String>,
}

fn invalid() -> Failure {
    Failure::input("the setup export violates its exact source or review tree contract")
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        let bytes = canonical::bytes(&serde_json::to_value(self).map_err(|_| invalid())?)?;
        if bytes.len() as u64 > MAX_PLAN {
            return Err(invalid());
        }
        digest::bytes("ai-stp:plan:v1", &bytes)
    }
}

fn encoded(value: &Value) -> Result<String> {
    String::from_utf8(canonical::bytes(value)?).map_err(|_| invalid())
}

fn render(connection: &Connection, source: &Source) -> Result<BTreeMap<String, String>> {
    let document = exact(connection, source)?;
    let definition_digest = document["artifact"]["digest"]
        .as_str()
        .ok_or_else(invalid)?;
    let definition = revisions::read_content(connection, definition_digest)?;
    let mut files: BTreeMap<String, String> = BTreeMap::from([
        ("setup-passport.json".into(), encoded(&document)?),
        (
            "setup-definition.json".into(),
            String::from_utf8(definition).map_err(|_| invalid())?,
        ),
    ]);
    let hashes = files
        .iter()
        .map(|(name, bytes)| {
            Ok((
                name.clone(),
                digest::bytes("ai-stp:artifact:v1", bytes.as_bytes())?,
            ))
        })
        .collect::<Result<BTreeMap<String, String>>>()?;
    let mut manifest = json!({"schema_id":"ai-stp-setup-export/1",
        "setup_id":source.stable_id,"version":source.version,
        "passport_digest":source.passport_digest,"definition_digest":definition_digest,"files":hashes});
    manifest["export_digest"] = digest::canonical("ai-stp:setup-export:v1", &manifest)?.into();
    files.insert("export-manifest.json".into(), encoded(&manifest)?);
    Ok(files)
}

pub fn plan(parent: &Path, source: Source, output: &Path) -> Result<Plan> {
    let state_parent = PathBuf::from(files::location(parent)?);
    let (output, parent_identity) = tree::destination(output)?;
    match Path::new(&output).symlink_metadata() {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        _ => {
            return Err(Failure::precondition(
                "the export destination must be unused",
            ));
        }
    }
    let files = Store::planning(&state_parent)?.transaction(|t| render(t, &source))?;
    let plan = Plan {
        schema_version: 1,
        action: "setup.export".into(),
        state_parent,
        source,
        output,
        parent_identity,
        files,
    };
    plan.digest()?;
    Ok(plan)
}

pub fn read(path: &Path) -> Result<Plan> {
    serde_json::from_value(canonical::parse(&files::read(path, MAX_PLAN)?)?).map_err(|_| invalid())
}

pub fn apply(plan: &Plan, expected_digest: &str) -> Result<Value> {
    if plan.schema_version != 1
        || plan.action != "setup.export"
        || !plan.state_parent.is_absolute()
        || plan.digest()? != expected_digest
    {
        return Err(invalid());
    }
    // Complete the read snapshot before touching the destination. No credentials,
    // writable registry transaction or source paths are required by an export.
    let observed = Store::planning(&plan.state_parent)?.transaction(|t| render(t, &plan.source))?;
    if plan.files != observed {
        return Err(invalid());
    }
    let manifest = canonical::parse(plan.files["export-manifest.json"].as_bytes())?;
    let (created, cleanup_pending) = tree::publish(
        &tree::Tree {
            output: &plan.output,
            parent_identity: &plan.parent_identity,
            files: &plan.files,
            purpose: tree::Purpose::SetupExport,
        },
        expected_digest,
    )?;
    Ok(json!({"schema_version":1,"plan_digest":expected_digest,
        "setup_id":plan.source.stable_id,"version":plan.source.version,
        "passport_digest":plan.source.passport_digest,"definition_digest":manifest["definition_digest"],
        "export_digest":manifest["export_digest"],"export_format":"ai-stp-setup-export/1",
        "output":serde_json::to_value(plan).map_err(|_| invalid())?["output"],
        "files_written":if created {plan.files.len()} else {0},
        "outcome":if created {"created"} else {"already_matches"},
        "result":"local_setup_definition","physical_target_tree_created":false,
        "staging_cleanup_pending":cleanup_pending}))
}
