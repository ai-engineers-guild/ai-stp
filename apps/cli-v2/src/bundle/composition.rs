use std::collections::BTreeMap;

use serde_json::{Value, json};

use super::{invalid, text};
use crate::error::{Failure, Result};

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
    conflicts: Option<Vec<Failure>>,
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

    pub fn for_report(harness: &str) -> Self {
        Self {
            conflicts: Some(Vec::new()),
            ..Self::new(harness)
        }
    }

    /// Reporting collects bounded conflict witnesses; compilation still stops
    /// at the first conflict and can never publish a partial package.
    fn reject(&mut self, failure: Failure) -> Result<()> {
        if let Some(conflicts) = &mut self.conflicts {
            if conflicts.len() >= 8192 {
                return Err(invalid("composition exceeds 8192 conflict witnesses"));
            }
            conflicts.push(failure);
            Ok(())
        } else {
            Err(failure)
        }
    }

    fn namespace<'a>(&self, kind: &'a str) -> &'a str {
        match (self.harness.as_str(), kind) {
            ("claude-code" | "opencode" | "grok-build", "skill" | "command") => "invocation",
            ("claude-code", kind) => kind,
            ("opencode", "agent" | "mcp") => kind,
            ("pi", "skill" | "command") => kind,
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
            self.reject(invalid(
                "managed_path_owned_twice: bundle v2 cannot assign a file to multiple components",
            )
            .with_details([
                ("constraint".into(), "managed_path_owned_twice".into()),
                ("stable_id".into(), owner.into()),
                ("also".into(), held.into()),
                ("path".into(), path.into()),
            ]))?;
        }
        self.paths.entry(folded).or_insert_with(|| owner.into());
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
                let held = self
                    .native_ids
                    .entry(namespace.clone())
                    .or_default()
                    .entry(native.into())
                    .or_insert_with(|| id.into())
                    .clone();
                if held != id {
                    self.reject(invalid(
                        "native_id_collision: multiple components declare the same native identifier",
                    ).with_details([
                        ("constraint".into(), "native_id_collision".into()),
                        ("stable_id".into(), id.into()),
                        ("also".into(), held.into()),
                        ("namespace".into(), namespace.clone().into()),
                        ("native_id".into(), native.into()),
                    ]))?;
                }
            }
        }
        let precedence = declared(document, "precedence")?;
        if document["component_type"] == "instruction" && !precedence.is_null() {
            let level = precedence
                .as_i64()
                .ok_or_else(|| invalid("instruction precedence is invalid"))?;
            if let Some(held) = self.precedence.insert(level, id.into()) {
                self.reject(invalid(
                    "instruction_precedence_conflict: multiple instructions declare the same precedence",
                ).with_details([
                    ("constraint".into(), "instruction_precedence_conflict".into()),
                    ("stable_id".into(), id.into()),
                    ("also".into(), held.into()),
                    ("precedence".into(), level.into()),
                ]))?;
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
            if let Some(held) = self.hooks.insert((event.into(), order), id.into()) {
                self.reject(
                    invalid("hook_order_conflict: multiple hooks declare the same event and order")
                        .with_details([
                            ("constraint".into(), "hook_order_conflict".into()),
                            ("stable_id".into(), id.into()),
                            ("also".into(), held.into()),
                            ("event".into(), event.into()),
                            ("order".into(), order.into()),
                        ]),
                )?;
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
    pub fn validate(&mut self, files: &[super::File]) -> Result<()> {
        let kinds: &[&str] = match self.harness.as_str() {
            "codex" => &["skill"],
            "antigravity" | "cursor" => &["agent", "skill"],
            "pi" | "grok-build" => &["skill", "command"],
            _ => &[],
        };
        for kind in kinds {
            let visible = crate::authoring::native_identity::visible_entries(
                &self.harness,
                kind,
                files
                    .iter()
                    .map(|file| (file.member.path.as_str(), file.member.bytes.as_slice())),
            );
            let visible = match visible {
                Ok(visible) => visible,
                Err(_) if self.conflicts.is_some() => {
                    self.reject(
                        invalid("the combined projections have conflicting native entries")
                            .with_details([
                                ("constraint".into(), "native_visibility_mismatch".into()),
                                ("component_type".into(), (*kind).into()),
                            ]),
                    )?;
                    continue;
                }
                Err(failure) => return Err(failure),
            };
            let declared: Vec<_> = self
                .native_ids
                .get(self.namespace(kind))
                .into_iter()
                .flat_map(|names| names.iter())
                .filter(|(_, owner)| self.kinds.get(*owner).is_some_and(|held| held == kind))
                .map(|(name, _)| name.as_str())
                .collect();
            if visible.iter().map(String::as_str).collect::<Vec<_>>() != declared {
                self.reject(
                    invalid("the assembled files change the visible native entries")
                        .with_details([("constraint".into(), "native_visibility_mismatch".into())]),
                )?;
            }
        }
        for index in 0..self.exclusions.len() {
            let exclusion = &self.exclusions[index];
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
                self.reject(
                    invalid("a component explicitly excludes a selected native surface")
                        .with_details([
                            ("constraint".into(), "declared_conflict".into()),
                            ("stable_id".into(), exclusion.owner.clone().into()),
                            ("also".into(), other.into()),
                            ("family".into(), exclusion.family.into()),
                            ("value".into(), exclusion.value.clone().into()),
                        ]),
                )?;
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
        let conflicts: Vec<_> = self
            .conflicts
            .into_iter()
            .flatten()
            .map(|failure| {
                json!({"schema_version":1,"code":failure.details["constraint"],
                "summary":failure.message,"details":failure.details})
            })
            .collect();
        (
            json!({"schema_version":1,"chosen":self.chosen,"rejected":[],"blocked":!conflicts.is_empty(),"conflicts":conflicts,
            "operations":["canonical_ordering","exact_reference_deduplication","dependency_closure","disjoint_managed_path_union","deterministic_report_generation"]}),
            json!({"schema_version":1,"entries":self.converted,"complete":complete}),
        )
    }
}
