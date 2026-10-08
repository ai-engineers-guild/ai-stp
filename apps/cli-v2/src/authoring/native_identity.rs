//! Native identifiers are observed from captured content, never from display metadata.

mod claude;
mod codex;
mod mcp;
mod opencode;
mod pi;

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;
use unicode_normalization::UnicodeNormalization;

use super::{discovery::Candidate, source::Captured};
use crate::{
    artifacts,
    error::{Failure, Result},
};

fn invalid() -> Failure {
    Failure::precondition(
        "native identifiers are missing, ambiguous, noncanonical or invalid for this source",
    )
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

pub(super) fn has_markdown_entries(harness: &str, kind: &str) -> bool {
    matches!(
        (harness, kind),
        ("claude-code" | "pi", "skill" | "command")
            | ("opencode", "skill" | "command" | "agent")
            | ("codex", "skill")
    )
}

fn markdown_entries<'a>(
    harness: &str,
    kind: &str,
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    match harness {
        "claude-code" => claude::invocations(kind, files),
        "codex" => codex::skills(files),
        "opencode" => opencode::entries(kind, files),
        "pi" => pi::entries(kind, files),
        _ => Err(invalid()),
    }
}

pub(crate) fn visible_pi_entries<'a>(
    kind: &str,
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let names = pi::visible(kind, files)?;
    valid(&names)?;
    Ok(names)
}

pub(crate) fn visible_codex_skills<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let names = codex::visible(files)?;
    valid(&names)?;
    Ok(names)
}

pub(super) fn check_source_context(
    harness: &str,
    candidate: &Candidate,
    root: &std::path::Path,
) -> Result<()> {
    if harness == "codex" && candidate.component_type == "skill" {
        super::source::reject_plugin_ancestors(
            root,
            &candidate.native_path,
            &codex::PLUGIN_DIRECTORIES,
        )?;
    }
    Ok(())
}

pub(super) fn read(
    harness: &str,
    candidate: &Candidate,
    content: &Captured,
) -> Result<Vec<String>> {
    let file_name = candidate
        .absolute
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(invalid)?;
    let names = match (candidate.component_type.as_str(), harness) {
        (kind, harness) if has_markdown_entries(harness, kind) => {
            if content.format == artifacts::FILE_FORMAT {
                markdown_entries(
                    harness,
                    kind,
                    [(candidate.native_path.as_str(), content.bytes.as_slice())],
                )?
            } else if content.format == artifacts::TREE_FORMAT {
                let mut files = artifacts::decode_tree(&content.bytes)?;
                for file in &mut files {
                    file.path = format!("{}/{}", candidate.native_path, file.path);
                }
                markdown_entries(
                    harness,
                    kind,
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
            let key = mcp::key(harness)?;
            if !candidate.declared_key.is_empty() && candidate.declared_key != key {
                return Err(invalid());
            }
            let names = mcp::names(
                harness,
                &candidate.native_path,
                &candidate.declared_key,
                &content.bytes,
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
    if has_markdown_entries(harness, kind) {
        let expected = markdown_entries(
            harness,
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
            mcp::names(harness, &file.path, key, &file.bytes)?
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
