//! Deterministic portable-source preparation for an explicit native provider scope.

use std::path::Path;

use serde_json::{Value, json};

use super::{freezing, source_project};
use crate::{
    artifacts, canonical, digest,
    error::{Failure, Result},
    harnesses::Shape,
    passport,
    projection::{self, Scope},
    provider::Info,
};

pub struct Prepared {
    pub adaptation: Value,
    pub projection_bytes: Vec<u8>,
    pub source_bytes: Vec<u8>,
    pub snapshot_digest: String,
}

fn invalid(message: &str) -> Failure {
    Failure::precondition(message)
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .filter(|s| !s.trim().is_empty())
        .ok_or_else(|| invalid("portable source metadata is incomplete"))
}

fn frontmatter(bytes: &[u8]) -> Result<Value> {
    let text = std::str::from_utf8(bytes).map_err(|_| invalid("skill source must be UTF-8"))?;
    let mut lines = text.split_inclusive('\n');
    if lines
        .next()
        .is_none_or(|line| line.trim_end_matches(['\r', '\n']) != "---")
    {
        return Err(invalid("a portable skill requires YAML frontmatter"));
    }
    let mut header = String::new();
    for line in lines {
        if line.trim_end_matches(['\r', '\n']) == "---" {
            let options = serde_saphyr::options! { budget: serde_saphyr::budget! {
                max_depth:8, max_events:10_000, max_aliases:100, max_documents:1,
            }};
            let value: Value =
                serde_saphyr::from_str_with_options(&header, options).map_err(|_| {
                    invalid("skill frontmatter is invalid or exceeds its parsing budget")
                })?;
            if !value.is_object() {
                return Err(invalid("skill frontmatter must be an object"));
            }
            return Ok(value);
        }
        header.push_str(line);
        if header.len() > 64 * 1024 {
            return Err(invalid("skill frontmatter exceeds 64 KiB"));
        }
    }
    Err(invalid("skill frontmatter is not closed"))
}

fn markdown(metadata: Value, body: &str) -> Result<Vec<u8>> {
    let mut output = String::from("---\n");
    for (key, value) in metadata
        .as_object()
        .ok_or_else(|| invalid("native metadata is not an object"))?
    {
        output.push_str(key);
        output.push_str(": ");
        // JSON scalar escaping is valid YAML 1.2; emit conventional frontmatter fields.
        output.push_str(
            &String::from_utf8(canonical::bytes(value)?)
                .map_err(|_| invalid("native metadata is not UTF-8"))?,
        );
        output.push('\n');
    }
    output.push_str("---\n");
    output.push_str(body);
    Ok(output.into_bytes())
}

/// Reads source only; installing or storing the result requires a separate exact plan.
pub fn prepare(root: &Path, requested: Scope, provider: &Info) -> Result<Prepared> {
    let project = source_project::capture(root)?;
    from_snapshot(&project, requested, provider)
}

