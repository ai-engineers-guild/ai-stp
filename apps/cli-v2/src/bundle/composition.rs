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
    paths: BTreeMap<String, String>,
    native_ids: BTreeMap<String, String>,
    precedence: BTreeMap<i64, String>,
    hooks: BTreeMap<(String, i64), String>,
    chosen: Vec<Value>,
    converted: Vec<Value>,
}

impl Composition {
    pub fn claim(&mut self, owner: &str, path: &str) -> Result<()> {
        if !crate::artifacts::safe_path(path) {
            return Err(invalid(
                "a component path escapes the portable bundle surface",
            ));
        }
        let folded = unicase::UniCase::new(path).to_folded_case();
        let prefix = format!("{folded}/");
        let descendant = self.paths.contains_key(&folded)
            || self
                .paths
                .range(prefix.clone()..)
                .next()
                .is_some_and(|(held, _)| held.starts_with(&prefix));
        let mut ancestor = folded.as_str();
        let mut owned_ancestor = false;
        while let Some((parent, _)) = ancestor.rsplit_once('/') {
            owned_ancestor |= self.paths.contains_key(parent);
            ancestor = parent;
        }
        if descendant || owned_ancestor {
            return Err(invalid(
                "managed_path_owned_twice: bundle v2 cannot assign a file to multiple components",
            ));
        }
        self.paths.insert(folded, owner.into());
        Ok(())
    }

    pub fn include(&mut self, document: &Value, scope: &Value, assessment: &Value) -> Result<()> {
        let id = text(document, "stable_id")?;
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
