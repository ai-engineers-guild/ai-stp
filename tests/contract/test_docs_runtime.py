"""The docs runtime proof refuses privilege, missing pages and foreign cleanup."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

spec = importlib.util.spec_from_file_location(
    "docs_runtime_qualifier", Path(".github/scripts/qualify-docs-runtime.py")
)
assert spec is not None and spec.loader is not None
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)


def metadata() -> dict[str, Any]:
    return {
        "Id": "a" * 64,
        "Config": {
            "User": "101:101",
            "Labels": {
                qualifier.ROLE: "docs-runtime",
                qualifier.SOURCE: "b" * 40,
                qualifier.ATTEMPT: "owned-attempt",
            },
        },
        "State": {"Running": True},
        "HostConfig": {
            "ReadonlyRootfs": True,
            "NetworkMode": "none",
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Memory": 256 * 1024 * 1024,
            "PidsLimit": 128,
            "NanoCpus": 1_000_000_000,
            "IpcMode": "private",
            "PidMode": "",
        },
    }


def status(uid: int = 101, gid: int = 101, caps: str = "0") -> str:
    return (
        f"Name:\tnginx\nUid:\t{uid} {uid} {uid} {uid}\n"
        f"Gid:\t{gid} {gid} {gid} {gid}\nCapEff:\t{caps}\n"
    )


def test_docs_proof_requires_actual_unprivileged_identity() -> None:
    assert qualifier.validate_runtime(metadata(), status())["uids"] == [101] * 4
    for value in [
        status(uid=0),
        status(gid=0),
        status(caps="1"),
        status().replace("101 101 101 101", "101 101 0 101"),
    ]:
        with pytest.raises(ValueError):
            qualifier.validate_runtime(metadata(), value)


@pytest.mark.parametrize("user", ["", "root", "0", "0:0"])
def test_docs_proof_refuses_a_root_image_default(user: str) -> None:
    data = metadata()
    data["Config"]["User"] = user
    with pytest.raises(ValueError):
        qualifier.validate_runtime(data, status())


@pytest.mark.parametrize(
    "field,value",
    [
        ("ReadonlyRootfs", False),
        ("NetworkMode", "host"),
        ("CapDrop", []),
        ("SecurityOpt", []),
        ("Memory", 0),
        ("PidsLimit", 0),
        ("NanoCpus", 0),
        ("IpcMode", "host"),
        ("PidMode", "host"),
    ],
)
def test_docs_proof_requires_isolated_execution(field: str, value: object) -> None:
    data = metadata()
    data["HostConfig"][field] = value
    with pytest.raises(ValueError):
        qualifier.validate_runtime(data, status())


def test_docs_cleanup_requires_exact_fixture_ownership() -> None:
    assert qualifier.owned_id(metadata(), "b" * 40, "owned-attempt") == "a" * 64
    for key in [qualifier.ROLE, qualifier.SOURCE, qualifier.ATTEMPT]:
        data = metadata()
        data["Config"]["Labels"][key] = "foreign"
        with pytest.raises(ValueError):
            qualifier.owned_id(data, "b" * 40, "owned-attempt")


def test_docs_proof_requires_each_actual_language_page() -> None:
    assert qualifier.page_proof('<html lang="ru">fixture</html>', "ru")["language"] == "ru"
    for body in ['<html lang="ru">fixture</html>', "<html>missing</html>", "not a page"]:
        with pytest.raises(ValueError):
            qualifier.page_proof(body, "en")
