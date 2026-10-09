//! Observe MCP entries and reject credential literals and credential-bearing URLs.

mod claude;

use jsonc_parser::cst::CstInputValue;
use toml_edit::{DocumentMut, Item, TableLike};

use super::{
    credentials::{Field, Guard},
    invalid,
};
use crate::{
    authoring::contribution::{self, Format},
    error::{Failure, Result},
};

pub(super) fn key(harness: &str) -> Result<&'static str> {
    match harness {
        "claude-code" | "cursor" | "antigravity" => Ok("mcpServers"),
        "codex" | "grok-build" => Ok("mcp_servers"),
        "opencode" => Ok("mcp"),
        _ => Err(invalid()),
    }
}

/// Empty `declared_key` denotes a host file; otherwise bytes hold only that key.
pub(super) fn names(
    harness: &str,
    path: &str,
    declared_key: &str,
    payload: &[u8],
) -> Result<Vec<String>> {
    let expected = key(harness)?;
    if harness == "claude-code"
        && !(path == ".mcp.json" || path == ".claude.json" && declared_key == expected)
    {
        return Err(Failure::precondition(
            "Claude MCP requires project .mcp.json or an owned .claude.json mcpServers contribution",
        )
        .with_details([("constraint".into(), "native_mcp_surface".into())]));
    }
    if !declared_key.is_empty() && declared_key != expected {
        return Err(invalid());
    }
    let source = contribution::text(payload)?;
    let format = Format::for_path(path)?;
    let mut guard = Guard::mcp(harness);
    let mut names = Vec::new();
    if format == Format::Toml {
        let document: DocumentMut = source.parse().map_err(|_| invalid())?;
        if declared_key.is_empty() {
            for (name, item) in document.iter().filter(|(name, _)| *name != expected) {
                guard.item(item, name, guard.field("host", name, Field::Plain), 1)?;
            }
        }
        let table: &dyn TableLike = if declared_key.is_empty() {
            document
                .get(expected)
                .and_then(Item::as_table_like)
                .ok_or_else(invalid)?
        } else {
            document.as_table()
        };
        for (name, server) in table.iter() {
            guard.table(
                server.as_table_like().ok_or_else(invalid)?,
                "",
                Field::Plain,
                0,
            )?;
            names.push(name.to_owned());
        }
    } else {
        let parsed = contribution::parse_json(source, format)?;
        let CstInputValue::Object(root) = &parsed else {
            return Err(invalid());
        };
        if harness == "claude-code"
            && path == ".mcp.json"
            && declared_key.is_empty()
            && root.iter().any(|(name, _)| name != expected)
        {
            return Err(Failure::precondition(
                "project .mcp.json capture requires only the mcpServers root key",
            ));
        }
        if declared_key.is_empty() {
            for (name, value) in root.iter().filter(|(name, _)| name != expected) {
                guard.json(value, name, guard.field("host", name, Field::Plain), 1)?;
            }
        }
        let entries = if declared_key.is_empty() {
            let (_, CstInputValue::Object(entries)) = root
                .iter()
                .find(|(name, _)| name == expected)
                .ok_or_else(invalid)?
            else {
                return Err(invalid());
            };
            entries
        } else {
            root
        };
        for (name, server) in entries {
            let CstInputValue::Object(fields) = server else {
                return Err(invalid());
            };
            guard.json(server, "", Field::Plain, 0)?;
            if harness == "claude-code" {
                claude::check(fields)?;
            }
            names.push(name.to_owned());
        }
    }
    contribution::checked_names(names)
}
