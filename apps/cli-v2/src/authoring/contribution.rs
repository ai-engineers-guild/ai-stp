//! Extract and compile one owned top-level key, without writing a host file.

use std::collections::BTreeSet;

use jsonc_parser::{
    ParseOptions, ast,
    cst::{CstInputValue, CstRootNode},
};
use toml_edit::{DocumentMut, Item};

use crate::error::{ErrorKind, Failure, Result};

#[derive(Clone, Copy, PartialEq)]
pub enum Format {
    Json,
    Jsonc,
    Toml,
}

impl Format {
    pub fn for_path(path: &str) -> Result<Self> {
        match path.rsplit('.').next() {
            Some("json") => Ok(Self::Json),
            Some("jsonc") => Ok(Self::Jsonc),
            Some("toml") => Ok(Self::Toml),
            _ => Err(Failure::input(
                "the host configuration format is unsupported",
            )),
        }
    }
}

fn invalid() -> Failure {
    Failure::precondition(
        "the owned configuration value is invalid, ambiguous or exceeds its limits",
    )
}

pub(super) fn text(bytes: &[u8]) -> Result<&str> {
    if bytes.len() > 4 * 1024 * 1024 {
        return Err(invalid());
    }
    std::str::from_utf8(bytes).map_err(|_| invalid())
}

fn key(key: &str) -> Result<()> {
    if key.is_empty() || key.len() > 255 || key.chars().any(char::is_control) {
        return Err(invalid());
    }
    Ok(())
}

fn options(format: Format) -> ParseOptions {
    ParseOptions {
        allow_comments: format == Format::Jsonc,
        allow_trailing_commas: format == Format::Jsonc,
        allow_loose_object_property_names: false,
        allow_missing_commas: false,
        allow_single_quoted_strings: false,
        allow_hexadecimal_numbers: false,
        allow_unary_plus_numbers: false,
        allow_bare_decimal_point_numbers: false,
        allow_non_finite_numbers: false,
        allow_extended_string_escapes: false,
    }
}

fn input(value: ast::Value<'_>, depth: usize, nodes: &mut usize) -> Result<CstInputValue> {
    *nodes += 1;
    if depth > 128 || *nodes > 20_000 {
        return Err(invalid());
    }
    Ok(match value {
        ast::Value::NullKeyword(_) => CstInputValue::Null,
        ast::Value::BooleanLit(value) => CstInputValue::Bool(value.value),
        ast::Value::StringLit(value) => CstInputValue::String(value.value.into_owned()),
        // Keep the original number token; converting via f64 would round IDs.
        ast::Value::NumberLit(value) => CstInputValue::Number(value.value.into()),
        ast::Value::Array(value) => CstInputValue::Array(
            value
                .elements
                .into_iter()
                .map(|item| input(item, depth + 1, nodes))
                .collect::<Result<_>>()?,
        ),
        ast::Value::Object(value) => {
            let mut names = BTreeSet::new();
            let mut properties = Vec::new();
            for property in value.properties {
                let name = property.name.into_string();
                if !names.insert(name.clone()) {
                    return Err(invalid());
                }
                properties.push((name, input(property.value, depth + 1, nodes)?));
            }
            CstInputValue::Object(properties)
        }
    })
}

pub(super) fn parse_json(source: &str, format: Format) -> Result<CstInputValue> {
    let parsed = jsonc_parser::parse_to_ast(source, &Default::default(), &options(format))
        .map_err(|_| invalid())?;
    input(parsed.value.ok_or_else(invalid)?, 0, &mut 0)
}

fn absent() -> Failure {
    Failure::new(
        ErrorKind::NotFound,
        "the host configuration does not contain the owned key",
    )
}

fn json_value(host: &str, format: Format, key: &str) -> Result<CstInputValue> {
    let CstInputValue::Object(properties) = parse_json(host, format)? else {
        return Err(invalid());
    };
    properties
        .into_iter()
        .find_map(|(name, value)| (name == key).then_some(value))
        .ok_or_else(absent)
}

pub fn has_entries(format: Format, host: &[u8], name: &str) -> Result<bool> {
    Ok(!entry_names(format, host, name)?.is_empty())
}

/// Only structural names leave discovery; commands, URLs and values stay private.
pub fn entry_names(format: Format, host: &[u8], name: &str) -> Result<Vec<String>> {
    key(name)?;
    let source = text(host)?;
    let names: Vec<String> = if format == Format::Toml {
        let document: DocumentMut = source.parse().map_err(|_| invalid())?;
        document
            .get(name)
            .and_then(Item::as_table_like)
            .map(|table| table.iter().map(|(key, _)| key.into()).collect())
            .unwrap_or_default()
    } else {
        match json_value(source, format, name) {
            Ok(CstInputValue::Object(values)) => values.into_iter().map(|(name, _)| name).collect(),
            Ok(_) => Vec::new(),
            Err(error) if matches!(error.kind, ErrorKind::NotFound) => Vec::new(),
            Err(error) => return Err(error),
        }
    };
    checked_names(names)
}

pub(super) fn checked_names(mut names: Vec<String>) -> Result<Vec<String>> {
    if names.len() > 500
        || names
            .iter()
            .any(|name| name.is_empty() || name.chars().count() > 200)
    {
        return Err(invalid());
    }
    names.sort();
    Ok(names)
}

pub fn extract(format: Format, host: &[u8], name: &str) -> Result<Vec<u8>> {
    key(name)?;
    let source = text(host)?;
    let output = if format == Format::Toml {
        let document: DocumentMut = source.parse().map_err(|_| invalid())?;
        let value = document
            .get(name)
            .ok_or_else(absent)?
            .clone()
            .into_table()
            .map_err(|_| invalid())?;
        DocumentMut::from(value).to_string()
    } else {
        let value = json_value(source, format, name)?;
        if !matches!(value, CstInputValue::Object(_)) {
            return Err(invalid());
        }
        let document = CstRootNode::parse("null", &options(Format::Json)).map_err(|_| invalid())?;
        document.set_value(value);
        document.to_string()
    };
    text(output.as_bytes())?;
    Ok(output.into_bytes())
}

pub fn assemble(
    format: Format,
    host: Option<&[u8]>,
    name: &str,
    component: &[u8],
) -> Result<Vec<u8>> {
    key(name)?;
    let component = text(component)?;
    let output = if format == Format::Toml {
        let mut document: DocumentMut =
            text(host.unwrap_or(b""))?.parse().map_err(|_| invalid())?;
        let value: DocumentMut = component.parse().map_err(|_| invalid())?;
        let mut table = value.into_table();
        table.set_implicit(!table.is_empty());
        document.insert(name, Item::Table(table));
        document.to_string()
    } else {
        let source = text(host.unwrap_or(b"{}"))?;
        if !matches!(parse_json(source, format)?, CstInputValue::Object(_)) {
            return Err(invalid());
        }
        let value = parse_json(component, format)?;
        if !matches!(value, CstInputValue::Object(_)) {
            return Err(invalid());
        }
        let document = CstRootNode::parse(source, &options(format)).map_err(|_| invalid())?;
        let object = document.object_value().ok_or_else(invalid)?;
        match object.get(name) {
            Some(property) => property.set_value(value),
            None => {
                object.append(name, value);
            }
        }
        document.to_string()
    };
    text(output.as_bytes())?;
    Ok(output.into_bytes())
}
