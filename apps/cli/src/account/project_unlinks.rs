//! Durable remote unlink intent; local binding retirement is a separate review.

pub(crate) mod interruption;
mod journal;
mod model;
mod workflow;

pub use super::project_links::Checkpoint;
pub use model::Plan;
pub use workflow::{apply, confirmation_plan, list, outcome, read_plan, request_plan, status};

use super::{
    access::{Access, Binding},
    contexts::{self, Context},
    corporate, project_links,
};
use crate::error::Failure;

fn invalid() -> Failure {
    Failure::precondition(
        "the original unlink, active binding, current context or reviewed source changed",
    )
}

pub(super) fn validate_write(confirm: bool, value: &serde_json::Value) -> crate::error::Result<()> {
    model::validate_write(confirm, value)
}
