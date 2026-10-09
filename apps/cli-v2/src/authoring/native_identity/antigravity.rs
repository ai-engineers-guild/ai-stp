//! Markdown identities observed in provider-pinned Antigravity 1.2.15.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;
use serde_json::Value;

use super::{invalid, mcp, valid};
use crate::{authoring::frontmatter, canonical, error::Result};

#[derive(Deserialize)]
struct Agent {
    name: String,
    description: String,
    #[serde(flatten)]
    fields: BTreeMap<String, Value>,
}

#[derive(Default, Deserialize)]
struct Skill {
    name: Option<String>,
    #[serde(rename = "description")]
    _description: Option<String>,
    #[serde(rename = "disable-model-invocation")]
    _disable_model_invocation: Option<bool>,
    #[serde(rename = "disable-slash-command")]
    _disable_slash_command: Option<bool>,
}

fn skill_path(path: &str) -> Option<&str> {
    let path = path.strip_prefix(".gemini/").unwrap_or(path);
    ["config/skills/", ".agents/skills/", ".agent/skills/"]
        .into_iter()
        .find_map(|root| path.strip_prefix(root))
}

pub(super) fn skills<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let files: Vec<_> = files.into_iter().collect();
    if files.iter().any(|(path, _)| skill_path(path).is_none()) {
        return Err(invalid());
    }
    let names = visible_skills(files)?;
    if names.is_empty() {
        return Err(invalid());
    }
    Ok(names)
}

pub(super) fn visible_skills<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let mut names = BTreeSet::new();
    for (path, bytes) in files {
        let Some(relative) = skill_path(path) else {
            continue;
        };
        // The pinned scanner visits immediate child directories only, including
        // hidden and node_modules directories. Auxiliary Markdown is not a skill.
        let Some((_, leaf)) = relative.split_once('/') else {
            continue;
        };
        let Some(stem) = leaf.strip_suffix(".md") else {
            continue;
        };
        if !stem.eq_ignore_ascii_case("skill") {
            continue;
        }
        let skill: Option<Skill> = frontmatter::decode(bytes, frontmatter::Dialect::CoreMerged)?;
        // The native fallback is the file stem, not the containing directory.
        let name = skill
            .unwrap_or_default()
            .name
            .filter(|name| !name.is_empty())
            .unwrap_or_else(|| stem.into());
        if !names.insert(name) {
            return Err(
                invalid().with_details([("constraint".into(), "native_id_collision".into())])
            );
        }
    }
    Ok(names.into_iter().collect())
}

fn local_path(path: &str) -> Option<&str> {
    let path = path.strip_prefix(".gemini/").unwrap_or(path);
    [
        "config/agents/",
        "antigravity-cli/agents/",
        ".agents/agents/",
    ]
    .into_iter()
    .find_map(|root| path.strip_prefix(root))
}

fn name(bytes: &[u8]) -> Result<String> {
    let agent: Agent = frontmatter::decode(bytes, frontmatter::Dialect::CoreMerged)?;
    if agent.name.is_empty() || agent.description.is_empty() {
        return Err(invalid());
    }
    for field in ["tools", "skills", "plugins"] {
        if agent.fields.get(field).is_some_and(|value| {
            value
                .as_array()
                .is_none_or(|items| items.iter().any(|item| !item.is_string()))
        }) {
            return Err(invalid());
        }
    }
    for field in ["mainAgent", "subagent"] {
        if agent
            .fields
            .get(field)
            .is_some_and(|value| !value.is_boolean())
        {
            return Err(invalid());
        }
    }
    for field in ["model", "commandExecutionPolicy"] {
        if agent
            .fields
            .get(field)
            .is_some_and(|value| !value.is_string())
        {
            return Err(invalid());
        }
    }
    if let Some(servers) = agent.fields.get("mcpServers") {
        let mut named = serde_json::Map::new();
        for server in servers.as_array().ok_or_else(invalid)? {
            let name = server
                .get("name")
                .and_then(Value::as_str)
                .filter(|name| !name.is_empty())
                .ok_or_else(invalid)?;
            if !server.is_object() || named.insert(name.to_owned(), server.clone()).is_some() {
                return Err(invalid());
            }
        }
        // These are agent-scoped declarations, but named credential fields have
        // the same restriction as standalone MCP configuration.
        let names = mcp::names(
            "antigravity",
            "mcp.json",
            "mcpServers",
            &canonical::bytes(&Value::Object(named))?,
        )?;
        valid(&names)?;
    }
    Ok(agent.name)
}

pub(super) fn agents<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let files: Vec<_> = files.into_iter().collect();
    if files.iter().any(|(path, _)| local_path(path).is_none()) {
        return Err(invalid());
    }
    let names = visible(files)?;
    if names.is_empty() {
        return Err(invalid());
    }
    Ok(names)
}

pub(super) fn visible<'a>(
    files: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<String>> {
    let mut captured = BTreeMap::new();
    for (path, bytes) in files {
        if let Some(path) = local_path(path)
            && captured.insert(path, bytes).is_some()
        {
            return Err(invalid());
        }
    }
    let mut names = BTreeSet::new();
    for (path, bytes) in captured {
        let direct = !path.contains('/');
        let nested = path.split('/').count() == 2;
        if (direct && path.ends_with(".json")) || (nested && path.ends_with("/agent.json")) {
            return Err(invalid());
        }
        if !(direct && path.ends_with(".md") || nested && path.ends_with("/agent.md")) {
            continue;
        }
        // Selection flags do not rename the definition: a subagent-only record
        // still owns its agent identity even though `agy agents` omits it.
        if !names.insert(name(bytes)?) {
            return Err(
                invalid().with_details([("constraint".into(), "native_id_collision".into())])
            );
        }
    }
    Ok(names.into_iter().collect())
}
