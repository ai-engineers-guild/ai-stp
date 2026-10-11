//! Public marked attachment semantics used for independent byte verification.

use super::invalid;
use crate::error::Result;

const BEGIN: &str = ":::begin-ai-stp";
const END: &str = ":::end-ai-stp";

struct Region<'a> {
    before: &'a str,
    section: &'a str,
    after: &'a str,
    prefix: &'a str,
}

fn region(text: &str) -> Result<Option<Region<'_>>> {
    let (begin, end) = match (text.find(BEGIN), text.find(END)) {
        (None, None) => return Ok(None),
        (Some(begin), Some(end))
            if begin < end
                && !text[begin + BEGIN.len()..].contains(BEGIN)
                && !text[end + END.len()..].contains(END) =>
        {
            (begin, end)
        }
        _ => return Err(invalid()),
    };
    let mut end = end + END.len();
    end += if text[end..].starts_with("\r\n") {
        2
    } else {
        usize::from(text[end..].starts_with('\n'))
    };
    let prefix = prefix(text);
    if prefix.len() > begin {
        return Err(invalid());
    }
    Ok(Some(Region {
        before: &text[..begin],
        section: &text[begin..end],
        after: &text[end..],
        prefix,
    }))
}

fn prefix(text: &str) -> &str {
    let Some(first) = text.lines().next().filter(|line| *line == "---") else {
        return "";
    };
    let mut offset = first.len() + if text.starts_with("---\r\n") { 2 } else { 1 };
    if offset > text.len() {
        return "";
    }
    for line in text[offset..].split_inclusive('\n') {
        offset += line.len();
        if line.trim_end_matches(['\r', '\n']) == "---" && line.ends_with('\n') {
            offset += if text[offset..].starts_with("\r\n") {
                2
            } else {
                usize::from(text[offset..].starts_with('\n'))
            };
            return &text[..offset];
        }
    }
    ""
}

pub(super) fn desired(
    existing: Option<&[u8]>,
    incoming: Option<&[u8]>,
    owned: bool,
) -> Result<Option<Vec<u8>>> {
    let previous = std::str::from_utf8(existing.unwrap_or_default()).map_err(|_| invalid())?;
    let held = region(previous)?;
    let Some(incoming) = incoming else {
        return Ok(held.map(|held| format!("{}{}", held.prefix, held.section).into_bytes()));
    };
    let next = std::str::from_utf8(incoming).map_err(|_| invalid())?;
    let next_region = region(next)?;
    if !owned && existing.is_some() {
        let unmarked = held.as_ref().map_or_else(
            || previous.to_owned(),
            |held| format!("{}{}", &held.before[held.prefix.len()..], held.after),
        );
        if !unmarked.trim().is_empty() && unmarked.trim() != next.trim() {
            return Err(invalid());
        }
    }
    let Some(held) = held else {
        return Ok(Some(incoming.to_vec()));
    };
    let result = if let Some(next_region) = next_region {
        format!(
            "{}{}{}",
            next_region.before, held.section, next_region.after
        )
    } else {
        let prefix = if next.starts_with("---\n") {
            ""
        } else {
            held.prefix
        };
        let newline = if next.is_empty() || next.ends_with('\n') {
            ""
        } else {
            "\n"
        };
        format!("{prefix}{next}{newline}{}", held.section)
    };
    Ok(Some(result.into_bytes()))
}
