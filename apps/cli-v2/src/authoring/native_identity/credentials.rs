//! Shared bounded checks for named credential values and credential-bearing URLs.

use jsonc_parser::cst::CstInputValue;
use toml_edit::{DocumentMut, Item, TableLike, Value};

use super::{invalid, mcp};
use crate::{
    authoring::contribution::{self, Format},
    error::{Failure, Result},
};

fn credential() -> Failure {
    Failure::precondition(
        "Native configuration credential fields must use external references, not literal values",
    )
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
            | "experimentalbearertoken"
            | "cookie"
            | "setcookie"
    ) || (matches!(
        parent,
        "env"
            | "environment"
            | "headers"
            | "http_headers"
            | "extra_headers"
            | "query"
            | "query_params"
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
            "Native configuration URLs must not contain user information or credential parameters",
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

fn reference(harness: &str, references: References, value: &str) -> bool {
    if references == References::None {
        return false;
    }
    if references == References::PiModel {
        let value = value.strip_prefix("Bearer ").unwrap_or(value);
        let name = value
            .strip_prefix("${")
            .and_then(|s| s.strip_suffix('}'))
            .or_else(|| value.strip_prefix('$'));
        return name.is_some_and(|name| {
            !name.is_empty()
                && name.len() <= 256
                && name.bytes().enumerate().all(|(i, b)| {
                    b == b'_' || b.is_ascii_alphabetic() || i > 0 && b.is_ascii_digit()
                })
        });
    }
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

pub(super) struct Guard<'a> {
    harness: &'a str,
    nodes: usize,
    references: References,
    native_header_names: bool,
}

#[derive(Clone, Copy, PartialEq)]
pub(super) enum Field {
    Plain,
    Credential,
    EnvironmentName,
}

#[derive(Clone, Copy, PartialEq)]
enum References {
    None,
    Native,
    PiModel,
}

impl<'a> Guard<'a> {
    pub(super) fn mcp(harness: &'a str) -> Self {
        Self {
            harness,
            nodes: 0,
            references: References::Native,
            native_header_names: true,
        }
    }

    fn check(&mut self, depth: usize) -> Result<()> {
        self.nodes += 1;
        if depth > 128 || self.nodes > 20_000 {
            return Err(invalid());
        }
        Ok(())
    }

    pub(super) fn field(&self, parent: &str, name: &str, inherited: Field) -> Field {
        if inherited != Field::Plain {
            inherited
        } else if self.native_header_names
            && self.harness == "codex"
            && parent.is_empty()
            && name == "env_http_headers"
        {
            // Only explicitly selected native server/provider maps hold these names.
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
                if !value.is_some_and(|value| {
                    value.is_empty() || reference(self.harness, self.references, value)
                }) =>
            {
                Err(credential())
            }
            Field::EnvironmentName if !value.is_some_and(variable) => Err(invalid()),
            _ => value.map_or(Ok(()), check_url),
        }
    }

    pub(super) fn json(
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

    pub(super) fn table(
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

    pub(super) fn item(
        &mut self,
        item: &Item,
        name: &str,
        held: Field,
        depth: usize,
    ) -> Result<()> {
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

/// Check the captured setting, including embedded MCP servers, without resolving
/// references, reading environment values or interpreting shell commands.
pub(super) fn settings(harness: &str, path: &str, owned_key: &str, bytes: &[u8]) -> Result<()> {
    if owned_key.len() > 255 || owned_key.chars().any(char::is_control) {
        return Err(invalid());
    }
    let source = contribution::text(bytes)?;
    let format = Format::for_path(path)?;
    let references = match harness {
        "opencode" => References::Native,
        "pi" if path.rsplit('/').next() == Some("models.json") => References::PiModel,
        _ => References::None,
    };
    let mut guard = Guard {
        harness,
        nodes: 0,
        references,
        native_header_names: false,
    };
    let embedded = mcp::key(harness).ok();
    if format == Format::Toml {
        let mut document: DocumentMut = source.parse().map_err(|_| invalid())?;
        if !owned_key.is_empty() {
            let mut wrapper = DocumentMut::new();
            wrapper.insert(owned_key, Item::Table(document.into_table()));
            document = wrapper;
        }
        for (name, item) in document.iter() {
            if Some(name) == embedded || harness == "codex" && name == "model_providers" {
                if Some(name) == embedded {
                    guard.references = References::Native;
                }
                guard.native_header_names = true;
                for (_, server) in item.as_table_like().ok_or_else(invalid)?.iter() {
                    guard.table(
                        server.as_table_like().ok_or_else(invalid)?,
                        "",
                        Field::Plain,
                        1,
                    )?;
                }
                guard.references = references;
                guard.native_header_names = false;
            } else {
                guard.item(item, name, guard.field("host", name, Field::Plain), 1)?;
            }
        }
    } else {
        let mut parsed = contribution::parse_json(source, format)?;
        if !owned_key.is_empty() {
            if !matches!(parsed, CstInputValue::Object(_)) {
                return Err(invalid());
            }
            parsed = CstInputValue::Object(vec![(owned_key.to_owned(), parsed)]);
        }
        if let CstInputValue::Object(fields) = &parsed {
            for (name, value) in fields {
                if Some(name.as_str()) == embedded {
                    let CstInputValue::Object(servers) = value else {
                        return Err(invalid());
                    };
                    guard.references = References::Native;
                    guard.native_header_names = true;
                    for (_, server) in servers {
                        if !matches!(server, CstInputValue::Object(_)) {
                            return Err(invalid());
                        }
                        guard.json(server, "", Field::Plain, 1)?;
                    }
                    guard.references = references;
                    guard.native_header_names = false;
                } else {
                    guard.json(value, name, guard.field("host", name, Field::Plain), 1)?;
                }
            }
        } else {
            // Some native settings, such as key bindings, are arrays.
            guard.json(&parsed, "", Field::Plain, 0)?;
        }
    }
    Ok(())
}
