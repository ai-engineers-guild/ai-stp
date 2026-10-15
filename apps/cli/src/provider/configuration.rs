//! Portable configuration plans and receipts, shared by execution and local history.

pub(crate) mod activation;
pub(crate) mod effects;
pub(crate) mod outcome;
pub(crate) mod plan;
pub(crate) mod project;
pub(crate) mod record;
pub(crate) mod set;

pub(crate) fn invalid() -> crate::error::Failure {
    crate::error::Failure::precondition(
        "the configuration operation, recorded ownership or exact target bytes changed",
    )
}

pub(crate) fn require_cancellation(version: &str) -> crate::error::Result<()> {
    if super::managed::sequence(version)? < super::managed::sequence("0.0.92")? {
        return Err(crate::error::Failure::precondition(
            "the original plan requires a component with exact cancellation (0.0.92 or newer); its release identity cannot be replaced",
        ));
    }
    Ok(())
}
