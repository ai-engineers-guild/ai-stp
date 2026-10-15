//! Local evidence from indexed bytes. A mapping is identity, never installation trust.

mod manifests;
mod records;
pub mod retained;

use crate::{
    digest,
    error::{Failure, Result},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::BTreeMap, path::Path, time::Instant};

const LIMIT: usize = 4096;
const TRACE_LIMIT: usize = 16;
const SOURCE: &str = include_str!("coordinates.json");

#[derive(Deserialize)]
struct Mapping {
    version: String,
    provenance: String,
    entries: Vec<(String, String, String)>,
}

#[derive(Clone, Eq, PartialEq, Ord, PartialOrd, Serialize)]
struct Evidence {
    source: &'static str,
    path: String,
    digest: String,
    reference: String,
}

type ClaimKey = (String, String, String, String, Option<String>);

#[derive(Default)]
struct Reader {
    path: String,
    hash: String,
    claims: BTreeMap<ClaimKey, Vec<Evidence>>,
    stopped: Option<&'static str>,
    files: usize,
    evidence_bytes: usize,
}

fn coordinate(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 512
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._:/@+*-".contains(&c))
        && !value.contains("://")
}

fn version(value: &str) -> Option<String> {
    let value = value.trim();
    (!value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b".*+<>=!~^|, -".contains(&c)))
    .then(|| value.into())
}

fn context(group: &str) -> &'static str {
    if matches!(
        group.to_ascii_lowercase().as_str(),
        "test" | "tests" | "testing"
    ) {
        "testing"
    } else {
        "development"
    }
}

impl Reader {
    fn add(
        &mut self,
        kind: &str,
        name: &str,
        context: &str,
        wanted: Option<&str>,
        source: &'static str,
        reference: &str,
    ) {
        if !coordinate(name) || kind == "package" && name.contains(':') {
            self.stopped
                .get_or_insert("unsupported technology coordinate");
            return;
        }
        let version = wanted.and_then(version);
        let version_kind = if version.is_none() {
            "unknown"
        } else if source == "lock_file" {
            "locked_version"
        } else if source == "checksum_file" {
            "recorded_version"
        } else {
            "declared_range"
        };
        let key = (
            kind.into(),
            name.into(),
            context.into(),
            version_kind.into(),
            version,
        );
        if !self.claims.contains_key(&key) && self.claims.len() >= LIMIT {
            self.stopped.get_or_insert("finding budget");
            return;
        }
        let trace = Evidence {
            source,
            path: self.path.clone(),
            digest: self.hash.clone(),
            reference: if coordinate(reference) && reference.len() <= 256 {
                reference.into()
            } else {
                String::new()
            },
        };
        if self
            .claims
            .get(&key)
            .is_some_and(|entries| entries.len() >= TRACE_LIMIT || entries.contains(&trace))
        {
            return;
        }
        let size = 6 * trace.path.len() + trace.reference.len() + 256;
        if self.evidence_bytes + size > 4 * 1024 * 1024 {
            self.stopped.get_or_insert("evidence byte budget");
            return;
        }
        self.evidence_bytes += size;
        self.claims.entry(key).or_default().push(trace);
    }

    fn dependency(&mut self, name: &str, spec: &Value, context: &str, reference: &str) {
        let name = spec.get("package").and_then(Value::as_str).unwrap_or(name);
        let wanted = spec
            .as_str()
            .or_else(|| spec.get("version").and_then(Value::as_str));
        self.add("package", name, context, wanted, "declared", reference);
    }

    fn requirements(&mut self, text: &str, context: &str, reference: &str) {
        for line in text.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if line.len() > 512 || line.starts_with('-') {
                self.stopped
                    .get_or_insert("unsupported requirement directive");
                continue;
            }
            // Extract only the distribution name; URLs, markers and local paths
            // never enter the report. This does not evaluate environment markers.
            let end = line
                .find(|c: char| !(c.is_ascii_alphanumeric() || "._-".contains(c)))
                .unwrap_or(line.len());
            let name = line[..end]
                .to_ascii_lowercase()
                .split(['.', '_', '-'])
                .filter(|v| !v.is_empty())
                .collect::<Vec<_>>()
                .join("-");
            if name.is_empty() {
                self.stopped.get_or_insert("unsupported requirement");
                continue;
            }
            let mut rest = line[end..].trim();
            if rest.starts_with('[') {
                let Some((_, after)) = rest.split_once(']') else {
                    self.stopped.get_or_insert("invalid requirement");
                    continue;
                };
                rest = after.trim();
            }
            if !rest.is_empty() && !rest.starts_with(['@', ';', '#', '(', '<', '>', '=', '!', '~'])
            {
                self.stopped
                    .get_or_insert("unsupported requirement locator");
                continue;
            }
            let wanted = rest
                .split([';', '#'])
                .next()
                .unwrap_or("")
                .trim()
                .trim_start_matches('(')
                .trim_end_matches(')');
            self.add(
                "package",
                &name,
                context,
                Some(wanted),
                "declared",
                reference,
            );
        }
    }
}

