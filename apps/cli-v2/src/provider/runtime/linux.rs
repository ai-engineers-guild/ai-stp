//! Minimal Linux filesystem and measured IPv4/IPv6/UDP network separation.

use super::{
    execution::Installation,
    prefix::{Prefix, View},
    probe,
    target::Target,
    unavailable,
};
use crate::{
    digest,
    error::Result,
    process::{self, Request},
    projection::Scope,
    provider::{plan, software},
    wire,
};
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    fs::File,
    io::{Read, Seek, Write},
    net::{TcpListener, UdpSocket},
    os::{
        fd::{AsRawFd, OwnedFd},
        unix::fs::MetadataExt,
    },
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

pub(super) fn sealed(bytes: &[u8]) -> Result<File> {
    let original = rustix::fs::memfd_create(
        "ai-stp-provider-input",
        rustix::fs::MemfdFlags::CLOEXEC | rustix::fs::MemfdFlags::ALLOW_SEALING,
    )
    .map_err(|_| unavailable())?;
    let mut file =
        File::from(rustix::io::fcntl_dupfd_cloexec(&original, 3).map_err(|_| unavailable())?);
    drop(original);
    file.write_all(bytes)
        .and_then(|_| file.rewind())
        .map_err(|_| unavailable())?;
    rustix::fs::fcntl_add_seals(
        &file,
        rustix::fs::SealFlags::SEAL
            | rustix::fs::SealFlags::SHRINK
            | rustix::fs::SealFlags::GROW
            | rustix::fs::SealFlags::WRITE,
    )
    .map_err(|_| unavailable())?;
    Ok(file)
}

