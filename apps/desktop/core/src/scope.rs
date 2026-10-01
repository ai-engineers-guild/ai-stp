//! Install-scope model (HK pattern, adapted to ai-stp).
//!
//! `All` is a read-only aggregation for views — it is never a valid target
//! for a mutation. `UserRoot` is only offered when the active provider
//! declares it (`plan_request_fields` may carry `target_scope`).

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Scope {
    All,
    Global,
    Project { path: PathBuf },
    UserRoot,
}

impl Scope {
    /// The value passed to `--scope` / `--target-scope`, if this scope is a
    /// concrete install target. `All` is not a target.
    pub fn as_install_target(&self) -> Option<&'static str> {
        match self {
            Self::Global => Some("global"),
            Self::Project { .. } => Some("project"),
            Self::UserRoot => Some("user_root"),
            Self::All => None,
        }
    }

    /// Project path for `Scope::Project`; required as `--project`/`--target`
    /// by commands gated on `scope=project`/`user_root`.
    pub fn project_path(&self) -> Option<&PathBuf> {
        match self {
            Self::Project { path } => Some(path),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_is_not_a_target() {
        assert_eq!(Scope::All.as_install_target(), None);
        assert_eq!(Scope::Global.as_install_target(), Some("global"));
        assert_eq!(
            Scope::Project { path: "/x".into() }.as_install_target(),
            Some("project")
        );
    }
}
