use super::*;
use std::{error::Error, os::unix::process::ExitStatusExt, process::ExitStatus};

#[test]
fn descriptor_transport_preserves_identity_and_refuses_ambiguous_frames()
-> std::result::Result<(), Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    let path = root.path().join("cafe\u{301}-$UNCHANGED");
    std::fs::write(&path, "exact bytes\n")?;
    let source = File::open(&path)?;
    let directory = File::open(root.path())?;
    let (mut sender, mut receiver) = UnixStream::pair()?;
    transport::send(&sender, &[source.as_fd(), directory.as_fd()])?;
    let received = transport::receive(&receiver)?;
    let mut transferred = File::from(received[0].try_clone()?);
    let mut body = String::new();
    transferred.read_to_string(&mut body)?;
    assert_eq!(body, "exact bytes\n");
    assert_eq!(transferred.metadata()?.ino(), source.metadata()?.ino());
    assert_eq!(
        File::from(received[1].try_clone()?).metadata()?.ino(),
        directory.metadata()?.ino()
    );
    for fd in &received {
        assert!(rustix::io::fcntl_getfd(fd)?.contains(rustix::io::FdFlags::CLOEXEC));
    }
    let reopened = local_executable(source.try_clone()?)?;
    assert_eq!(reopened.metadata()?.ino(), source.metadata()?.ino());
    std::fs::rename(&path, root.path().join("held"))?;
    std::fs::write(&path, "substitute\n")?;
    // The held descriptor still names the original inode after a rename.
    assert_eq!(
        local_executable(source.try_clone()?)?.metadata()?.ino(),
        source.metadata()?.ino()
    );
    std::fs::remove_file(root.path().join("held"))?;
    assert!(local_executable(source).is_err());
    assert!(local_executable(directory).is_err());

    let output = Output {
        status: ExitStatus::from_raw(7 << 8),
        stdout: b"cafe\xcc\x81:$UNCHANGED\0".to_vec(),
        stderr: vec![0xff, 0, 0xfe],
    };
    transport::write_output(&mut sender, &output)?;
    sender.shutdown(std::net::Shutdown::Write)?;
    let returned = transport::read_output(&mut receiver, 128)?;
    assert_eq!(returned.status.code(), Some(7));
    assert_eq!(returned.stdout, output.stdout);
    assert_eq!(returned.stderr, output.stderr);

    // Truncation, oversized declarations and bytes after the response all refuse.
    for bytes in [
        vec![0, 0, 0],
        [0i32.to_le_bytes(), 129u32.to_le_bytes(), 0u32.to_le_bytes()].concat(),
        vec![0; 13],
    ] {
        let (mut sender, mut receiver) = UnixStream::pair()?;
        sender.write_all(&bytes)?;
        sender.shutdown(std::net::Shutdown::Write)?;
        assert!(transport::read_output(&mut receiver, 128).is_err());
    }
    let (mut sender, receiver) = UnixStream::pair()?;
    sender.write_all(b"S")?;
    assert!(transport::receive(&receiver).is_err());
    assert!(transport::send(&sender, &[]).is_err());

    let mut command = Command {
        arguments: vec![b"0".to_vec(), b"0".to_vec()],
        environment: vec![(b"HOME".to_vec(), b"/home".to_vec())],
        directory: b"/".to_vec(),
        timeout_millis: 1000,
        output_limit: 128,
        descriptor_arguments: vec![1],
    };
    command.validate()?;
    for positions in [vec![1, 1], vec![2], vec![usize::MAX]] {
        command.descriptor_arguments = positions;
        assert!(command.validate().is_err());
    }
    command.descriptor_arguments.clear();
    command.arguments[0].push(0);
    assert!(command.validate().is_err());
    Ok(())
}
