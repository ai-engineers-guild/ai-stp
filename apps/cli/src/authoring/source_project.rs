//! One bounded authoring snapshot; metadata never becomes native source content.

use std::{collections::BTreeSet, path::Path};

use pulldown_cmark::{Event, Parser, Tag, TagEnd};
use serde_json::{Value, json};

use super::{passports::Patch, scaffold, source};
use crate::{
    artifacts::{self, Member},
    canonical, digest,
    error::{Failure, Result},
};

/// A local snapshot, not executable validation, publication approval or trust evidence.
pub struct Captured {
    pub patch: Patch,
    pub files: Vec<Member>,
    pub report: Value,
}

fn invalid() -> Failure {
    Failure::precondition(
        "the authoring project has an invalid descriptor, passport or source layout",
    )
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(invalid)
}

pub(super) fn unfinished(path: &str, bytes: &[u8]) -> bool {
    let Ok(text) = std::str::from_utf8(bytes) else {
        return false;
    };
    const MARKER: &str = "TODO(ai-stp-scaffold):";
    if !matches!(
        Path::new(path).extension().and_then(|s| s.to_str()),
        Some("md" | "mdc" | "markdown")
    ) {
        return text.contains(MARKER);
    }
    let mut code = false;
    Parser::new(text).any(|event| match event {
        Event::Start(Tag::CodeBlock(_)) => {
            code = true;
            false
        }
        Event::End(TagEnd::CodeBlock) => {
            code = false;
            false
        }
        Event::Text(text) if !code => text.contains(MARKER),
        _ => false,
    })
}

pub fn capture(root: &Path) -> Result<Captured> {
    let members = source::project(root)?;
    let bytes = |path: &str| {
        members
            .iter()
            .find(|member| member.path == path)
            .map(|member| member.bytes.as_slice())
            .ok_or_else(invalid)
    };
    let descriptor = canonical::parse(bytes(".ai-stp-template.json")?)?;
    let patch = Patch::parse(bytes("component-passport.json")?)?;
    let values: Value = patch.clone().into();
    let request = scaffold::Request {
        component_type: text(&descriptor, "component_type")?.into(),
        name: text(&values, "name")?.into(),
        language: text(&descriptor, "language")?.into(),
    };
    let rendered = scaffold::render(&request)?;
    // The generator owns its descriptor. Unsupported generations never inherit /7 semantics.
    if descriptor != canonical::parse(rendered[".ai-stp-template.json"].as_bytes())?
        || values["component_type"] != request.component_type
    {
        return Err(invalid());
    }
    let entries = values["entry_points"]
        .as_array()
        .filter(|entries| !entries.is_empty() && entries.len() <= 64)
        .ok_or_else(invalid)?;
    let mut entry_points = BTreeSet::new();
    for entry in entries {
        let entry = entry.as_str().ok_or_else(invalid)?;
        if !artifacts::safe_path(entry) || !entry_points.insert(entry.to_owned()) {
            return Err(invalid());
        }
    }
    let snapshot_digest = digest::bytes("ai-stp:artifact:v1", &artifacts::encode_tree(&members)?)?;
    let mut files: Vec<_> = members
        .into_iter()
        .filter_map(|mut member| {
            member.path = member.path.strip_prefix("source/")?.into();
            Some(member)
        })
        .collect();
    files.sort_by(|a, b| a.path.cmp(&b.path));
    let mut issues = Vec::new();
    if files.is_empty() {
        issues.push(json!({"code":"source_empty","path":"source"}));
    }
    for entry in &entry_points {
        match files.iter().find(|file| &file.path == entry) {
            None => {
                issues.push(json!({"code":"entry_point_missing","path":format!("source/{entry}")}))
            }
            Some(file) if file.bytes.iter().all(u8::is_ascii_whitespace) => {
                issues.push(json!({"code":"entry_point_empty","path":format!("source/{entry}")}))
            }
            Some(file) if std::str::from_utf8(&file.bytes).is_err() => {
                issues.push(json!({"code":"entry_point_not_utf8","path":format!("source/{entry}")}))
            }
            _ => {}
        }
    }
    if values["description"].as_str().is_none_or(|description| {
        description.trim().is_empty() || unfinished("description.md", description.as_bytes())
    }) {
        issues.push(json!({"code":"description_incomplete","path":"component-passport.json"}));
    }
    for file in &files {
        if unfinished(&file.path, &file.bytes) {
            issues.push(json!({"code":"scaffold_marker","path":format!("source/{}",file.path)}));
        }
    }
    let source_digest = digest::bytes("ai-stp:artifact:v1", &artifacts::encode_tree(&files)?)?;
    let inventory = files
        .iter()
        .map(|file| {
            Ok(json!({"path":file.path,"mode":file.mode,
        "size_bytes":file.bytes.len(),"digest":digest::bytes("ai-stp:artifact:v1",&file.bytes)?}))
        })
        .collect::<Result<Vec<_>>>()?;
    let report = json!({"schema_version":1,"template_version":descriptor["template_version"],
        "component_type":request.component_type,"name":request.name,"language":request.language,
        "snapshot_digest":snapshot_digest,"source_digest":source_digest,"source_format":artifacts::TREE_FORMAT,
        "entry_points":entry_points,"files":inventory,"source_ready":issues.is_empty(),"issues":issues,
        "execution":"not_run","publication":"not_assessed"});
    Ok(Captured {
        patch,
        files,
        report,
    })
}

pub fn inspect(root: &Path) -> Result<Value> {
    Ok(capture(root)?.report)
}
