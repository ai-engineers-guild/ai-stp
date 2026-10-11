//! Closed stdio syntax conversion. Unknown controls never become omissions.

use std::collections::BTreeMap;

use jsonc_parser::cst::CstInputValue;
use serde_json::{Value, json};
use toml_edit::{DocumentMut, Item, TableLike};

use super::{invalid, text};
use crate::{
    artifacts::{self, Member},
    authoring::{
        contribution::{self, Format},
        freezing,
    },
    error::Result,
    harnesses::Shape,
    projection::{self, Scope},
    provider::Info,
};

fn literal(value: &str) -> Result<String> {
    if value.contains('\0') || ["${", "{env:", "{file:"].iter().any(|m| value.contains(m)) {
        return Err(invalid());
    }
    Ok(value.into())
}

fn json_value(value: CstInputValue) -> Result<Value> {
    Ok(match value {
        CstInputValue::String(s) => literal(&s)?.into(),
        CstInputValue::Array(a) => a
            .into_iter()
            .map(json_value)
            .collect::<Result<Vec<_>>>()?
            .into(),
        CstInputValue::Object(o) => Value::Object(
            o.into_iter()
                .map(|(k, v)| Ok((k, json_value(v)?)))
                .collect::<Result<_>>()?,
        ),
        // The supported grammar has no numbers, booleans or nulls.
        _ => return Err(invalid()),
    })
}

fn toml_table(table: &dyn TableLike) -> Result<Value> {
    Ok(Value::Object(
        table
            .iter()
            .map(|(k, v)| Ok((k.into(), toml_item(v)?)))
            .collect::<Result<_>>()?,
    ))
}

fn toml_item(item: &Item) -> Result<Value> {
    if let Some(table) = item.as_table_like() {
        toml_table(table)
    } else if let Some(value) = item.as_str() {
        Ok(literal(value)?.into())
    } else if let Some(values) = item.as_array() {
        Ok(values
            .iter()
            .map(|v| literal(v.as_str().ok_or_else(invalid)?))
            .collect::<Result<Vec<_>>>()?
            .into())
    } else {
        Err(invalid())
    }
}

pub(super) struct Servers(BTreeMap<String, Server>);

struct Server {
    command: String,
    args: Vec<String>,
    environment: BTreeMap<String, String>,
}

fn supported(harness: &str) -> Result<()> {
    match harness {
        "codex" | "cursor" | "opencode" => Ok(()),
        _ => Err(invalid()),
    }
}

pub(super) fn decode(bytes: &[u8], harness: &str, format: Format, whole: bool) -> Result<Servers> {
    supported(harness)?;
    let input = contribution::text(bytes)?;
    let mut document = if format == Format::Toml {
        let document: DocumentMut = input.parse().map_err(|_| invalid())?;
        // Bound recursion before walking arbitrary tables by using the closed
        // server grammar below: root -> server -> environment, strings only.
        let mut servers = serde_json::Map::new();
        if document.len() > 500 {
            return Err(invalid());
        }
        for (name, item) in document.iter() {
            let table = item.as_table_like().ok_or_else(invalid)?;
            if table.len() > 4 {
                return Err(invalid());
            }
            for (key, value) in table.iter() {
                if key == "env" {
                    let env = value.as_table_like().ok_or_else(invalid)?;
                    if env.len() > 500 || env.iter().any(|(_, v)| !v.is_str()) {
                        return Err(invalid());
                    }
                } else if !(value.is_str()
                    || value
                        .as_array()
                        .is_some_and(|a| a.iter().all(|v| v.is_str())))
                {
                    return Err(invalid());
                }
            }
            servers.insert(name.into(), toml_table(table)?);
        }
        Value::Object(servers)
    } else {
        json_value(contribution::parse_json(input, format)?)?
    };
    if whole {
        let root = document.as_object_mut().ok_or_else(invalid)?;
        if root.len() != 1 {
            return Err(invalid());
        }
        document = root.remove("mcpServers").ok_or_else(invalid)?;
    }
    let entries = document.as_object().ok_or_else(invalid)?;
    if entries.is_empty() || entries.len() > 500 {
        return Err(invalid());
    }
    let mut servers = BTreeMap::new();
    for (name, value) in entries {
        let object = value.as_object().ok_or_else(invalid)?;
        let local = harness == "opencode";
        let allowed = if local {
            &["type", "command", "environment"][..]
        } else {
            &["type", "command", "args", "env"][..]
        };
        if object.keys().any(|key| !allowed.contains(&key.as_str()))
            || (local && value["type"] != "local")
            || (!local
                && object.contains_key("type")
                && (harness == "codex" || value["type"] != "stdio"))
        {
            return Err(invalid());
        }
        let (command, args) = if local {
            let parts = value["command"].as_array().ok_or_else(invalid)?;
            let (first, rest) = parts.split_first().ok_or_else(invalid)?;
            (
                first.as_str().ok_or_else(invalid)?.to_owned(),
                rest.iter()
                    .map(|v| v.as_str().map(String::from).ok_or_else(invalid))
                    .collect::<Result<Vec<_>>>()?,
            )
        } else {
            (
                text(value, "command")?.into(),
                match object.get("args") {
                    None => Vec::new(),
                    Some(Value::Array(a)) => a
                        .iter()
                        .map(|v| v.as_str().map(String::from).ok_or_else(invalid))
                        .collect::<Result<Vec<_>>>()?,
                    _ => return Err(invalid()),
                },
            )
        };
        if command.trim().is_empty() {
            return Err(invalid());
        }
        let environment = match object.get(if local { "environment" } else { "env" }) {
            None => BTreeMap::new(),
            Some(Value::Object(env)) if env.len() <= 500 => env
                .iter()
                .map(|(k, v)| {
                    if k.is_empty() || k.contains(['=', '\0']) {
                        return Err(invalid());
                    }
                    Ok((k.clone(), v.as_str().ok_or_else(invalid)?.to_owned()))
                })
                .collect::<Result<_>>()?,
            _ => return Err(invalid()),
        };
        servers.insert(
            name.clone(),
            Server {
                command,
                args,
                environment,
            },
        );
    }
    Ok(Servers(servers))
}

