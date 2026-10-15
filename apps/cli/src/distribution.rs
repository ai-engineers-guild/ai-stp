//! Explicit archive-owned installation. Never overwrite package-manager prefixes.

use std::path::{Path, PathBuf};

use cap_std::fs::Dir;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{
    authoring, canonical, digest,
    error::{Failure, Result},
    files::{self, OwnedDirectory},
    identity,
    registry::VERSION,
};

const OWNER: &[u8] = b"ai-stp native archive installation v1\n";
const LIMIT: u64 = 256 * 1024 * 1024;
const BINARY: &str = if cfg!(windows) {
    "ai-stp.exe"
} else {
    "ai-stp"
};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct Release {
    version: String,
    binary_sha256: String,
    os: String,
    architecture: String,
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema_version: u32,
    action: String,
    created_at: String,
    expires_at: String,
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    prefix: PathBuf,
    parent_identity: [String; 2],
    #[serde(
        serialize_with = "files::serialize_path",
        deserialize_with = "files::deserialize_path"
    )]
    source: PathBuf,
    expected: Option<Release>,
    release: Release,
}

fn invalid() -> Failure {
    Failure::precondition(
        "native installation ownership, plan or binary changed; package-managed and desktop prefixes cannot be replaced",
    )
}

fn version(value: &str) -> Result<(u64, u64, u64, u64)> {
    let (core, preview) = value
        .split_once("-preview.")
        .map_or((value, u64::MAX), |(core, preview)| {
            (core, preview.parse().unwrap_or(0))
        });
    let numbers: Vec<u64> = core
        .split('.')
        .map(str::parse)
        .collect::<std::result::Result<_, _>>()
        .map_err(|_| invalid())?;
    match numbers.as_slice() {
        [major, minor, patch] if preview > 0 => Ok((*major, *minor, *patch, preview)),
        _ => Err(invalid()),
    }
}

fn binding(prefix: &Path) -> Result<(PathBuf, [String; 2])> {
    let parent = prefix
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .ok_or_else(invalid)?;
    let leaf = prefix.file_name().ok_or_else(invalid)?;
    let (parent, identity) = identity::root(parent)?;
    Ok((parent.join(leaf), identity))
}

fn open(prefix: &Path, create: bool) -> Result<Option<OwnedDirectory>> {
    OwnedDirectory::open(
        prefix.parent().ok_or_else(invalid)?,
        prefix
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(invalid)?,
        OWNER,
        create,
    )
}

fn record(directory: &OwnedDirectory) -> Result<Option<Release>> {
    directory
        .read_file("release.json", 4096)?
        .map(|bytes| serde_json::from_value(canonical::parse(&bytes)?).map_err(|_| invalid()))
        .transpose()
}

fn pending(directory: &OwnedDirectory) -> Result<Option<Plan>> {
    directory
        .read_file("pending.json", 65536)?
        .map(|bytes| serde_json::from_value(canonical::parse(&bytes)?).map_err(|_| invalid()))
        .transpose()
}

fn inventory(directory: &OwnedDirectory) -> Result<()> {
    let mut count = 0;
    for entry in directory.directory.entries().map_err(|_| invalid())? {
        count += 1;
        let entry = entry.map_err(|_| invalid())?;
        let name = entry.file_name();
        let name = name.to_str().ok_or_else(invalid)?;
        if count > 64
            || !(matches!(
                name,
                "owner" | "lock" | "release.json" | "pending.json" | "receipt.json"
            ) || name == BINARY
                || name.starts_with(".tmp-"))
        {
            return Err(invalid());
        }
        if !directory
            .directory
            .symlink_metadata(name)
            .map_err(|_| invalid())?
            .is_file()
        {
            return Err(invalid());
        }
    }
    Ok(())
}