/// Inspect the defined bounded detection surface. No source or state is written.
pub fn inspect(root: &Path) -> Result<Value> {
    let (root, directory) = super::open_root(root)?;
    inspect_at(&root, &directory)
}

fn inspect_at(root: &Path, directory: &cap_std::fs::Dir) -> Result<Value> {
    let mapping: Mapping = serde_json::from_str(SOURCE)
        .map_err(|_| Failure::precondition("embedded technology mapping is invalid"))?;
    let mut identities = BTreeMap::new();
    for (id, kind, name) in &mapping.entries {
        if identities
            .insert((kind.as_str(), name.as_str()), id)
            .is_some_and(|old| old != id)
        {
            return Err(Failure::precondition(
                "embedded technology coordinate is ambiguous",
            ));
        }
    }
    let mut reader = Reader::default();
    let started = Instant::now();
    let index = super::index::visit_at(root, directory, &mut |path, language, bytes| {
        if started.elapsed().as_secs() >= 20 {
            reader.stopped.get_or_insert("detection time budget");
            return;
        }
        reader.path = path.into();
        reader.hash = bytes.map(digest::sha256).unwrap_or_default();
        if let Some(language) = language
            && bytes.is_some()
        {
            reader.add(
                "alias",
                language,
                "unspecified",
                None,
                "source_file",
                "language",
            );
        }
        let name = path.rsplit('/').next().unwrap_or(path);
        if identities.contains_key(&("configuration", name)) && bytes.is_some() {
            reader.add(
                "configuration",
                name,
                "unspecified",
                None,
                "configuration",
                "filename",
            );
        }
        if !manifests::supported(name) && !records::supported(name) {
            return;
        }
        reader.files += 1;
        if reader.files > 2000 {
            reader.stopped.get_or_insert("manifest budget");
            return;
        }
        let result = (|| {
            let text = std::str::from_utf8(bytes.ok_or(())?).map_err(|_| ())?;
            if manifests::supported(name) {
                manifests::read(name, text, &mut reader)
            } else {
                records::read(name, text, &mut reader)
            }
        })();
        if result.is_err() {
            reader
                .stopped
                .get_or_insert("invalid or unavailable manifest");
        }
    })?;
    if let Some(excluded) = index["excluded"].as_array() {
        for entry in excluded {
            let name = entry["path"]
                .as_str()
                .unwrap_or("")
                .rsplit('/')
                .next()
                .unwrap_or("");
            if manifests::supported(name) || records::supported(name) {
                reader.stopped.get_or_insert("excluded manifest");
            }
        }
    }
    let mut findings: BTreeMap<(String, String, String), Vec<Value>> = BTreeMap::new();
    for ((kind, name, context, version_kind, version), mut evidence) in reader.claims {
        evidence.sort();
        findings
            .entry((kind, name, context))
            .or_default()
            .push(json!({"version":version,"version_kind":version_kind,"evidence":evidence}));
    }
    let findings:Vec<_> = findings.into_iter().map(|((kind,name,context),claims)| {
        let id = identities.get(&(kind.as_str(),name.as_str()));
        json!({"kind":kind,"coordinate":name,"context":context,"technology_id":id,"claims":claims})
    }).collect();
    let stopped = index["stopped_by"].as_str().or(reader.stopped);
    Ok(
        json!({"schema_version":1,"detector_version":"native-technology/1","root":index["root"],
        "state":if stopped.is_some(){"partial"}else{"complete"},"stopped_by":stopped,
        "index_digest":digest::sha256(&serde_json_canonicalizer::to_vec(&index).map_err(|_|Failure::precondition("technology index cannot be encoded"))?),
        "mapping":{"version":mapping.version,"provenance":mapping.provenance,"digest":digest::sha256(SOURCE.as_bytes())},
        "findings":findings,"execution":"not_run","installed_software_verified":false,"publication":"not_performed"}),
    )
}
