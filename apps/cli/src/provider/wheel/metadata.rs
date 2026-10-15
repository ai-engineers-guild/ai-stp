//! Bounded wheel header fields; package descriptions are never interpreted.

use std::collections::BTreeMap;

use super::{MAX_METADATA, invalid};
use crate::error::Result;

pub(crate) fn platform_tag(platform: &str) -> Result<&'static str> {
    match platform {
        "linux/x86_64" => Ok("manylinux_2_34_x86_64"),
        "linux/arm64" => Ok("manylinux_2_34_aarch64"),
        "macos/x86_64" => Ok("macosx_10_12_x86_64"),
        "macos/arm64" => Ok("macosx_11_0_arm64"),
        "windows/x86_64" => Ok("win_amd64"),
        "windows/arm64" => Ok("win_arm64"),
        _ => Err(invalid()),
    }
}

fn headers(bytes: &[u8]) -> Result<BTreeMap<String, Vec<String>>> {
    if bytes.len() > MAX_METADATA {
        return Err(invalid());
    }
    let text = std::str::from_utf8(bytes).map_err(|_| invalid())?;
    let mut fields: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut previous = String::new();
    for (index, line) in text.lines().enumerate() {
        if line.is_empty() {
            break;
        }
        if index >= 2000
            || line.len() > 16 * 1024
            || line.chars().any(|c| c.is_control() && c != '\t')
        {
            return Err(invalid());
        }
        if line.starts_with([' ', '\t']) {
            let value = fields
                .get_mut(&previous)
                .and_then(|values| values.last_mut())
                .ok_or_else(invalid)?;
            if value.len() + line.len() > 16 * 1024 {
                return Err(invalid());
            }
            value.push(' ');
            value.push_str(line.trim());
            continue;
        }
        let (name, value) = line.split_once(':').ok_or_else(invalid)?;
        if name.is_empty()
            || name.len() > 128
            || !name.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
        {
            return Err(invalid());
        }
        previous = name.to_ascii_lowercase();
        fields
            .entry(previous.clone())
            .or_default()
            .push(value.trim().to_owned());
    }
    Ok(fields)
}

fn one<'a>(fields: &'a BTreeMap<String, Vec<String>>, name: &str) -> Result<&'a str> {
    let values = fields
        .get(name)
        .filter(|values| values.len() == 1)
        .ok_or_else(invalid)?;
    Ok(values[0].as_str())
}

pub(super) fn validate(
    files: &BTreeMap<String, Vec<u8>>,
    info: &str,
    project: &str,
    version: &str,
    tag: &str,
) -> Result<String> {
    let metadata = headers(files.get(&format!("{info}/METADATA")).ok_or_else(invalid)?)?;
    let name = one(&metadata, "name")?;
    let mut normalized = String::new();
    for byte in name.bytes() {
        if matches!(byte, b'-' | b'_' | b'.') {
            if !normalized.ends_with('-') {
                normalized.push('-');
            }
        } else if byte.is_ascii_alphanumeric() {
            normalized.push(char::from(byte.to_ascii_lowercase()));
        } else {
            return Err(invalid());
        }
    }
    if normalized != project || one(&metadata, "version")? != version {
        return Err(invalid());
    }
    let metadata_version = one(&metadata, "metadata-version")?;
    if !matches!(
        metadata_version,
        "1.1" | "1.2" | "2.1" | "2.2" | "2.3" | "2.4" | "2.5" | "2.6"
    ) {
        return Err(invalid());
    }
    let license = if metadata.contains_key("license-expression") {
        one(&metadata, "license-expression")?
    } else {
        one(&metadata, "license")?
    };
    if license.is_empty()
        || license.len() > 1024
        || matches!(license, "NOASSERTION" | "NONE" | "UNKNOWN")
    {
        return Err(invalid());
    }
    let wheel = headers(files.get(&format!("{info}/WHEEL")).ok_or_else(invalid)?)?;
    if one(&wheel, "wheel-version")? != "1.0"
        || one(&wheel, "root-is-purelib")? != "false"
        || one(&wheel, "tag")? != format!("py3-none-{tag}")
    {
        return Err(invalid());
    }
    Ok(license.into())
}
