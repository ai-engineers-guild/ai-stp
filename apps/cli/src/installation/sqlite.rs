//! SQLite file operations confined to a held metadata directory.
//!
//! One process-lifetime registration routes ephemeral names to held scopes. A
//! scope owns its OS lock and in-process identity claim until SQLite closes all
//! handles. No ambient database path, temporary database, WAL or mmap is allowed.

use std::{
    borrow::Cow,
    collections::{BTreeMap, HashSet},
    io::{self, Read, Seek, SeekFrom, Write},
    sync::{Arc, Mutex, OnceLock, Weak},
};

use cap_fs_ext::{DirExt, FollowSymlinks, MetadataExt, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::{Dir, File, Metadata, OpenOptions};
use sqlite_plugin::{
    flags::{AccessFlags, CreateMode, LockLevel, OpenKind, OpenMode, OpenOpts},
    vars,
    vfs::{RegisterOpts, Vfs, VfsHandle, VfsResult, register_static},
};

use crate::installation::{Error, ReasonCode, Result};

pub(crate) const DATABASE: &str = "records.sqlite3";
pub(crate) const JOURNAL: &str = "records.sqlite3-journal";
pub(crate) const LOCK: &str = "records.lock";
pub(crate) const NAME: &str = "ai-stp-installation-records-v1";
const FILE_LIMIT: u64 = 256 * 1024 * 1024;
type FileId = crate::installation::identity::Identity;

#[derive(Default)]
struct Registry {
    sequence: u64,
    scopes: BTreeMap<String, Weak<Scope>>,
    claimed: HashSet<FileId>,
}

fn registry() -> &'static Mutex<Registry> {
    static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();
    REGISTRY.get_or_init(Mutex::default)
}

fn invalid() -> Error {
    Error::new(
        ReasonCode::RecoveryRequired,
        "transaction metadata or directory identity is inconsistent",
    )
}

fn checked<T>(value: io::Result<T>) -> Result<T> {
    value.map_err(|error| invalid().with_source(error))
}

#[cfg_attr(
    not(unix),
    allow(
        clippy::unnecessary_wraps,
        reason = "Directory flushing is available on Unix only."
    )
)]
fn sync_directory(directory: &Dir) -> Result<()> {
    #[cfg(unix)]
    checked(checked(directory.open("."))?.sync_all())?;
    #[cfg(not(unix))]
    let _ = directory;
    Ok(())
}

fn directory_identity(directory: &Dir) -> Result<FileId> {
    #[cfg(windows)]
    {
        let metadata = checked(directory.dir_metadata())?;
        use cap_std::fs::MetadataExt as _;
        if metadata.file_attributes() & 0x400 != 0 {
            return Err(invalid());
        }
    }
    checked(crate::installation::identity::directory(directory))
}

fn refused() -> io::Error {
    io::Error::other("transaction metadata file or held directory changed")
}

fn valid(metadata: &Metadata) -> bool {
    #[cfg(windows)]
    {
        use cap_std::fs::MetadataExt as _;
        if metadata.file_attributes() & 0x400 != 0 {
            return false;
        }
    }
    metadata.is_file()
        && !metadata.is_symlink()
        && metadata.nlink() == 1
        && metadata.len() <= FILE_LIMIT
}

pub(crate) struct Observed {
    metadata: Metadata,
    identity: FileId,
}

impl std::ops::Deref for Observed {
    type Target = Metadata;
    fn deref(&self) -> &Self::Target {
        &self.metadata
    }
}

fn identity(observed: &Observed) -> FileId {
    observed.identity
}

fn observe_file(file: &File) -> io::Result<Observed> {
    Ok(Observed {
        metadata: file.metadata()?,
        identity: crate::installation::identity::file(file)?,
    })
}

pub(crate) fn inspect(directory: &Dir, name: &str) -> io::Result<Option<Observed>> {
    match directory.symlink_metadata(name) {
        Ok(metadata) if valid(&metadata) => {
            let file = directory.open_with(name, &options(false))?;
            let observed = observe_file(&file)?;
            if !valid(&observed) {
                return Err(refused());
            }
            Ok(Some(observed))
        }
        Ok(_) => Err(refused()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error),
    }
}

fn sql<T>(result: io::Result<T>) -> VfsResult<T> {
    result.map_err(|_| vars::SQLITE_IOERR)
}

struct Claim {
    id: String,
    directory: FileId,
}

