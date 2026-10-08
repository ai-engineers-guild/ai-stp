//! Native identifiers are observed from captured content, never from display metadata.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;
use unicode_normalization::UnicodeNormalization;

use super::{
    contribution::{self, Format},
    discovery::Candidate,
    frontmatter,
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

fn agent_name(bytes: &[u8]) -> Result<Vec<String>> {
    let header = frontmatter::required(bytes)?;
    let name = header["name"].as_str().ok_or_else(invalid)?;
    if name.starts_with('-')
        || name.contains(':')
        || name.chars().count() > 256
        || header["description"]
            .as_str()
            .is_none_or(|text| text.trim().is_empty())
    {
        return Err(invalid());
    }
    Ok(vec![name.to_owned()])
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
            agent_name(&content.bytes)?
        }
        _ => vec![file_name.to_owned()],
    };
    valid(&names)?;
    Ok(names)
}

/// Passport declarations cannot replace mechanically observed native identities.
pub(super) fn verify_projection(
    kind: &str,
    harness: &str,
    source: &Value,
    payload: &[u8],
) -> Result<()> {
    let expected = match (kind, harness) {
        ("mcp", _) => {
            if source["content_format"] != artifacts::FILE_FORMAT {
                return Err(invalid());
            }
            let name = source["source_name"].as_str().ok_or_else(invalid)?;
            mcp_names(
                harness,
                name,
                source["declared_key"].as_str().unwrap_or(""),
                payload,
            )?
        }
        ("agent", "claude-code") => {
            if source["content_format"] != artifacts::FILE_FORMAT {
                return Err(invalid());
            }
            agent_name(payload)?
        }
        _ => return Ok(()),
    };
    matches(&source["native_ids"], &expected)
}

fn matches(declaration: &Value, expected: &[String]) -> Result<()> {
    valid(expected)?;
    let declared = declaration.as_array().ok_or_else(invalid)?;
    let names = declared
        .iter()
        .map(|name| name.as_str().ok_or_else(invalid))
        .collect::<Result<BTreeSet<_>>>()?;
    if expected.is_empty()
        || names.len() != declared.len()
        || names != expected.iter().map(String::as_str).collect()
    {
        return Err(
            invalid().with_details([("constraint".into(), "native_identifier_mismatch".into())])
        );
    }
    Ok(())
}

/// Retained or catalog projections get the same byte-derived check as new sources.
/// Call only after the archive has closed over its member digests and metadata.
pub(crate) fn verify_members(
    kind: &str,
    harness: &str,
    scope: &Value,
    files: &[artifacts::Member],
) -> Result<()> {
    if !(kind == "mcp" || kind == "agent" && harness == "claude-code") {
        return Ok(());
    }
    let declared: BTreeMap<_, _> = scope["members"]
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(|item| Ok((item["path"].as_str().ok_or_else(invalid)?, item)))
        .collect::<Result<_>>()?;
    if files.is_empty() {
        return Err(invalid());
    }
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
            agent_name(&file.bytes)?
        };
        matches(&declaration["native_ids"], &names)?;
    }
    Ok(())
}
