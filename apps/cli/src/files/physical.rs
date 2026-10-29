//! Full directory-object identity queried only from an already held handle.

use cap_std::fs::Dir;
use serde::{Deserialize, Serialize};

use crate::error::{Failure, Result};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum DirectoryIdentity {
    Unix { device: String, inode: String },
    Windows { volume: String, file_id: String },
}

fn invalid() -> Failure {
    Failure::precondition("the full physical directory identity is unavailable or invalid")
}

impl DirectoryIdentity {
    pub(crate) fn validate(&self) -> Result<()> {
        let decimal64 = |s: &str| s.parse::<u64>().is_ok_and(|n| n.to_string() == s);
        match self {
            Self::Unix { device, inode } if decimal64(device) && decimal64(inode) => Ok(()),
            Self::Windows { volume, file_id }
                if decimal64(volume)
                    && file_id
                        .parse::<u128>()
                        .is_ok_and(|n| n.to_string() == *file_id) =>
            {
                Ok(())
            }
            _ => Err(invalid()),
        }
    }

    pub(crate) fn capture(directory: &Dir) -> Result<Self> {
        #[cfg(unix)]
        {
            use cap_fs_ext::MetadataExt;
            let metadata = directory.dir_metadata().map_err(|_| invalid())?;
            Ok(Self::Unix {
                device: metadata.dev().to_string(),
                inode: metadata.ino().to_string(),
            })
        }
        #[cfg(windows)]
        {
            // FileID::new queries FileIdInfo from this held handle. No ambient
            // path reopening or fallback to a truncated legacy ID is permitted.
            let identity = fs_id::FileID::new(directory).map_err(|_| invalid())?;
            Ok(Self::Windows {
                volume: identity.storage_id().to_string(),
                file_id: identity.internal_file_id().to_string(),
            })
        }
        #[cfg(not(any(unix, windows)))]
        {
            let _ = directory;
            Err(invalid())
        }
    }
}

/// Compare actual directory ancestry, including aliases, without using display
/// strings as proof. Failure to inspect a parent is a refusal, not disjointness.
pub(crate) fn contains(ancestor: &Dir, descendant: &Dir) -> Result<bool> {
    let expected = DirectoryIdentity::capture(ancestor)?;
    let mut current = descendant.try_clone().map_err(|_| invalid())?;
    for _ in 0..256 {
        let before = DirectoryIdentity::capture(&current)?;
        if before == expected {
            return Ok(true);
        }
        let parent = current
            .open_parent_dir(cap_std::ambient_authority())
            .map_err(|_| invalid())?;
        if DirectoryIdentity::capture(&parent)? == before {
            return Ok(false);
        }
        current = parent;
    }
    Err(invalid())
}

pub(crate) fn require_disjoint(left: &Dir, right: &Dir) -> Result<()> {
    if contains(left, right)? || contains(right, left)? {
        return Err(Failure::precondition(
            "finish or reconcile the retained work for this physical checkout before changing its location",
        ));
    }
    Ok(())
}
