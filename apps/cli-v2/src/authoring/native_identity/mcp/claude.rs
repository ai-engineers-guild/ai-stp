//! Configuration shapes accepted by the Claude 2.1.294 MCP loader.

use jsonc_parser::cst::CstInputValue as Value;

use crate::error::{Failure, Result};

type Fields = [(String, Value)];

fn get<'a>(fields: &'a Fields, name: &str) -> Option<&'a Value> {
    fields
        .iter()
        .find_map(|(key, value)| (key == name).then_some(value))
}

fn string(value: &Value) -> bool {
    matches!(value, Value::String(_))
}

fn strings(value: &Value) -> bool {
    matches!(value, Value::Array(values) if values.iter().all(string))
}

fn mapping(value: &Value) -> bool {
    matches!(value, Value::Object(fields) if fields.iter().all(|(_, value)| string(value)))
}

fn optional(fields: &Fields, name: &str, check: impl FnOnce(&Value) -> bool) -> bool {
    get(fields, name).is_none_or(check)
}

fn nonempty(value: Option<&Value>) -> bool {
    matches!(value, Some(Value::String(value)) if !value.trim().is_empty())
}

fn oauth(value: &Value) -> bool {
    let Value::Object(fields) = value else {
        return false;
    };
    optional(fields, "clientId", string)
        && optional(fields, "scopes", string)
        && optional(fields, "callbackPort", |value| {
            matches!(value, Value::Number(value) if value.parse::<f64>().is_ok_and(|port| {
                (1.0..=65535.0).contains(&port) && port.fract() == 0.0
            }))
        })
        && optional(fields, "authServerMetadataUrl", |value| {
            matches!(value, Value::String(value) if value.trim().starts_with("https://") && url::Url::parse(value).is_ok_and(|url| {
                url.scheme() == "https" && url.has_host()
            }))
        })
}

pub(super) fn check(fields: &Fields) -> Result<()> {
    let transport = get(fields, "type");
    let valid = if transport.is_none()
        || matches!(transport, Some(Value::String(value)) if value == "stdio")
    {
        nonempty(get(fields, "command"))
            && optional(fields, "args", strings)
            && optional(fields, "env", mapping)
    } else if let Some(Value::String(transport)) = transport
        && matches!(
            transport.as_str(),
            "http" | "streamable-http" | "sse" | "ws"
        )
    {
        nonempty(get(fields, "url"))
            && optional(fields, "headers", mapping)
            && optional(fields, "headersHelper", string)
            && (transport == "ws" || optional(fields, "oauth", oauth))
    } else {
        false
    };
    if !valid {
        return Err(Failure::precondition(
            "Claude MCP transport configuration is invalid or unsupported",
        )
        .with_details([("constraint".into(), "native_mcp_transport".into())]));
    }
    Ok(())
}