pub(super) fn encode(
    servers: &Servers,
    harness: &str,
    format: Format,
    whole: bool,
) -> Result<Vec<u8>> {
    supported(harness)?;
    if format == Format::Toml {
        let mut document = DocumentMut::new();
        for (name, server) in &servers.0 {
            let mut table = toml_edit::Table::new();
            table["command"] = toml_edit::value(&server.command);
            table["args"] = toml_edit::value(server.args.iter().collect::<toml_edit::Array>());
            if !server.environment.is_empty() {
                let mut env = toml_edit::Table::new();
                for (key, value) in &server.environment {
                    env[key] = toml_edit::value(value);
                }
                table["env"] = Item::Table(env);
            }
            document[name] = Item::Table(table);
        }
        return Ok(document.to_string().into_bytes());
    }
    let mut entries = serde_json::Map::new();
    for (name, server) in &servers.0 {
        let mut value = if harness == "opencode" {
            json!({"type":"local","command":std::iter::once(&server.command).chain(&server.args).collect::<Vec<_>>()})
        } else {
            json!({"command":server.command,"args":server.args})
        };
        if !server.environment.is_empty() {
            value[if harness == "opencode" {
                "environment"
            } else {
                "env"
            }] = json!(server.environment);
        }
        entries.insert(name.clone(), value);
    }
    // Native arguments and environment values are opaque strings, not passport
    // metadata: NFC normalization could change a filesystem path or credential.
    serde_json::to_vec(&if whole {
        json!({"mcpServers":entries})
    } else {
        Value::Object(entries)
    })
    .map_err(|_| invalid())
}

/// The MCP converter owns its exact file/contribution routes.
pub(super) fn project(
    before: &Value,
    scope: &Value,
    source_harness: &str,
    provider: &Info,
    files: &[Member],
) -> Result<(Value, Vec<u8>)> {
    let target = text(provider.document(), "harness_id")?;
    let requested: Scope = serde_json::from_value(scope["scope"].clone()).map_err(|_| invalid())?;
    let from = projection::route("mcp", source_harness, requested)?
        .filter(|r| r.target_scope == requested && r.shape == Shape::File)
        .ok_or_else(invalid)?;
    let to = projection::route("mcp", target, requested)?
        .filter(|r| r.target_scope == requested && r.shape == Shape::File)
        .ok_or_else(invalid)?;
    let members = scope["members"].as_array().ok_or_else(invalid)?;
    if files.len() != 1
        || members.len() != 1
        || files[0].path != from.relative
        || (from.declared_key.is_empty() && members[0]["ownership"] != "whole")
        || (!from.declared_key.is_empty()
            && (members[0]["ownership"] != "contribution"
                || members[0]["ownership_key"] != from.declared_key))
    {
        return Err(invalid());
    }
    let servers = decode(
        &files[0].bytes,
        source_harness,
        Format::for_path(&from.relative)?,
        from.declared_key.is_empty(),
    )?;
    let bytes = encode(
        &servers,
        target,
        Format::for_path(&to.relative)?,
        to.declared_key.is_empty(),
    )?;
    let values = json!({"harness_id":target,"scope":requested,"projection_kind":to.projection_kind,
            "managed_paths":[to.relative],"declared_key":to.declared_key,"source_locator":format!("{}#{}",to.relative,to.declared_key),
            "content_format":artifacts::FILE_FORMAT,"source_mode":files[0].mode,"native_ids":members[0]["native_ids"],
            "permissions":scope["permissions"],"supported_os":scope["supported_os"],"supported_arch":scope["supported_arch"],"supported_harness_versions":[]});
    freezing::project(before, &values, bytes, std::slice::from_ref(provider))
}
