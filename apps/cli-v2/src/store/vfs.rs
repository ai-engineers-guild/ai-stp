//! SQLite I/O through the held private registry directory. One registration
//! routes connection-local names to scopes; no ambient database path is opened.

use std::{
    borrow::Cow,
    collections::BTreeMap,
    fs::File,
    io::{self, Read, Seek, SeekFrom, Write},
    sync::{Arc, Mutex, OnceLock, Weak},
};

use cap_fs_ext::{DirExt, MetadataExt};
use cap_std::fs::{Dir, Metadata};
use sqlite_plugin::{
    flags::{AccessFlags, CreateMode, LockLevel, OpenKind, OpenMode, OpenOpts},
    vars,
    vfs::{RegisterOpts, Vfs, VfsHandle, VfsResult, register_static},
};

use crate::{
    error::{ErrorKind, Failure, Result},
    files::{OwnedDirectory, private_options},
};

pub(super) const NAME: &str = "ai-stp-registry-v1";
const DATABASE: &str = "registry.sqlite3";
const JOURNAL: &str = "registry.sqlite3-journal";
const WAL: &str = "registry.sqlite3-wal";
const SHM: &str = "registry.sqlite3-shm";
type Identity = (u64, u64);

#[derive(Default)]
struct Registry {
    sequence: u64,
    scopes: BTreeMap<String, Weak<Scope>>,
}

fn registry() -> &'static Mutex<Registry> {
    static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();
    REGISTRY.get_or_init(Mutex::default)
}

fn refused() -> io::Error {
    io::Error::other("the held registry directory or file changed")
}

fn identity(metadata: &Metadata) -> Identity {
    (metadata.dev(), metadata.ino())
}

fn valid(metadata: &Metadata) -> bool {
    #[cfg(unix)]
    {
        use cap_std::fs::MetadataExt as _;
        if metadata.mode() & 0o077 != 0 {
            return false;
        }
    }
    #[cfg(windows)]
    {
        use cap_std::fs::MetadataExt as _;
        if metadata.file_attributes() & 0x400 != 0 {
            return false;
        }
    }
    metadata.is_file() && !metadata.is_symlink() && metadata.nlink() == 1
}

fn inspect(directory: &Dir, name: &str) -> io::Result<Option<Metadata>> {
    match directory.symlink_metadata(name) {
        Ok(metadata) if valid(&metadata) => Ok(Some(metadata)),
        Ok(_) => Err(refused()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error),
    }
}

fn sql<T>(result: io::Result<T>) -> VfsResult<T> {
    result.map_err(|_| vars::SQLITE_IOERR)
}

pub(super) struct Scope {
    id: String,
    parent: Dir,
    owned: OwnedDirectory,
    directory_identity: Identity,
    // Transfer this exact checked handle to SQLite once. Reopening the main
    // file would introduce another validation/open race and weaken POSIX locks.
    database: Mutex<Option<File>>,
    observed: Mutex<BTreeMap<String, Identity>>,
}

impl Scope {
    pub(super) fn open(parent: Dir, owned: OwnedDirectory) -> Result<Arc<Self>> {
        let failure = || Failure::precondition("the registry file boundary is invalid");
        static REGISTERED: OnceLock<VfsResult<()>> = OnceLock::new();
        REGISTERED
            .get_or_init(|| {
                register_static(
                    c"ai-stp-registry-v1".into(),
                    Confined,
                    RegisterOpts {
                        make_default: false,
                    },
                )
                .map(|_| ())
            })
            .as_ref()
            .map_err(|_| failure())?;
        let before = inspect(&owned.directory, DATABASE)
            .map_err(|_| failure())?
            .ok_or_else(failure)?;
        let file = owned
            .directory
            .open_with(DATABASE, private_options().read(true))
            .map_err(|_| failure())?
            .into_std();
        let metadata = Metadata::from_file(&file).map_err(|_| failure())?;
        if !valid(&metadata) || identity(&metadata) != identity(&before) {
            return Err(failure());
        }
        lock_database(&file).map_err(|_| {
            Failure::new(
                ErrorKind::Unavailable,
                "the registry is held by another SQLite connection",
            )
        })?;
        let directory_identity = identity(&owned.directory.dir_metadata().map_err(|_| failure())?);
        let mut registry = registry().lock().map_err(|_| failure())?;
        registry.sequence = registry.sequence.checked_add(1).ok_or_else(failure)?;
        let scope = Arc::new(Self {
            id: registry.sequence.to_string(),
            parent,
            owned,
            directory_identity,
            database: Mutex::new(Some(file)),
            observed: Mutex::new(BTreeMap::from([(DATABASE.to_owned(), identity(&metadata))])),
        });
        registry
            .scopes
            .insert(scope.id.clone(), Arc::downgrade(&scope));
        drop(registry);
        scope.validate().map_err(|_| failure())?;
        // SQLite may discard a non-hot companion without opening it. Inspect
        // existing companion headers before granting that cleanup authority.
        for name in [JOURNAL, WAL, SHM] {
            scope.inspect(name).map_err(|_| failure())?;
        }
        Ok(scope)
    }

