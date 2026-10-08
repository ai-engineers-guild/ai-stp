"""Exact prerequisites over a genuine registry backup and moved/copied project roots."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from ai_stp_cli.commands.environment import (
    _access_requirements,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_cli.local import revisions, versions
from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.cli.install import EnvironmentRequirement
from ai_stp_contracts.fixtures import case
from ai_stp_foundation.digests import digest_canonical
from ai_stp_passports import ComponentVersionPassport, SetupVersionPassport

Runner = Callable[[Path, Path, list[str], int], dict[str, Any]]


def prove(binary: Path, home: Path, temporary: Path, run: Runner) -> None:
    project = "project_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    target = temporary / "environment-target"
    target.mkdir()
    (target / ".ai-stp").mkdir()
    (target / ".ai-stp" / "project-id").write_text(project, encoding="ascii")
    snapshot = temporary / "environment-backup.sqlite"
    source = temporary / "environment-live.sqlite"
    component: dict[str, Any] = json.loads(
        json.dumps(dict(case("readComponentVersion.published").body or {}))
    )["passport"]
    setup: dict[str, Any] = json.loads(
        json.dumps(dict(case("readSetupVersion.published").body or {}))
    )["passport"]
    component["required_env"] = [
        {"name": "PATH", "purpose": "Executable lookup"},
        {"name": "AI_STP_V2_PROOF_ABSENT", "purpose": "Example prerequisite"},
    ]
    component["requires_credentials"] = True
    component_digest = ""
    with closing(open_registry(source)) as connection:
        for document in [component, setup]:
            if document is setup:
                document["components"] = [
                    {
                        "stable_id": component["stable_id"],
                        "version": component["version"],
                        "passport_digest": component_digest,
                    }
                ]
            stored = revisions.commit(
                connection, document, device_id="device_01ARZ3NDEKTSV4RRFFQ69G5FAV"
            )
            digest = digest_canonical("ai-stp:passport:v1", stored.envelope.model_dump(mode="json"))
            if document is component:
                component_digest = digest
            versions.record(
                connection,
                stable_id=document["stable_id"],
                version=document["version"],
                passport_digest=digest,
                revision_id=stored.revision_id,
                at=document["created_at"],
            )
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'project', ?)",
            (project, setup["created_at"]),
        )
        connection.execute(
            "INSERT INTO project_root (root, stable_id) VALUES (?, ?)",
            (str(target.resolve()), project),
        )
        connection.commit()
        with closing(sqlite3.connect(snapshot)) as destination:
            connection.backup(destination)
            destination.execute("PRAGMA journal_mode=DELETE")
    original = snapshot.read_bytes()
    reference = setup["stable_id"] + "@" + setup["version"]
    args = [
        "environment",
        "requirements",
        "--project",
        project,
        "--target",
        str(target),
        "--setup",
        reference,
        "--snapshot",
        str(snapshot),
        "--sha256",
        "sha256:" + hashlib.sha256(original).hexdigest(),
    ]
    result = run(binary, home, args, 0)["data"]
    assert result["configuration_state"] == "not_observed"
    assert result["setups"] == [reference]
    for item in result["requirements"]:
        EnvironmentRequirement.model_validate(item)
    actual = [
        item
        for item in result["requirements"]
        if item["kind"] in {"environment_variable", "authorization"}
    ]
    expected = [
        item.model_dump(mode="json")
        for item in _access_requirements(
            [
                SetupVersionPassport.model_validate(setup),
                ComponentVersionPassport.model_validate(component),
            ]
        )
    ]
    assert actual == expected
    assert snapshot.read_bytes() == original
    # Different path spellings can refer to the same existing directory. In
    # particular, Rust and Python resolve Windows verbatim prefixes differently.
    marker = target / ".ai-stp" / "project-id"
    marker.unlink()
    with closing(sqlite3.connect(snapshot)) as equivalent:
        equivalent.execute(
            "UPDATE project_root SET root = ? WHERE stable_id = ?",
            (str(target.resolve() / ".." / target.name), project),
        )
        equivalent.commit()
    args[-1] = "sha256:" + hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert run(binary, home, args, 0)["data"] == result
    snapshot.write_bytes(original)
    args[-1] = "sha256:" + hashlib.sha256(original).hexdigest()
    marker.write_text(project, encoding="ascii")
    # A copied marker cannot take the identity while its original exists.
    moved = temporary / "environment-moved"
    moved.mkdir()
    (moved / ".ai-stp").mkdir()
    (moved / ".ai-stp" / "project-id").write_text(project, encoding="ascii")
    args[args.index("--target") + 1] = str(moved)
    run(binary, home, args, 4)
    (moved / ".ai-stp" / "project-id").unlink()
    (moved / ".ai-stp").rmdir()
    moved.rmdir()
    target.rename(moved)
    assert run(binary, home, args, 0)["data"] == result
    assert snapshot.read_bytes() == original, "a read updated the moved-root mapping"
    for statement, parameters in [
        (
            "UPDATE object_version SET passport_digest = ? WHERE stable_id = ?",
            ("sha256:" + "0" * 64, component["stable_id"]),
        ),
        ("UPDATE object_version SET major = ? WHERE stable_id = ?", (99, component["stable_id"])),
    ]:
        snapshot.write_bytes(original)
        with closing(sqlite3.connect(snapshot)) as corrupt:
            corrupt.execute(statement, parameters)
            corrupt.commit()
        args[-1] = "sha256:" + hashlib.sha256(snapshot.read_bytes()).hexdigest()
        run(binary, home, args, 4)
    assert not list(home.iterdir())
