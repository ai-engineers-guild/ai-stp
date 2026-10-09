//! Minimal Linux filesystem and measured IPv4/IPv6/UDP network separation.

use super::{probe, unavailable};
use crate::{
    digest,
    error::Result,
    process::{self, Request},
    wire,
};
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    fs::File,
    io::{Read, Seek, Write},
    net::{TcpListener, UdpSocket},
    os::{fd::AsRawFd, unix::fs::MetadataExt},
    path::{Path, PathBuf},
    time::Duration,
};

pub(super) struct Launcher {
    image: File,
    executable: PathBuf,
    digest: String,
}

fn identity(mut file: &File) -> Result<String> {
    let metadata = file.metadata().map_err(|_| unavailable())?;
    if !metadata.is_file()
        || metadata.uid() != 0
        || metadata.mode() & 0o6022 != 0
        || metadata.mode() & 0o111 == 0
        || metadata.len() > 1024 * 1024
    {
        return Err(unavailable());
    }
    file.rewind().map_err(|_| unavailable())?;
    let mut bytes = Vec::new();
    file.take(1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| unavailable())?;
    if bytes.len() as u64 != metadata.len() {
        return Err(unavailable());
    }
    Ok(digest::sha256(&bytes))
}

fn environment() -> Vec<(OsString, OsString)> {
    [
        ("PATH", ""),
        ("HOME", "/home"),
        ("LANG", "C.UTF-8"),
        ("AI_STP_PROVIDER_RUNTIME_CACHE", "/tmp/provider-cache"),
    ]
    .map(|(a, b)| (a.into(), b.into()))
    .into()
}

fn base() -> Vec<OsString> {
    [
        "--unshare-user",
        "--disable-userns",
        "--cap-drop",
        "ALL",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-net",
        "--unshare-pid",
        "--die-with-parent",
        "--new-session",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind-try",
        "/lib",
        "/lib",
        "--ro-bind-try",
        "/lib64",
        "/lib64",
        "--ro-bind-try",
        "/bin",
        "/bin",
        "--ro-bind-try",
        "/etc/ld.so.cache",
        "/etc/ld.so.cache",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/home",
        "--chdir",
        "/tmp",
    ]
    .map(OsString::from)
    .into()
}

fn request<'a>(
    executable: &'a Path,
    arguments: &'a [OsString],
    environment: &'a [(OsString, OsString)],
) -> Request<'a> {
    Request {
        executable,
        arguments,
        directory: Path::new("/"),
        environment,
        timeout: Duration::from_secs(10),
        output_limit: 1024 * 1024,
    }
}

