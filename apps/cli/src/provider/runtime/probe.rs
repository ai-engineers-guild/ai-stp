//! Private self-probe: loopback only, bounded payload and no filesystem authority.

use crate::error::{Failure, Result};
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    io::Write,
    net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr, TcpStream, UdpSocket},
    time::Duration,
};

pub const FLAG: &str = "--internal-provider-network-probe";

pub fn run(arguments: &[OsString]) -> Result<Value> {
    let invalid = || Failure::input("the private network probe arguments are invalid");
    if arguments.len() != 4 {
        return Err(invalid());
    }
    let mut ports = [0u16; 3];
    for (slot, value) in ports.iter_mut().zip(&arguments[..3]) {
        *slot = value
            .to_str()
            .filter(|s| s.len() <= 5)
            .and_then(|s| s.parse::<u16>().ok())
            .filter(|v| *v != 0)
            .ok_or_else(invalid)?;
    }
    let nonce = arguments[3]
        .to_str()
        .filter(|s| s.len() == 26 && s.bytes().all(|b| b.is_ascii_alphanumeric()))
        .ok_or_else(invalid)?;
    let mut sent = [false; 3];
    for (index, address) in [
        IpAddr::V4(Ipv4Addr::LOCALHOST),
        IpAddr::V6(Ipv6Addr::LOCALHOST),
    ]
    .into_iter()
    .enumerate()
    {
        if let Ok(mut socket) = TcpStream::connect_timeout(
            &SocketAddr::new(address, ports[index]),
            Duration::from_millis(500),
        ) {
            socket
                .set_write_timeout(Some(Duration::from_millis(500)))
                .map_err(|_| invalid())?;
            sent[index] = socket.write_all(nonce.as_bytes()).is_ok();
        }
    }
    let socket = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).map_err(|_| invalid())?;
    socket
        .set_write_timeout(Some(Duration::from_millis(500)))
        .map_err(|_| invalid())?;
    sent[2] = socket
        .send_to(nonce.as_bytes(), (Ipv4Addr::LOCALHOST, ports[2]))
        .is_ok();
    Ok(json!({"sent":sent}))
}