impl Claim {
    fn acquire(directory: &Dir) -> Result<Self> {
        let directory = directory_identity(directory)?;
        let mut registry = registry().lock().map_err(|_| invalid())?;
        if registry.claimed.contains(&directory) {
            return Err(Error::new(
                ReasonCode::LockUnavailable,
                "transaction metadata is already open",
            ));
        }
        registry.sequence = registry.sequence.checked_add(1).ok_or_else(invalid)?;
        let id = registry.sequence.to_string();
        registry.claimed.insert(directory);
        Ok(Self { id, directory })
    }
}

impl Drop for Claim {
    fn drop(&mut self) {
        let mut registry = registry()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        registry.scopes.remove(&self.id);
        registry.claimed.remove(&self.directory);
    }
}

pub(crate) struct Scope {
    root: Dir,
    directory: Dir,
    directory_identity: FileId,
    name: String,
    lock: std::fs::File,
    lock_identity: FileId,
    writable: bool,
    observed: Mutex<BTreeMap<String, FileId>>,
    // Released after all file handles, including the OS lock, are closed.
    claim: Claim,
}

impl Scope {
    pub(crate) fn open(
        root: &Dir,
        name: &str,
        directory: Dir,
        writable: bool,
    ) -> Result<Arc<Self>> {
        static REGISTERED: OnceLock<bool> = OnceLock::new();
        if name.is_empty() || name.contains(['/', '\\', ':']) || matches!(name, "." | "..") {
            return Err(invalid());
        }
        if !REGISTERED.get_or_init(|| {
            register_static(
                c"ai-stp-installation-records-v1".to_owned(),
                Confined,
                RegisterOpts {
                    make_default: false,
                },
            )
            .is_ok()
        }) {
            return Err(invalid());
        }
        let claim = Claim::acquire(&directory)?;
        let root = checked(root.try_clone())?;
        let directory_identity = directory_identity(&directory)?;
        let before = checked(inspect(&directory, LOCK))?.map(|m| identity(&m));
        let mut options = options(writable);
        options.create(writable);
        let lock = checked(directory.open_with(LOCK, &options))?;
        let metadata = checked(observe_file(&lock))?;
        let lock_identity = identity(&metadata);
        if !valid(&metadata) || metadata.len() != 0 || before.is_some_and(|id| id != lock_identity)
        {
            return Err(invalid());
        }
        let lock = lock.into_std();
        let acquired = if writable {
            lock.try_lock()
        } else {
            lock.try_lock_shared()
        };
        acquired.map_err(|error| {
            Error::new(
                ReasonCode::LockUnavailable,
                "transaction metadata is held by another process",
            )
            .with_source(error)
        })?;
        let scope = Arc::new(Self {
            root,
            directory,
            directory_identity,
            name: name.into(),
            lock,
            lock_identity,
            writable,
            observed: Mutex::default(),
            claim,
        });
        checked(scope.check())?;
        if writable {
            sync_directory(&scope.directory)?;
        }
        registry()
            .lock()
            .map_err(|_| invalid())?
            .scopes
            .insert(scope.claim.id.clone(), Arc::downgrade(&scope));
        Ok(scope)
    }

    pub(crate) fn path(&self) -> String {
        format!("{}/{DATABASE}", self.claim.id)
    }

    pub(crate) fn validate(&self) -> Result<()> {
        checked(self.check())?;
        for (name, expected) in self.observed.lock().map_err(|_| invalid())?.iter() {
            let metadata = checked(inspect(&self.directory, name))?.ok_or_else(invalid)?;
            if identity(&metadata) != *expected {
                return Err(invalid());
            }
        }
        Ok(())
    }

    fn check(&self) -> io::Result<()> {
        let named = self.root.open_dir_nofollow(&self.name)?;
        if directory_identity(&named).map_err(|_| refused())? != self.directory_identity {
            return Err(refused());
        }
        let named = inspect(&self.directory, LOCK)?.ok_or_else(refused)?;
        let opened = Observed {
            metadata: Metadata::from_file(&self.lock)?,
            identity: crate::installation::identity::standard_file(&self.lock)?,
        };
        if identity(&named) != self.lock_identity
            || identity(&opened) != self.lock_identity
            || !valid(&opened)
            || opened.len() != 0
            || named.len() != 0
        {
            return Err(refused());
        }
        Ok(())
    }

    fn inspect(&self, name: &str) -> io::Result<Option<Observed>> {
        self.check()?;
        let metadata = inspect(&self.directory, name)?;
        let mut observed = self.observed.lock().map_err(|_| refused())?;
        match (observed.get(name), &metadata) {
            (Some(expected), Some(actual)) if *expected == identity(actual) => {}
            (None, Some(actual)) => {
                if name == JOURNAL {
                    self.check_journal(actual)?;
                }
                observed.insert(name.to_owned(), identity(actual));
            }
            (None, None) => {}
            _ => return Err(refused()),
        }
        Ok(metadata)
    }