fn bundle_arguments(request: &plan::Request) -> Vec<OsString> {
    vec![
        "--bundle".into(),
        "/run/bundle".into(),
        "--bundle-format".into(),
        request.bundle.bundle_format.clone().into(),
        "--bundle-digest".into(),
        request.bundle.bundle_digest.clone().into(),
        "--artifact-digest".into(),
        request.bundle.artifact_digest.clone().into(),
        "--bundle-size".into(),
        request.bundle.bundle_size.to_string().into(),
    ]
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
            &launcher.image,
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
        self.invoke(bytes, &["provider-info".into()], &[], None, None, None)
    }
    pub(super) fn install(
        &self,
        bytes: &[u8],
        target: &Target,
        installation: &Installation<'_>,
    ) -> Result<Vec<u8>> {
        self.invoke(
            bytes,
            &installation.command(bytes, target)?,
            &[target],
            None,
            Some((installation.prefix, View::Observed)),
            Some(installation),
        )
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
        self.invoke(bytes, &arguments, &[target], None, None, None)
    }
    pub(super) fn validate(
        &self,
        bytes: &[u8],
        target: &Target,
        request: &plan::Request,
        bundle: &[u8],
    ) -> Result<Vec<u8>> {
        // v3 requires the target argument even though validation never reads it.
        let mut arguments = vec![
            "validate-bundle".into(),
            "--json".into(),
            "--target".into(),
            target.path().as_os_str().into(),
        ];
        arguments.extend(bundle_arguments(request));
        self.invoke(bytes, &arguments, &[], Some(bundle), None, None)
    }
    pub(super) fn plan(
        &self,
        bytes: &[u8],
        target: &Target,
        scope: Scope,
        request: &plan::Request,
        bundle: &[u8],
    ) -> Result<Vec<u8>> {
        let mut arguments = vec![
            "plan-operation".into(),
            "--json".into(),
            "--target".into(),
            target.path().as_os_str().into(),
            "--operation".into(),
            request.operation.clone().into(),
            "--operation-id".into(),
            request.operation_id.clone().into(),
            "--expires-at".into(),
            request.expires_at.clone().into(),
            "--provider-release-digest".into(),
            digest::sha256(bytes).into(),
        ];
        if scope != Scope::Global {
            arguments.extend(["--target-scope".into(), scope.as_str().into()]);
        }
        arguments.extend(bundle_arguments(request));
        self.invoke(bytes, &arguments, &[target], Some(bundle), None, None)
    }
    pub(super) fn software_plan(
        &self,
        bytes: &[u8],
        target: &Target,
        prefix: &Prefix,
        scope: Scope,
        request: &software::Request,
        view: View,
    ) -> Result<Vec<u8>> {
        if view == View::EmptyStage
            && (prefix.missing().is_none() || request.operation != "software_install")
        {
            return Err(unavailable());
        }
        let mut arguments = vec![
            "plan-operation".into(),
            "--json".into(),
            "--target".into(),
            target.path().as_os_str().into(),
            "--prefix".into(),
            prefix.path().as_os_str().into(),
            "--operation".into(),
            request.operation.clone().into(),
            "--operation-id".into(),
            request.operation_id.clone().into(),
            "--expires-at".into(),
            request.expires_at.clone().into(),
            "--provider-release-digest".into(),
            digest::sha256(bytes).into(),
        ];
        if let Some(version) = &request.software_version {
            arguments.extend(["--software-version".into(), version.into()]);
        }
        if scope != Scope::Global {
            arguments.extend(["--target-scope".into(), scope.as_str().into()]);
        }
        prefix.revalidate()?;
        let targets: Vec<_> = std::iter::once(target).chain(prefix.mounted()).collect();
        let output = self.invoke(
            bytes,
            &arguments,
            &targets,
            None,
            prefix.missing().map(|path| (path, view)),
            None,
        )?;
        prefix.revalidate()?;
        Ok(output)
    }
    fn invoke(
        &self,
        bytes: &[u8],
        command: &[OsString],
        targets: &[&Target],
        bundle: Option<&[u8]>,
        synthetic_prefix: Option<(&Path, View)>,
        installation: Option<&Installation<'_>>,
    ) -> Result<Vec<u8>> {
        let input = sealed(bytes)?;
        let mut arguments = base();
        let mut handles = Vec::new();
        if targets.len() > 2 {
            return Err(unavailable());
        }
        let missing_parent = synthetic_prefix
            .map(|(p, _)| p.parent().ok_or_else(unavailable))
            .transpose()?;
        if let Some(parent) = missing_parent {
            // A fresh namespace represents the requested prefix view. The host
            // parent stays held and is never mounted or passed to the child.
            arguments.extend(["--tmpfs".into(), parent.as_os_str().into()]);
        }
        if let Some((prefix, View::EmptyStage)) = synthetic_prefix {
            // The component plans for an empty private stage. The native plan
            // separately binds the absent host destination and physical parent.
            arguments.extend([
                "--perms".into(),
                "0700".into(),
                "--dir".into(),
                prefix.as_os_str().into(),
            ]);
        }
        for target in targets {
            target.revalidate()?;
            let handle = target.handle()?;
            arguments.extend([
                "--ro-bind-fd".into(),
                handle.as_raw_fd().to_string().into(),
                target.path().as_os_str().into(),
            ]);
            handles.push((arguments.len() - 2, handle));
        }
        if let Some(installation) = installation {
            installation.mount(&mut arguments, &mut handles)?;
        }
        if let Some(parent) = missing_parent {
            arguments.extend(["--remount-ro".into(), parent.as_os_str().into()]);
        }
        if !targets.is_empty() {
            let source = File::open("/proc/self/exe").map_err(|_| unavailable())?;
            let image =
                File::from(rustix::io::fcntl_dupfd_cloexec(&source, 3).map_err(|_| unavailable())?);
            drop(source);
            if image.metadata().map_err(|_| unavailable())?.len() > 512 * 1024 * 1024 {
                return Err(unavailable());
            }
            arguments.extend([
                "--perms".into(),
                "0500".into(),
                "--ro-bind-data".into(),
                image.as_raw_fd().to_string().into(),
                "/run/target-entry".into(),
            ]);
            handles.push((arguments.len() - 2, OwnedFd::from(image)));
        }
        if let Some(bundle) = bundle {
            let handle = OwnedFd::from(sealed(bundle)?);
            arguments.extend([
                "--perms".into(),
                "0400".into(),
                "--ro-bind-data".into(),
                handle.as_raw_fd().to_string().into(),
                "/run/bundle".into(),
            ]);
            handles.push((arguments.len() - 2, handle));
        }
        arguments.extend(
            [
                "--perms",
                "0500",
                "--ro-bind-data",
                "0",
                "/run/provider",
                "--",
            ]
            .map(OsString::from),
        );
        if !targets.is_empty() {
            arguments.extend([
                "/run/target-entry".into(),
                super::entry::FLAG.into(),
                targets.len().to_string().into(),
            ]);
            for target in targets {
                let (device, inode) = target.identity()?;
                arguments.extend([
                    device.to_string().into(),
                    inode.to_string().into(),
                    target.path().as_os_str().into(),
                ]);
            }
        } else {
            arguments.push("/run/provider".into());
        }
        if let Some(installation) = installation {
            let (dev, ino) = installation.stage.identity()?;
            arguments.extend([
                super::entry::WRITABLE_PREFIX.into(),
                dev.to_string().into(),
                ino.to_string().into(),
                installation.prefix.as_os_str().into(),
            ]);
        } else if let Some((prefix, view)) = synthetic_prefix {
            arguments.extend([
                if view == View::EmptyStage {
                    super::entry::EMPTY_PREFIX
                } else {
                    super::entry::MISSING_PREFIX
                }
                .into(),
                prefix.as_os_str().into(),
            ]);
        }
        arguments.extend_from_slice(command);
        self.revalidate()?;
        let environment = environment();
        let mut request = request(&self.executable, &arguments, &environment);
        if installation.is_some() {
            request.timeout = Duration::from_secs(300);
        }
        let output = process::with_files(request, &self.image, input, handles)?;
        if !output.status.success() {
            return Err(crate::error::Failure::new(
                crate::error::ErrorKind::Unavailable,
                "the isolated provider command did not complete",
            )
            .with_details([
                ("exit_code".into(), output.status.code().into()),
                (
                    "command".into(),
                    command.first().and_then(|item| item.to_str()).into(),
                ),
            ]));
        }
        Ok(output.stdout)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::provider::Info;
    use std::{error::Error, fs, os::unix::fs::symlink};

    fn missing_prefix_keeps_its_parent_private() -> std::result::Result<(), Box<dyn Error>> {
        let root = tempfile::tempdir_in("/tmp")?;
        let parent = root.path().join("parent");
        let sibling = parent.join("sibling");
        fs::create_dir_all(&sibling)?;
        fs::write(sibling.join("private"), b"retained")?;
        let path = parent.join("programs");
        let prefix = Prefix::open(&path)?;
        assert!(prefix.mounted().is_none());
        prefix.disjoint(&Target::open(&sibling)?.directory()?)?;
        assert!(
            prefix
                .disjoint(&Target::open(&parent)?.directory()?)
                .is_err()
        );
        assert!(
            prefix
                .disjoint(&Target::open(root.path())?.directory()?)
                .is_err()
        );
        assert!(Prefix::open(&path.join("deeper")).is_err());
        symlink(&parent, root.path().join("alias"))?;
        assert!(Prefix::open(&root.path().join("alias/programs")).is_err());
        symlink(&sibling, &path)?;
        assert!(prefix.revalidate().is_err());
        assert!(Prefix::open(&path).is_err());
        fs::remove_file(&path)?;
        prefix.revalidate()?;
        fs::create_dir(&path)?;
        assert!(prefix.revalidate().is_err());
        assert!(Prefix::open(&path)?.mounted().is_some());
        fs::remove_dir(&path)?;
        fs::rename(&parent, root.path().join("moved"))?;
        fs::create_dir(&parent)?;
        assert!(prefix.revalidate().is_err());
        assert_eq!(
            fs::read(root.path().join("moved/sibling/private"))?,
            b"retained"
        );
        Ok(())
    }

    #[test]
    fn held_target_refuses_aliases_substitution_and_forged_status()
    -> std::result::Result<(), Box<dyn Error>> {
        missing_prefix_keeps_its_parent_private()?;
        let temporary = tempfile::tempdir_in("/tmp")?;
        let path = temporary.path().join("target");
        fs::create_dir(&path)?;
        fs::write(path.join("marker"), "exact\n")?;
        fs::write(temporary.path().join("private"), "outside\n")?;
        let target = Target::open(&path)?;
        target.revalidate()?;
        // A same-inode writable directory is not a read-only provider mount.
        assert!(target.verify_mount(target.identity()?).is_err());
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

        Ok(())
    }
}
