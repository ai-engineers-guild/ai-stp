//! Closed business inputs and retained child plans share one task journal.

use super::{input, install};
use crate::{
    authoring::{Identity, embedded},
    error::{Failure, Result},
};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Clone, Deserialize, Serialize)]
#[serde(untagged)]
pub(super) enum Input {
    Author(input::Input),
    Install(install::Input),
}

impl From<input::Input> for Input {
    fn from(value: input::Input) -> Self {
        Self::Author(value)
    }
}

impl Input {
    pub fn stored(intent: &str, value: Value) -> Result<Self> {
        match intent {
            "author" => input::Input::stored(value).map(Self::Author),
            "install" => install::Input::parse(value).map(Self::Install),
            _ => Err(Failure::input("this native task intent is unavailable")),
        }
    }
    pub fn intent(&self) -> &'static str {
        match self {
            Self::Author(_) => "author",
            Self::Install(_) => "install",
        }
    }
    pub fn value(&self) -> Result<Value> {
        serde_json::to_value(self).map_err(|_| Failure::input("task input cannot be encoded"))
    }
    pub fn admit(&self) -> Result<()> {
        match self {
            Self::Author(input) => input.admit(),
            Self::Install(input) => input.validate(),
        }
    }
    pub fn harness(&self) -> &str {
        match self {
            Self::Author(input) => input.harness(),
            Self::Install(input) => &input.harness_id,
        }
    }
    pub fn project(&self) -> &str {
        match self {
            Self::Author(_) => "",
            Self::Install(input) => input.project_root.as_deref().unwrap_or(""),
        }
    }
    pub fn scope(&self) -> &str {
        match self {
            Self::Author(_) => "global",
            Self::Install(input) => input.scope(),
        }
    }
    pub fn question(&self) -> Result<Option<Value>> {
        match self {
            Self::Author(input) => input.question(),
            Self::Install(_) => Ok(None),
        }
    }
    pub fn answer(&self, question: &str, value: &str) -> Result<Self> {
        match self {
            Self::Author(input) => input.answer(question, value).map(Self::Author),
            Self::Install(_) => Err(Failure::input(
                "the exact install task has no pending question",
            )),
        }
    }
    pub fn request(&self) -> Result<embedded::Request> {
        match self {
            Self::Author(input) => input.request(),
            Self::Install(_) => Err(Failure::precondition(
                "this task is not an author operation",
            )),
        }
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(untagged)]
pub(super) enum Plan {
    Author(embedded::Plan),
    Install(install::Checkpoint),
}

impl Plan {
    pub fn digest(&self) -> Result<String> {
        match self {
            Self::Author(plan) => plan.digest(),
            Self::Install(plan) => plan.digest(),
        }
    }
    pub fn author(&self) -> Result<&embedded::Plan> {
        match self {
            Self::Author(plan) => Ok(plan),
            Self::Install(_) => Err(Failure::precondition(
                "this task is not an author operation",
            )),
        }
    }
    pub fn children(&self) -> Vec<String> {
        match self {
            Self::Author(plan) => vec![plan.operation_id.clone()],
            Self::Install(plan) => plan.children(),
        }
    }
    pub fn validate(&self, input: &Input, identity: &Identity) -> Result<()> {
        match (self, input) {
            (Self::Author(plan), Input::Author(input)) => {
                if &plan.identity != identity
                    || super::journal::encode(&plan.request)?
                        != super::journal::encode(&input.request()?)?
                {
                    return Err(Failure::precondition(
                        "the author task child changed its input or owner",
                    ));
                }
                Ok(())
            }
            (Self::Install(plan), Input::Install(input)) => plan.validate(input, identity),
            _ => Err(Failure::precondition(
                "the retained child belongs to another task intent",
            )),
        }
    }
    pub fn outcome(&self) -> Result<Value> {
        match self {
            Self::Author(plan) => Ok(embedded::outcome(plan)),
            Self::Install(plan) => plan.outcome(),
        }
    }
}
