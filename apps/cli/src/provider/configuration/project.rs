//! Portable explicit project and exact selection binding.

use super::{invalid, plan::Plan};
use crate::{authoring::Identity, error::Result, passport, projection::Scope};
use serde::{Deserialize, Serialize};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Selection {
    pub stable_id: String,
    pub version: String,
    pub selected_at: String,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Binding {
    pub project_id: String,
    pub identity: Identity,
    pub passport_digest: String,
    pub selection: Option<Selection>,
}

impl Binding {
    pub fn validate(&self, plan: &Plan) -> Result<()> {
        self.identity.validate()?;
        if plan.target_scope != Scope::Project
            || !passport::stable_id(&self.project_id, "project")
            || !super::super::plan::hash(&self.passport_digest)
        {
            return Err(invalid());
        }
        if let Some(selection) = &self.selection
            && (!passport::stable_id(&selection.stable_id, "setup")
                || !passport::version_number(&selection.version)
                || !passport::timestamp(&selection.selected_at))
        {
            return Err(invalid());
        }
        if plan.operation()? != "remove"
            && self.selection.as_ref().is_none_or(|selection| {
                plan.setup["stable_id"] != selection.stable_id
                    || plan.setup["version"] != selection.version
            })
        {
            return Err(invalid());
        }
        Ok(())
    }
}
