"""Bounded GitHub API access for qualified source delivery; never log response payloads."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, cast


class PromotionRefused(RuntimeError):
    """The caller has no authority to substitute another promotion path."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PromotionRefused(message)


class GitHub:
    def __init__(self, repository: str) -> None:
        require(
            bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)), "Invalid repository"
        )
        self.repository = repository

    def request(
        self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        arguments = ["gh", "api", "--hostname", "github.com", "--include", "--method", method]
        if body is not None:
            arguments += ["--input", "-"]
        arguments.append(f"repos/{self.repository}" + (f"/{path}" if path else ""))
        result = subprocess.run(
            arguments,
            input=json.dumps(body) if body is not None else None,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        headers, separator, payload = result.stdout.partition("\n\n")
        status = re.match(r"HTTP/\S+ ([0-9]{3})\b", headers)
        require(
            bool(separator and status),
            f"GitHub did not return an HTTP response for {method} {path}",
        )
        code = int(cast(re.Match[str], status)[1])
        require(result.returncode == 0 or code >= 400, "GitHub transport failed")
        return code, json.loads(payload) if payload.strip() else None

    def read(self, path: str) -> Any:
        status, value = self.request(path)
        require(status == 200, f"GitHub refused GET {path} ({status})")
        return value

    def write(self, path: str, body: dict[str, Any], *, create: bool = False) -> Any:
        method = "POST" if create else "PATCH"
        status, value = self.request(path, method=method, body=body)
        require(status == (201 if create else 200), f"GitHub refused {method} {path} ({status})")
        return value
