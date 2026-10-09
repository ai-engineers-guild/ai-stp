//! Observe MCP entries and reject credential literals and credential-bearing URLs.

mod claude;

use jsonc_parser::cst::CstInputValue;
use toml_edit::{DocumentMut, Item, TableLike, Value};

use super::invalid;
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

fn credential() -> Failure {
    Failure::precondition("MCP credential fields must use external references, not literal values")
        .with_details([("constraint".into(), "literal_credential".into())])
}

fn folded(name: &str) -> String {
    name.chars()
        .filter(char::is_ascii_alphanumeric)
        .flat_map(char::to_lowercase)
        .collect()
}

fn sensitive(parent: &str, name: &str) -> bool {
    let name = folded(name.rsplit('.').next().unwrap_or(name));
    matches!(
        name.as_str(),
        "apikey"
            | "accesskey"
            | "accesskeyid"
            | "accesstoken"
            | "authtoken"
            | "authorization"
            | "proxyauthorization"
            | "clientsecret"
            | "credential"
            | "credentials"
            | "password"
            | "passwd"
            | "privatekey"
            | "refreshtoken"
            | "secret"
            | "secretkey"
            | "sessiontoken"
            | "token"
            | "bearertoken"
            | "cookie"
            | "setcookie"
    ) || (matches!(
        parent,
        "env" | "environment" | "headers" | "http_headers" | "query"
    ) && [
        "apikey",
        "accesskey",
        "accesskeyid",
        "token",
        "secret",
        "password",
        "passwd",
        "privatekey",
        "cookie",
    ]
    .iter()
    .any(|suffix| name.ends_with(suffix)))
}

fn check_url(value: &str) -> Result<()> {
    let Ok(url) = url::Url::parse(value) else {
        return Ok(());
    };
    if !url.has_host() {
        return Ok(());
    }
    // Parse the scalar as data, without resolving references or contacting a
    // host. URL/form decoding exposes encoded parameter names exactly once.
    if !url.username().is_empty()
        || url.password().is_some()
        || url.query_pairs().any(|(key, _)| sensitive("query", &key))
        || url.fragment().is_some_and(|fragment| {
            url::form_urlencoded::parse(fragment.as_bytes())
                .any(|(key, _)| sensitive("query", &key))
        })
    {
        return Err(Failure::precondition(
            "MCP URLs must not contain user information or credential parameters",
        )
        .with_details([("constraint".into(), "credential_url".into())]));
    }
    Ok(())
}

fn variable(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 256
        && name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'))
}

fn reference(harness: &str, value: &str) -> bool {
    let value = value.strip_prefix("Bearer ").unwrap_or(value);
    let variable_name = match harness {
        "claude-code" | "grok-build" => value.strip_prefix("${").and_then(|s| s.strip_suffix('}')),
        "cursor" => value
            .strip_prefix("${env:")
            .and_then(|s| s.strip_suffix('}')),
        "opencode" => value
            .strip_prefix("{env:")
            .and_then(|s| s.strip_suffix('}')),
        _ => None,
    };
    if variable_name.is_some_and(variable) {
        return true;
    }
    harness == "opencode"
        && value
            .strip_prefix("{file:")
            .and_then(|s| s.strip_suffix('}'))
            .is_some_and(|path| {
                !path.trim().is_empty()
                    && !path
                        .chars()
                        .any(|c| c.is_control() || matches!(c, '{' | '}'))
            })
}

struct Guard<'a> {
    harness: &'a str,
    nodes: usize,
}

#[derive(Clone, Copy, PartialEq)]
enum Field {
    Plain,
    Credential,
    EnvironmentName,
}

impl Guard<'_> {
    fn check(&mut self, depth: usize) -> Result<()> {
        self.nodes += 1;
        if depth > 128 || self.nodes > 20_000 {
            return Err(invalid());
        }
        Ok(())
    }

    fn field(&self, parent: &str, name: &str, inherited: Field) -> Field {
        if inherited != Field::Plain {
            inherited
        } else if self.harness == "codex" && parent.is_empty() && name == "env_http_headers" {
            // Only this server-level map holds environment names, not headers.
            Field::EnvironmentName
        } else if sensitive(parent, name) {
            Field::Credential
        } else {
            Field::Plain
        }
    }

    fn scalar(&self, value: Option<&str>, field: Field) -> Result<()> {
        match field {
            Field::Credential
                if !value
                    .is_some_and(|value| value.is_empty() || reference(self.harness, value)) =>
            {
                Err(credential())
            }
            Field::EnvironmentName if !value.is_some_and(variable) => Err(invalid()),
            _ => value.map_or(Ok(()), check_url),
        }
    }

    fn json(
        &mut self,
        value: &CstInputValue,
        parent: &str,
        held: Field,
        depth: usize,
    ) -> Result<()> {
        self.check(depth)?;
        match value {
            CstInputValue::Object(fields) => {
                for (name, value) in fields {
                    self.json(value, name, self.field(parent, name, held), depth + 1)?;
                }
                Ok(())
            }
            CstInputValue::Array(values) => {
                for value in values {
                    self.json(value, parent, held, depth + 1)?;
                }
                Ok(())
            }
            CstInputValue::Null => Ok(()),
            CstInputValue::String(value) => self.scalar(Some(value), held),
            _ => self.scalar(None, held),
        }
    }

    fn table(
        &mut self,
        table: &dyn TableLike,
        parent: &str,
        held: Field,
        depth: usize,
    ) -> Result<()> {
        self.check(depth)?;
        for (name, item) in table.iter() {
            let held = self.field(parent, name, held);
            self.item(item, name, held, depth + 1)?;
        }
        Ok(())
    }

    fn item(&mut self, item: &Item, name: &str, held: Field, depth: usize) -> Result<()> {
        match item {
            Item::Table(table) => self.table(table, name, held, depth)?,
            Item::Value(value) => self.toml(value, name, held, depth)?,
            Item::ArrayOfTables(tables) => {
                for table in tables {
                    self.table(table, name, held, depth + 1)?;
                }
            }
            Item::None => {}
        }
        Ok(())
    }

    fn toml(&mut self, value: &Value, parent: &str, held: Field, depth: usize) -> Result<()> {
        self.check(depth)?;
        match value {
            Value::InlineTable(table) => self.table(table, parent, held, depth + 1),
            Value::Array(values) => {
                for value in values {
                    self.toml(value, parent, held, depth + 1)?;
                }
                Ok(())
            }
            _ => self.scalar(value.as_str(), held),
        }
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
    let mut guard = Guard { harness, nodes: 0 };
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