pub(super) fn from_snapshot(
    project: &source_project::Captured,
    requested: Scope,
    provider: &Info,
) -> Result<Prepared> {
    if project.report["source_ready"] != true {
        return Err(invalid("the portable source is not structurally ready")
            .with_details([("source".into(), project.report.clone())]));
    }
    let values: Value = project.patch.clone().into();
    let kind = text(&values, "component_type")?;
    let name = text(&values, "name")?;
    let description = text(&values, "description")?;
    let harness = text(provider.document(), "harness_id")?;
    let route = projection::route(kind, harness, requested)?
        .filter(|route| route.target_scope == requested)
        .ok_or_else(|| {
            invalid("the requested harness scope has no explicit provider route for this kind")
        })?;
    let source_bytes = artifacts::encode_tree(&project.files)?;
    let source_digest = digest::bytes("ai-stp:artifact:v1", &source_bytes)?;
    let mut source = json!({"harness_id":harness,"scope":requested,"projection_kind":route.projection_kind,
        "native_ids":[name],"declared_key":"","source_mode":0o644});
    let payload;
    if kind == "skill" {
        let entry = project
            .files
            .iter()
            .find(|file| file.path == "SKILL.md")
            .ok_or_else(|| invalid("a skill source must contain SKILL.md at its root"))?;
        let metadata = frontmatter(&entry.bytes)?;
        if metadata.as_object().is_none_or(|object| {
            object.keys().any(|key| {
                ![
                    "name",
                    "description",
                    "license",
                    "compatibility",
                    "metadata",
                ]
                .contains(&key.as_str())
            })
        }) {
            return Err(invalid(
                "harness-specific skill fields require an explicit native adaptation",
            ));
        }
        if metadata["name"] != name
            || name.contains("--")
            || text(&metadata, "description")?.chars().count() > 1024
            || metadata
                .get("license")
                .is_some_and(|value| !value.is_string())
            || metadata.get("compatibility").is_some_and(|value| {
                value
                    .as_str()
                    .is_none_or(|s| s.is_empty() || s.chars().count() > 500)
            })
            || metadata.get("metadata").is_some_and(|value| {
                value
                    .as_object()
                    .is_none_or(|object| object.values().any(|v| !v.is_string()))
            })
        {
            return Err(invalid(
                "skill frontmatter disagrees with its portable identity or field limits",
            ));
        }
        source["managed_paths"] = json!([format!("{}/{name}", route.relative)]);
        source["content_format"] = artifacts::TREE_FORMAT.into();
        payload = source_bytes.clone();
    } else {
        if project.files.len() != 1 || !matches!(kind, "instruction" | "command" | "agent") {
            return Err(invalid(
                "this portable kind requires one complete text source; auxiliary files need an explicit native adaptation",
            ));
        }
        let file = &project.files[0];
        let body = std::str::from_utf8(&file.bytes)
            .map_err(|_| invalid("portable text source must be UTF-8"))?;
        if body.lines().next().is_some_and(|line| line.trim() == "---") {
            return Err(invalid(
                "native frontmatter requires an explicit native adaptation; portable conversion will not discard it",
            ));
        }
        let mut suffix = "md";
        payload = match (kind, harness) {
            ("instruction", "cursor") => {
                suffix = "mdc";
                markdown(json!({"alwaysApply":true}), body)?
            }
            ("instruction", "antigravity") => markdown(
                json!({"trigger":"always_on","description":description}),
                body,
            )?,
            ("instruction", _) => file.bytes.clone(),
            ("command", "cursor") => file.bytes.clone(),
            ("command", "claude-code" | "codex" | "pi" | "opencode") => {
                markdown(json!({"description":description}), body)?
            }
            ("agent", "codex") => {
                suffix = "toml";
                let mut document = toml_edit::DocumentMut::new();
                document["name"] = toml_edit::value(name);
                document["description"] = toml_edit::value(description);
                document["developer_instructions"] = toml_edit::value(body);
                document.to_string().into_bytes()
            }
            ("agent", "claude-code" | "cursor" | "antigravity") => {
                markdown(json!({"name":name,"description":description}), body)?
            }
            ("agent", "opencode") => {
                markdown(json!({"description":description,"mode":"subagent"}), body)?
            }
            _ => {
                return Err(invalid(
                    "this harness has no verified portable text conversion; provide an explicit native adaptation",
                ));
            }
        };
        let path = if route.shape == Shape::File {
            route.relative.clone()
        } else {
            format!("{}/{name}.{suffix}", route.relative)
        };
        source["managed_paths"] = json!([path]);
        source["content_format"] = artifacts::FILE_FORMAT.into();
        source["source_mode"] = file.mode.into();
    }
    let (mut adaptation, projection_bytes) =
        freezing::project(&values, &source, payload, std::slice::from_ref(provider))?;
    adaptation["implementation_mode"] = "derived".into();
    adaptation["source_artifact"] = json!({"digest":source_digest,"size_bytes":source_bytes.len()});
    adaptation["scope_adaptations"][0]["technical_support_reason"] = "portable source compiled for the explicit provider profile; harness execution not assessed".into();
    let adaptation = seal_derived(adaptation)?;
    Ok(Prepared {
        adaptation,
        projection_bytes,
        source_bytes,
        snapshot_digest: text(&project.report, "snapshot_digest")?.into(),
    })
}

pub(super) fn seal_derived(mut adaptation: Value) -> Result<Value> {
    let scopes = adaptation["scope_adaptations"]
        .as_array_mut()
        .ok_or_else(|| invalid("portable adaptation scopes are invalid"))?;
    scopes.sort_by(|a, b| a["scope"].as_str().cmp(&b["scope"].as_str()));
    let projections: Vec<_> = scopes
        .iter()
        .map(
            |scope| json!({"scope":scope["scope"],"digest":scope["projection_artifact"]["digest"]}),
        )
        .collect();
    let transform = json!({"transform_id":"portable-source","version":"1.0",
        "harness_id":adaptation["harness_id"],"component_type":adaptation["logical_component_type"],
        "source_digest":adaptation["source_artifact"]["digest"],"projections":projections});
    adaptation["transform"] = json!({"transform_id":"portable-source","version":"1.0",
        "digest":digest::canonical("ai-stp:component-adaptation:v1",&transform)?});
    passport::versions::seal_adaptation(&adaptation)
}
