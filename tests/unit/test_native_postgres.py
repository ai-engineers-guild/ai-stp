"""Native service commands must complete while their owned descendants remain live."""

from __future__ import annotations

import hashlib
import socket
import sys
from pathlib import Path

import pytest
from tests.support.native_postgres import run_command

CHILD = """
import socket, sys
with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=5) as lease:
    lease.settimeout(10)
    lease.sendall(b"R")
    if lease.recv(1) != b"K":
        raise RuntimeError("owned test lease was not acknowledged")
    lease.sendall(b"D")
"""

PARENT = """
import subprocess, sys
child = subprocess.Popen(
    [sys.executable, "-c", sys.argv[1], sys.argv[2]],
    stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr,
)
print(child.pid, flush=True)
"""


@pytest.mark.parametrize("input_data", [None, b"owned-private-input\n"])
def test_command_does_not_wait_for_a_live_descendants_inherited_output(
    input_data: bytes | None,
) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(15)
        output = run_command(
            Path(sys.executable),
            "-c",
            PARENT,
            CHILD,
            str(listener.getsockname()[1]),
            input_data=input_data,
        )
        assert output.strip().isdecimal()
        peer, _ = listener.accept()
        with peer:
            peer.settimeout(5)
            assert peer.recv(1) == b"R"
            peer.sendall(b"K")
            assert peer.recv(1) == b"D"
            assert peer.recv(1) == b""


def test_private_command_input_uses_a_non_echoing_anonymous_pipe() -> None:
    payload = b"owned-disposable-input\nowned-disposable-input\n"
    observed = run_command(
        Path(sys.executable),
        "-c",
        "import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())",
        input_data=payload,
    )
    assert observed.strip() == hashlib.sha256(payload).hexdigest()


def test_private_command_failure_does_not_expose_its_input() -> None:
    payload = b"owned-disposable-input\n"
    with pytest.raises(AssertionError) as failure:
        run_command(
            Path(sys.executable),
            "-c",
            "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); sys.exit(1)",
            input_data=payload,
        )
    assert str(failure.value) == "PostgreSQL command echoed private input"
    assert payload.decode().strip() not in str(failure.value)
