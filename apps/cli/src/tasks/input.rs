//! Closed author facts and questions; the existing wire model remains authoritative.

use std::{collections::BTreeSet, path::PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{
    authoring::embedded,
    canonical,
    error::{Failure, Result},
    harnesses,
    wire::Schema,
};

static SCHEMA: Schema = Schema::new(include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/resources/schemas/v1/cli-task-input-author.schema.json"
)));

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Input {
    #[serde(default = "version")]
    schema_version: u32,
    directory: Option<String>,
    harness_id: Option<String>,
    component_type: Option<String>,
    name: Option<String>,
    license_spdx: Option<String>,
}

fn version() -> u32 {
    1
}

impl Input {
    pub(super) fn parse(value: Value) -> Result<Self> {
        let input = Self::stored(value)?;
        input.admit()?;
        Ok(input)
    }

    /// Historical records retain their wire meaning when current surfaces change.
    pub(super) fn stored(value: Value) -> Result<Self> {
        if canonical::bytes(&value)?.len() > 16 * 1024 {
            return Err(Failure::input("task input exceeds 16 KiB"));
        }
        SCHEMA
            .validate(&value)
            .map_err(|_| Failure::input("input does not match the author task schema"))?;
        let input: Self =
            serde_json::from_value(value).map_err(|_| Failure::input("author input is invalid"))?;
        for value in [
            &input.directory,
            &input.harness_id,
            &input.component_type,
            &input.name,
            &input.license_spdx,
        ]
        .into_iter()
        .flatten()
        {
            if value.trim().is_empty() || value.len() > 4096 || value.chars().any(char::is_control)
            {
                return Err(Failure::input(
                    "author input strings must be nonempty and bounded without control characters",
                ));
            }
        }
        if input
            .directory
            .as_ref()
            .is_some_and(|p| !PathBuf::from(p).is_absolute())
        {
            return Err(Failure::input("author task directory must be absolute"));
        }
        if input.name.as_ref().is_some_and(|name| {
            name.trim() != name
                || name.chars().count() > 160
                || !crate::artifacts::safe_path(name)
                || name.contains('/')
        }) {
            return Err(Failure::input(
                "author name must be one portable path segment of at most 160 characters",
            ));
        }
        if input
            .license_spdx
            .as_ref()
            .is_some_and(|license| license.trim() != license || license.len() > 256)
        {
            return Err(Failure::input(
                "author license must be a nonempty identifier of at most 256 bytes",
            ));
        }
        if canonical::bytes(&input.value()?)?.len() > 16 * 1024 {
            return Err(Failure::input("normalized author input exceeds 16 KiB"));
        }
        Ok(input)
    }

    pub(super) fn admit(&self) -> Result<()> {
        if let Some(kind) = &self.component_type {
            let supported = match &self.harness_id {
                Some(harness) => embedded::kinds(harness)?.contains(kind),
                None => available_kinds()?.contains(kind),
            };
            if !supported {
                return Err(Failure::input(
                    "the current installation component has no authoring surface for that kind",
                ));
            }
        }
        Ok(())
    }

    pub(super) fn value(&self) -> Result<Value> {
        serde_json::to_value(self).map_err(|_| Failure::input("author input cannot be encoded"))
    }

    pub(super) fn harness(&self) -> &str {
        self.harness_id.as_deref().unwrap_or("")
    }

    pub(super) fn question(&self) -> Result<Option<Value>> {
        let missing = if self.directory.is_none() {
            Some((
                "directory",
                "Which absolute directory holds the component files?",
                Vec::new(),
                "",
            ))
        } else if self.harness_id.is_none() {
            Some((
                "harness-id",
                "Which harness should host this component?",
                harnesses::definitions()?
                    .iter()
                    .filter(|h| h.harness_id != "undefined")
                    .map(|h| h.harness_id.clone())
                    .collect(),
                "",
            ))
        } else if self.component_type.is_none() {
            Some((
                "component-type",
                "Which component kind is this directory?",
                embedded::kinds(self.harness())?,
                "",
            ))
        } else if self.name.is_none() {
            Some((
                "name",
                "What is the component's short native name?",
                Vec::new(),
                "",
            ))
        } else if self.license_spdx.is_none() {
            Some((
                "license-spdx",
                "Which SPDX license identifier applies to these files?",
                Vec::new(),
                "LicenseRef-AI-STP-Private",
            ))
        } else {
            None
        };
        Ok(missing.map(|(id,prompt,choices,recommended)| json!({"question_id":id,"prompt":prompt,"value_type":"string",
            "choices":choices,"recommended":recommended,"why":"Author needs explicit facts before creating private immutable objects.","actor":"human"})))
    }

    pub(super) fn answer(&self, question: &str, value: &str) -> Result<Self> {
        let expected = self
            .question()?
            .ok_or_else(|| Failure::input("this task has no open question"))?;
        if expected["question_id"] != question {
            return Err(Failure::input("answer must name the current question"));
        }
        let choices = expected["choices"]
            .as_array()
            .ok_or_else(|| Failure::input("invalid question"))?;
        if !choices.is_empty() && !choices.iter().any(|choice| choice == value) {
            return Err(Failure::input("answer is outside the declared choices"));
        }
        let mut next = self.value()?;
        next[question.replace('-', "_")] = value.into();
        Self::parse(next)
    }

    pub(super) fn request(&self) -> Result<embedded::Request> {
        let required = |value: &Option<String>| {
            value
                .clone()
                .ok_or_else(|| Failure::input("author task is missing required facts"))
        };
        Ok(embedded::Request {
            directory: PathBuf::from(required(&self.directory)?),
            harness_id: required(&self.harness_id)?,
            component_type: required(&self.component_type)?,
            name: required(&self.name)?,
            license_spdx: required(&self.license_spdx)?,
        })
    }
}

fn available_kinds() -> Result<BTreeSet<String>> {
    let mut kinds = BTreeSet::new();
    for harness in harnesses::definitions()? {
        kinds.extend(embedded::kinds(&harness.harness_id)?);
    }
    Ok(kinds)
}

pub(super) fn descriptor() -> Result<Value> {
    let supported_kinds = available_kinds()?;
    let schema: Value = serde_json::from_str(include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/resources/schemas/v1/cli-task-input-author.schema.json"
    )))
    .map_err(|_| Failure::precondition("the embedded author schema is invalid"))?;
    let fields = schema["properties"]
        .as_object()
        .ok_or_else(|| Failure::precondition("the embedded author properties are invalid"))?
        .iter()
        .filter(|(name, _)| *name != "schema_version")
        .map(|(name, field)| {
            let choices = if name == "component_type" {
                json!(supported_kinds)
            } else {
                field["anyOf"]
                    .as_array()
                    .and_then(|items| {
                        items.iter().find_map(|item| {
                            item.get("enum").or_else(|| {
                                item["$ref"]
                                    .as_str()
                                    .and_then(|reference| reference.strip_prefix("#/$defs/"))
                                    .and_then(|name| schema["$defs"][name].get("enum"))
                            })
                        })
                    })
                    .cloned()
                    .unwrap_or_else(|| json!([]))
            };
            json!({"name":name,"required":false,"value_type":"string","choices":choices})
        })
        .collect::<Vec<_>>();
    Ok(
        json!({"name":"author","when":"Create one private immutable component and setup from an explicit local directory.",
        "input_schema":"cli-task-input-author","input_fields":fields}),
    )
}