    fn check_journal(&self, expected: &Observed) -> io::Result<()> {
        // SQLite may delete a non-hot journal without ever opening it. Refuse
        // foreign bytes here, before xAccess can cause that cleanup. Empty or
        // zeroed headers are SQLite's own interrupted initialization state.
        let mut file = self.directory.open_with(JOURNAL, &options(false))?;
        let metadata = observe_file(&file)?;
        if !valid(&metadata) || identity(&metadata) != identity(expected) {
            return Err(refused());
        }
        let mut header = [0; 8];
        let length = usize::try_from(metadata.len().min(8)).map_err(|_| refused())?;
        file.read_exact(&mut header[..length])?;
        if header != [0; 8] && header != [0xd9, 0xd5, 0x05, 0xf9, 0x20, 0xa1, 0x63, 0xd7] {
            return Err(refused());
        }
        let named = inspect(&self.directory, JOURNAL)?.ok_or_else(refused)?;
        if identity(&named) != identity(expected) {
            return Err(refused());
        }
        Ok(())
    }

    fn sync(&self) -> io::Result<()> {
        self.check()?;
        sync_directory(&self.directory).map_err(|_| refused())
    }
}

impl Drop for Scope {
    fn drop(&mut self) {
        // A concurrent fork may retain this open file description until exec.
        // Release authority when the last SQLite scope closes, before its
        // in-process claim becomes available to another operation.
        let _ = self.lock.unlock();
    }
}

