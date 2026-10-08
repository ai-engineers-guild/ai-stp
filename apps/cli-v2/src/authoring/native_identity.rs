//! Native identifiers are observed from captured content, never from display metadata.

mod claude;

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;
use unicode_normalization::UnicodeNormalization;

use super::{
    contribution::{self, Format},
    discovery::Candidate,
    source::Captured,
};
use crate::{
    artifacts,
    error::{Failure, Result},
};

fn invalid() -> Failure {
    Failure::precondition(
        "native identifiers are missing, ambiguous, noncanonical or invalid for this source",
    )
}

fn mcp_key(harness: &str) -> Result<&'static str> {
    match harness {
        "claude-code" | "cursor" | "antigravity" => Ok("mcpServers"),
        "codex" | "grok-build" => Ok("mcp_servers"),
        "opencode" => Ok("mcp"),
        _ => Err(invalid()),
    }
}

fn mcp_names(harness: &str, path: &str, key: &str, payload: &[u8]) -> Result<Vec<String>> {
    let format = Format::for_path(path)?;
    let expected_key = mcp_key(harness)?;
    if key.is_empty() {
        contribution::entry_names(format, payload, expected_key)
    } else if key == expected_key {
        contribution::component_names(format, payload)
    } else {
        Err(invalid())
    }
}

fn valid(names: &[String]) -> Result<()> {
    if names.iter().any(|name| {
        name.trim().is_empty()
            || name.chars().count() > 512
            || name.chars().any(char::is_control)
            || name.nfc().collect::<String>() != *name
    }) {
        return Err(invalid());
    }
    Ok(())
}

pub(super) fn read(candidate: &Candidate, content: &Captured) -> Result<Vec<String>> {
    let file_name = candidate
        .absolute
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(invalid)?;
    let names = match (
        candidate.component_type.as_str(),
        candidate.harness_id.as_str(),
    ) {
        ("skill" | "command", "claude-code") => {
            if content.format == artifacts::FILE_FORMAT {
                claude::invocations(
                    &candidate.component_type,
                    [(candidate.native_path.as_str(), content.bytes.as_slice())],
                )?
            } else if content.format == artifacts::TREE_FORMAT {
                let mut files = artifacts::decode_tree(&content.bytes)?;
                for file in &mut files {
                    file.path = format!("{}/{}", candidate.native_path, file.path);
                }
                claude::invocations(
                    &candidate.component_type,
                    files
                        .iter()
                        .map(|file| (file.path.as_str(), file.bytes.as_slice())),
                )?
            } else {
                return Err(invalid());
            }
        }
        ("instruction" | "skill", _) => Vec::new(),
        ("mcp", _) => {
            if content.format != artifacts::FILE_FORMAT {
                return Err(invalid());
            }
            let key = mcp_key(&candidate.harness_id)?;
            if !candidate.declared_key.is_empty() && candidate.declared_key != key {
                return Err(invalid());
            }
            let names = contribution::entry_names(
                Format::for_path(&candidate.native_path)?,
                &content.bytes,
                key,
            )?;
            if names.is_empty() {
                return Err(invalid());
            }
            if !candidate.declared_key.is_empty()
                && candidate.evidence_refs
                    != names
                        .iter()
                        .map(|name| format!("{key}.{name}"))
                        .collect::<Vec<_>>()
            {
                return Err(Failure::precondition(
                    "MCP declarations changed after discovery",
                ));
            }
            names
        }
        ("agent", "claude-code") => {
            if content.format != artifacts::FILE_FORMAT || !file_name.ends_with(".md") {
                return Err(invalid());
            }
            claude::agent_names(&content.bytes)?
        }
        _ => vec![file_name.to_owned()],
    };
    valid(&names)?;
    Ok(names)
}

fn declared_names(declaration: &Value) -> Result<BTreeSet<&str>> {
    let declared = declaration.as_array().ok_or_else(invalid)?;
    let names = declared
        .iter()
        .map(|name| name.as_str().ok_or_else(invalid))
        .collect::<Result<BTreeSet<_>>>()?;
    if names.len() != declared.len() {
        return Err(invalid());
    }
    Ok(names)
}

fn matches(names: BTreeSet<&str>, expected: &[String]) -> Result<()> {
    valid(expected)?;
    if expected.is_empty() || names != expected.iter().map(String::as_str).collect() {
        return Err(
            invalid().with_details([("constraint".into(), "native_identifier_mismatch".into())])
        );
    }
    Ok(())
}

/// Retained or catalog projections get the same byte-derived check as new sources.
/// Inputs come from freshly compiled files or an archive verified against its declarations.
pub(crate) fn verify_files(
    kind: &str,
    harness: &str,
    declarations: &[Value],
    files: &[artifacts::Member],
) -> Result<()> {
    if harness == "claude-code" && matches!(kind, "skill" | "command") {
        let expected = claude::invocations(
            kind,
            files
                .iter()
                .map(|file| (file.path.as_str(), file.bytes.as_slice())),
        )?;
        let mut names = BTreeSet::new();
        for declaration in declarations {
            if declaration["ownership"] != "whole" {
                return Err(invalid());
            }
            names.extend(declared_names(&declaration["native_ids"])?);
        }
        return matches(names, &expected);
    }
    if !(kind == "mcp" || kind == "agent" && harness == "claude-code") {
        return Ok(());
    }
    let declared: BTreeMap<_, _> = declarations
        .iter()
        .map(|item| Ok((item["path"].as_str().ok_or_else(invalid)?, item)))
        .collect::<Result<_>>()?;
    if files.is_empty() {
        return Err(invalid());
    }
    let mut observed = BTreeSet::new();
    for file in files {
        let declaration = declared.get(file.path.as_str()).ok_or_else(invalid)?;
        let names = if kind == "mcp" {
            let key = match declaration["ownership"].as_str() {
                Some("whole") => "",
                Some("contribution") => {
                    declaration["ownership_key"].as_str().ok_or_else(invalid)?
                }
                _ => return Err(invalid()),
            };
            mcp_names(harness, &file.path, key, &file.bytes)?
        } else {
            if declaration["ownership"] != "whole" || !file.path.ends_with(".md") {
                return Err(invalid());
            }
            claude::agent_names(&file.bytes)?
        };
        for name in &names {
            if !observed.insert(name.clone()) {
                return Err(
                    invalid().with_details([("constraint".into(), "native_id_collision".into())])
                );
            }
        }
        matches(declared_names(&declaration["native_ids"])?, &names)?;
    }
    Ok(())
}
