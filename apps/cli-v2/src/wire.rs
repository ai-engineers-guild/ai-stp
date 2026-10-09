//! Embedded generated wire schemas. Validation never resolves external input.

use std::sync::OnceLock;

use serde_json::Value;

use crate::error::{ErrorKind, Failure, Result};

pub struct Schema {
    source: &'static str,
    reader_defaults: bool,
    definition: Option<&'static str>,
    compiled: OnceLock<std::result::Result<jsonschema::Validator, String>>,
}

impl Schema {
    pub const fn new(source: &'static str) -> Self {
        Self {
            source,
            reader_defaults: false,
            definition: None,
            compiled: OnceLock::new(),
        }
    }

    /// Historical readers accept omitted fields with explicit schema defaults.
    /// The original document is never filled or reserialized for its identity.
    pub const fn reader(source: &'static str) -> Self {
        Self {
            source,
            reader_defaults: true,
            definition: None,
            compiled: OnceLock::new(),
        }
    }

    pub const fn definition(source: &'static str, definition: &'static str) -> Self {
        Self {
            source,
            reader_defaults: false,
            definition: Some(definition),
            compiled: OnceLock::new(),
        }
    }

    pub fn validate(&self, document: &Value) -> Result<()> {
        let validator = self
            .compiled
            .get_or_init(|| {
                let mut schema: Value = serde_json::from_str(self.source)
                    .map_err(|_| "embedded schema is invalid".to_owned())?;
                if self.reader_defaults {
                    allow_explicit_defaults(&mut schema);
                }
                if let Some(definition) = self.definition {
                    schema = serde_json::json!({"$defs":schema["$defs"],"$ref":format!("#/$defs/{definition}")});
                }
                jsonschema::options()
                    .offline()
                    .should_validate_formats(true)
                    .build(&schema)
                    .map_err(|_| "embedded schema cannot be compiled".to_owned())
            })
            .as_ref()
            .map_err(|message| Failure::new(ErrorKind::Internal, message.clone()))?;
        if !validator.is_valid(document) {
            return Err(Failure::precondition(
                "document does not match the supported wire contract",
            ));
        }
        Ok(())
    }
}

fn allow_explicit_defaults(schema: &mut Value) {
    if let Value::Object(object) = schema {
        let optional: Vec<String> = object
            .get("properties")
            .and_then(Value::as_object)
            .into_iter()
            .flat_map(|properties| properties.iter())
            .filter(|(_, value)| value.get("default").is_some())
            .map(|(key, _)| key.clone())
            .collect();
        if let Some(required) = object.get_mut("required").and_then(Value::as_array_mut) {
            required.retain(|key| {
                !key.as_str()
                    .is_some_and(|key| optional.iter().any(|v| v == key))
            });
        }
        // Traverse schema keywords only, never examples, const values or defaults.
        for key in [
            "$defs",
            "properties",
            "patternProperties",
            "dependentSchemas",
        ] {
            if let Some(children) = object.get_mut(key).and_then(Value::as_object_mut) {
                for child in children.values_mut() {
                    allow_explicit_defaults(child);
                }
            }
        }
        for key in ["allOf", "anyOf", "oneOf", "prefixItems"] {
            if let Some(children) = object.get_mut(key).and_then(Value::as_array_mut) {
                for child in children {
                    allow_explicit_defaults(child);
                }
            }
        }
        for key in [
            "items",
            "additionalProperties",
            "if",
            "then",
            "else",
            "not",
            "contains",
        ] {
            if let Some(child) = object.get_mut(key) {
                allow_explicit_defaults(child);
            }
        }
    }
}

/// Check canonical representability and duplicate keys, preserving wire strings.
pub fn parse(bytes: &[u8]) -> Result<Value> {
    crate::canonical::parse(bytes).map_err(|_| Failure::precondition("wire JSON is invalid"))?;
    serde_json::from_slice(bytes).map_err(|_| Failure::precondition("wire JSON is invalid"))
}
