//! Only declared contribution paths are read from a held, unaliased target.

use std::{collections::BTreeSet, path::Path};

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{
    error::{Failure, Result},
    files,
    objects::Objects,
    projection::{self, Scope},
    selection::graph,
};

#[cfg(target_os = "linux")]
use crate::provider::runtime::target::Target;

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Binding {
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    pub path: std::path::PathBuf,
    pub identity: [String; 2],
}

pub(crate) struct Root {
    #[cfg(target_os = "linux")]
    target: Option<Target>,
}

fn invalid() -> Failure {
    Failure::precondition("the bundle host input is absent, aliased, changed or exceeds its bounds")
}

impl Root {
    pub(crate) fn open(path: Option<&Path>, state: &Path, output_parent: &Path) -> Result<Self> {
        #[cfg(target_os = "linux")]
        {
            let target = path.map(Target::open).transpose()?;
            if let Some(target) = &target {
                target.state_parent(state)?;
                target.outside(output_parent)?;
            }
            Ok(Self { target })
        }
        #[cfg(not(target_os = "linux"))]
        {
            let _ = (path, state, output_parent);
            Err(Failure::precondition(
                "bundle host observation requires a supported native provider runtime",
            ))
        }
    }

    pub(crate) fn binding(&self) -> Result<Option<Binding>> {
        #[cfg(target_os = "linux")]
        {
            self.target
                .as_ref()
                .map(|target| {
                    target.revalidate()?;
                    let (device, inode) = target.identity()?;
                    Ok(Binding {
                        path: target.path().to_owned(),
                        identity: [device.to_string(), inode.to_string()],
                    })
                })
                .transpose()
        }
        #[cfg(not(target_os = "linux"))]
        Err(invalid())
    }

    pub(crate) fn outside(&self, parent: &Path) -> Result<()> {
        #[cfg(target_os = "linux")]
        {
            if let Some(target) = &self.target {
                target.outside(parent)?;
            }
            Ok(())
        }
        #[cfg(not(target_os = "linux"))]
        {
            let _ = parent;
            Err(invalid())
        }
    }

    pub(crate) fn read(&self, paths: &BTreeSet<String>) -> Result<super::Hosts> {
        #[cfg(target_os = "linux")]
        {
            if paths.len() > 2000 {
                return Err(invalid());
            }
            let Some(target) = &self.target else {
                return if paths.is_empty() {
                    Ok(Default::default())
                } else {
                    Err(invalid())
                };
            };
            let mut bytes = 0usize;
            let mut result = super::Hosts::new();
            for path in paths {
                let content = target.read(path)?.map(|content| content.bytes);
                bytes = bytes
                    .checked_add(content.as_ref().map_or(0, Vec::len))
                    .ok_or_else(invalid)?;
                if bytes > 64 * 1024 * 1024 {
                    return Err(invalid());
                }
                result.insert(path.clone(), content);
            }
            target.revalidate()?;
            Ok(result)
        }
        #[cfg(not(target_os = "linux"))]
        {
            let _ = paths;
            Err(invalid())
        }
    }
}

/// The compiler consumes precisely these paths. Call in the same registry
/// transaction as graph verification and compilation; never scan the target.
pub(crate) fn paths(
    connection: &Connection,
    setup: &Value,
    harness: &str,
    scope: Scope,
) -> Result<BTreeSet<String>> {
    let graph = graph::exact(connection, std::slice::from_ref(setup))?;
    if graph["resolved"] != true {
        return Err(invalid());
    }
    let mut result = BTreeSet::new();
    for node in graph["nodes"].as_array().ok_or_else(invalid)? {
        let field = |key| node[key].as_str().ok_or_else(invalid);
        let document = Objects { connection }.exact_version(
            field("stable_id")?,
            field("version")?,
            Some(field("passport_digest")?),
        )?;
        if document["kind"] == "setup" {
            continue;
        }
        let (_, adaptation) =
            projection::adaptation(&document, harness, scope).ok_or_else(invalid)?;
        for member in adaptation["members"].as_array().ok_or_else(invalid)? {
            if member["ownership"] == "contribution" {
                let path = member["path"].as_str().ok_or_else(invalid)?;
                if !crate::artifacts::safe_path(path) || result.len() >= 2000 {
                    return Err(invalid());
                }
                result.insert(path.into());
            }
        }
    }
    Ok(result)
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;

    #[test]
    fn contribution_hosts_distinguish_absence_from_aliases_and_changed_roots()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let temporary = tempfile::tempdir()?;
        let target = temporary.path().join("target");
        let state = temporary.path().join("state");
        std::fs::create_dir(&target)?;
        std::fs::create_dir(&state)?;
        std::fs::write(target.join("settings.json"), b"{\"theme\":\"dark\"}")?;
        let root = Root::open(Some(&target), &state, temporary.path())?;
        let names = BTreeSet::from(["settings.json".into(), "missing/host.json".into()]);
        let observed = root.read(&names)?;
        assert_eq!(
            observed["settings.json"].as_deref(),
            Some(b"{\"theme\":\"dark\"}".as_slice())
        );
        assert_eq!(observed["missing/host.json"], None);
        assert!(root.outside(&target).is_err());
        assert!(Root::open(Some(&target), &target, temporary.path()).is_err());
        assert!(
            Root::open(None, &state, temporary.path())?
                .read(&names)
                .is_err()
        );

        std::os::unix::fs::symlink("missing", target.join("dangling"))?;
        std::os::unix::fs::symlink("settings.json", target.join("alias.json"))?;
        for name in ["dangling/host.json", "alias.json"] {
            assert!(root.read(&BTreeSet::from([name.into()])).is_err(), "{name}");
        }
        std::fs::hard_link(target.join("settings.json"), target.join("hard.json"))?;
        assert!(root.read(&BTreeSet::from(["hard.json".into()])).is_err());
        std::fs::rename(&target, temporary.path().join("moved"))?;
        std::fs::create_dir(&target)?;
        assert!(root.binding().is_err());
        assert!(root.read(&names).is_err());
        Ok(())
    }
}
