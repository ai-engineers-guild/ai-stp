//! Project JSON: strict input, NFC strings, RFC 8785 bytes.

use std::fmt;

use serde::de::{MapAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::{Map, Value, value::RawValue};
use unicode_normalization::UnicodeNormalization;

use crate::error::{Failure, Result};

const MAX_SAFE_INTEGER: i64 = 9_007_199_254_740_991;
const MAX_DEPTH: usize = 128;
const MAX_JSON_BYTES: usize = 16 * 1024 * 1024;

fn invalid() -> Failure {
    Failure::input("JSON cannot be represented as NFC-normalized RFC 8785 data")
}

fn normalize(text: &str) -> Result<String> {
    if text.contains('\u{feff}') {
        return Err(invalid());
    }
    Ok(text.nfc().collect())
}

struct Object<'a>(Vec<(String, &'a RawValue)>);

impl<'de> Deserialize<'de> for Object<'de> {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> std::result::Result<Self, D::Error> {
        struct ObjectVisitor;
        impl<'de> Visitor<'de> for ObjectVisitor {
            type Value = Object<'de>;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("a JSON object")
            }

            fn visit_map<M: MapAccess<'de>>(
                self,
                mut map: M,
            ) -> std::result::Result<Object<'de>, M::Error> {
                let mut pairs = Vec::new();
                while let Some(pair) = map.next_entry()? {
                    pairs.push(pair);
                }
                Ok(Object(pairs))
            }
        }
        deserializer.deserialize_map(ObjectVisitor)
    }
}

fn decode(raw: &RawValue, depth: usize) -> Result<Value> {
    if depth > MAX_DEPTH {
        return Err(invalid());
    }
    let text = raw.get();
    match text.as_bytes().first() {
        Some(b'{') => {
            let Object(pairs) = serde_json::from_str(text).map_err(|_| invalid())?;
            let mut object = Map::new();
            for (key, raw) in pairs {
                let key = normalize(&key)?;
                if object.contains_key(&key) {
                    return Err(invalid());
                }
                object.insert(key, decode(raw, depth + 1)?);
            }
            Ok(Value::Object(object))
        }
        Some(b'[') => {
            let items: Vec<&RawValue> = serde_json::from_str(text).map_err(|_| invalid())?;
            items.iter().map(|item| decode(item, depth + 1)).collect()
        }
        Some(b'"') => {
            let text: String = serde_json::from_str(text).map_err(|_| invalid())?;
            Ok(Value::String(normalize(&text)?))
        }
        Some(b'-' | b'0'..=b'9') if !text.contains(['.', 'e', 'E']) => {
            let integer = text.parse::<i64>().map_err(|_| invalid())?;
            if !(-MAX_SAFE_INTEGER..=MAX_SAFE_INTEGER).contains(&integer) {
                return Err(invalid());
            }
            Ok(Value::from(integer))
        }
        _ => serde_json::from_str(text).map_err(|_| invalid()),
    }
}

/// Parse without losing duplicate keys or rounding oversized integer tokens.
pub fn parse(bytes: &[u8]) -> Result<Value> {
    if bytes.len() > MAX_JSON_BYTES {
        return Err(invalid());
    }
    let raw: &RawValue = serde_json::from_slice(bytes).map_err(|_| invalid())?;
    decode(raw, 0)
}

/// Validate even in-process values before creating a content identity.
pub fn bytes(value: &Value) -> Result<Vec<u8>> {
    let encoded = serde_json::to_vec(value).map_err(|_| invalid())?;
    let normalized = parse(&encoded)?;
    serde_json_canonicalizer::to_vec(&normalized).map_err(|_| invalid())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retained_project_bytes_preserve_numbers_unicode_and_key_order() -> Result<()> {
        // Fixed RFC 8785 number representations and project NFC semantics.
        let cases = [
            (
                "[333333333.33333329,1E30,4.50,2e-3,1e-27,-0.0]",
                "[333333333.3333333,1e+30,4.5,0.002,1e-27,0]",
            ),
            (
                "{\"\u{e000}\":2,\"\u{10000}\":1,\"z\":0}",
                "{\"z\":0,\"\u{10000}\":1,\"\u{e000}\":2}",
            ),
            (
                "{\"path\":\"/tmp/cafe\u{301}\",\"n\":-0.0}",
                "{\"n\":0,\"path\":\"/tmp/caf\u{e9}\"}",
            ),
        ];
        for (input, expected) in cases {
            assert_eq!(bytes(&parse(input.as_bytes())?)?, expected.as_bytes());
        }
        Ok(())
    }

    #[test]
    fn provider_wire_paths_keep_their_distinct_retained_digest() -> Result<()> {
        let value = serde_json::json!({"path":"/tmp/cafe\u{301}","n":-0.0});
        let wire = serde_json_canonicalizer::to_vec(&value).map_err(|_| invalid())?;
        assert_eq!(wire, "{\"n\":0,\"path\":\"/tmp/cafe\u{301}\"}".as_bytes());
        assert_eq!(
            crate::digest::bytes("ai-stp:provider-plan:v3", &wire)?,
            "sha256:7fd86b905e7f0041c990d2d12683d36b95da8c886adf2cbaead1c15ba9ba8ca7"
        );
        assert_eq!(
            crate::digest::canonical("ai-stp:passport:v1", &value)?,
            "sha256:2ac24a235d63b8c3fc564656a0fda45bc31599aceb19048a463fd5dd8b011d55"
        );
        assert_ne!(wire, bytes(&value)?);
        Ok(())
    }

    #[test]
    fn ambiguous_or_oversized_project_json_still_refuses() {
        for input in [
            r#"{"a":1,"a":2}"#,
            r#"{"a":1,"\u0061":2}"#,
            r#"{"e\u0301":1,"\u00e9":2}"#,
            r#"[{"a":1,"a":2}]"#,
            "9007199254740992",
            "-9007199254740992",
            r#""\ufeff""#,
        ] {
            assert!(parse(input.as_bytes()).is_err(), "{input}");
        }
        assert!(bytes(&serde_json::json!(9_007_199_254_740_992_i64)).is_err());
    }
}
