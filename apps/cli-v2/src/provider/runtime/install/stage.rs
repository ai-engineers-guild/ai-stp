//! Same-filesystem private assembly and no-replace whole-directory publication.

use cap_std::fs::{Dir, DirBuilder, DirBuilderExt};
use std::{io::ErrorKind, path::Path};

use super::super::target::Target;
use super::{
    journal::{Phase, Record, identity},
    plan::{Plan, invalid},
};
use crate::{error::Result, files::OwnedDirectory};

pub(super) struct Stage {
    parent: Target,
    private: Option<OwnedDirectory>,
    name: String,
    owner: Vec<u8>,
    leaf: String,
    pub root: Target,
    published: bool,
}

fn sync(directory: &Dir) -> Result<()> {
    directory
        .open(".")
        .and_then(|file| file.sync_all())
        .map_err(|_| invalid())
}

fn absent(parent: &Dir, name: &str) -> Result<bool> {
    match parent.symlink_metadata(name) {
        Err(error) if error.kind() == ErrorKind::NotFound => Ok(true),
        Ok(_) => Ok(false),
        Err(_) => Err(invalid()),
    }
}

fn cancellation_parent(plan: &Plan) -> Result<(Target, String, Vec<u8>)> {
    let parent = Target::open(Path::new(&plan.prefix.path).parent().ok_or_else(invalid)?)?;
    if identity(&parent)? != plan.prefix.parent_identity {
        return Err(invalid());
    }
    let name = format!(".ai-stp-{}", plan.operation_id);
    let bytes = serde_json_canonicalizer::to_vec(&plan.value()?).map_err(|_| invalid())?;
    let digest = crate::digest::bytes("ai-stp:installation-operation:v1", &bytes)?;
    let owner = format!("ai-stp:program-stage/v1\n{}\n{digest}\n", plan.operation_id).into_bytes();
    Ok((parent, name, owner))
}

pub(super) fn prepare_cancellation(plan: &Plan, record: &mut Record) -> Result<()> {
    if !matches!(
        record.phase,
        Phase::Prepared | Phase::Staged | Phase::Publishing
    ) {
        return Err(invalid());
    }
    let (parent, name, owner) = cancellation_parent(plan)?;
    let directory = parent.directory()?;
    if absent(&directory, &name)? {
        if record.phase == Phase::Publishing {
            return Err(invalid());
        }
        return Ok(());
    }
    let private = Target::open(&parent.path().join(&name))?;
    let private_id = identity(&private)?;
    if record
        .stage_parent
        .as_ref()
        .is_some_and(|v| v != &private_id)
    {
        return Err(invalid());
    }
    let owned = OwnedDirectory::open_at(&directory, &name, &owner, true)?.ok_or_else(invalid)?;
    private.revalidate()?;
    for entry in owned.directory.entries().map_err(|_| invalid())? {
        if !matches!(
            entry.map_err(|_| invalid())?.file_name().to_str(),
            Some("owner" | "lock" | "payload")
        ) {
            return Err(invalid());
        }
    }
    if !absent(&owned.directory, "payload")? {
        let payload = Target::open(&private.path().join("payload"))?;
        let root_id = identity(&payload)?;
        if record.stage_root.as_ref().is_some_and(|v| v != &root_id) {
            return Err(invalid());
        }
        if let Ok(final_root) = Target::open(Path::new(&plan.prefix.path))
            && identity(&final_root)? == root_id
        {
            return Err(invalid());
        }
        if record.phase == Phase::Prepared
            && payload
                .directory()?
                .entries()
                .map_err(|_| invalid())?
                .next()
                .is_some()
        {
            return Err(invalid());
        }
        record.stage_root = Some(root_id);
    } else if record.phase == Phase::Publishing {
        // Once the recorded root moved, only apply may finish publication.
        return Err(invalid());
    }
    record.stage_parent = Some(private_id);
    owned.sync()?;
    parent.revalidate()
}

/// Cancellation was committed before deletion. Repeated cleanup recognizes
/// removed children without ever deleting or recreating a final program root.
pub(super) fn discard(plan: &Plan, record: &Record) -> Result<()> {
    if record.phase != Phase::Cancelling {
        return Err(invalid());
    }
    let (parent, name, owner) = cancellation_parent(plan)?;
    let directory = parent.directory()?;
    if absent(&directory, &name)? {
        return sync(&directory);
    }
    let private = Target::open(&parent.path().join(&name))?;
    if Some(identity(&private)?) != record.stage_parent {
        return Err(invalid());
    }
    let held = private.directory()?;
    if !absent(&held, "payload")? {
        let payload = Target::open(&private.path().join("payload"))?;
        if Some(identity(&payload)?) != record.stage_root {
            return Err(invalid());
        }
        held.remove_dir_all("payload").map_err(|_| invalid())?;
        sync(&held)?;
    }
    cleanup_private(&parent, &name, &owner, record)
}

