//! A single bounded request, exact descriptor capabilities and bounded raw output.

use super::unavailable;
use crate::error::Result;
use rustix::net::{
    self, RecvAncillaryBuffer, RecvAncillaryMessage, RecvFlags, ReturnFlags, SendAncillaryBuffer,
    SendAncillaryMessage, SendFlags,
};
use std::{
    io::{IoSlice, IoSliceMut, Read, Write},
    mem::MaybeUninit,
    os::{
        fd::{BorrowedFd, OwnedFd},
        unix::{net::UnixStream, process::ExitStatusExt},
    },
    process::{ExitStatus, Output},
};

pub(super) const MAX_FILES: usize = 18;

pub(super) fn send(channel: &UnixStream, files: &[BorrowedFd<'_>]) -> Result<()> {
    if !(2..=MAX_FILES).contains(&files.len()) {
        return Err(unavailable());
    }
    let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(MAX_FILES))];
    let mut control = SendAncillaryBuffer::new(&mut space);
    if !control.push(SendAncillaryMessage::ScmRights(files))
        || net::sendmsg(
            channel,
            &[IoSlice::new(b"S")],
            &mut control,
            SendFlags::NOSIGNAL,
        )
        .map_err(|_| unavailable())?
            != 1
    {
        return Err(unavailable());
    }
    Ok(())
}

pub(super) fn receive(channel: &UnixStream) -> Result<Vec<OwnedFd>> {
    let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(MAX_FILES))];
    let mut control = RecvAncillaryBuffer::new(&mut space);
    let mut marker = [0];
    let received = net::recvmsg(
        channel,
        &mut [IoSliceMut::new(&mut marker)],
        &mut control,
        RecvFlags::CMSG_CLOEXEC,
    )
    .map_err(|_| unavailable())?;
    let mut files = Vec::new();
    for message in control.drain() {
        match message {
            RecvAncillaryMessage::ScmRights(held) => files.extend(held),
            _ => return Err(unavailable()),
        }
    }
    if received.bytes != 1
        || marker != *b"S"
        || received
            .flags
            .intersects(ReturnFlags::CTRUNC | ReturnFlags::TRUNC)
        || !(2..=MAX_FILES).contains(&files.len())
    {
        return Err(unavailable());
    }
    Ok(files)
}

pub(super) fn write_output(channel: &mut UnixStream, output: &Output) -> Result<()> {
    channel
        .write_all(&output.status.into_raw().to_le_bytes())
        .and_then(|_| channel.write_all(&(output.stdout.len() as u32).to_le_bytes()))
        .and_then(|_| channel.write_all(&(output.stderr.len() as u32).to_le_bytes()))
        .and_then(|_| channel.write_all(&output.stdout))
        .and_then(|_| channel.write_all(&output.stderr))
        .map_err(|_| unavailable())
}

pub(super) fn read_output(channel: &mut UnixStream, limit: usize) -> Result<Output> {
    let mut word = [0; 4];
    channel.read_exact(&mut word).map_err(|_| unavailable())?;
    let status = ExitStatus::from_raw(i32::from_le_bytes(word));
    channel.read_exact(&mut word).map_err(|_| unavailable())?;
    let stdout = u32::from_le_bytes(word) as usize;
    channel.read_exact(&mut word).map_err(|_| unavailable())?;
    let stderr = u32::from_le_bytes(word) as usize;
    if stdout > limit || stderr > limit {
        return Err(unavailable());
    }
    let mut output = Output {
        status,
        stdout: vec![0; stdout],
        stderr: vec![0; stderr],
    };
    channel
        .read_exact(&mut output.stdout)
        .and_then(|_| channel.read_exact(&mut output.stderr))
        .map_err(|_| unavailable())?;
    let mut extra = [0];
    if channel.read(&mut extra).map_err(|_| unavailable())? != 0 {
        return Err(unavailable());
    }
    Ok(output)
}