    pub(super) fn path(&self) -> String {
        format!("{}/{DATABASE}", self.id)
    }

    fn check(&self) -> io::Result<()> {
        let named = self.parent.open_dir_nofollow(super::NAMESPACE)?;
        let metadata = named.dir_metadata()?;
        #[cfg(unix)]
        if cap_std::fs::MetadataExt::mode(&metadata) & 0o077 != 0 {
            return Err(refused());
        }
        if identity(&metadata) != self.directory_identity {
            return Err(refused());
        }
        self.owned.validate_lock().map_err(|_| refused())
    }

    pub(super) fn validate(&self) -> io::Result<()> {
        self.check()?;
        for (name, expected) in self.observed.lock().map_err(|_| refused())?.iter() {
            if inspect(&self.owned.directory, name)?.as_ref().map(identity) != Some(*expected) {
                return Err(refused());
            }
        }
        Ok(())
    }

    fn inspect(&self, name: &str) -> io::Result<Option<Metadata>> {
        self.check()?;
        let metadata = inspect(&self.owned.directory, name)?;
        let mut observed = self.observed.lock().map_err(|_| refused())?;
        match (observed.get(name), &metadata) {
            (Some(expected), Some(actual)) if *expected == identity(actual) => {}
            (None, Some(actual)) => {
                if matches!(name, JOURNAL | WAL) {
                    self.companion_header(name, actual)?;
                }
                observed.insert(name.to_owned(), identity(actual));
            }
            (None, None) => {}
            _ => return Err(refused()),
        }
        Ok(metadata)
    }

    fn companion_header(&self, name: &str, expected: &Metadata) -> io::Result<()> {
        let mut file = crate::files::open_regular(&self.owned.directory, name.as_ref())?;
        let opened = file.metadata()?;
        if !valid(&opened) || identity(&opened) != identity(expected) {
            return Err(refused());
        }
        let mut header = [0; 8];
        let size = usize::try_from(opened.len().min(8)).map_err(|_| refused())?;
        file.read_exact(&mut header[..size])?;
        let known = if name == JOURNAL {
            header == [0xd9, 0xd5, 0x05, 0xf9, 0x20, 0xa1, 0x63, 0xd7]
        } else {
            matches!(
                header,
                [0x37, 0x7f, 0x06, 0x82 | 0x83, 0x00, 0x2d, 0xe2, 0x18]
            )
        };
        if header != [0; 8] && !known {
            return Err(refused());
        }
        Ok(())
    }

    fn sync(&self) -> io::Result<()> {
        self.check()?;
        self.owned.sync().map_err(|_| refused())
    }
}

impl Drop for Scope {
    fn drop(&mut self) {
        registry()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .scopes
            .remove(&self.id);
    }
}

// A separate process using the standard SQLite VFS must also be excluded.
// POSIX whole-file record locks overlap SQLite's byte locks; the main handle
// is never cloned or reopened while this connection lives. The namespace lock
// additionally excludes other Store connections within this process.
#[cfg(unix)]
fn lock_database(file: &File) -> io::Result<()> {
    rustix::fs::fcntl_lock(file, rustix::fs::FlockOperation::NonBlockingLockExclusive)
        .map_err(Into::into)
}
#[cfg(windows)]
fn lock_database(file: &File) -> io::Result<()> {
    file.try_lock().map_err(Into::into)
}