fn options(writable: bool) -> OpenOptions {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .write(writable)
        .follow(FollowSymlinks::No)
        .nonblock(true);
    #[cfg(unix)]
    {
        use cap_std::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
pub(crate) fn check_lock_release_with_retained_descriptor(root: &Dir, name: &str) {
    let directory = || root.open_dir_nofollow(name).unwrap();
    let scope = Scope::open(root, name, directory(), true).unwrap();
    // A fork can retain this open file description until the child's exec.
    let retained = scope.lock.try_clone().unwrap();
    drop(scope);
    let next = Scope::open(root, name, directory(), true);
    assert!(next.is_ok(), "a closed scope retained its OS lock");
    drop(next);
    drop(retained);
}

fn resolve(path: &str) -> io::Result<(Arc<Scope>, &str)> {
    let (id, name) = path.split_once('/').ok_or_else(refused)?;
    if !matches!(
        name,
        DATABASE | JOURNAL | "records.sqlite3-wal" | "records.sqlite3-shm"
    ) {
        return Err(refused());
    }
    let scope = registry()
        .lock()
        .map_err(|_| refused())?
        .scopes
        .get(id)
        .and_then(Weak::upgrade)
        .ok_or_else(refused)?;
    Ok((scope, name))
}

struct Handle {
    scope: Arc<Scope>,
    file: File,
    name: String,
    identity: FileId,
    readonly: bool,
}

impl Handle {
    fn check(&self) -> io::Result<()> {
        let named = self.scope.inspect(&self.name)?.ok_or_else(refused)?;
        let opened = observe_file(&self.file)?;
        if !valid(&opened)
            || identity(&opened) != self.identity
            || identity(&named) != self.identity
        {
            return Err(refused());
        }
        Ok(())
    }
}

impl VfsHandle for Handle {
    fn readonly(&self) -> bool {
        self.readonly
    }
    fn in_memory(&self) -> bool {
        false
    }
}

struct Confined;

impl Vfs for Confined {
    type Handle = Handle;

    fn canonical_path<'a>(&self, path: Cow<'a, str>) -> VfsResult<Cow<'a, str>> {
        sql(resolve(&path))?;
        Ok(path)
    }

    fn open(&self, path: Option<&str>, opts: OpenOpts) -> VfsResult<Handle> {
        let (scope, name) = sql(resolve(path.ok_or(vars::SQLITE_CANTOPEN)?))?;
        if !matches!(
            (name, opts.kind()),
            (DATABASE, OpenKind::MainDb) | (JOURNAL, OpenKind::MainJournal)
        ) || opts.delete_on_close()
            || (!scope.writable && !opts.mode().is_readonly())
        {
            return Err(vars::SQLITE_CANTOPEN);
        }
        let before = sql(scope.inspect(name))?.map(|metadata| identity(&metadata));
        let readonly = opts.mode().is_readonly();
        let mut options = options(!readonly);
        if let OpenMode::ReadWrite { create } = opts.mode() {
            match create {
                CreateMode::Create => {
                    options
                        .create(before.is_none())
                        .create_new(before.is_none());
                }
                CreateMode::MustCreate => {
                    options.create_new(true);
                }
                CreateMode::None => {}
            }
        }
        let file = sql(scope.directory.open_with(name, &options))?;
        let metadata = sql(observe_file(&file))?;
        if !valid(&metadata) || before.is_some_and(|id| id != identity(&metadata)) {
            return Err(vars::SQLITE_IOERR);
        }
        let handle = Handle {
            file,
            scope,
            name: name.to_owned(),
            identity: identity(&metadata),
            readonly,
        };
        sql(handle.check())?;
        if before.is_none() {
            sql(handle.scope.sync())?;
        }
        Ok(handle)
    }

    fn delete(&self, path: &str) -> VfsResult<()> {
        let (scope, name) = sql(resolve(path))?;
        if !scope.writable || name != JOURNAL {
            return Err(vars::SQLITE_IOERR_DELETE);
        }
        if sql(scope.inspect(name))?.is_some() {
            sql(scope.directory.remove_file(name))?;
            scope
                .observed
                .lock()
                .map_err(|_| vars::SQLITE_IOERR)?
                .remove(name);
            sql(scope.sync())?;
        }
        Ok(())
    }

    fn access(&self, path: &str, _: AccessFlags) -> VfsResult<bool> {
        let (scope, name) = sql(resolve(path))?;
        let present = sql(scope.inspect(name))?.is_some();
        if present && !matches!(name, DATABASE | JOURNAL) {
            return Err(vars::SQLITE_IOERR);
        }
        Ok(present)
    }

    fn file_size(&self, handle: &mut Handle) -> VfsResult<usize> {
        sql(handle.check())?;
        usize::try_from(sql(handle.file.metadata())?.len()).map_err(|_| vars::SQLITE_IOERR)
    }

    fn truncate(&self, handle: &mut Handle, size: usize) -> VfsResult<()> {
        sql(handle.check())?;
        if handle.readonly || size as u64 > FILE_LIMIT {
            return Err(vars::SQLITE_IOERR);
        }
        sql(handle.file.set_len(size as u64))
    }

    fn read(&self, handle: &mut Handle, offset: usize, data: &mut [u8]) -> VfsResult<usize> {
        sql(handle.check())?;
        data.fill(0);
        sql(handle.file.seek(SeekFrom::Start(offset as u64)))?;
        let mut total = 0;
        while total < data.len() {
            let read = sql(handle.file.read(&mut data[total..]))?;
            if read == 0 {
                break;
            }
            total += read;
        }
        Ok(total)
    }

    fn write(&self, handle: &mut Handle, offset: usize, data: &[u8]) -> VfsResult<usize> {
        sql(handle.check())?;
        if handle.readonly
            || offset
                .checked_add(data.len())
                .is_none_or(|end| end as u64 > FILE_LIMIT)
        {
            return Err(vars::SQLITE_IOERR);
        }
        sql(handle.file.seek(SeekFrom::Start(offset as u64)))?;
        sql(handle.file.write_all(data))?;
        Ok(data.len())
    }

    // The scope already holds a shared (reader) or exclusive (writer) OS lock
    // for the entire connection. SQLite cannot weaken it between transactions.
    fn lock(&self, handle: &mut Handle, level: LockLevel) -> VfsResult<()> {
        sql(handle.check())?;
        if handle.readonly && !matches!(level, LockLevel::Shared) {
            return Err(vars::SQLITE_READONLY);
        }
        Ok(())
    }

    fn unlock(&self, handle: &mut Handle, _: LockLevel) -> VfsResult<()> {
        sql(handle.check())
    }
    fn check_reserved_lock(&self, handle: &mut Handle) -> VfsResult<bool> {
        sql(handle.check())?;
        Ok(false)
    }

    fn sync(&self, handle: &mut Handle) -> VfsResult<()> {
        sql(handle.check())?;
        if handle.readonly {
            return Err(vars::SQLITE_READONLY);
        }
        sql(handle.file.sync_all())?;
        sql(handle.scope.sync())
    }

    // Do not inherit the bridge's memory-VFS defaults: ordinary files promise
    // neither atomic writes, safe append, sequential persistence nor PSOW.
    fn device_characteristics(&self, _: &mut Handle) -> VfsResult<i32> {
        Ok(0)
    }
    fn close(&self, _: Handle) -> VfsResult<()> {
        Ok(())
    }
}
