//! Bounded data-only YAML headers shared by portable and native authoring.

use crate::error::{Failure, Result};
use serde_json::Value;
use serde_saphyr::granit_parser::{Event, Parser, ScalarStyle};
use std::sync::LazyLock;

#[derive(Clone, Copy, PartialEq)]
pub(super) enum Dialect {
    Core,
    CoreMerged,
    JsYaml3,
}

// js-yaml 3 infers these non-string types in addition to ordinary YAML scalars.
static LEGACY_SCALAR: LazyLock<std::result::Result<regex::Regex, regex::Error>> =
    LazyLock::new(|| {
        regex::Regex::new(concat!(
            r"\A(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|",
            r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt]|[ \t]+)[0-9]{1,2}:[0-9]{2}:[0-9]{2}",
            r"(?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?|",
            r"[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+|",
            r"[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.(?:[0-9_]*[0-9])?",
            r")\z"
        ))
    });

fn ambiguous() -> Failure {
    Failure::precondition(
        "frontmatter contains a scalar or tag outside the supported native dialect",
    )
}

pub(super) fn optional(bytes: &[u8], dialect: Dialect) -> Result<Value> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| Failure::precondition("the Markdown source must be UTF-8"))?;
    if text.lines().next() == Some("---") {
        required(bytes, dialect)
    } else if text
        .trim_start_matches(|character: char| character.is_whitespace() || character == '\u{feff}')
        .starts_with("---")
    {
        Err(Failure::precondition(
            "frontmatter requires an exact opening delimiter on the first line without a BOM",
        ))
    } else {
        Ok(serde_json::json!({}))
    }
}

pub(super) fn required(bytes: &[u8], dialect: Dialect) -> Result<Value> {
    let value: Value = decode(bytes, dialect)?;
    if !value.is_object() {
        return Err(Failure::precondition("frontmatter must be an object"));
    }
    Ok(value)
}

pub(super) fn decode<T: serde::de::DeserializeOwned>(bytes: &[u8], dialect: Dialect) -> Result<T> {
    let header = header(bytes)?;
    let value = serde_saphyr::from_str_with_options(&header, options(dialect)).map_err(|_| {
        Failure::precondition("frontmatter is invalid or exceeds its parsing budget")
    })?;
    // Deserialize with budgets first; the event pass never expands aliases.
    for event in Parser::new_from_str(&header) {
        let (event, _) = event.map_err(|_| ambiguous())?;
        if matches!(event, Event::DocumentStart(_, Some(_))) {
            return Err(ambiguous());
        }
        if event.tag().is_some_and(|tag| {
            !["str", "bool", "int", "float", "null", "seq", "map"]
                .iter()
                .any(|kind| tag.is_yaml_core_schema_tag(kind))
        }) {
            return Err(ambiguous());
        }
        if let Event::Scalar(value, style, _, tag) = event {
            if (tag.as_ref().is_some_and(|tag| {
                tag.is_yaml_core_schema_tag("bool") || tag.is_yaml_core_schema_tag("null")
            }) || tag.is_none() && style == ScalarStyle::Plain)
                && matches!(
                    value.to_ascii_lowercase().as_str(),
                    "true" | "false" | "null"
                )
                && !matches!(
                    value.as_ref(),
                    "true"
                        | "True"
                        | "TRUE"
                        | "false"
                        | "False"
                        | "FALSE"
                        | "null"
                        | "Null"
                        | "NULL"
                )
            {
                return Err(ambiguous());
            }
            if dialect == Dialect::JsYaml3
                && tag.is_none()
                && style == ScalarStyle::Plain
                && LEGACY_SCALAR
                    .as_ref()
                    .map_err(|_| ambiguous())?
                    .is_match(&value)
            {
                return Err(ambiguous());
            }
        }
    }
    Ok(value)
}

fn options(dialect: Dialect) -> serde_saphyr::Options {
    serde_saphyr::options! {
        strict_booleans: true,
        legacy_octal_numbers: dialect == Dialect::JsYaml3,
        reject_unsupported_tags: true,
        merge_keys: if dialect != Dialect::Core {
            serde_saphyr::MergeKeyPolicy::Merge
        } else {
            serde_saphyr::MergeKeyPolicy::AsOrdinary
        },
        budget: serde_saphyr::budget! {
        max_depth:8, max_events:10_000, max_aliases:100, max_documents:1,
    }}
}

fn header(bytes: &[u8]) -> Result<String> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| Failure::precondition("the Markdown source must be UTF-8"))?;
    let mut lines = text.split_inclusive('\n');
    if lines
        .next()
        .is_none_or(|line| line.trim_end_matches(['\r', '\n']) != "---")
    {
        return Err(Failure::precondition(
            "the source requires YAML frontmatter on its first line",
        ));
    }
    let mut header = String::new();
    for line in lines {
        if line.trim_end_matches(['\r', '\n']) == "---" {
            return Ok(header);
        }
        header.push_str(line);
        if header.len() > 64 * 1024 {
            return Err(Failure::precondition("frontmatter exceeds 64 KiB"));
        }
    }
    Err(Failure::precondition("frontmatter is not closed"))
}