struct Handle {
    scope: Arc<Scope>,
    file: File,
    name: String,
    identity: Identity,
}

impl Handle {
    fn check(&self) -> io::Result<()> {
        let named = self.scope.inspect(&self.name)?.ok_or_else(refused)?;
        let opened = Metadata::from_file(&self.file)?;
        if !valid(&opened)
            || identity(&opened) != self.identity
            || identity(&named) != self.identity
        {
            return Err(refused());
        }
        Ok(())
    }
}

impl Drop for Handle {
    fn drop(&mut self) {
        if self.name == DATABASE {
            #[cfg(unix)]
            let _ = rustix::fs::fcntl_lock(&self.file, rustix::fs::FlockOperation::Unlock);
            #[cfg(windows)]
            let _ = self.file.unlock();
        }
    }
}

impl VfsHandle for Handle {
    fn readonly(&self) -> bool {
        false
    }
    fn in_memory(&self) -> bool {
        false
    }
}

fn resolve(path: &str) -> io::Result<(Arc<Scope>, &str)> {
    let (id, name) = path.split_once('/').ok_or_else(refused)?;
    if !matches!(name, DATABASE | JOURNAL | WAL | SHM) {
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
            (DATABASE, OpenKind::MainDb) | (JOURNAL, OpenKind::MainJournal) | (WAL, OpenKind::Wal)
        ) || opts.delete_on_close()
            || opts.mode().is_readonly()
        {
            return Err(vars::SQLITE_CANTOPEN);
        }
        let before = sql(scope.inspect(name))?.as_ref().map(identity);
        let file = if name == DATABASE {
            scope
                .database
                .lock()
                .map_err(|_| vars::SQLITE_IOERR)?
                .take()
                .ok_or(vars::SQLITE_CANTOPEN)?
        } else {
            let mut options = private_options();
            options.read(true);
            if let OpenMode::ReadWrite { create } = opts.mode() {
                match create {
                    CreateMode::Create => {
                        options.create_new(before.is_none());
                    }
                    CreateMode::MustCreate => {
                        options.create_new(true);
                    }
                    CreateMode::None => {}
                }
            }
            sql(scope.owned.directory.open_with(name, &options))?.into_std()
        };
        let metadata = sql(Metadata::from_file(&file))?;
        if !valid(&metadata) || before.is_some_and(|id| id != identity(&metadata)) {
            return Err(vars::SQLITE_IOERR);
        }
        let handle = Handle {
            scope,
            file,
            name: name.to_owned(),
            identity: identity(&metadata),
        };
        sql(handle.check())?;
        if before.is_none() {
            sql(handle.scope.sync())?;
        }
        Ok(handle)
    }

    fn delete(&self, path: &str) -> VfsResult<()> {
        let (scope, name) = sql(resolve(path))?;
        if !matches!(name, JOURNAL | WAL) {
            return Err(vars::SQLITE_IOERR_DELETE);
        }
        if sql(scope.inspect(name))?.is_some() {
            sql(scope.owned.directory.remove_file(name))?;
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
        Ok(sql(scope.inspect(name))?.is_some())
    }
    fn file_size(&self, handle: &mut Handle) -> VfsResult<usize> {
        sql(handle.check())?;
        usize::try_from(sql(handle.file.metadata())?.len()).map_err(|_| vars::SQLITE_IOERR)
    }
    fn truncate(&self, handle: &mut Handle, size: usize) -> VfsResult<()> {
        sql(handle.check())?;
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
        sql(handle.file.seek(SeekFrom::Start(offset as u64)))?;
        sql(handle.file.write_all(data))?;
        Ok(data.len())
    }
    // The physical database lock remains exclusive until SQLite closes. These
    // callbacks cannot weaken it, including between query-only transactions.
    fn lock(&self, handle: &mut Handle, _: LockLevel) -> VfsResult<()> {
        sql(handle.check())
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
        sql(handle.file.sync_all())?;
        sql(handle.scope.sync())
    }
    fn device_characteristics(&self, _: &mut Handle) -> VfsResult<i32> {
        Ok(0)
    }
    fn close(&self, _: Handle) -> VfsResult<()> {
        Ok(())
    }
}