impl Stage {
    pub fn open(plan: &Plan, record: &mut Record) -> Result<Self> {
        let prefix = Path::new(&plan.prefix.path);
        let parent = Target::open(prefix.parent().ok_or_else(invalid)?)?;
        if identity(&parent)? != plan.prefix.parent_identity {
            return Err(invalid());
        }
        let directory = parent.directory()?;
        let name = format!(".ai-stp-{}", plan.operation_id);
        let leaf = prefix
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or_else(invalid)?
            .to_owned();
        let owner = format!(
            "ai-stp:program-stage/v1\n{}\n{}\n",
            plan.operation_id, record.plan_digest
        )
        .into_bytes();
        let private_path = parent.path().join(&name);
        let staged_path = private_path.join("payload");
        let published = !absent(&directory, &leaf)?;
        if published && record.phase != Phase::Publishing {
            return Err(invalid());
        }
        if published {
            let root = Target::open(prefix)?;
            if Some(identity(&root)?) != record.stage_root {
                return Err(invalid());
            }
            if let Ok(private) = Target::open(&private_path) {
                if Some(identity(&private)?) != record.stage_parent
                    || !absent(&private.directory()?, "payload")?
                {
                    return Err(invalid());
                }
            } else if !absent(&directory, &name)? {
                return Err(invalid());
            }
            return Ok(Self {
                parent,
                private: None,
                name,
                owner,
                leaf,
                root,
                published,
            });
        }
        let private =
            OwnedDirectory::open_at(&directory, &name, &owner, record.phase == Phase::Prepared)?
                .ok_or_else(invalid)?;
        let held = Target::open(&private_path)?;
        let private_identity = identity(&held)?;
        if record
            .stage_parent
            .as_ref()
            .is_some_and(|id| id != &private_identity)
        {
            return Err(invalid());
        }
        if record.phase == Phase::Prepared {
            let mut builder = DirBuilder::new();
            builder.mode(0o700);
            match private.directory.create_dir_with("payload", &builder) {
                Ok(()) => (),
                Err(error) if error.kind() == ErrorKind::AlreadyExists => (),
                Err(_) => return Err(invalid()),
            }
        }
        let root = Target::open(&staged_path)?;
        let root_identity = identity(&root)?;
        if record.phase == Phase::Prepared {
            if root
                .directory()?
                .entries()
                .map_err(|_| invalid())?
                .next()
                .is_some()
            {
                return Err(invalid());
            }
            sync(&root.directory()?)?;
            private.sync()?;
            record.stage_parent = Some(private_identity);
            record.stage_root = Some(root_identity);
        } else if record.stage_root.as_ref() != Some(&root_identity) {
            return Err(invalid());
        }
        held.revalidate()?;
        parent.revalidate()?;
        Ok(Self {
            parent,
            private: Some(private),
            name,
            owner,
            leaf,
            root,
            published,
        })
    }

    pub fn activate(&mut self) -> Result<()> {
        let directory = self.parent.directory()?;
        let expected = identity(&self.root)?;
        self.root.revalidate()?;
        if !self.published {
            let private = self.private.as_ref().ok_or_else(invalid)?;
            rustix::fs::renameat_with(
                &private.directory,
                "payload",
                &directory,
                &self.leaf,
                rustix::fs::RenameFlags::NOREPLACE,
            )
            .map_err(|_| invalid())?;
            private.sync()?;
            self.root = Target::open(&self.parent.path().join(&self.leaf))?;
            if identity(&self.root)? != expected {
                return Err(invalid());
            }
            self.published = true;
        } else if !absent(&directory, &self.name)? {
            let private = Target::open(&self.parent.path().join(&self.name))?;
            sync(&private.directory()?)?;
        }
        sync(&directory)?;
        self.parent.revalidate()?;
        self.root.revalidate()
    }

    pub fn cleanup(&self, record: &Record) -> Result<()> {
        if !self.published {
            return Err(invalid());
        }
        cleanup_private(&self.parent, &self.name, &self.owner, record)
    }
}

fn cleanup_private(
    held_parent: &Target,
    stage_name: &str,
    owner: &[u8],
    record: &Record,
) -> Result<()> {
    let parent = held_parent.directory()?;
    if absent(&parent, stage_name)? {
        return Ok(());
    }
    let target = Target::open(&held_parent.path().join(stage_name))?;
    if Some(identity(&target)?) != record.stage_parent {
        return Err(invalid());
    }
    let directory = target.directory()?;
    for entry in directory.entries().map_err(|_| invalid())? {
        let entry = entry.map_err(|_| invalid())?;
        if !matches!(entry.file_name().to_str(), Some("owner" | "lock")) {
            return Err(invalid());
        }
    }
    // A retry may see only one of the two empty transaction-control files.
    for name in ["owner", "lock"] {
        if absent(&directory, name)? {
            continue;
        }
        let file =
            crate::files::open_regular(&directory, Path::new(name)).map_err(|_| invalid())?;
        let metadata = file.metadata().map_err(|_| invalid())?;
        if cap_fs_ext::MetadataExt::nlink(&metadata) != 1 {
            return Err(invalid());
        }
        if name == "owner" {
            use std::io::Read;
            let mut bytes = Vec::new();
            file.take(257)
                .read_to_end(&mut bytes)
                .map_err(|_| invalid())?;
            if bytes != owner {
                return Err(invalid());
            }
        } else if metadata.len() != 0 {
            return Err(invalid());
        }
        directory.remove_file(name).map_err(|_| invalid())?;
    }
    target.revalidate()?;
    parent.remove_dir(stage_name).map_err(|_| invalid())?;
    sync(&parent)
}
