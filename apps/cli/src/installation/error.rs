//! Typed failures carrying the stable reason codes the wire contract names.

use std::fmt;

/// A stable, machine-readable refusal reason.
///
/// The consumer matches on these strings, so a variant's wire spelling is part
/// of the contract and never changes to suit a message. The
/// `unsupported_*`, `projection_profile_mismatch` and platform variants are the
/// closed set the provider kit manifest declares; the rest describe local
/// failures that occur before or during a mutation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReasonCode {
    /// The requested operation is not declared by this provider.
    UnsupportedOperation,
    /// A component kind outside the declared vocabulary.
    UnsupportedComponentKind,
    /// A native surface this provider does not own.
    UnsupportedNativeSurface,
    /// A bundle format this provider cannot read.
    UnsupportedBundleFormat,
    /// A protocol version this provider does not implement.
    UnsupportedProtocolVersion,
    /// The projection profile does not match the one the bundle was built for.
    ProjectionProfileMismatch,
    /// A permission profile this provider does not offer.
    UnsupportedPermissionProfile,
    /// The running operating system is outside the declared support matrix.
    UnsupportedPlatform,
    /// The running architecture is outside the declared support matrix.
    UnsupportedArchitecture,
    /// A journal, transaction directory or partial backup slot is present.
    ///
    /// Planning refuses cleanly rather than guessing; only recovery may resolve
    /// this state.
    RecoveryRequired,
    /// The target changed after the lock was taken.
    Stale,
    /// The target path is not a usable canonical directory.
    InvalidTarget,
    /// The target lock could not be acquired.
    LockUnavailable,
    /// Durable state could not be read, written or promoted.
    StateUnavailable,
    /// A digest, size or echo did not match its expected value.
    IntegrityMismatch,
}

impl ReasonCode {
    /// The exact string the wire surface emits.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::UnsupportedOperation => "unsupported_operation",
            Self::UnsupportedComponentKind => "unsupported_component_kind",
            Self::UnsupportedNativeSurface => "unsupported_native_surface",
            Self::UnsupportedBundleFormat => "unsupported_bundle_format",
            Self::UnsupportedProtocolVersion => "unsupported_protocol_version",
            Self::ProjectionProfileMismatch => "projection_profile_mismatch",
            Self::UnsupportedPermissionProfile => "unsupported_permission_profile",
            Self::UnsupportedPlatform => "unsupported_platform",
            Self::UnsupportedArchitecture => "unsupported_architecture",
            Self::RecoveryRequired => "recovery_required",
            Self::Stale => "stale",
            Self::InvalidTarget => "invalid_target",
            Self::LockUnavailable => "lock_unavailable",
            Self::StateUnavailable => "state_unavailable",
            Self::IntegrityMismatch => "integrity_mismatch",
        }
    }
}

impl fmt::Display for ReasonCode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// A refusal: a stable reason plus a human-readable detail.
#[derive(Debug)]
pub struct Error {
    reason: ReasonCode,
    detail: String,
    source: Option<Box<dyn std::error::Error + Send + Sync>>,
}

impl Error {
    /// Build a refusal from a reason and a detail.
    pub fn new(reason: ReasonCode, detail: impl Into<String>) -> Self {
        Self {
            reason,
            detail: detail.into(),
            source: None,
        }
    }

    /// Attach the underlying cause.
    #[must_use]
    pub fn with_source(mut self, source: impl std::error::Error + Send + Sync + 'static) -> Self {
        self.source = Some(Box::new(source));
        self
    }

    /// Whether the cause underneath was "that path is not there".
    ///
    /// Asked by the tree walk, which meets three separate gaps between listing
    /// an entry and reading it and must tell a racing writer from a real
    /// failure. The source is kept as a boxed `dyn Error`, so the io kind is
    /// recovered by downcast rather than by matching on the message -- a guard
    /// that matched prose would measure how a failure was described.
    #[must_use]
    pub fn is_missing_path(&self) -> bool {
        self.source
            .as_ref()
            .and_then(|source| source.downcast_ref::<std::io::Error>())
            .is_some_and(|source| source.kind() == std::io::ErrorKind::NotFound)
    }

    /// The stable reason code.
    #[must_use]
    pub const fn reason(&self) -> ReasonCode {
        self.reason
    }

    /// The human-readable detail.
    #[must_use]
    pub fn detail(&self) -> &str {
        &self.detail
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.reason, self.detail)
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        self.source
            .as_ref()
            .map(|boxed| &**boxed as &(dyn std::error::Error + 'static))
    }
}

/// Result carrying a typed refusal.
pub type Result<T> = std::result::Result<T, Error>;
