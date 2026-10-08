use std::collections::BTreeMap;

use serde_json::{Value, json};

use super::{invalid, text};
use crate::error::Result;

fn declared<'a>(document: &'a Value, field: &str) -> Result<&'a Value> {
    let fact = &document["facts"][field]["value"];
    match document.get(field) {
        Some(value) if !fact.is_null() && value != fact => Err(invalid(
            "logical composition metadata disagrees with its declared fact",
        )),
        Some(value) => Ok(value),
        None => Ok(fact),
    }
}

#[derive(Default)]
pub(super) struct Composition {
    harness: String,
    paths: BTreeMap<String, String>,
    native_ids: BTreeMap<String, BTreeMap<String, String>>,
    kinds: BTreeMap<String, String>,
    exclusions: Vec<Exclusion>,
    precedence: BTreeMap<i64, String>,
    hooks: BTreeMap<(String, i64), String>,
    chosen: Vec<Value>,
    converted: Vec<Value>,
}

struct Exclusion {
    owner: String,
    family: &'static str,
    value: String,
}

fn overlap_owner<'a>(
    paths: &'a BTreeMap<String, String>,
    path: &str,
    except: &str,
) -> Option<&'a str> {
    let mut ancestor = Some(path);
    while let Some(path) = ancestor {
        if let Some(owner) = paths.get(path).filter(|owner| owner.as_str() != except) {
            return Some(owner);
        }
        ancestor = path.rsplit_once('/').map(|(parent, _)| parent);
    }
    let prefix = format!("{path}/");
    paths
        .range(prefix.clone()..)
        .take_while(|(held, _)| held.starts_with(&prefix))
        .find_map(|(_, owner)| (owner != except).then_some(owner.as_str()))
}

impl Composition {
    pub fn new(harness: &str) -> Self {
        Self {
            harness: harness.into(),
            ..Self::default()
        }
    }

