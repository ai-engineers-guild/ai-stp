//! Provider processes belong to a transient service before any child is created.

mod service;
#[cfg(test)]
mod tests;
mod transport;

use std::{
    collections::BTreeSet,
    ffi::{OsStr, OsString},
    fs::File,
    io::{Read, Write},
    os::{
        fd::{AsFd, AsRawFd, OwnedFd},
        unix::{
            ffi::{OsStrExt, OsStringExt},
            fs::MetadataExt,
            net::UnixStream,
        },
    },
    path::{Path, PathBuf},
    process::{Child, Command as ProcessCommand, Output, Stdio},
    sync::OnceLock,
    thread,
    time::Duration,
};

use command_fds::CommandFdExt;
use serde::{Deserialize, Serialize};

use super::Request;
use crate::error::{Failure, Result};

/// Internal descriptor-only worker entry; not a public command or authority input.
pub const FLAG: &str = "--ai-stp-provider-worker";
pub const SUPERVISOR_FLAG: &str = "--ai-stp-provider-supervisor";
const MAX_IMAGE: u64 = 512 * 1024 * 1024;
const MAX_REQUEST: usize = 64 * 1024;

fn unavailable() -> Failure {
    super::unavailable("the bounded Linux provider service is unavailable")
}

fn seal_image() -> Result<File> {
    let mut source = File::open("/proc/self/exe")
        .map_err(|_| unavailable())?
        .take(MAX_IMAGE + 1);
    let mut file = File::from(
        rustix::fs::memfd_create(
            "ai-stp-provider-worker",
            rustix::fs::MemfdFlags::CLOEXEC | rustix::fs::MemfdFlags::ALLOW_SEALING,
        )
        .map_err(|_| unavailable())?,
    );
    let size = std::io::copy(&mut source, &mut file).map_err(|_| unavailable())?;
    if size == 0 || size > MAX_IMAGE {
        return Err(unavailable());
    }
    rustix::fs::fcntl_add_seals(
        &file,
        rustix::fs::SealFlags::SEAL
            | rustix::fs::SealFlags::WRITE
            | rustix::fs::SealFlags::SHRINK
            | rustix::fs::SealFlags::GROW,
    )
    .map_err(|_| unavailable())?;
    Ok(file)
}

fn image() -> Result<&'static File> {
    static IMAGE: OnceLock<Result<File>> = OnceLock::new();
    IMAGE
        .get_or_init(seal_image)
        .as_ref()
        .map_err(|_| unavailable())
}

struct Worker(Child);

