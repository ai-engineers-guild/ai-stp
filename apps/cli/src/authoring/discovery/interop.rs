//! Third-party metadata is a local claim, never repository or publisher verification.

use super::{Candidate, Diagnostic, Dir, Discovery, Path, Scanner, Scope, refused};
use crate::{canonical, digest, error::Result, files, projects};
use serde_json::{Value, json};
use std::collections::BTreeSet;

const NORI: &str = "nori.json";
const LOCK: &str = ".agents/.skill-lock.json";

struct Entry {
    path: String,
    kind: &'static str,
    name: String,
    version: Option<String>,
    claim: Option<String>,
}

fn text(value: &Value) -> Result<&str> {
    value
        .as_str()
        .filter(|value| {
            !value.trim().is_empty() && value.len() <= 512 && !value.chars().any(char::is_control)
        })
        .ok_or_else(refused)
}

fn slug(value: &Value) -> Result<&str> {
    let value = text(value)?;
    if value.len() > 255
        || !value.as_bytes()[0].is_ascii_alphanumeric()
        || !value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        || projects::secret_name(value)
    {
        return Err(refused());
    }
    Ok(value)
}

fn skill_name(value: &str) -> Result<String> {
    text(&json!(value))?;
    let mut name = String::new();
    let mut replacing = false;
    for ch in value.to_lowercase().chars() {
        if ch.is_ascii_lowercase() || ch.is_ascii_digit() || matches!(ch, '.' | '_') {
            name.push(ch);
            replacing = false;
        } else if !replacing {
            name.push('-');
            replacing = true;
        }
    }
    let mut name = name.trim_matches(['.', '-']).to_owned();
    name.truncate(255);
    if name.is_empty() || projects::secret_name(&name) {
        return Err(refused());
    }
    Ok(name)
}

fn nori(document: &Value) -> Result<Vec<Entry>> {
    let name = text(&document["name"])?;
    let version = text(&document["version"])?;
    let mut entries = Vec::new();
    if matches!(document["type"].as_str(), Some("skill" | "inlined-skill")) {
        entries.push(Entry {
            path: ".".into(),
            kind: "skill",
            name: name.into(),
            version: Some(version.into()),
            claim: None,
        });
    }
    for (field, key, kind) in [
        ("skills", "id", "skill"),
        ("subagents", "id", "agent"),
        ("slashcommands", "command", "command"),
    ] {
        if document[field].is_null() {
            continue;
        }
        let records = document[field].as_array().ok_or_else(refused)?;
        if entries.len() + records.len() > 500 {
            return Err(refused());
        }
        for record in records {
            let id = slug(&record[key])?;
            entries.push(Entry {
                path: format!("{field}/{id}"),
                kind,
                name: id.into(),
                version: Some(version.into()),
                claim: None,
            });
        }
    }
    Ok(entries)
}

fn locked(document: &Value) -> Result<Vec<Entry>> {
    if document["version"].as_u64() != Some(3) {
        return Err(refused());
    }
    let records = document["skills"].as_object().ok_or_else(refused)?;
    if records.len() > 500 {
        return Err(refused());
    }
    records
        .iter()
        .map(|(name, record)| {
            let name = skill_name(name)?;
            let source = text(&record["source"])?;
            let claim = text(&record["skillFolderHash"])?;
            if !matches!(claim.len(), 40 | 64)
                || !claim
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            {
                return Err(refused());
            }
            Ok(Entry {
                path: format!(".agents/skills/{name}"),
                kind: "skill",
                name: source.into(),
                version: None,
                claim: Some(claim.into()),
            })
        })
        .collect()
}

fn metadata(
    scanner: &Scanner,
    directory: &Dir,
    path: &str,
) -> Result<Option<cap_std::fs::Metadata>> {
    let Some((parent, name)) = scanner.parent(directory, path)? else {
        return Ok(None);
    };
    scanner.metadata(&parent, &name)
}

