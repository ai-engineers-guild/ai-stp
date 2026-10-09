//! Bounded portable authoring text. CommonMark code blocks are always literal.

use std::{collections::BTreeSet, path::Path};

use pulldown_cmark::{Event, Parser, Tag};
use serde_json::{Value, json};

use crate::{
    artifacts, digest,
    error::{Failure, Result},
    files, harnesses,
};

const MAX_SOURCE: usize = 64 * 1024;
const MAX_RENDERED: usize = 64 * 1024;

fn invalid() -> Failure {
    Failure::input("the authoring template has invalid syntax, identity, paths or size")
}

pub fn render(source: &str, harness: &str, name: &str, root: &str) -> Result<Value> {
    let definition = harnesses::definition(harness)?;
    if harness == "undefined"
        || source.len() > MAX_SOURCE
        || name.is_empty()
        || name.len() > 64
        || !name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
        || name.starts_with('-')
        || name.ends_with('-')
        || root.len() > 512
        || !artifacts::safe_path(root)
        || source
            .chars()
            .any(|c| c.is_control() && !matches!(c, '\n' | '\t'))
    {
        return Err(invalid());
    }
    let blocks: Vec<_> = Parser::new(source)
        .into_offset_iter()
        .filter_map(|(event, range)| {
            matches!(event, Event::Start(Tag::CodeBlock(_))).then_some(range)
        })
        .collect();
    let mut block = 0;
    let mut offset = 0;
    let mut active = None;
    let mut used = BTreeSet::new();
    let mut output = String::new();
    for line in source.split_inclusive('\n') {
        let end = offset + line.len();
        while blocks.get(block).is_some_and(|range| range.end <= offset) {
            block += 1;
        }
        let literal = blocks
            .get(block)
            .is_some_and(|range| range.start < end && range.end > offset);
        offset = end;
        if literal {
            if active != Some(false) {
                output.push_str(line);
            }
        } else {
            let trimmed = line.trim();
            if let Some(names) = trimmed
                .strip_prefix("{{#harness:")
                .and_then(|s| s.strip_suffix("}}"))
            {
                if active.is_some() {
                    return Err(invalid());
                }
                let mut seen = BTreeSet::new();
                for name in names.split(',') {
                    if name == "undefined"
                        || !seen.insert(name)
                        || harnesses::definition(name).is_err()
                    {
                        return Err(invalid());
                    }
                }
                active = Some(seen.contains(harness));
            } else if trimmed == "{{/harness}}" {
                if active.take().is_none() {
                    return Err(invalid());
                }
            } else if active != Some(false) {
                let mut rest = line;
                while let Some((before, after)) = rest.split_once("{{") {
                    output.push_str(before);
                    let (tag, after) = after.split_once("}}").ok_or_else(invalid)?;
                    let value = match tag {
                        "harness_id" => harness,
                        "component_name" => name,
                        "component_root" => root,
                        "config_root" => definition.config_root.as_deref().unwrap_or(""),
                        _ => return Err(invalid()),
                    };
                    used.insert(tag);
                    output.push_str(value);
                    if output.len() > MAX_RENDERED {
                        return Err(invalid());
                    }
                    rest = after;
                }
                output.push_str(rest);
            }
        }
        if output.len() > MAX_RENDERED {
            return Err(invalid());
        }
    }
    if active.is_some() {
        return Err(invalid());
    }
    Ok(
        json!({"schema_version":1,"harness_id":harness,"component_name":name,"component_root":root,
        "source_digest":digest::sha256(source.as_bytes()),"rendered_digest":digest::sha256(output.as_bytes()),
        "placeholders":used,"content":output}),
    )
}

pub fn read(path: &Path, harness: &str, name: &str, root: &str) -> Result<Value> {
    let source = String::from_utf8(files::read(path, MAX_SOURCE as u64)?).map_err(|_| invalid())?;
    render(
        &source.replace("\r\n", "\n").replace('\r', "\n"),
        harness,
        name,
        root,
    )
}
