"""Delivering the canonical Agent Skill to a harness (issue #97).

The Skill is the product's control plane: the agent reads it to operate this
CLI. Installation writes a package — `SKILL.md` plus `references/` — and an
ownership record covering every owned file. The destination is named rather
than discovered until `SPEC-014`. Nothing is overwritten silently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import redact_home, write_private
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER

HARNESSES: Final[tuple[str, ...]] = HARNESS_ID_ORDER
LOCALES: Final[tuple[str, ...]] = ("en", "ru")
MANIFEST: Final[str] = ".ai-stp-skill.json"
SKILL_FILENAME: Final[str] = "SKILL.md"
PACKAGE_DOMAIN: Final[str] = "ai-stp:skill-package:v1"
ARTIFACT_DOMAIN: Final[str] = "ai-stp:artifact:v1"


@dataclass(frozen=True)
class Installed:
    """What is at a destination, and whether this CLI put it there."""

    #: `absent`, `owned`, `foreign`, or `stale` when owned but since edited.
    state: str
    digest: str | None
    harness: str | None
    locale: str | None = None
    files: tuple[str, ...] = ()


def package_files(harness: str | None, locale: str = "en") -> dict[str, bytes]:
    """Every owned file of the Skill package this build ships."""
    if locale not in LOCALES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "no skill locale is shipped for that locale",
            details={"locale": locale, "supported": ", ".join(LOCALES)},
            next_actions=["skill status --target <path> --json"],
        )
    root = resources.files("ai_stp_cli").joinpath("skills")
    if harness is None:
        skill_root = root.joinpath("canonical" if locale == "en" else "locales/ru")
        skill_text = skill_root.joinpath(SKILL_FILENAME).read_bytes()
        refs = skill_root.joinpath("references")
    else:
        if harness not in HARNESSES:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "no projection is shipped for that harness",
                details={"harness": harness, "supported": ", ".join(HARNESSES)},
                next_actions=["capabilities --json"],
            )
        name = f"{harness}.md" if locale == "en" else f"{harness}.ru.md"
        skill_text = root.joinpath("projections", name).read_bytes()
        refs = root.joinpath("canonical" if locale == "en" else "locales/ru").joinpath("references")
    files = {SKILL_FILENAME: skill_text}
    for item in refs.iterdir():
        if item.name.endswith(".md"):
            files[f"references/{item.name}"] = item.read_bytes()
    return files


def available(harness: str | None, locale: str = "en") -> str:
    """The Skill map this build ships for a harness, or the canonical one."""
    return package_files(harness, locale)[SKILL_FILENAME].decode("utf-8")


def digest_of(text: str) -> str:
    return digest_bytes(ARTIFACT_DOMAIN, text.encode("utf-8"))


def digest_of_package(files: dict[str, bytes]) -> str:
    body: list[JsonValue] = [
        cast(
            JsonValue,
            {"path": path, "digest": digest_bytes(ARTIFACT_DOMAIN, payload)},
        )
        for path, payload in sorted(files.items())
    ]
    return digest_canonical(PACKAGE_DOMAIN, cast(JsonValue, body))


def inspect(target: Path) -> Installed:
    """What is at `target`, without changing it."""
    skill = target / SKILL_FILENAME
    claim = _claim(target)
    if not skill.exists() and claim is None:
        return Installed("absent", None, None)
    if claim is None:
        present = digest_of(skill.read_text(encoding="utf-8")) if skill.exists() else None
        return Installed("foreign", present, None)
    files = _claimed_files(target)
    digest = digest_of_package(files) if files else None
    harness = claim.get("harness") or None
    locale = claim.get("locale") or None
    names = tuple(sorted(files))
    if digest == claim.get("digest"):
        return Installed("owned", digest, harness, locale, names)
    return Installed("stale", digest, harness, locale, names)


def install(target: Path, harness: str | None, locale: str = "en") -> Installed:
    """Put the Skill package at `target`, refusing to overwrite what is not ours."""
    files = package_files(harness, locale)
    if available(harness, locale).encode() != files[SKILL_FILENAME]:
        raise CliFailure("AI_STP_INTERNAL", "the shipped skill map drifted from the package")
    wanted = digest_of_package(files)
    present = inspect(target)
    if present.state == "foreign":
        raise CliFailure(
            "AI_STP_CONFLICT",
            "a skill this installation does not own is already at that destination",
            details={"path": redact_home(target)},
            next_actions=["skill status --target <path> --json"],
        )
    if present.state == "stale":
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the installed skill was edited after this installation wrote it",
            details={"path": redact_home(target)},
            next_actions=["skill remove --target <path> --json"],
        )

    for relative, payload in files.items():
        write_private(target / relative, payload.decode("utf-8"))
    write_private(
        target / MANIFEST,
        json.dumps(
            {
                "digest": wanted,
                "harness": harness,
                "locale": locale,
                "files": sorted(files),
            },
            sort_keys=True,
        )
        + "\n",
    )
    return Installed("owned", wanted, harness, locale, tuple(sorted(files)))


def remove(target: Path) -> Installed:
    """Take back only what the ownership record claims."""
    present = inspect(target)
    if present.state == "absent":
        return present
    if present.state == "foreign":
        raise CliFailure(
            "AI_STP_CONFLICT",
            "that skill was not installed by this installation",
            details={"path": redact_home(target)},
            next_actions=["skill status --target <path> --json"],
        )
    listed = _claim_file_list(target)
    for relative in listed:
        (target / relative).unlink(missing_ok=True)
    references = target / "references"
    if references.is_dir():
        for child in tuple(references.iterdir()):
            child.unlink(missing_ok=True)
        references.rmdir()
    (target / SKILL_FILENAME).unlink(missing_ok=True)
    (target / MANIFEST).unlink(missing_ok=True)
    return Installed("absent", None, None)


def _claim(target: Path) -> dict[str, str] | None:
    path = target / MANIFEST
    if not path.exists():
        return None
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    document = cast(dict[str, object], parsed)
    claimed: dict[str, str] = {}
    for key, value in document.items():
        if value is None:
            continue
        if key == "files" and isinstance(value, list):
            claimed[key] = json.dumps(value)
            continue
        claimed[str(key)] = str(value)
    return claimed


def _claim_file_list(target: Path) -> tuple[str, ...]:
    path = target / MANIFEST
    if not path.exists():
        return ()
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return ()
    if not isinstance(parsed, dict):
        return ()
    raw_files: object = cast(dict[object, object], parsed).get("files")
    if not isinstance(raw_files, list):
        if (target / SKILL_FILENAME).exists():
            return (SKILL_FILENAME,)
        return ()
    names: list[str] = []
    for item in cast(list[object], raw_files):
        if not isinstance(item, str):
            return ()
        names.append(item)
    return tuple(names)


def _claimed_files(target: Path) -> dict[str, bytes]:
    names = _claim_file_list(target)
    files: dict[str, bytes] = {}
    for relative in names:
        path = target / relative
        if path.is_file():
            files[relative] = path.read_bytes()
    if not files and (target / SKILL_FILENAME).is_file():
        files[SKILL_FILENAME] = (target / SKILL_FILENAME).read_bytes()
    return files
