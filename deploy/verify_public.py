#!/usr/bin/env python3
"""Verify the public route with normal DNS and strict TLS."""

from __future__ import annotations

import argparse
import ast
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 64 * 1024
MAX_WEB_BYTES = 1024 * 1024


class VerificationError(RuntimeError):
    """The public route does not prove the expected deployment identity."""


class StrictHttpsRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Allow only same-origin HTTPS redirects."""

    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> urllib.request.Request | None:
        source = urllib.parse.urlsplit(request.full_url)
        target = urllib.parse.urlsplit(new_url)
        if target.scheme != "https" or target.netloc != source.netloc:
            raise VerificationError(
                "public verification refused a redirect outside its HTTPS origin"
            )
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def _literal_assignment(path: Path, name: str) -> str | None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        target: ast.expr | None = None
        value_node: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value_node = node.value
        if isinstance(target, ast.Name) and target.id == name:
            if value_node is None:
                raise VerificationError(f"{path}: {name} has no value")
            value = ast.literal_eval(value_node)
            if value is None or isinstance(value, str):
                return value
            raise VerificationError(f"{path}: {name} is not a string literal")
    raise VerificationError(f"{path}: {name} is absent")


def migration_head(directory: Path) -> str:
    """Return the only Alembic head without importing migration code."""
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("__"):
            continue
        revision = _literal_assignment(path, "revision")
        parent = _literal_assignment(path, "down_revision")
        if revision is None:
            raise VerificationError(f"{path}: revision cannot be null")
        if revision in revisions:
            raise VerificationError(f"duplicate migration revision: {revision}")
        revisions.add(revision)
        if parent is not None:
            parents.add(parent)
    heads = sorted(revisions - parents)
    if len(heads) != 1:
        raise VerificationError(f"expected one migration head, found: {heads}")
    return heads[0]


def validated_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (parsed.path not in ("", "/"))
    ):
        raise VerificationError("public origin must be a bare https origin")
    return value.rstrip("/")


def _default_fetch(url: str, limit: int) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "ai-stp-deploy-verifier/1"})
    opener = urllib.request.build_opener(StrictHttpsRedirectHandler())
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read(limit + 1)
            if len(body) > limit:
                raise VerificationError(f"response exceeded {limit} bytes: {url}")
            return int(response.status), body
    except (urllib.error.URLError, TimeoutError) as error:
        raise VerificationError(f"request failed for {url}: {error}") from error


def _json(body: bytes, path: str) -> dict[str, Any]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"{path} did not return JSON") from error
    if not isinstance(value, dict):
        raise VerificationError(f"{path} did not return an object")
    return value


def verify(
    origin: str,
    *,
    expected_commit: str,
    expected_schema: str,
    expected_environment: str,
    fetch: Callable[[str, int], tuple[int, bytes]] = _default_fetch,
) -> None:
    """Verify user-visible health, TLS route and exact deployed identity."""
    origin = validated_origin(origin)
    expected = {
        "/v1/health/live": ("status", "alive"),
        "/v1/health/ready": ("status", "ready"),
    }
    for path, (field, value) in expected.items():
        status, body = fetch(origin + path, MAX_JSON_BYTES)
        if status != 200:
            raise VerificationError(f"{path} returned HTTP {status}")
        payload = _json(body, path)
        if payload.get("schema_version") != 1 or payload.get(field) != value:
            raise VerificationError(f"{path} returned an unexpected payload")

    status, body = fetch(origin + "/v1/system/version", MAX_JSON_BYTES)
    if status != 200:
        raise VerificationError(f"/v1/system/version returned HTTP {status}")
    identity = _json(body, "/v1/system/version")
    claims = {
        "git_commit": expected_commit,
        "schema_revision": expected_schema,
        "environment": expected_environment,
    }
    for field, expected_value in claims.items():
        if identity.get(field) != expected_value:
            raise VerificationError(
                f"deployed {field} is {identity.get(field)!r}, expected {expected_value!r}"
            )

    status, _body = fetch(origin + "/", MAX_WEB_BYTES)
    if status != 200:
        raise VerificationError(f"web root returned HTTP {status}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--migrations-dir", type=Path, required=True)
    # `prod` is the name of the one deployed environment (ADR-0086). The
    # default used to be `staging` while `.env.prod` declared `prod`, so the
    # check would have rejected the very host it had just deployed to.
    parser.add_argument("--expected-environment", default="prod")
    # Promotion and deployment are deliberately not the same event (`ADR-0103`):
    # CI advances a ref and the target pulls it on its own timer. A single
    # immediate check therefore proves nothing about a deployment that has not
    # started yet, which is why this check used to be advisory. Waiting a
    # bounded time turns it back into a claim: the target had this long to
    # deploy the promoted commit, and it either did or it did not.
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    # Read from the repository, not from the deployment, so a broken migration
    # tree fails immediately instead of being retried until the deadline.
    try:
        expected_schema = migration_head(args.migrations_dir)
    except VerificationError as error:
        print(f"public verification failed: {error}", file=sys.stderr)
        return 1

    deadline = time.monotonic() + max(args.wait_seconds, 0)
    attempts = 0
    while True:
        attempts += 1
        try:
            verify(
                args.origin,
                expected_commit=args.expected_commit,
                expected_schema=expected_schema,
                expected_environment=args.expected_environment,
            )
        except VerificationError as error:
            if time.monotonic() >= deadline:
                print(
                    f"public verification failed after {attempts} attempt(s): {error}",
                    file=sys.stderr,
                )
                return 1
            print(f"not deployed yet, retrying: {error}", file=sys.stderr)
            time.sleep(max(args.poll_seconds, 1))
            continue
        print(
            f"public verification passed: commit={args.expected_commit} "
            f"schema={expected_schema} attempts={attempts}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