fn installed(directory: &OwnedDirectory) -> Result<Option<String>> {
    let bytes = directory.read_file(BINARY, LIMIT)?;
    #[cfg(unix)]
    if bytes.is_some() {
        use cap_std::fs::PermissionsExt;
        if directory
            .directory
            .symlink_metadata(BINARY)
            .map_err(|_| invalid())?
            .permissions()
            .mode()
            & 0o777
            != 0o755
        {
            return Err(invalid());
        }
    }
    Ok(bytes.map(|bytes| digest::sha256(&bytes)))
}

fn revalidate(directory: &OwnedDirectory, prefix: &Path) -> Result<()> {
    let (_, named) = identity::root(prefix)?;
    if named != identity::physical_root(&directory.directory)? {
        return Err(invalid());
    }
    directory.validate_lock()
}

pub fn plan(prefix: &Path) -> Result<Value> {
    let (prefix, parent_identity) = binding(prefix)?;
    let source = PathBuf::from(files::location(
        &std::env::current_exe().map_err(|_| invalid())?,
    )?);
    if source.starts_with(&prefix) {
        return Err(Failure::precondition(
            "run the verified new archive executable outside its managed installation prefix",
        ));
    }
    let release = Release {
        version: VERSION.into(),
        binary_sha256: digest::sha256(&files::read(&source, LIMIT)?),
        os: std::env::consts::OS.into(),
        architecture: std::env::consts::ARCH.into(),
    };
    let expected = if let Some(directory) = open(&prefix, false)? {
        inventory(&directory)?;
        if pending(&directory)?.is_some() {
            return Err(Failure::precondition(
                "resume the pending installation plan returned by cli install status",
            ));
        }
        let existing = record(&directory)?;
        if installed(&directory)?
            != existing
                .as_ref()
                .map(|release| release.binary_sha256.clone())
        {
            return Err(invalid());
        }
        if let Some(existing) = &existing
            && (version(&release.version)? < version(&existing.version)?
                || existing.os != release.os
                || existing.architecture != release.architecture)
        {
            return Err(invalid());
        }
        existing
    } else {
        None
    };
    let created_at = format!("{:.3}", jiff::Timestamp::now());
    let plan = Plan {
        schema_version: 1,
        action: "cli.install".into(),
        expires_at: authoring::expiry(&created_at)?,
        created_at,
        prefix,
        parent_identity,
        source,
        expected,
        release,
    };
    let value = serde_json::to_value(&plan).map_err(|_| invalid())?;
    Ok(json!({"plan_digest":digest::canonical("ai-stp:plan:v1", &value)?,"plan":value}))
}

pub fn status(prefix: &Path) -> Result<Value> {
    let (prefix, _) = binding(prefix)?;
    let Some(directory) = open(&prefix, false)? else {
        return Ok(json!({"schema_version":1,"state":"absent","prefix":prefix}));
    };
    inventory(&directory)?;
    let pending = pending(&directory)?;
    let retained = pending
        .map(|plan| {
            let value = serde_json::to_value(plan).map_err(|_| invalid())?;
            Ok::<_, Failure>(
                json!({"plan_digest":digest::canonical("ai-stp:plan:v1", &value)?,"plan":value}),
            )
        })
        .transpose()?;
    let release = record(&directory)?;
    let exact = installed(&directory)?
        == release
            .as_ref()
            .map(|release| release.binary_sha256.clone());
    Ok(
        json!({"schema_version":1,"state":if retained.is_some() {"pending"} else if release.is_some() && exact {"verified"} else {"uninitialized"},
        "prefix":prefix,"release":release,"binary_matches":exact,"pending_operation":retained}),
    )
}