fn select(scanner: &Scanner, directory: &Dir, entry: &mut Entry) -> Result<cap_std::fs::Metadata> {
    let held = if entry.path == "." {
        Some(directory.dir_metadata().map_err(|_| refused())?)
    } else {
        metadata(scanner, directory, &entry.path)?
    };
    if entry.kind == "skill" {
        let held = held
            .filter(cap_std::fs::Metadata::is_dir)
            .ok_or_else(refused)?;
        let manifest = if entry.path == "." {
            "SKILL.md".into()
        } else {
            format!("{}/SKILL.md", entry.path)
        };
        if !metadata(scanner, directory, &manifest)?.is_some_and(|meta| meta.is_file()) {
            return Err(refused());
        }
        return Ok(held);
    }
    // Nori identifiers are stems; append rather than replacing a dotted stem's suffix.
    let markdown = format!("{}.md", entry.path);
    let alternate = metadata(scanner, directory, &markdown)?;
    match (held, alternate) {
        (Some(held), None) => Ok(held),
        (None, Some(held)) if held.is_file() => {
            entry.path = markdown;
            Ok(held)
        }
        _ => Err(refused()),
    }
}

fn discover(
    scanner: &Scanner,
    directory: &Dir,
    root: &Path,
    scope: Scope,
    source: &str,
) -> Result<Vec<Candidate>> {
    let Some((parent, name)) = scanner.parent(directory, source)? else {
        return Ok(Vec::new());
    };
    if scanner.metadata(&parent, &name)?.is_none() {
        return Ok(Vec::new());
    }
    let bytes = scanner.read(&parent, &name)?;
    let manifest_digest = digest::bytes("ai-stp:artifact:v1", &bytes)?;
    // Reject duplicate/NFC-colliding keys without rewriting names before the
    // upstream lock filename algorithm sees them.
    canonical::parse(&bytes)?;
    let document: Value = serde_json::from_slice(&bytes).map_err(|_| refused())?;
    if !document.is_object() {
        return Err(refused());
    }
    let entries = if source == NORI {
        nori(&document)?
    } else {
        locked(&document)?
    };
    let mut seen = BTreeSet::new();
    let mut found = Vec::new();
    for mut entry in entries {
        let held = select(scanner, directory, &mut entry)?;
        if !seen.insert((entry.path.clone(), entry.kind)) {
            return Err(refused());
        }
        let absolute = if entry.path == "." {
            root.to_owned()
        } else {
            root.join(&entry.path)
        };
        let source_path = files::display(Path::new(&files::location(&absolute)?));
        let provenance = json!({
            "kind":"package", "state":"observed", "repository":null, "revision":null,
            "subpath":null, "package_name":entry.name, "package_version":entry.version,
            "digest":null, "claimed_folder_hash":entry.claim,
            "manifest_digest":manifest_digest, "evidence":[source]
        });
        let candidate_id = digest::canonical(
            "ai-stp:native-discovery:v1",
            &json!({
                "component_type":entry.kind,"projection_kind":"native_files","native_role":null,
                "harness_id":"undefined","layout_source":source,"scope":scope,
                "source_path":source_path,"provenance":provenance,
                "entry_points":[],"transport_capabilities":[],"evidence_refs":[source]
            }),
        )?;
        found.push(Candidate {
            component_type: entry.kind.into(),
            projection_kind: "native_files".into(),
            native_role: None,
            harness_id: "undefined".into(),
            scope,
            candidate_id,
            layout_source: source.into(),
            provenance,
            source_path,
            native_path: entry.path,
            byte_length: held.is_file().then_some(held.len()),
            holds_secret: false,
            reason: "declared in bounded local metadata; destination harness is explicit",
            entry_points: Vec::new(),
            transport_capabilities: Vec::new(),
            evidence_refs: vec![source.into()],
            declared_key: String::new(),
            absolute,
            metadata_port: true,
        });
    }
    Ok(found)
}

pub(super) fn merge(
    scanner: &Scanner,
    directory: &Dir,
    root: &Path,
    scope: Scope,
    result: &mut Discovery,
) {
    for source in [NORI, LOCK] {
        if source == NORI && scope != Scope::Project {
            continue;
        }
        match discover(scanner, directory, root, scope, source) {
            Ok(found) => {
                for candidate in found {
                    result.components.retain(|existing| {
                        !(existing.absolute == candidate.absolute
                            && existing.component_type == candidate.component_type)
                    });
                    result.components.push(candidate);
                }
            }
            Err(_) => {
                result.complete = false;
                result.diagnostics.push(Diagnostic {
                    code:"invalid_metadata", source:source.into(),
                    reason:"metadata is ambiguous, unsupported, unsafe, unavailable or exceeds its bound",
                });
            }
        }
    }
}
