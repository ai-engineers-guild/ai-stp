//! Minimal authoring trees, planned byte-for-byte before creation.

pub mod setup;

use std::{collections::BTreeMap, path::Path};

use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::json;

use super::passports::Patch;
use crate::{
    canonical, digest,
    error::{Failure, Result},
    files::{self, tree},
};

const DRAFT: &str = "TODO(ai-stp-scaffold):";
pub const KINDS: &[&str] = &["instruction", "skill", "command", "agent", "cli"];
pub const LANGUAGES: &[&str] = &[
    "none",
    "python",
    "typescript",
    "javascript",
    "rust",
    "go",
    "dart-flutter",
];

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub component_type: String,
    pub name: String,
    pub language: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Plan<T = Request> {
    pub schema_version: u8,
    pub action: String,
    #[serde(
        serialize_with = "files::serialize_location",
        deserialize_with = "files::deserialize_location"
    )]
    pub output: String,
    pub parent_identity: [String; 2],
    pub request: T,
    /// Exact UTF-8 source, not an execution instruction or an arbitrary file upload.
    pub files: BTreeMap<String, String>,
}

impl<T: Serialize> Plan<T> {
    pub fn digest(&self) -> Result<String> {
        let domain = match self.action.as_str() {
            "component.scaffold" => "ai-stp:scaffold-plan:v1",
            "setup.scaffold" => "ai-stp:setup-scaffold-plan:v1",
            _ => return Err(invalid()),
        };
        digest::canonical(domain, &serde_json::to_value(self).map_err(|_| invalid())?)
    }
}

fn invalid() -> Failure {
    Failure::input("the scaffold request or exact source plan is invalid")
}

pub fn plan(output: &Path, request: Request) -> Result<Plan> {
    let files = render(&request)?;
    planned(output, "component.scaffold", request, files)
}

fn planned<T>(
    output: &Path,
    action: &str,
    request: T,
    files: BTreeMap<String, String>,
) -> Result<Plan<T>> {
    let (output, parent_identity) = tree::destination(output)?;
    match Path::new(&output).symlink_metadata() {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        _ => {
            return Err(Failure::precondition(
                "the scaffold destination exists or cannot be inspected",
            ));
        }
    }
    Ok(Plan {
        schema_version: 1,
        action: action.into(),
        output,
        parent_identity,
        request,
        files,
    })
}

pub fn read(path: &Path) -> Result<Plan> {
    read_plan(path)
}

fn read_plan<T: DeserializeOwned>(path: &Path) -> Result<Plan<T>> {
    serde_json::from_value(canonical::parse(&files::read(path, 64 * 1024)?)?).map_err(|_| invalid())
}

pub fn apply(plan: &Plan, expected_digest: &str) -> Result<serde_json::Value> {
    apply_exact(
        plan,
        expected_digest,
        "component.scaffold",
        render(&plan.request)?,
    )
}

fn apply_exact<T: Serialize>(
    plan: &Plan<T>,
    expected_digest: &str,
    action: &str,
    files: BTreeMap<String, String>,
) -> Result<serde_json::Value> {
    if plan.digest()? != expected_digest {
        return Err(Failure::precondition(
            "the scaffold plan digest changed before apply",
        ));
    }
    if plan.schema_version != 1 || plan.action != action || plan.files != files {
        return Err(invalid());
    }
    let (created, cleanup_pending) = tree::publish(
        &tree::Tree {
            output: &plan.output,
            parent_identity: &plan.parent_identity,
            files: &plan.files,
            purpose: tree::Purpose::Scaffold,
        },
        expected_digest,
    )?;
    Ok(json!({"schema_version":1,"plan_digest":expected_digest,
        "output":serde_json::to_value(plan).map_err(|_|invalid())?["output"],
        "files_written":if created { plan.files.len() } else { 0 },
        "outcome":if created { "created" } else { "already_matches" },
        "publication_ready":false,"staging_cleanup_pending":cleanup_pending}))
}

fn encoded(value: serde_json::Value) -> Result<String> {
    String::from_utf8(canonical::bytes(&value)?).map_err(|_| invalid())
}

