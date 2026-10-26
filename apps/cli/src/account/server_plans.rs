//! Python-compatible server plan preimages, distinct from local canonical JSON.

use std::{collections::BTreeMap, fmt::Write};

use serde_json::Value;

use crate::error::{Failure, Result};

pub(super) fn bytes(value: &Value) -> Result<Vec<u8>> {
    let invalid = || Failure::precondition("the server plan preimage is invalid");
    let fields: BTreeMap<_, _> = value.as_object().ok_or_else(invalid)?.iter().collect();
    if fields
        .values()
        .any(|value| !value.is_string() && !value.is_null() && !value.is_u64())
    {
        return Err(invalid());
    }
    let text = serde_json::to_string(&fields).map_err(|_| invalid())?;
    let mut encoded = String::with_capacity(text.len());
    for character in text.chars() {
        if character >= '\u{7f}' {
            let mut units = [0; 2];
            for unit in character.encode_utf16(&mut units) {
                write!(&mut encoded, "\\u{unit:04x}").map_err(|_| invalid())?;
            }
        } else {
            encoded.push(character);
        }
    }
    Ok(encoded.into_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn unlink_revisions_keep_integer_bytes_and_python_ascii_strings() -> Result<()> {
        assert_eq!(
            bytes(&json!({"revision":17,"name":"café","other":null}))?,
            br#"{"name":"caf\u00e9","other":null,"revision":17}"#
        );
        for value in [
            json!({"revision":-1}),
            json!({"revision":1.5}),
            json!({"revision":true}),
            json!({"nested":{}}),
        ] {
            assert!(bytes(&value).is_err());
        }
        Ok(())
    }
}
