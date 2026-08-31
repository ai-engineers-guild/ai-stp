#!/usr/bin/env python3
"""Verify the public route with normal DNS and strict TLS."""

from __future__ import annotations

import argparse
import ast
import http.client
import json
import re
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
    except (OSError, http.client.HTTPException) as error:
        # Everything a restarting target does to an open socket, in one place.
        # `URLError` alone was not enough: the deployment window drops
        # connections mid-response, and `http.client.RemoteDisconnected` is a
        # `ConnectionResetError` that urllib lets through unwrapped. It then
        # escaped the retry loop below and failed the job outright — for the one
        # condition that loop exists to wait out.
        raise VerificationError(f"request failed for {url}: {error}") from error


def _json(body: bytes, path: str) -> dict[str, Any]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"{path} did not return JSON") from error
    if not isinstance(value, dict):
        raise VerificationError(f"{path} did not return an object")
    return value


def _fetched(
    fetch: Callable[[str, int], tuple[int, bytes]], url: str, limit: int
) -> tuple[int, bytes]:
    """Call `fetch` and turn every transport failure into a retryable one.

    Wrapped here rather than only inside `_default_fetch`, because the caller
    supplies the fetch and should not have to know this convention — and because
    the convention is the point: everything a restarting target does to a socket
    is "not ready yet", which the loop in `main` waits out, not a reason to fail
    the deployment.
    """
    try:
        return fetch(url, limit)
    except VerificationError:
        raise
    except (OSError, http.client.HTTPException) as error:
        raise VerificationError(f"request failed for {url}: {error}") from error


def verify(
    origin: str,
    *,
    expected_commit: str,
    expected_schema: str,
    expected_environment: str,
    fetch: Callable[[str, int], tuple[int, bytes]] = _default_fetch,
    commit_accepted: Callable[[str], bool] | None = None,
) -> None:
    """Verify user-visible health, TLS route and the deployed identity.

    `commit_accepted` decides what counts as the promoted commit having arrived.
    The default is exact equality, and that is what this asserted unconditionally
    until 2026-08-29 — when three pushes inside twenty minutes put three deploy
    runs against one host. The ref is monotonic and the host deploys the newest,
    so each older run waited for a SHA the host would never record again and
    failed after 106 attempts against a host serving a commit that *contained*
    its own.

    Being overtaken is the deployment succeeding. The property is that the
    promoted commit reached the target, and a descendant carries it — so the
    caller supplies the ancestry test rather than this file guessing, and an
    unrelated SHA still fails.
    """
    origin = validated_origin(origin)
    expected = {
        "/v1/health/live": ("status", "alive"),
        "/v1/health/ready": ("status", "ready"),
    }
    for path, (field, value) in expected.items():
        status, body = _fetched(fetch, origin + path, MAX_JSON_BYTES)
        if status != 200:
            raise VerificationError(f"{path} returned HTTP {status}")
        payload = _json(body, path)
        if payload.get("schema_version") != 1 or payload.get(field) != value:
            raise VerificationError(f"{path} returned an unexpected payload")

    status, body = _fetched(fetch, origin + "/v1/system/version", MAX_JSON_BYTES)
    if status != 200:
        raise VerificationError(f"/v1/system/version returned HTTP {status}")
    identity = _json(body, "/v1/system/version")
    claims = {
        "schema_revision": expected_schema,
        "environment": expected_environment,
    }
    for field, expected_value in claims.items():
        if identity.get(field) != expected_value:
            raise VerificationError(
                f"deployed {field} is {identity.get(field)!r}, expected {expected_value!r}"
            )

    deployed = identity.get("git_commit")
    accepted = commit_accepted if commit_accepted is not None else expected_commit.__eq__
    if not isinstance(deployed, str) or not accepted(deployed):
        raise VerificationError(
            f"deployed git_commit is {deployed!r}, expected {expected_commit!r} "
            "or a commit containing it"
        )

    status, _body = fetch(origin + "/", MAX_WEB_BYTES)
    if status != 200:
        raise VerificationError(f"web root returned HTTP {status}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    parser.add_argument("--expected-commit", required=True)
    # Named rather than derived from the checkout: the clone is shallow and its
    # remote is not the fact this needs. Only used to ask which commit contains
    # which.
    parser.add_argument("--repository", default="ai-engineers-guild/ai-stp")
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


#: Where the commit graph actually lives. Asked over HTTPS rather than of the
#: local clone: `actions/checkout` here is shallow and pinned to the promoted
#: SHA, so a commit pushed *after* this job started — which is precisely the
#: overtaking case — is not in the clone at all, and `git merge-base` would
#: answer "not an ancestor" for the one situation this exists to recognise. A
#: repair that is correct in isolation and unreachable in place is worse than
#: none, because it reads as fixed.
COMPARE_URL = "https://api.github.com/repos/{repository}/compare/{base}...{head}"

#: This one comparison gets its own bound, and it is measured rather than
#: chosen. A run failed here with `response exceeded 65536 bytes` against a
#: healthy target: the compare response carries every changed file between the
#: two refs, so its size tracks how busy the repository was and nothing about
#: the deployment.
#:
#: Measured on this repository: adjacent commits 28 KiB, and an afternoon
#: spanning a 234-file sync **1.1 MiB**. `per_page=1` was tried first and moves
#: it by 7% — it bounds the commit list, and the files are what is large, so
#: there is no lighter question to ask this endpoint.
#:
#: Still a bound. It exists to stop an unbounded read, not to police an API
#: whose response size nobody here controls.
MAX_COMPARE_BYTES = 8 * 1024 * 1024


def contains(
    expected: str,
    deployed: str,
    *,
    repository: str,
    fetch: Callable[[str, int], tuple[int, bytes]] = _default_fetch,
) -> bool:
    """Whether `deployed` is `expected` or a commit that contains it.

    `identical` and `ahead` mean the promotion arrived. `behind`, `diverged`, an
    unparseable answer or any transport failure mean it did not — the caller
    then keeps waiting and eventually fails, which is the previous behaviour and
    the safe direction.
    """
    if deployed == expected:
        return True
    if not re.fullmatch(r"[0-9a-f]{40}", deployed) or not re.fullmatch(r"[0-9a-f]{40}", expected):
        return False
    url = COMPARE_URL.format(repository=repository, base=expected, head=deployed)
    try:
        status, body = fetch(url, MAX_COMPARE_BYTES)
        if status != 200:
            return False
        answer = json.loads(body.decode("utf-8"))
    except (OSError, http.client.HTTPException, ValueError, UnicodeDecodeError):
        return False
    return isinstance(answer, dict) and answer.get("status") in {"identical", "ahead"}


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
                commit_accepted=lambda deployed: contains(
                    args.expected_commit, deployed, repository=args.repository
                ),
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