impl Drop for Worker {
    fn drop(&mut self) {
        // The owned child cannot be PID-reused before wait. Before attachment
        // it can only wait at the gate; afterwards the service owns descendants.
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Command {
    arguments: Vec<Vec<u8>>,
    environment: Vec<(Vec<u8>, Vec<u8>)>,
    directory: Vec<u8>,
    timeout_millis: u64,
    output_limit: usize,
    /// Only these argument slots name descriptors. Other numeric strings are literal.
    descriptor_arguments: Vec<usize>,
}

impl Command {
    fn validate(&self) -> Result<()> {
        let positions: BTreeSet<_> = self.descriptor_arguments.iter().collect();
        if self.arguments.len() > 256
            || self.environment.len() > 64
            || self.descriptor_arguments.len() > transport::MAX_FILES - 2
            || positions.len() != self.descriptor_arguments.len()
            || positions.iter().any(|&&i| i >= self.arguments.len())
            || self.timeout_millis == 0
            || self.timeout_millis > 300_000
            || self.output_limit == 0
            || self.output_limit > 16 * 1024 * 1024
            || !Path::new(OsStr::from_bytes(&self.directory)).is_absolute()
            || self
                .arguments
                .iter()
                .chain(std::iter::once(&self.directory))
                .chain(
                    self.environment
                        .iter()
                        .flat_map(|(name, value)| [name, value]),
                )
                .any(|value| value.contains(&0))
            || self
                .environment
                .iter()
                .any(|(name, _)| name.is_empty() || name.contains(&b'='))
        {
            return Err(unavailable());
        }
        Ok(())
    }
}

pub(super) fn invoke(
    request: Request<'_>,
    executable: &File,
    input: File,
    descriptors: Vec<(usize, OwnedFd)>,
) -> Result<Output> {
    super::validate(&request)?;
    let command = Command {
        arguments: request
            .arguments
            .iter()
            .map(|a| a.as_bytes().to_vec())
            .collect(),
        environment: request
            .environment
            .iter()
            .map(|(k, v)| (k.as_bytes().to_vec(), v.as_bytes().to_vec()))
            .collect(),
        directory: request.directory.as_os_str().as_bytes().to_vec(),
        timeout_millis: request
            .timeout
            .as_millis()
            .try_into()
            .map_err(|_| unavailable())?,
        output_limit: request.output_limit,
        descriptor_arguments: descriptors.iter().map(|(index, _)| *index).collect(),
    };
    command.validate()?;
    let body = serde_json::to_vec(&command).map_err(|_| unavailable())?;
    if body.len() > MAX_REQUEST {
        return Err(unavailable());
    }
    let (mut channel, remote) = UnixStream::pair().map_err(|_| unavailable())?;
    channel
        .set_read_timeout(Some(request.timeout + Duration::from_secs(10)))
        .map_err(|_| unavailable())?;
    channel
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|_| unavailable())?;
    let image = image()?;
    let service = service::Service::start(image, request.timeout)?;
    // Preserve the caller's mount namespace, including private temporary
    // directories. The sealed worker cannot spawn until attached and verified.
    let worker = Worker(
        ProcessCommand::new("/proc/self/fd/0")
            .args([FLAG, service.name(), &std::process::id().to_string()])
            .env_clear()
            .current_dir("/")
            .stdin(Stdio::from(image.try_clone().map_err(|_| unavailable())?))
            .stdout(Stdio::from(OwnedFd::from(remote)))
            .stderr(Stdio::null())
            .spawn()
            .map_err(|_| unavailable())?,
    );
    service.attach(worker.0.id())?;
    channel.write_all(&[1]).map_err(|_| unavailable())?;
    // All capabilities remain held until sendmsg has transferred them. No path
    // in the manager's potentially different mount namespace names these inputs.
    let mut files = vec![executable.as_fd(), input.as_fd()];
    files.extend(descriptors.iter().map(|(_, fd)| fd.as_fd()));
    transport::send(&channel, &files)?;
    channel
        .write_all(&(body.len() as u32).to_le_bytes())
        .and_then(|_| channel.write_all(&body))
        .map_err(|_| unavailable())?;
    let output = transport::read_output(&mut channel, request.output_limit)?;
    // Closing the private lease also stops a worker interrupted while returning.
    drop(channel);
    drop(service);
    drop(worker);
    Ok(output)
}

fn membership(unit: &OsStr) -> Result<()> {
    let unit = unit.to_str().ok_or_else(unavailable)?;
    let id = unit
        .strip_prefix("ai-stp-provider-")
        .and_then(|s| s.strip_suffix(".service"))
        .ok_or_else(unavailable)?;
    ulid::Ulid::from_string(id).map_err(|_| unavailable())?;
    let mut group = String::new();
    File::open("/proc/self/cgroup")
        .map_err(|_| unavailable())?
        .take(4097)
        .read_to_string(&mut group)
        .map_err(|_| unavailable())?;
    if group.len() > 4096
        || !group
            .lines()
            .any(|line| line.starts_with("0::/") && line.ends_with(&format!("/{unit}")))
    {
        return Err(unavailable());
    }
    let required = rustix::fs::SealFlags::SEAL
        | rustix::fs::SealFlags::WRITE
        | rustix::fs::SealFlags::SHRINK
        | rustix::fs::SealFlags::GROW;
    if !rustix::fs::fcntl_get_seals(std::io::stdin())
        .map_err(|_| unavailable())?
        .contains(required)
    {
        return Err(unavailable());
    }
    Ok(())
}

fn local_executable(received: File) -> Result<File> {
    // AppArmor resolves an executable in its current mount namespace. A file
    // transferred from a private mount can otherwise lose its installed profile.
    // Reopen only the very same inode, then execute through that held descriptor.
    let path = std::fs::read_link(format!("/proc/self/fd/{}", received.as_raw_fd()))
        .map_err(|_| unavailable())?;
    let local = File::open(path).map_err(|_| unavailable())?;
    let before = received.metadata().map_err(|_| unavailable())?;
    let after = local.metadata().map_err(|_| unavailable())?;
    if !before.is_file() || before.dev() != after.dev() || before.ino() != after.ino() {
        return Err(unavailable());
    }
    Ok(local)
}

/// The service main owns a separate lease even if the execution worker freezes.
pub fn supervise(unit: &OsStr) -> Result<()> {
    membership(unit)?;
    let mut channel = UnixStream::from(
        std::io::stdout()
            .as_fd()
            .try_clone_to_owned()
            .map_err(|_| unavailable())?,
    );
    channel.write_all(&[1]).map_err(|_| unavailable())?;
    let mut byte = [0];
    // EOF, unexpected traffic and I/O failure all retire the service main;
    // systemd kills the complete group under the verified lifetime policy.
    let _ = channel.read(&mut byte);
    Ok(())
}

/// The caller-created worker waits for attachment before accepting any work.
pub fn worker(unit: &OsStr, parent: &OsStr) -> Result<()> {
    rustix::process::set_parent_process_death_signal(Some(rustix::process::Signal::KILL))
        .map_err(|_| unavailable())?;
    let expected = parent.to_str().and_then(|s| s.parse::<u32>().ok());
    if expected.is_none() || rustix::process::getppid().map(|p| p.as_raw_pid() as u32) != expected {
        return Err(unavailable());
    }
    let mut channel = UnixStream::from(
        std::io::stdout()
            .as_fd()
            .try_clone_to_owned()
            .map_err(|_| unavailable())?,
    );
    channel
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|_| unavailable())?;
    channel
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|_| unavailable())?;
    let mut gate = [0];
    channel.read_exact(&mut gate).map_err(|_| unavailable())?;
    if gate != [1] {
        return Err(unavailable());
    }
    membership(unit)?;
    let mut files = transport::receive(&channel)?.into_iter();
    let executable = local_executable(File::from(files.next().ok_or_else(unavailable)?))?;
    let input = File::from(files.next().ok_or_else(unavailable)?);
    let descriptors: Vec<_> = files.collect();
    let mut length = [0; 4];
    channel.read_exact(&mut length).map_err(|_| unavailable())?;
    let length = u32::from_le_bytes(length) as usize;
    if length == 0 || length > MAX_REQUEST {
        return Err(unavailable());
    }
    let mut body = vec![0; length];
    channel.read_exact(&mut body).map_err(|_| unavailable())?;
    let command: Command = serde_json::from_slice(&body).map_err(|_| unavailable())?;
    command.validate()?;
    if descriptors.len() != command.descriptor_arguments.len() {
        return Err(unavailable());
    }
    let mut arguments: Vec<_> = command
        .arguments
        .into_iter()
        .map(OsString::from_vec)
        .collect();
    for (position, descriptor) in command.descriptor_arguments.into_iter().zip(&descriptors) {
        arguments[position] = descriptor.as_raw_fd().to_string().into();
    }
    let environment: Vec<_> = command
        .environment
        .into_iter()
        .map(|(k, v)| (OsString::from_vec(k), OsString::from_vec(v)))
        .collect();
    let directory = PathBuf::from(OsString::from_vec(command.directory));
    let path = PathBuf::from(format!("/proc/self/fd/{}", executable.as_raw_fd()));
    channel.set_read_timeout(None).map_err(|_| unavailable())?;
    let mut lease = channel.try_clone().map_err(|_| unavailable())?;
    thread::Builder::new()
        .name("ai-stp-provider-lease".into())
        .spawn(move || {
            let mut byte = [0];
            let _ = lease.read(&mut byte);
            // Normal EOF, unexpected traffic and I/O failure all revoke the lease.
            // Exiting the service main lets systemd kill even stopped/setsid children.
            std::process::exit(70);
        })
        .map_err(|_| unavailable())?;
    let output = super::execute_command(
        Request {
            executable: &path,
            arguments: &arguments,
            directory: &directory,
            environment: &environment,
            timeout: Duration::from_millis(command.timeout_millis),
            output_limit: command.output_limit,
        },
        Stdio::from(input),
        |command| {
            command.preserved_fds(descriptors);
        },
    )?;
    transport::write_output(&mut channel, &output)
}
