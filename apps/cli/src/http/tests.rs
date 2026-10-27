//! A real timed response body while another thread creates child exits.

use std::{
    error::Error,
    io::{self, Read, Write},
    net::TcpListener,
    process::{Command, Stdio},
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};

#[test]
fn timed_post_response_survives_concurrent_child_exits_without_resending()
-> Result<(), Box<dyn Error>> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let address = listener.local_addr()?;
    listener.set_nonblocking(true)?;
    let (started, request_arrived) = mpsc::channel();
    let (headers_ready, header_exits) = mpsc::channel();
    let (finished, body_exits) = mpsc::channel();
    let server = thread::spawn(move || -> io::Result<()> {
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut socket = loop {
            match listener.accept() {
                Ok((socket, _)) => break socket,
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    if Instant::now() >= deadline {
                        return Err(io::Error::other("HTTP client did not connect"));
                    }
                    thread::sleep(Duration::from_millis(5));
                }
                Err(error) => return Err(error),
            }
        };
        // There is exactly one connection: another HTTP attempt cannot succeed.
        drop(listener);
        socket.set_nonblocking(false)?;
        socket.set_read_timeout(Some(Duration::from_secs(5)))?;
        socket.set_write_timeout(Some(Duration::from_secs(5)))?;
        let mut headers = Vec::new();
        while !headers.ends_with(b"\r\n\r\n") && headers.len() < 4096 {
            let mut byte = [0];
            socket.read_exact(&mut byte)?;
            headers.push(byte[0]);
        }
        let headers = String::from_utf8(headers).map_err(io::Error::other)?;
        assert!(headers.starts_with("POST /original HTTP/1.1\r\n"));
        assert!(headers.ends_with("\r\n\r\n"));
        let mut body = [0; 4];
        socket.read_exact(&mut body)?;
        assert_eq!(&body, b"once");
        started.send(()).map_err(io::Error::other)?;
        header_exits
            .recv_timeout(Duration::from_secs(5))
            .map_err(io::Error::other)?;
        socket.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n")?;
        body_exits
            .recv_timeout(Duration::from_secs(5))
            .map_err(io::Error::other)?;
        socket.write_all(b"ok")
    });
    let children = thread::spawn(move || -> io::Result<usize> {
        request_arrived
            .recv_timeout(Duration::from_secs(5))
            .map_err(io::Error::other)?;
        // Stall both response phases while actual children exit. Linux timed
        // reads can receive SIGCHLD from another thread's spawn.
        thread::sleep(Duration::from_millis(25));
        for index in 0..64 {
            if !Command::new("/usr/bin/true")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()?
                .success()
            {
                return Err(io::Error::other("controlled child failed"));
            }
            if index == 31 {
                headers_ready.send(()).map_err(io::Error::other)?;
                thread::sleep(Duration::from_millis(25));
            }
        }
        finished.send(()).map_err(io::Error::other)?;
        Ok(64)
    });
    let agent = super::anonymous_agent();
    let body = agent
        .post(format!("http://{address}/original"))
        .send(b"once")
        .and_then(|mut response| {
            assert_eq!(response.status(), 200);
            response.body_mut().with_config().limit(3).read_to_vec()
        });
    let exited = children.join().map_err(|_| "child-exit fixture panicked")?;
    let served = server.join().map_err(|_| "HTTP fixture panicked")?;
    // Preserve the client error if an interrupted body read closed the socket.
    assert_eq!(body?, b"ok");
    assert_eq!(exited?, 64);
    served?;
    Ok(())
}
