//! Deliberately approximate, top-level line scans; never compiler evidence.

use std::{collections::BTreeMap, time::Instant};

use regex::Regex;

use super::{DEADLINE, MAX_SYMBOLS, Outline};
use crate::error::{Failure, Result};

pub(super) struct Reader(BTreeMap<&'static str, Vec<(&'static str, Regex)>>);

impl Reader {
    pub(super) fn new() -> Result<Self> {
        let mut languages: BTreeMap<_, Vec<_>> = BTreeMap::new();
        for (language, kind, pattern) in [
            (
                "typescript",
                "function",
                r"^export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)",
            ),
            (
                "typescript",
                "class",
                r"^export\s+(?:default\s+)?(?:abstract\s+)?class\s+(\w+)",
            ),
            (
                "typescript",
                "type",
                r"^export\s+(?:type|interface|enum)\s+(\w+)",
            ),
            (
                "typescript",
                "constant",
                r"^export\s+(?:const|let|var)\s+(\w+)",
            ),
            (
                "javascript",
                "function",
                r"^export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)",
            ),
            (
                "javascript",
                "class",
                r"^export\s+(?:default\s+)?class\s+(\w+)",
            ),
            (
                "javascript",
                "constant",
                r"^export\s+(?:const|let|var)\s+(\w+)",
            ),
            (
                "rust",
                "function",
                r"^pub(?:\([^)]*\))?\s+(?:async\s+)?fn\s+(\w+)",
            ),
            (
                "rust",
                "type",
                r"^pub(?:\([^)]*\))?\s+(?:struct|enum|trait|type|union)\s+(\w+)",
            ),
            (
                "rust",
                "constant",
                r"^pub(?:\([^)]*\))?\s+(?:const|static)\s+(\w+)",
            ),
            ("rust", "module", r"^pub(?:\([^)]*\))?\s+mod\s+(\w+)"),
            ("rust", "entry", r"^(?:async\s+)?fn\s+(main)\s*\("),
            ("go", "function", r"^func\s+(?:\([^)]*\)\s*)?([A-Z]\w*)"),
            ("go", "type", r"^type\s+([A-Z]\w*)"),
            ("go", "constant", r"^(?:const|var)\s+([A-Z]\w*)"),
            ("go", "entry", r"^func\s+(main)\s*\("),
            ("dart", "class", r"^(?:abstract\s+)?class\s+(\w+)"),
            ("dart", "type", r"^(?:mixin|enum|extension|typedef)\s+(\w+)"),
            (
                "dart",
                "function",
                r"^(?:[\w<>,\s\[\]?]+\s+)?(\w+)\s*\([^)]*\)\s*(?:async\s*)?\{",
            ),
        ] {
            let pattern = Regex::new(pattern)
                .map_err(|_| Failure::precondition("the source outline adapter is invalid"))?;
            languages.entry(language).or_default().push((kind, pattern));
        }
        Ok(Self(languages))
    }

    pub(super) fn read(
        &self,
        text: &str,
        language: &str,
        started: Instant,
    ) -> std::result::Result<Outline, &'static str> {
        let patterns = self
            .0
            .get(language)
            .ok_or("no adapter is declared for this language")?;
        let mut outline = Outline {
            symbols: 0,
            entry: false,
        };
        for line in text.lines() {
            if started.elapsed() >= DEADLINE {
                return Err("time budget");
            }
            if line.is_empty()
                || line.starts_with([' ', '\t'])
                || ["//", "#", "/*", "*", "--"]
                    .iter()
                    .any(|prefix| line.starts_with(prefix))
            {
                continue;
            }
            for (kind, pattern) in patterns {
                if let Some(found) = pattern.captures(line) {
                    let name = found
                        .get(1)
                        .ok_or("the source outline adapter is invalid")?
                        .as_str();
                    outline.symbols += usize::from(*kind != "entry");
                    outline.entry |= *kind == "entry"
                        || (*kind == "function"
                            && (name == "main" || (language == "go" && name == "Main")));
                    if outline.symbols > MAX_SYMBOLS {
                        return Err("symbol budget");
                    }
                    break;
                }
            }
        }
        Ok(outline)
    }
}
