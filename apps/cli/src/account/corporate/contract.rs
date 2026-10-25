//! Keep bounded observations to generated contract fields, including nested DTOs.

use crate::{
    error::{Failure, Result},
    wire,
};
use serde_json::{Map, Value, json};
use std::{collections::BTreeMap, sync::OnceLock};

pub(super) struct Contract {
    source: &'static str,
    schema: wire::Schema,
    document: OnceLock<Value>,
}

fn invalid() -> Failure {
    Failure::precondition(
        "the corporate observation cannot be projected to its bounded wire contract",
    )
}

impl Contract {
    pub const fn new(source: &'static str) -> Self {
        Self {
            source,
            schema: wire::Schema::reader(source),
            document: OnceLock::new(),
        }
    }

    pub fn project(&self, value: &Value) -> Result<Value> {
        self.schema.validate(value)?;
        let root = self.document.get_or_init(|| {
            let mut value = serde_json::from_str(self.source).unwrap_or(Value::Null);
            wire::allow_explicit_defaults(&mut value);
            value
        });
        if !root.is_object() {
            return Err(invalid());
        }
        let projected = project(root, root, value, 0, &mut BTreeMap::new())?;
        self.schema.validate(&projected)?;
        Ok(projected)
    }
}

fn project(
    root: &Value,
    schema: &Value,
    value: &Value,
    depth: usize,
    variants: &mut BTreeMap<String, jsonschema::Validator>,
) -> Result<Value> {
    if depth > 128 {
        return Err(invalid());
    }
    if let Some(reference) = schema["$ref"].as_str() {
        let target = reference
            .strip_prefix('#')
            .and_then(|path| root.pointer(path))
            .ok_or_else(invalid)?;
        return project(root, target, value, depth + 1, variants);
    }
    if let Some(choices) = schema
        .get("anyOf")
        .or_else(|| schema.get("oneOf"))
        .and_then(Value::as_array)
    {
        for choice in choices {
            let key = serde_json::to_string(choice).map_err(|_| invalid())?;
            let matches = match variants.entry(key) {
                std::collections::btree_map::Entry::Vacant(entry) => entry
                    .insert(
                        jsonschema::options()
                            .offline()
                            .should_validate_formats(true)
                            .build(&json!({"$defs":root["$defs"],"allOf":[choice]}))
                            .map_err(|_| invalid())?,
                    )
                    .is_valid(value),
                std::collections::btree_map::Entry::Occupied(entry) => entry.get().is_valid(value),
            };
            if matches {
                return project(root, choice, value, depth + 1, variants);
            }
        }
        return Err(invalid());
    }
    match value {
        Value::Object(fields) => {
            let mut output = Map::new();
            for (key, value) in fields {
                let selected = schema
                    .get("properties")
                    .and_then(|properties| properties.get(key))
                    .or_else(|| {
                        schema
                            .get("additionalProperties")
                            .filter(|schema| schema.is_object())
                    });
                if let Some(selected) = selected {
                    output.insert(
                        key.clone(),
                        project(root, selected, value, depth + 1, variants)?,
                    );
                }
            }
            if let Some(parts) = schema["allOf"].as_array() {
                for part in parts {
                    let extra = project(root, part, value, depth + 1, variants)?;
                    output.extend(extra.as_object().ok_or_else(invalid)?.clone());
                }
            }
            Ok(Value::Object(output))
        }
        Value::Array(items) => items
            .iter()
            .map(|item| project(root, &schema["items"], item, depth + 1, variants))
            .collect::<Result<Vec<_>>>()
            .map(Value::Array),
        _ => Ok(value.clone()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn open_wire_extensions_never_become_nested_native_observations() -> Result<()> {
        static CONTRACT: Contract = Contract::new(
            r##"{
            "type":"object","required":["items","reasons"],"additionalProperties":true,
            "$defs":{"Item":{"type":"object","required":["id"],"additionalProperties":true,
                "properties":{"id":{"type":"string"},"label":{"anyOf":[{"type":"string"},{"type":"null"}]}}}},
            "properties":{"items":{"type":"array","items":{"$ref":"#/$defs/Item"}},
                "reasons":{"type":"object","additionalProperties":{"type":"string"}}}
        }"##,
        );
        let value = json!({"items":[{"id":"one","label":null,"future_token":"canary"},
            {"id":"two","label":"Name","future_private":{"token":"canary"}}],
            "reasons":{"read":"available"},"future_token":"canary"});
        let result = CONTRACT.project(&value)?;
        assert_eq!(
            result,
            json!({"items":[{"id":"one","label":null},{"id":"two","label":"Name"}],
            "reasons":{"read":"available"}})
        );
        assert!(!result.to_string().contains("canary"));
        Ok(())
    }
}
