#!/usr/bin/env python3
"""Fail closed unless a deploy comes from an allowed PR merge."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

MAX_RESPONSE_BYTES = 1024 * 1024


class SourceError(RuntimeError):
    """The requested deployment source is not an approved integration shape."""


def _csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def verify_local_merge(root: Path, sha: str) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()
    if head != sha:
        raise SourceError(f"checked-out HEAD {head} does not equal requested SHA {sha}")
    parents = subprocess.run(
        ["git", "show", "-s", "--format=%P", sha],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.split()
    if len(parents) != 2:
        raise SourceError("deployment source must be a two-parent PR merge commit")


def _github_fetch(url: str, token: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "ai-stp-deploy-source-verifier/1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as error:
        raise SourceError(f"GitHub source lookup failed: {error}") from error
    if len(body) > MAX_RESPONSE_BYTES:
        raise SourceError("GitHub source lookup response exceeded the limit")
    value = json.loads(body)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SourceError("GitHub source lookup returned an unexpected payload")
    return value


def verify_pull_request(
    pulls: list[dict[str, Any]],
    *,
    sha: str,
    base: str,
    allowed_heads: set[str],
) -> int:
    matches: list[dict[str, Any]] = []
    for pull in pulls:
        base_data = pull.get("base")
        head_data = pull.get("head")
        if (
            pull.get("merged_at")
            and pull.get("merge_commit_sha") == sha
            and isinstance(base_data, dict)
            and base_data.get("ref") == base
            and isinstance(head_data, dict)
            and head_data.get("ref") in allowed_heads
        ):
            matches.append(pull)
    if len(matches) != 1:
        raise SourceError("SHA is not the unique allowed PR merge into the integration branch")
    number = matches[0].get("number")
    if not isinstance(number, int):
        raise SourceError("associated pull request has no numeric identifier")
    return number


def verify(
    *,
    root: Path,
    repository: str,
    sha: str,
    actor: str,
    token: str,
    api_url: str,
    allowed_actors: set[str],
    allowed_heads: set[str],
    fetch: Callable[[str, str], list[dict[str, Any]]] = _github_fetch,
) -> int:
    if actor not in allowed_actors:
        raise SourceError(f"actor {actor!r} is not allowed to deploy")
    if not token:
        raise SourceError("GitHub token is unavailable for source verification")
    if not allowed_heads:
        raise SourceError("no allowed PR head branches were configured")
    verify_local_merge(root, sha)
    quoted_repository = "/".join(
        urllib.parse.quote(part, safe="") for part in repository.split("/")
    )
    url = f"{api_url.rstrip('/')}/repos/{quoted_repository}/commits/{sha}/pulls"
    return verify_pull_request(fetch(url, token), sha=sha, base="dev", allowed_heads=allowed_heads)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--allowed-actors", required=True)
    parser.add_argument("--allowed-heads", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        pull_number = verify(
            root=args.root,
            repository=args.repository,
            sha=args.sha,
            actor=args.actor,
            token=os.environ.get("GITHUB_TOKEN", ""),
            api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            allowed_actors=_csv(args.allowed_actors),
            allowed_heads=_csv(args.allowed_heads),
        )
    except (SourceError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"deployment source rejected: {error}", file=sys.stderr)
        return 1
    print(f"deployment source accepted: sha={args.sha} pull_request={pull_number}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
