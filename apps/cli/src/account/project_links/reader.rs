//! Current project.link authority is separate from an immutable original actor.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::{Binding, Context, contexts, corporate, invalid, model, workflow};
use crate::error::Result;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(in crate::account) struct Reader {
    pub context: Context,
    pub account: Binding,
    pub organization: Value,
    pub observation: Value,
}

impl Reader {
    pub fn unchanged(&self, fresh: &Self) -> Result<()> {
        if self.context != fresh.context
            || self.account != fresh.account
            || corporate::authority(&self.organization, &self.observation)
                != corporate::authority(&fresh.organization, &fresh.observation)
        {
            return Err(invalid());
        }
        Ok(())
    }

    pub fn validate(&self, source: &model::Plan) -> Result<()> {
        workflow::reader_matches(&self.context, source.snapshot())?;
        self.validate_authority()
    }

    pub fn matches_binding(context: &Context, binding: &super::binding::Snapshot) -> Result<()> {
        let contexts::Authority::Remote {
            account,
            organization,
            ..
        } = &context.authority
        else {
            return Err(invalid());
        };
        if context.root != binding.context.root
            || account.origin != binding.account.origin
            || account.account_id != binding.account.account_id
            || account.root_identity != binding.account.root_identity
            || organization["organization_id"] != binding.link["organization_id"]
            || organization["kind"] != "corporate"
        {
            return Err(invalid());
        }
        Ok(())
    }

    pub fn validate_binding(&self, binding: &super::binding::Snapshot) -> Result<()> {
        Self::matches_binding(&self.context, binding)?;
        self.validate_authority()
    }

    fn validate_authority(&self) -> Result<()> {
        self.context.digest()?;
        self.account.validate()?;
        let contexts::Authority::Remote {
            account,
            organization,
            ..
        } = &self.context.authority
        else {
            return Err(invalid());
        };
        let mut bound = account.as_ref().clone();
        bound.revision.clone_from(&self.account.revision);
        let projected = contexts::organizations_projection(
            &json!({"schema_version":1,"items":[self.organization]}),
        )?;
        if bound != self.account
            || organization["organization_id"] != self.organization["organization_id"]
            || projected["items"][0] != self.organization
            || self.organization["kind"] != "corporate"
            || contexts::active_projection(&self.observation)? != self.observation
            || self.observation["organization_id"] != self.organization["organization_id"]
            || !self.observation["capabilities"]["capabilities"]
                .as_array()
                .is_some_and(|items| items.iter().any(|item| item == "project.link"))
        {
            return Err(invalid());
        }
        Ok(())
    }
}
