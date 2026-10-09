//! One-shot child processes with explicit authority and bounded capture.

use std::{
    ffi::OsString,
    io::Read,
    path::Path,
    process::{Command, Output, Stdio},
    sync::mpsc::{self, Receiver},
    thread,
    time::{Duration, Instant},
};

use process_wrap::std::{ChildWrapper, CommandWrap};

use crate::error::{ErrorKind, Failure, Result};

pub struct Request<'a> {
    pub executable: &'a Path,
    pub arguments: &'a [OsString],
    pub directory: &'a Path,
    pub environment: &'a [(OsString, OsString)],
    pub timeout: Duration,
    pub output_limit: usize,
}

fn unavailable(message: &'static str) -> Failure {
    Failure::new(ErrorKind::Unavailable, message)
}

fn capture(reader: impl Read + Send + 'static, limit: usize) -> Result<Receiver<Result<Vec<u8>>>> {
    let (sender, receiver) = mpsc::sync_channel(1);
    thread::Builder::new()
        .name("ai-stp-process-output".into())
        .spawn(move || {
            let mut bytes = Vec::new();
            let result = reader.take(limit as u64 + 1).read_to_end(&mut bytes);
            let result = if result.is_err() {
                Err(unavailable("child output could not be read"))
            } else if bytes.len() > limit {
                Err(Failure::precondition(
                    "child output exceeded its byte limit",
                ))
            } else {
                Ok(bytes)
            };
            let _ = sender.send(result);
        })
        .map_err(|_| unavailable("child output reader could not be started"))?;
    Ok(receiver)
}

struct Child {
    process: Box<dyn ChildWrapper>,
    stopped: bool,
}

impl Child {
    fn stop(&mut self) {
        if !self.stopped {
            let _ = self.process.start_kill();
            self.stopped = true;
        }
    }
}

impl Drop for Child {
    fn drop(&mut self) {
        // Includes surviving descendants after a successful leader exit. This
        // is process lifecycle control, not a sandbox against setsid/escape.
        self.stop();
        let until = Instant::now() + Duration::from_secs(2);
        while matches!(self.process.try_wait(), Ok(None)) && Instant::now() < until {
            thread::sleep(Duration::from_millis(5));
        }
    }
}

/// The caller selects an absolute executable and the complete child environment.
/// No shell, inherited stdin or diagnostic output enters the machine envelope.
pub fn run(request: Request<'_>) -> Result<Output> {
    execute(request, Stdio::null())
}

/// Explicit anonymous input for the Linux provider boundary; never inherited stdin.
#[cfg(target_os = "linux")]
pub(crate) fn with_input(request: Request<'_>, input: std::fs::File) -> Result<Output> {
    execute(request, Stdio::from(input))
}

fn execute(request: Request<'_>, input: Stdio) -> Result<Output> {
    if !request.executable.is_absolute()
        || !request.directory.is_absolute()
        || request.timeout.is_zero()
        || request.timeout > Duration::from_secs(300)
        || request.output_limit == 0
        || request.output_limit > 16 * 1024 * 1024
    {
        return Err(Failure::input("child execution bounds are invalid"));
    }
    #[cfg(windows)]
    if !request
        .executable
        .extension()
        .and_then(|value| value.to_str())
        .is_some_and(|value| value.eq_ignore_ascii_case("exe"))
    {
        return Err(Failure::input(
            "Windows children must be native executables",
        ));
    }
    let mut command = Command::new(request.executable);
    command
        .args(request.arguments)
        .current_dir(request.directory)
        .env_clear()
        .envs(request.environment.iter().cloned())
        .stdin(input)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut command = CommandWrap::from(command);
    #[cfg(unix)]
    command.wrap(process_wrap::std::ProcessGroup::leader());
    #[cfg(windows)]
    command.wrap(process_wrap::std::JobObject);
    let started = Instant::now();
    let mut child = Child {
        process: command
            .spawn()
            .map_err(|_| unavailable("child process could not be started"))?,
        stopped: false,
    };
    let stdout = capture(
        child
            .process
            .stdout()
            .take()
            .ok_or_else(|| unavailable("child stdout is absent"))?,
        request.output_limit,
    )?;
    let stderr = capture(
        child
            .process
            .stderr()
            .take()
            .ok_or_else(|| unavailable("child stderr is absent"))?,
        request.output_limit,
    )?;
    let mut outputs: [Option<Vec<u8>>; 2] = [None, None];
    let mut status = None;
    loop {
        for (slot, receiver) in outputs.iter_mut().zip([&stdout, &stderr]) {
            if slot.is_none() {
                match receiver.try_recv() {
                    Ok(result) => *slot = Some(result?),
                    Err(mpsc::TryRecvError::Empty) => {}
                    Err(mpsc::TryRecvError::Disconnected) => {
                        return Err(unavailable("child output reader stopped unexpectedly"));
                    }
                }
            }
        }
        if status.is_none() {
            status = child
                .process
                .try_wait()
                .map_err(|_| unavailable("child status could not be read"))?;
            if status.is_some() {
                // A descendant may retain pipes after its parent exits.
                child.stop();
            }
        }
        if let Some(status) = status
            && outputs.iter().all(Option::is_some)
        {
            let [stdout, stderr] = outputs;
            return Ok(Output {
                status,
                stdout: stdout.unwrap_or_default(),
                stderr: stderr.unwrap_or_default(),
            });
        }
        if started.elapsed() >= request.timeout {
            return Err(unavailable("child execution exceeded its deadline"));
        }
        thread::sleep(Duration::from_millis(5));
    }
}