pub fn apply(path: &Path, expected_digest: &str) -> Result<Value> {
    let value = canonical::parse(&files::read(path, 65536)?)?;
    let plan: Plan = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    if plan.schema_version != 1
        || plan.action != "cli.install"
        || digest::canonical("ai-stp:plan:v1", &value)? != expected_digest
        || binding(&plan.prefix)? != (plan.prefix.clone(), plan.parent_identity.clone())
        || plan.expires_at != authoring::expiry(&plan.created_at)?
        || plan.release.version != VERSION
        || plan.release.os != std::env::consts::OS
        || plan.release.architecture != std::env::consts::ARCH
        || plan.expected.as_ref().is_some_and(|old| {
            version(&old.version).is_err() || version(&old.version).ok() > version(VERSION).ok()
        })
    {
        return Err(invalid());
    }
    let at = format!("{:.3}", jiff::Timestamp::now());
    let existing = open(&plan.prefix, false)?;
    let admitted = existing.as_ref().map(pending).transpose()?.flatten();
    if let Some(admitted) = &admitted {
        if admitted != &plan {
            return Err(invalid());
        }
    } else {
        if let Some(directory) = &existing
            && directory
                .read_file("receipt.json", 65536)?
                .is_some_and(|bytes| {
                    canonical::parse(&bytes)
                        .is_ok_and(|receipt| receipt["plan_digest"] == expected_digest)
                })
            && record(directory)?.as_ref() == Some(&plan.release)
            && installed(directory)?.as_deref() == Some(&plan.release.binary_sha256)
        {
            return status_receipt(&plan, expected_digest);
        }
        if at < plan.created_at || at > plan.expires_at {
            return Err(Failure::precondition(
                "the installation plan expired before admission",
            ));
        }
    }
    let directory = match existing {
        Some(directory) => directory,
        None => open(&plan.prefix, true)?.ok_or_else(invalid)?,
    };
    inventory(&directory)?;
    revalidate(&directory, &plan.prefix)?;
    let current = installed(&directory)?;
    let already_published =
        admitted.is_some() && current.as_deref() == Some(&plan.release.binary_sha256);
    if !already_published {
        if record(&directory)? != plan.expected
            || current
                != plan
                    .expected
                    .as_ref()
                    .map(|release| release.binary_sha256.clone())
        {
            return Err(invalid());
        }
        let source = PathBuf::from(files::location(
            &std::env::current_exe().map_err(|_| invalid())?,
        )?);
        if source.starts_with(&plan.prefix) {
            return Err(invalid());
        }
        let bytes = files::read(&source, LIMIT)?;
        if digest::sha256(&bytes) != plan.release.binary_sha256 {
            return Err(invalid());
        }
        revalidate(&directory, &plan.prefix)?;
        directory.atomic("pending.json", &canonical::bytes(&value)?)?;
        directory.atomic_checked(BINARY, &bytes, |file| {
            #[cfg(unix)]
            {
                use cap_std::fs::PermissionsExt;
                file.set_permissions(cap_std::fs::Permissions::from_mode(0o755))
                    .map_err(|_| invalid())?;
            }
            let _ = file;
            Ok(())
        })?;
    }
    if installed(&directory)?.as_deref() != Some(&plan.release.binary_sha256) {
        return Err(invalid());
    }
    revalidate(&directory, &plan.prefix)?;
    let parent = Dir::open_ambient_dir(
        plan.prefix.parent().ok_or_else(invalid)?,
        cap_std::ambient_authority(),
    )
    .map_err(|_| invalid())?;
    if identity::physical_root(&parent)? != plan.parent_identity {
        return Err(invalid());
    }
    directory.atomic(
        "release.json",
        &canonical::bytes(&serde_json::to_value(&plan.release).map_err(|_| invalid())?)?,
    )?;
    let receipt = status_receipt(&plan, expected_digest)?;
    directory.atomic("receipt.json", &canonical::bytes(&receipt)?)?;
    directory
        .directory
        .remove_file("pending.json")
        .map_err(|_| invalid())?;
    directory.sync()?;
    Ok(receipt)
}

fn status_receipt(plan: &Plan, digest: &str) -> Result<Value> {
    Ok(
        json!({"schema_version":1,"state":"verified","ownership":"native_archive","plan_digest":digest,
        "prefix":plan.prefix,"executable":plan.prefix.join(BINARY),"release":plan.release,
        "state_modified":false,"path_modified":false}),
    )
}
