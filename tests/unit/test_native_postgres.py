"""Native service commands must complete while their owned descendants remain live."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

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


def test_command_does_not_wait_for_a_live_descendants_inherited_output() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(15)
        output = run_command(
            Path(sys.executable), "-c", PARENT, CHILD, str(listener.getsockname()[1])
        )
        assert output.strip().isdecimal()
        peer, _ = listener.accept()
        with peer:
            peer.settimeout(5)
            assert peer.recv(1) == b"R"
            peer.sendall(b"K")
            assert peer.recv(1) == b"D"
            assert peer.recv(1) == b""
