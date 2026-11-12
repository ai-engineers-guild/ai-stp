"""Owned vendor pipe shutdown must reap processes even after stdin closes."""

from __future__ import annotations

import subprocess
import sys

from tests.support.native_pipe import Pipe


def test_closed_vendor_input_does_not_skip_owned_process_cleanup() -> None:
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            'import os,time; os.close(0); print("{}",flush=True); time.sleep(30)',
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    pipe = Pipe(process)
    try:
        assert pipe.messages.get(timeout=5) == b"{}\n"
        # Buffered bytes make close observe the vendor's already-closed input.
        pipe.input.write(b"pending")
        pipe.close()
        assert process.poll() is not None
        assert not pipe.reader.is_alive()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        pipe.stopped.set()
        pipe.reader.join(timeout=5)
        pipe.output.close()