    fn namespace<'a>(&self, kind: &'a str) -> &'a str {
        match (self.harness.as_str(), kind) {
            ("claude-code" | "opencode", "skill" | "command") => "invocation",
            ("claude-code", kind) => kind,
            ("opencode", "agent" | "mcp") => kind,
            // Other harnesses keep the conservative shared space until verified.
            _ => "native",
        }
    }

    pub fn claim(&mut self, owner: &str, path: &str) -> Result<()> {
        if !crate::artifacts::safe_path(path) {
            return Err(invalid(
                "a component path escapes the portable bundle surface",
            ));
        }
        let folded = unicase::UniCase::new(path).to_folded_case();
        if let Some(held) = overlap_owner(&self.paths, &folded, "") {
            return Err(invalid(
                "managed_path_owned_twice: bundle v2 cannot assign a file to multiple components",
            )
            .with_details([
                ("constraint".into(), "managed_path_owned_twice".into()),
                ("stable_id".into(), owner.into()),
                ("also".into(), held.into()),
                ("path".into(), path.into()),
            ]));
        }
        self.paths.insert(folded, owner.into());
        Ok(())
    }

    pub fn include(&mut self, document: &Value, scope: &Value, assessment: &Value) -> Result<()> {
        let id = text(document, "stable_id")?;
        let namespace = self.namespace(text(document, "component_type")?).to_owned();
        self.kinds
            .insert(id.into(), text(document, "component_type")?.into());
        for family in ["paths", "commands", "agents", "hooks", "mcp", "plugins"] {
            for value in document["conflicts"][family]
                .as_array()
                .into_iter()
                .flatten()
            {
                let value = value
                    .as_str()
                    .ok_or_else(|| invalid("a declared conflict is not a string"))?;
                if self.exclusions.len() >= 8192
                    || value.is_empty()
                    || value.len() > 1024
                    || value.chars().any(char::is_control)
                    || (family == "paths" && !crate::artifacts::safe_path(value))
                {
                    return Err(invalid(
                        "declared conflicts exceed their bounded native name or relative path contract",
                    ));
                }
                self.exclusions.push(Exclusion {
                    owner: id.into(),
                    family,
                    value: value.into(),
                });
            }
        }
        for member in scope["members"]
            .as_array()
            .ok_or_else(|| invalid("members missing"))?
        {
            for native in member["native_ids"].as_array().into_iter().flatten() {
                let native = native
                    .as_str()
                    .ok_or_else(|| invalid("a native identifier is invalid"))?;
                if self
                    .native_ids
                    .entry(namespace.clone())
                    .or_default()
                    .insert(native.into(), id.into())
                    .is_some_and(|held| held != id)
                {
                    return Err(invalid(
                        "native_id_collision: multiple components declare the same native identifier",
                    ));
                }
            }
        }
        let precedence = declared(document, "precedence")?;
        if document["component_type"] == "instruction" && !precedence.is_null() {
            let level = precedence
                .as_i64()
                .ok_or_else(|| invalid("instruction precedence is invalid"))?;
            if self.precedence.insert(level, id.into()).is_some() {
                return Err(invalid(
                    "instruction_precedence_conflict: multiple instructions declare the same precedence",
                ));
            }
        }
        let order = declared(document, "hook_order")?;
        if document["component_type"] == "hook" && !order.is_null() {
            let order = order
                .as_i64()
                .ok_or_else(|| invalid("hook order is invalid"))?;
            let event = declared(document, "hook_event")?;
            let event = if event.is_null() {
                ""
            } else {
                event
                    .as_str()
                    .ok_or_else(|| invalid("hook event is invalid"))?
            };
            if self
                .hooks
                .insert((event.into(), order), id.into())
                .is_some()
            {
                return Err(invalid(
                    "hook_order_conflict: multiple hooks declare the same event and order",
                ));
            }
        }
        let report = assessment["assessments"]
            .as_array()
            .and_then(|items| items.iter().find(|item| item["stable_id"] == id))
            .ok_or_else(|| invalid("component assessment missing"))?;
        self.chosen.push(
            json!({"schema_version":1,"stable_id":id,"version":document["version"],
            "lane":report["lane"],"reason":report["lane_reason"]}),
        );
        let losses = scope["semantic_losses"]
            .as_array()
            .ok_or_else(|| invalid("semantic losses missing"))?;
        let mut paths = scope["members"]
            .as_array()
            .ok_or_else(|| invalid("members missing"))?
            .iter()
            .map(|item| text(item, "path"))
            .collect::<Result<Vec<_>>>()?;
        paths.sort();
        let mut common: Vec<_> = paths
            .first()
            .into_iter()
            .flat_map(|path| path.split('/'))
            .collect();
        for path in paths.iter().skip(1) {
            let shared = common
                .iter()
                .zip(path.split('/'))
                .take_while(|(left, right)| **left == *right)
                .count();
            common.truncate(shared);
        }
        self.converted.push(json!({"schema_version":1,"stable_id":id,
            "component_type":scope["provider_component_kind"],"logical_component_type":document["component_type"],
            "native_surface":common.join("/"),"native_paths":paths,"projection_kind":scope["projection_kind"],
            "state":if losses.is_empty(){"complete"}else{"partial"},"losses":losses}));
        Ok(())
    }

    /// Check after collecting every selected component, so neither graph order
    /// nor the side that declares an exclusion can hide a contradiction.
    pub fn validate(&self) -> Result<()> {
        for exclusion in &self.exclusions {
            let other = if exclusion.family == "paths" {
                overlap_owner(
                    &self.paths,
                    &unicase::UniCase::new(&exclusion.value).to_folded_case(),
                    &exclusion.owner,
                )
            } else {
                let kind = match exclusion.family {
                    "commands" => "command",
                    "agents" => "agent",
                    "hooks" => "hook",
                    "mcp" => "mcp",
                    "plugins" => "plugin",
                    _ => return Err(invalid("unknown native conflict family")),
                };
                self.native_ids
                    .get(self.namespace(kind))
                    .and_then(|names| names.get(&exclusion.value))
                    .filter(|owner| {
                        *owner != &exclusion.owner
                            && (self.namespace(kind) == "invocation"
                                || self.kinds.get(*owner).is_some_and(|held| held == kind))
                    })
                    .map(String::as_str)
            };
            if let Some(other) = other {
                return Err(
                    invalid("a component explicitly excludes a selected native surface")
                        .with_details([
                            ("constraint".into(), "declared_conflict".into()),
                            ("stable_id".into(), exclusion.owner.clone().into()),
                            ("also".into(), other.into()),
                            ("family".into(), exclusion.family.into()),
                            ("value".into(), exclusion.value.clone().into()),
                        ]),
                );
            }
        }
        Ok(())
    }

    pub fn reports(mut self) -> (Value, Value) {
        self.chosen
            .sort_by(|a, b| a["stable_id"].as_str().cmp(&b["stable_id"].as_str()));
        self.converted
            .sort_by(|a, b| a["stable_id"].as_str().cmp(&b["stable_id"].as_str()));
        let complete = self
            .converted
            .iter()
            .all(|entry| entry["state"] == "complete");
        (
            json!({"schema_version":1,"chosen":self.chosen,"rejected":[],"conflicts":[],"blocked":false,
            "operations":["canonical_ordering","exact_reference_deduplication","dependency_closure","disjoint_managed_path_union","deterministic_report_generation"]}),
            json!({"schema_version":1,"entries":self.converted,"complete":complete}),
        )
    }
}
