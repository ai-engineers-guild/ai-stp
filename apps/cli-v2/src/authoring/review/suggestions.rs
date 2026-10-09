//! Exact retained manifest declarations are suggestions, never confirmation.

use std::collections::BTreeMap;

use serde_json::{Value, json};

use crate::{
    artifacts,
    authoring::passports::Patch,
    canonical,
    error::{ErrorKind, Failure, Result},
    objects::Objects,
    store::{Store, revisions},
    wire::Schema,
};

static SCHEMA: Schema = Schema::new(include_str!(
    "../../../../../schemas/v1/cli-component-passport-suggestions.schema.json"
));

const PUBLICATION_FIELDS: &[&str] = &[
    "component_type",
    "description",
    "entry_points",
    "harness_id",
    "license",
    "name",
    "permissions",
    "projection_kind",
    "provides_capabilities",
    "requires_authorization",
    "requires_capabilities",
    "requires_components",
    "requires_credentials",
    "runtime_requirements",
    "source",
    "tags",
];

fn invalid() -> Failure {
    Failure::precondition("retained enrichment metadata is invalid, ambiguous or exceeds its bound")
}

// Convert only the declared component table. Unrelated TOML datetime and
// package-manager fields are not passport data and must not affect suggestions.
fn toml_item(item: &toml_edit::Item, depth: usize, nodes: &mut usize) -> Result<Value> {
    *nodes += 1;
    if depth > 64 || *nodes > 20_000 {
        return Err(invalid());
    }
    if let Some(table) = item.as_table_like() {
        return table
            .iter()
            .map(|(key, item)| Ok((key.into(), toml_item(item, depth + 1, nodes)?)))
            .collect::<Result<serde_json::Map<_, _>>>()
            .map(Value::Object);
    }
    match item {
        toml_edit::Item::Value(value) => toml_value(value, depth, nodes),
        toml_edit::Item::ArrayOfTables(tables) => tables
            .iter()
            .map(|table| toml_item(&toml_edit::Item::Table(table.clone()), depth + 1, nodes))
            .collect::<Result<Vec<_>>>()
            .map(Value::Array),
        _ => Err(invalid()),
    }
}

fn toml_value(value: &toml_edit::Value, depth: usize, nodes: &mut usize) -> Result<Value> {
    match value {
        toml_edit::Value::String(value) => Ok(value.value().clone().into()),
        toml_edit::Value::Integer(value) => Ok((*value.value()).into()),
        toml_edit::Value::Float(value) => serde_json::Number::from_f64(*value.value())
            .map(Value::Number)
            .ok_or_else(invalid),
        toml_edit::Value::Boolean(value) => Ok((*value.value()).into()),
        toml_edit::Value::Array(values) => values
            .iter()
            .map(|value| toml_item(&toml_edit::Item::Value(value.clone()), depth + 1, nodes))
            .collect::<Result<Vec<_>>>()
            .map(Value::Array),
        toml_edit::Value::InlineTable(_) => {
            toml_item(&toml_edit::Item::Value(value.clone()), depth + 1, nodes)
        }
        toml_edit::Value::Datetime(_) => Err(invalid()),
    }
}

fn declaration(path: &str, bytes: &[u8]) -> Result<Option<Value>> {
    if bytes.len() > 1024 * 1024 {
        return Err(invalid());
    }
    let fields = if path == "package.json" {
        let document = canonical::parse(bytes).map_err(|_| invalid())?;
        let mut value = &document;
        for key in ["ai-stp", "component"] {
            let Some(next) = value.as_object().ok_or_else(invalid)?.get(key) else {
                return Ok(None);
            };
            value = next;
        }
        value.clone()
    } else {
        let text = std::str::from_utf8(bytes).map_err(|_| invalid())?;
        let document: toml_edit::DocumentMut = text.parse().map_err(|_| invalid())?;
        let mut table: &dyn toml_edit::TableLike = document.as_table();
        for key in ["tool", "ai-stp"] {
            let Some(item) = table.get(key) else {
                return Ok(None);
            };
            table = item.as_table_like().ok_or_else(invalid)?;
        }
        let Some(item) = table.get("component") else {
            return Ok(None);
        };
        toml_item(item, 0, &mut 0)?
    };
    let fields = fields.as_object().ok_or_else(invalid)?;
    if fields.is_empty() {
        return Ok(None);
    }
    let patch: Value = Patch::try_from(json!(fields))
        .map_err(|_| invalid())?
        .into();
    Ok(Some(patch))
}

fn add(
    candidates: &mut BTreeMap<String, Value>,
    field: &str,
    value: Value,
    evidence: &str,
) -> Result<()> {
    let patch: Value = Patch::try_from(json!({field: value}))
        .map_err(|_| invalid())?
        .into();
    let value = patch[field].clone();
    if let Some(existing) = candidates.get_mut(field) {
        if existing["value"] != value {
            return Err(Failure::new(
                ErrorKind::Conflict,
                "retained enrichment declarations disagree",
            ));
        }
        existing["source_refs"]
            .as_array_mut()
            .ok_or_else(invalid)?
            .push(evidence.into());
    } else {
        candidates.insert(
            field.into(),
            json!({"schema_version":1,"field":field,"value":value,
            "source_refs":[evidence],"requires_confirmation":true}),
        );
    }
    Ok(())
}

pub fn suggest(store: &mut Store, id: &str) -> Result<Value> {
    store.transaction(|transaction| {
        let objects = Objects { connection:transaction };
        objects.require_active(id)?;
        let document = objects.head("component",id)?;
        let facts = &document["facts"];
        let mut candidates = BTreeMap::new();
        let exact = ["source_repository","source_revision","source_subpath"].map(|key| facts[key]["value"].as_str());
        if let [Some(repository),Some(commit),Some(path)] = exact
            && !repository.is_empty() && !commit.is_empty() && !path.is_empty() {
            add(&mut candidates,"source",json!({"repository":repository,"commit":commit,"path":path}),"adopted:exact-source")?;
        }
        if let Some(address) = facts["content_digest"]["value"].as_str() {
            let bytes = revisions::read_content(transaction,address)?;
            match facts["content_format"]["value"].as_str() {
                Some(artifacts::TREE_FORMAT) => {
                    for member in artifacts::decode_tree(&bytes)? {
                        if !["package.json","pyproject.toml"].contains(&member.path.as_str()) { continue; }
                        if let Some(fields) = declaration(&member.path,&member.bytes)? {
                            for (field,value) in fields.as_object().ok_or_else(invalid)? {
                                add(&mut candidates,field,value.clone(),&format!("artifact:{}",member.path))?;
                            }
                        }
                    }
                }
                Some(artifacts::FILE_FORMAT) => (),
                _ => return Err(invalid()),
            }
        }
        let unresolved:Vec<_> = PUBLICATION_FIELDS.iter().copied()
            .filter(|field| !candidates.contains_key(*field) && facts[*field]["confirmation"] != "user_confirmed")
            .collect();
        let result = json!({"schema_version":1,"stable_id":document["stable_id"],"revision_id":document["revision_id"],
            "suggestions":candidates.into_values().collect::<Vec<_>>(),"unresolved_fields":unresolved});
        SCHEMA.validate(&result)?;
        Ok(result)
    })
}