fn valid_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && !name.starts_with('-')
        && !name.ends_with('-')
        && name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

pub(super) fn render(request: &Request) -> Result<BTreeMap<String, String>> {
    let Request {
        name,
        component_type: kind,
        language,
    } = request;
    if !KINDS.contains(&kind.as_str())
        || !LANGUAGES.contains(&language.as_str())
        || (kind == "cli") == (language == "none")
        || !valid_name(name)
        || (kind == "skill" && name.contains("--"))
    {
        return Err(invalid());
    }
    let (entry, source, managed) = match kind.as_str() {
        "skill" => (
            "SKILL.md".into(),
            format!(
                "---\nname: {name}\ndescription: \"{DRAFT} describe the skill.\"\n---\n\n# {name}\n\n{DRAFT} implement the skill.\n"
            ),
            format!("skills/{name}"),
        ),
        "instruction" => (
            "AGENTS.md".into(),
            format!("# {name}\n\n{DRAFT} write the instructions.\n"),
            "instructions/AGENTS.md".into(),
        ),
        "command" | "agent" => {
            let leaf = format!("{name}.md");
            (
                leaf.clone(),
                format!("# {name}\n\n{DRAFT} define the {kind} behavior.\n"),
                format!("{kind}s/{leaf}"),
            )
        }
        "cli" => {
            let (extension, source) = program(language)?;
            (
                format!("src/main.{extension}"),
                source,
                format!("bin/{name}"),
            )
        }
        _ => return Err(invalid()),
    };
    let descriptor = json!({"schema_version":1,"template_version":"component-scaffold/7",
        "generator_version":"ai-stp/7","component_type":kind,"language":language,
        "harness_variant":"portable","executable":kind=="cli","standard_family":"ai-stp-standard/1",
        "additional_harnesses":[]});
    let patch = json!({"name":name,"component_type":kind,"description":format!("{DRAFT} describe the component."),
        "projection_kind":if kind=="cli" {"package"}else{"native_files"},
        "license":{"spdx_id":"NOASSERTION","redistribution_allowed":false},
        "managed_paths":[managed],"native_ids":[name],"entry_points":[entry],"harness_variants":["portable"]});
    Patch::try_from(patch.clone())?;
    Ok(BTreeMap::from([
        (".ai-stp-template.json".into(), encoded(descriptor)?),
        ("component-passport.json".into(), encoded(patch)?),
        (
            ".gitignore".into(),
            ".env\n.env.*\n__pycache__/\n*.pyc\nnode_modules/\ntarget/\n.dart_tool/\nbuild/\n"
                .into(),
        ),
        (format!("source/{entry}"), source),
    ]))
}

fn program(language: &str) -> Result<(&'static str, String)> {
    let message = format!("{DRAFT} implement this program before use.");
    Ok(match language {
        "python" => (
            "py",
            format!(
                "import sys\n\n\ndef main() -> int:\n    print({message:?}, file=sys.stderr)\n    return 1\n\n\nif __name__ == \"__main__\":\n    raise SystemExit(main())\n"
            ),
        ),
        "javascript" => (
            "js",
            format!("console.error({message:?});\nprocess.exitCode = 1;\n"),
        ),
        "typescript" => (
            "ts",
            format!("console.error({message:?});\nprocess.exitCode = 1;\n"),
        ),
        "rust" => (
            "rs",
            format!(
                "fn main() -> std::process::ExitCode {{\n    eprintln!({message:?});\n    std::process::ExitCode::FAILURE\n}}\n"
            ),
        ),
        "go" => (
            "go",
            format!(
                "package main\n\nimport (\n    \"fmt\"\n    \"os\"\n)\n\nfunc main() {{\n    fmt.Fprintln(os.Stderr, {message:?})\n    os.Exit(1)\n}}\n"
            ),
        ),
        "dart-flutter" => (
            "dart",
            format!(
                "import 'dart:io';\n\nvoid main() {{\n  stderr.writeln({message:?});\n  exitCode = 1;\n}}\n"
            ),
        ),
        _ => return Err(invalid()),
    })
}
