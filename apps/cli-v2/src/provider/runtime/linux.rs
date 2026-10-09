//! Minimal Linux filesystem and measured IPv4/IPv6/UDP network separation.

use super::{probe, target::Target, unavailable};
use crate::{
    digest,
    error::Result,
    process::{self, Request},
    projection::Scope,
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
    fn system() -> Result<Self> {
        let source = File::open("/usr/bin/bwrap").map_err(|_| unavailable())?;
        let image =
            File::from(rustix::io::fcntl_dupfd_cloexec(&source, 3).map_err(|_| unavailable())?);
        Ok(Self {
            digest: identity(&image)?,
            // The child inherits this descriptor until exec closes CLOEXEC.
            // Path replacement cannot substitute the measured launcher inode.
            executable: format!("/proc/self/fd/{}", image.as_raw_fd()).into(),
            image,
        })
    }
    pub(super) fn observe() -> Result<Self> {
        let launcher = Self::system()?;
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
            return Err(unavailable().with_details([("stage".into(), "network_probe".into())]));
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
        self.invoke(bytes, &["provider-info".into()], None)
    }
    pub(super) fn status(&self, bytes: &[u8], target: &Target, scope: Scope) -> Result<Vec<u8>> {
        let mut arguments = vec![
            "status".into(),
            "--target".into(),
            target.path().as_os_str().into(),
            "--json".into(),
        ];
        if scope != Scope::Global {
            arguments.extend(["--target-scope".into(), scope.as_str().into()]);
        }
        self.invoke(bytes, &arguments, Some(target))
    }
    fn invoke(
        &self,
        bytes: &[u8],
        command: &[OsString],
        target: Option<&Target>,
    ) -> Result<Vec<u8>> {
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
        let mut handles = Vec::new();
        if let Some(target) = target {
            let handle = target.handle()?;
            arguments.extend([
                "--ro-bind-fd".into(),
                handle.as_raw_fd().to_string().into(),
                target.path().as_os_str().into(),
            ]);
            handles.push(handle);
        }
        arguments.extend(
            [
                "--perms",
                "0500",
                "--ro-bind-data",
                "0",
                "/run/provider",
                "--",
                "/run/provider",
            ]
            .map(OsString::from),
        );
        arguments.extend_from_slice(command);
        self.revalidate()?;
        let output = process::with_files(
            request(&self.executable, &arguments, &environment()),
            input,
            handles,
        )?;
        if !output.status.success() {
            return Err(crate::error::Failure::new(
                crate::error::ErrorKind::Unavailable,
                "the isolated provider command did not complete",
            )
            .with_details([("exit_code".into(), output.status.code().into())]));
        }
        Ok(output.stdout)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::provider::Info;
    use std::{error::Error, fs, os::unix::fs::symlink};

    #[test]
    fn held_target_refuses_aliases_substitution_and_forged_status()
    -> std::result::Result<(), Box<dyn Error>> {
        let temporary = tempfile::tempdir_in("/tmp")?;
        let path = temporary.path().join("target");
        fs::create_dir(&path)?;
        fs::write(path.join("marker"), "exact\n")?;
        fs::write(temporary.path().join("private"), "outside\n")?;
        let target = Target::open(&path)?;
        target.revalidate()?;
        symlink(&path, temporary.path().join("alias"))?;
        symlink(temporary.path(), temporary.path().join("parent-alias"))?;
        let nested = path.join("state");
        fs::create_dir(&nested)?;
        for rejected in [
            &path,
            &nested,
            temporary.path(),
            &temporary.path().join("alias"),
        ] {
            assert!(target.state_parent(rejected).is_err());
        }
        fs::remove_dir(&nested)?;
        let state = temporary.path().join("state");
        fs::create_dir(&state)?;
        let held_state = target.state_parent(&state)?;
        fs::rename(&state, temporary.path().join("held-state"))?;
        symlink(&path, &state)?;
        assert!(target.state_parent(&state).is_err());
        held_state.write("held-marker", b"state")?;
        assert_eq!(
            fs::read(temporary.path().join("held-state/held-marker"))?,
            b"state"
        );
        assert!(!path.join("held-marker").exists());
        for rejected in [
            temporary.path().join("alias"),
            temporary.path().join("parent-alias/target"),
            path.join("../target"),
            PathBuf::from("/"),
            PathBuf::from("/tmp"),
            PathBuf::from("/usr"),
            PathBuf::from("relative"),
        ] {
            assert!(Target::open(&rejected).is_err());
        }
        let providers: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/provider-declarations.json"
        ))?;
        let info = Info::parse(&serde_json::to_vec(&providers[1])?)?;
        let empty = digest::sha256(b"");
        let document = json!({"protocol_version":3,"provider_id":"codex-setup-system","harness_id":"codex","canonical_target":path,
            "state":"missing","target_digest":empty,"target_identity_digest":empty,"provider_state":{"present":false},"journal":null,"backups":[],"shadowed_by":[],"cleanup_state":"none"});
        target.response(&serde_json::to_vec(&document)?, &info)?;
        for (key, value) in [
            ("canonical_target", json!(temporary.path())),
            ("provider_id", json!("another-provider")),
            ("harness_id", json!("pi")),
            ("cleanup_state", json!("invented")),
            ("target_digest", json!("bad")),
            ("unknown", json!(true)),
        ] {
            let mut changed = document.clone();
            changed[key] = value;
            assert!(
                target
                    .response(&serde_json::to_vec(&changed)?, &info)
                    .is_err()
            );
        }
        assert!(
            target
                .response(b"{\"state\":\"missing\",\"state\":\"managed\"}", &info)
                .is_err()
        );
        let held = File::from(target.handle()?);
        let before = held.metadata()?;
        fs::rename(&path, temporary.path().join("moved"))?;
        fs::create_dir(&path)?;
        assert!(target.revalidate().is_err());
        assert!(
            target
                .response(&serde_json::to_vec(&document)?, &info)
                .is_err()
        );
        assert_eq!(held.metadata()?.ino(), before.ino());
        assert_ne!(fs::metadata(&path)?.ino(), before.ino());

        // Exercise the actual descriptor transfer and mount policy when supported.
        // This fixture is deliberately unsigned and never enters the public API.
        let target = Target::open(&temporary.path().join("moved"))?;
        if let Ok(launcher) = Launcher::system() {
            let control = launcher.invoke(
                b"#!/bin/sh\nprintf 'ready'\n",
                &["provider-info".into()],
                Some(&target),
            );
            if let Ok(control) = control {
                assert_eq!(control, b"ready");
                let script = br##"#!/bin/sh
test "$1" = status || exit 20
test "$HOME" = /home && test -z "$PATH" || exit 21
test ! -e "$3/private" && test ! -e /etc/passwd || exit 22
read -r value < "$2/marker"
test "$value" = exact || exit 23
for entry in /proc/self/fd/*; do
    test ! -d "$entry" || exit 24
done
if { printf changed > "$2/marker"; } 2>/dev/null; then exit 25; fi
if { printf created > "$2/new"; } 2>/dev/null; then exit 26; fi
printf '{"verified":true}\n'
"##;
                let output = launcher.invoke(
                    script,
                    &[
                        "status".into(),
                        target.path().as_os_str().into(),
                        temporary.path().as_os_str().into(),
                    ],
                    Some(&target),
                )?;
                assert_eq!(wire::parse(&output)?, json!({"verified":true}));
                assert_eq!(fs::read(target.path().join("marker"))?, b"exact\n");
                assert!(!target.path().join("new").exists());
            } else {
                eprintln!(
                    "Host isolation unavailable; no positive mount-containment evidence claimed"
                );
            }
        }
        Ok(())
    }
}
