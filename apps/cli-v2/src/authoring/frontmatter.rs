//! Bounded data-only YAML headers shared by portable and native authoring.

use crate::error::{Failure, Result};
use serde_json::Value;

pub(super) fn optional(bytes: &[u8]) -> Result<Value> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| Failure::precondition("the Markdown source must be UTF-8"))?;
    if text.lines().next() == Some("---") {
        required(bytes)
    } else {
        Ok(serde_json::json!({}))
    }
}

pub(super) fn required(bytes: &[u8]) -> Result<Value> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| Failure::precondition("the Markdown source must be UTF-8"))?;
    let mut lines = text.split_inclusive('\n');
    if lines
        .next()
        .is_none_or(|line| line.trim_end_matches(['\r', '\n']) != "---")
    {
        return Err(Failure::precondition(
            "the source requires YAML frontmatter on its first line",
        ));
    }
    let mut header = String::new();
    for line in lines {
        if line.trim_end_matches(['\r', '\n']) == "---" {
            let options = serde_saphyr::options! { budget: serde_saphyr::budget! {
                max_depth:8, max_events:10_000, max_aliases:100, max_documents:1,
            }};
            let value: Value =
                serde_saphyr::from_str_with_options(&header, options).map_err(|_| {
                    Failure::precondition("frontmatter is invalid or exceeds its parsing budget")
                })?;
            if !value.is_object() {
                return Err(Failure::precondition("frontmatter must be an object"));
            }
            return Ok(value);
        }
        header.push_str(line);
        if header.len() > 64 * 1024 {
            return Err(Failure::precondition("frontmatter exceeds 64 KiB"));
        }
    }
    Err(Failure::precondition("frontmatter is not closed"))
}
