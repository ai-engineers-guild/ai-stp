//! Default location and explicit first-run initialization. Reads never bootstrap state.

use std::path::{Component, Path, PathBuf};

use serde_json::{Value, json};

use crate::{
    error::{Failure, Result},
    files, identity,
};

/// Preserve the existing cross-platform XDG layout during the writer cutover.
pub fn state_root() -> Option<PathBuf> {
    let root = if let Some(value) = std::env::var_os("AI_STP_STATE_DIR") {
        PathBuf::from(value)
    } else {
        std::env::var_os("XDG_DATA_HOME")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .or_else(|| files::home().map(|home| home.join(".local/share")))?
            .join("ai-stp")
    };
    (root.is_absolute()
        && root.parent().is_some()
        && root.components().count() <= 64
        && !root
            .components()
            .any(|part| matches!(part, Component::ParentDir)))
    .then_some(root)
}

pub fn location() -> Result<Value> {
    let path = state_root().ok_or_else(|| {
        Failure::input("set an absolute AI_STP_STATE_DIR or provide an absolute HOME/XDG_DATA_HOME")
    })?;
    Ok(json!({"schema_version":1,"state_dir":path,"exists":path.is_dir()}))
}

/// The explicit init command authorizes a local identity, never migration or login.
/// The existing identity journal owns exact plan admission and crash recovery.
pub fn initialize(root: &Path, storage: identity::Storage) -> Result<Value> {
    storage.validate()?;
    if !root.is_absolute()
        || root.parent().is_none()
        || root.components().count() > 64
        || root
            .components()
            .any(|part| matches!(part, Component::ParentDir))
    {
        return Err(Failure::input(
            "initialization requires an absolute state directory",
        ));
    }
    let mut builder = std::fs::DirBuilder::new();
    builder.recursive(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    builder
        .create(root)
        .map_err(|_| Failure::precondition("state directory cannot be created"))?;
    let metadata = root
        .symlink_metadata()
        .map_err(|_| Failure::precondition("state directory cannot be inspected"))?;
    if !metadata.is_dir() || metadata.is_symlink() {
        return Err(Failure::precondition(
            "state directory must be a real directory",
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o077 != 0 {
            return Err(Failure::precondition(
                "state directory must have owner-only permissions",
            ));
        }
    }
    if let Some(identity) = identity::current(root)? {
        if identity.storage() != storage {
            return Err(Failure::precondition(
                "the existing identity uses another credential store",
            ));
        }
        return Ok(identity.report());
    }
    let at = format!("{:.3}", jiff::Timestamp::now());
    let plan = identity::plan(root, storage, &at)?;
    let digest = plan.digest()?;
    identity::apply(&plan, &digest, &at).map(|identity| identity.report())
}

pub fn doctor(root: &Path) -> Value {
    let ready = cap_std::fs::Dir::open_ambient_dir(root, cap_std::ambient_authority())
        .ok()
        .is_some_and(|directory| {
            crate::store::migration::ensure_ready(&directory).is_ok()
                && directory.is_file("ai-stp-v2-identity/identity.json")
        });
    json!({"schema_version":1,"state":if ready && cfg!(target_os="linux") {"ready"} else {"needs_user_action"},
    "checks":[
        {"name":"runtime","state":"ready","detail":"Rust; no Python runtime required"},
        {"name":"local_identity","state":if ready {"ready"} else {"needs_user_action"},
         "detail":if ready {"Identity record present; use device show to verify its key"} else {"Run init for fresh state or state migrate plan for an existing Python installation"}},
        {"name":"configuration_installation","state":if cfg!(target_os="linux") {"ready"} else {"needs_user_action"},
         "detail":if cfg!(target_os="linux") {"Linux isolated provider execution available; each operation verifies its runtime"} else {"Provider execution is not available on this operating system"}}
    ]})
}
