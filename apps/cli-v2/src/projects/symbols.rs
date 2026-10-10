//! A bounded table of contents, with the strength of each language adapter explicit.

mod python;
mod scanned;

use std::{
    collections::BTreeMap,
    path::Path,
    time::{Duration, Instant},
};

use serde_json::{Value, json};

use crate::{error::Result, wire::Schema};

const MAX_FILES: usize = 2000;
const MAX_SOURCE: usize = 512 * 1024;
const MAX_SYMBOLS: usize = 10_000;
const DEADLINE: Duration = Duration::from_secs(20);
static SCHEMA: Schema = Schema::new(include_str!(
    "../../../../schemas/v1/cli-project-symbols.schema.json"
));

struct Outline {
    symbols: usize,
    entry: bool,
}

#[derive(Default)]
struct Language {
    files: usize,
    available: usize,
    symbols: usize,
    tests: usize,
    entries: Vec<String>,
    reason: Option<&'static str>,
}

fn is_test(path: &str) -> bool {
    let path = format!("/{}", path.to_lowercase());
    [
        "test_", "_test.", ".test.", ".spec.", "/tests/", "/test/", "/spec/",
    ]
    .iter()
    .any(|marker| path.contains(marker))
}

pub fn survey(path: &Path) -> Result<Value> {
    let started = Instant::now();
    let mut python = python::Reader::new()?;
    let scanned = scanned::Reader::new()?;
    let mut languages: BTreeMap<String, Language> = BTreeMap::new();
    let mut visited = 0;
    let mut stopped = None;
    let index = super::index::visit(path, &mut |path, language, bytes| {
        let Some(language) = language else { return };
        if visited >= MAX_FILES {
            stopped.get_or_insert("file budget");
            return;
        }
        if started.elapsed() >= DEADLINE {
            stopped.get_or_insert("time budget");
            return;
        }
        visited += 1;
        let held = languages.entry(language.into()).or_default();
        held.files += 1;
        held.tests += usize::from(is_test(path));
        let outline = (|| {
            let bytes = bytes.ok_or("indexed source bytes are unavailable")?;
            if bytes.len() > MAX_SOURCE {
                return Err("larger than the source budget");
            }
            let text = std::str::from_utf8(bytes).map_err(|_| "source is not UTF-8")?;
            if language == "python" {
                python.read(text, started)
            } else {
                scanned.read(text, language, started)
            }
        })();
        match outline {
            Ok(outline) => {
                held.available += 1;
                held.symbols += outline.symbols;
                if outline.entry {
                    held.entries.push(path.into());
                }
            }
            Err(reason) => {
                held.reason.get_or_insert(reason);
                stopped.get_or_insert(reason);
            }
        }
    })?;
    let languages:Vec<_> = languages.into_iter().map(|(language,mut held)| {
        held.entries.sort();
        let method = if language == "python" { "syntax_tree" } else { "line_scan" };
        let reason = held.reason.or((method == "line_scan").then_some("read line by line; declarations in strings or block comments may be counted"));
        json!({"schema_version":1,"language":language,"state":if held.available>0 {"available"}else{"not_available"},
            "method":(held.available>0).then_some(method),"reason":reason,
            "files":held.files,"symbols":held.symbols,"tests":held.tests,"entry_points":held.entries})
    }).collect();
    let stopped = index["stopped_by"].as_str().or(stopped);
    let result = json!({"schema_version":1,"root":index["root"],"state":if stopped.is_some(){"partial"}else{"complete"},"stopped_by":stopped,"languages":languages});
    SCHEMA.validate(&result)?;
    Ok(result)
}