struct Endpoints {
    tcp4: TcpListener,
    tcp6: TcpListener,
    udp: UdpSocket,
    nonce: String,
}
impl Endpoints {
    fn new() -> Result<Self> {
        let tcp4 = TcpListener::bind("127.0.0.1:0").map_err(|_| unavailable())?;
        let tcp6 = TcpListener::bind("[::1]:0").map_err(|_| unavailable())?;
        let udp = UdpSocket::bind("127.0.0.1:0").map_err(|_| unavailable())?;
        tcp4.set_nonblocking(true).map_err(|_| unavailable())?;
        tcp6.set_nonblocking(true).map_err(|_| unavailable())?;
        udp.set_nonblocking(true).map_err(|_| unavailable())?;
        Ok(Self {
            tcp4,
            tcp6,
            udp,
            nonce: ulid::Ulid::generate().to_string(),
        })
    }
    fn arguments(&self) -> Result<Vec<OsString>> {
        Ok(vec![
            probe::FLAG.into(),
            self.tcp4
                .local_addr()
                .map_err(|_| unavailable())?
                .port()
                .to_string()
                .into(),
            self.tcp6
                .local_addr()
                .map_err(|_| unavailable())?
                .port()
                .to_string()
                .into(),
            self.udp
                .local_addr()
                .map_err(|_| unavailable())?
                .port()
                .to_string()
                .into(),
            self.nonce.clone().into(),
        ])
    }
    fn received(&self) -> Result<[bool; 3]> {
        let mut found = [false; 3];
        for (index, listener) in [&self.tcp4, &self.tcp6].into_iter().enumerate() {
            match listener.accept() {
                Ok((mut socket, _)) => {
                    socket
                        .set_read_timeout(Some(Duration::from_millis(500)))
                        .map_err(|_| unavailable())?;
                    let mut bytes = Vec::new();
                    Read::by_ref(&mut socket)
                        .take(64)
                        .read_to_end(&mut bytes)
                        .map_err(|_| unavailable())?;
                    if bytes != self.nonce.as_bytes() {
                        return Err(unavailable());
                    }
                    found[index] = true;
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => (),
                Err(_) => return Err(unavailable()),
            }
        }
        let mut bytes = [0u8; 64];
        match self.udp.recv_from(&mut bytes) {
            Ok((size, _)) => {
                if bytes[..size] != *self.nonce.as_bytes() {
                    return Err(unavailable());
                }
                found[2] = true;
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => (),
            Err(_) => return Err(unavailable()),
        }
        Ok(found)
    }
}

impl Launcher {
    pub(super) fn observe() -> Result<Self> {
        let image = File::open("/usr/bin/bwrap").map_err(|_| unavailable())?;
        let launcher = Self {
            digest: identity(&image)?,
            // The child inherits this descriptor until exec closes CLOEXEC.
            // Path replacement cannot substitute the measured launcher inode.
            executable: format!("/proc/self/fd/{}", image.as_raw_fd()).into(),
            image,
        };
        let endpoints = Endpoints::new()?;
        let environment = environment();
        let arguments = endpoints.arguments()?;
        let output = process::run(request(
            Path::new("/proc/self/exe"),
            &arguments,
            &environment,
        ))?;
        if !output.status.success()
            || wire::parse(&output.stdout)?["sent"] != json!([true, true, true])
            || endpoints.received()? != [true, true, true]
        {
            return Err(unavailable());
        }
        let mut isolated = base();
        isolated.extend([
            "--perms".into(),
            "0500".into(),
            "--ro-bind-data".into(),
            "0".into(),
            "/run/probe".into(),
            "--".into(),
            "/run/probe".into(),
        ]);
        isolated.extend(arguments);
        launcher.revalidate()?;
        // Hold this running image, not a path that an updater can replace.
        // The new user namespace cannot follow another process's /proc/exe.
        let image = File::open("/proc/self/exe").map_err(|_| unavailable())?;
        if image.metadata().map_err(|_| unavailable())?.len() > 512 * 1024 * 1024 {
            return Err(unavailable());
        }
        let output = process::with_input(
            request(&launcher.executable, &isolated, &environment),
            image,
        )?;
        if !output.status.success() {
            return Err(unavailable());
        }
        let report = wire::parse(&output.stdout)?;
        if report["sent"].as_array().is_none_or(|values| {
            values.len() != 3 || values[0] != false || values[1] != false || !values[2].is_boolean()
        }) || endpoints.received()? != [false, false, false]
        {
            return Err(unavailable());
        }
        Ok(launcher)
    }
    fn revalidate(&self) -> Result<()> {
        if identity(&self.image)? != self.digest {
            return Err(unavailable());
        }
        Ok(())
    }
    pub(super) fn report(&self) -> Value {
        json!({"enforcement":"enforced","launcher":"bubblewrap","launcher_digest":self.digest,"positive_control":["ipv4_tcp","ipv6_tcp","ipv4_udp"],"isolated":"denied","filesystem":"declared_runtime_only"})
    }
    pub(super) fn inspect(&self, bytes: &[u8]) -> Result<Vec<u8>> {
        let mut input = File::from(
            rustix::fs::memfd_create(
                "ai-stp-provider",
                rustix::fs::MemfdFlags::CLOEXEC | rustix::fs::MemfdFlags::ALLOW_SEALING,
            )
            .map_err(|_| unavailable())?,
        );
        input
            .write_all(bytes)
            .and_then(|_| input.rewind())
            .map_err(|_| unavailable())?;
        rustix::fs::fcntl_add_seals(
            &input,
            rustix::fs::SealFlags::SEAL
                | rustix::fs::SealFlags::SHRINK
                | rustix::fs::SealFlags::GROW
                | rustix::fs::SealFlags::WRITE,
        )
        .map_err(|_| unavailable())?;
        let mut arguments = base();
        arguments.extend(
            [
                "--perms",
                "0500",
                "--ro-bind-data",
                "0",
                "/run/provider",
                "--",
                "/run/provider",
                "provider-info",
            ]
            .map(OsString::from),
        );
        self.revalidate()?;
        let output =
            process::with_input(request(&self.executable, &arguments, &environment()), input)?;
        if !output.status.success() {
            return Err(unavailable());
        }
        Ok(output.stdout)
    }
}
