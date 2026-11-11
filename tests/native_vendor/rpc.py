"""Bounded native pipe ownership shared by the Codex and Pi readers."""

from __future__ import annotations

import queue
import subprocess
import threading
from contextlib import suppress


class Pipe:
    """Read LF-delimited records without unbounded pipes or reader threads."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdin is not None and process.stdout is not None
        self.process = process
        self.input = process.stdin
        self.output = process.stdout
        self.messages: queue.Queue[bytes | Exception] = queue.Queue(maxsize=32)
        self.stopped = threading.Event()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        try:
            while not self.stopped.is_set():
                line = self.output.readline(2 * 1024 * 1024 + 1)
                if not line:
                    raise EOFError("Vendor closed its local RPC output")
                if len(line) > 2 * 1024 * 1024 or not line.endswith(b"\n"):
                    raise ValueError("Vendor RPC line exceeds the declared bound")
                while not self.stopped.is_set():
                    try:
                        self.messages.put(line, timeout=0.5)
                        break
                    except queue.Full:
                        continue
        except (OSError, ValueError, EOFError) as error:
            if not self.stopped.is_set():
                with suppress(queue.Full):
                    self.messages.put_nowait(error)

    def close(self) -> None:
        self.stopped.set()
        with suppress(BrokenPipeError):
            self.input.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.reader.join(timeout=5)
        assert not self.reader.is_alive(), "Owned RPC reader did not stop"
        self.output.close()
