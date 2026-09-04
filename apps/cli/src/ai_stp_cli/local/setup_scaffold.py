"""Physical setup authoring trees, distinct from compose and install."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.authoring import (
    DRAFT,
    GITIGNORE,
    TYPE_LANGUAGE_MATRIX,
    TYPES,
    component_scaffold_files,
    initialize_authoring_git,
    write_new_tree,
)
from ai_stp_cli.local.evaluation import reference_profile
from ai_stp_contracts.authoring import (
    DECLARATIVE_COMPONENT_TYPES,
    ComponentScaffoldFile,
    ComponentTemplateDescriptor,
    SetupMemberDescriptor,
    SetupScaffoldPlan,
    SetupScaffoldResult,
    SetupTemplateDescriptor,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER
from ai_stp_passports.versions import ComponentType

_NAME: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def setup_scaffold_plan(
    *,
    name: str,
    harness: str,
    output: Path,
    components: str | None = None,
) -> tuple[SetupScaffoldPlan, dict[str, bytes]]:
    """Preview every byte of one complete setup authoring scaffold."""
    if not _NAME.fullmatch(name):
        raise _fail("the setup name must be a lowercase bounded slug")
    if harness not in HARNESS_ID_ORDER:
        raise _fail("a setup scaffold requires one concrete harness")
    destination = output.expanduser().resolve(strict=False)
    _require_unused(destination)
    members = _parse_members(components)
    descriptor = SetupTemplateDescriptor(
        harness_id=harness,  # pyright: ignore[reportArgumentType]
        setup_name=name,
        members=list(members),
    )
    files = setup_scaffold_files(descriptor)
    entries = [
        ComponentScaffoldFile(
            path=path,
            digest=digest_bytes("ai-stp:artifact:v1", payload),
            byte_length=len(payload),
        )
        for path, payload in sorted(files.items())
    ]
    body: dict[str, JsonValue] = {
        "schema_version": 1,
        "output": str(destination),
        "setup_name": name,
        "descriptor": cast(JsonValue, descriptor.model_dump(mode="json")),
        "files": cast(JsonValue, [item.model_dump(mode="json") for item in entries]),
        "publication_ready": False,
        "requires_exact_source_before_publication": True,
    }
    digest = digest_bytes("ai-stp:setup-scaffold-plan:v1", canonize(body))
    plan = SetupScaffoldPlan.model_validate(
        {
            "plan_id": f"setup_scaffold_{digest.removeprefix('sha256:')[:24]}",
            "plan_digest": digest,
            **body,
        }
    )
    return plan, files


def apply_setup_scaffold(
    plan: SetupScaffoldPlan,
    files: dict[str, bytes],
    *,
    expected_digest: str,
) -> SetupScaffoldResult:
    """Create exactly the planned new setup directory without replacing any path."""
    if plan.plan_digest != expected_digest:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED", "the scaffold plan digest changed before apply"
        )
    destination = Path(plan.output)
    _require_unused(destination)
    expected_files = {item.path: (item.digest, item.byte_length, item.mode) for item in plan.files}
    observed_files = {
        path: (digest_bytes("ai-stp:artifact:v1", payload), len(payload), 0o600)
        for path, payload in files.items()
    }
    if observed_files != expected_files:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the scaffold bytes no longer match the exact plan",
        )
    write_new_tree(destination, files)
    git = initialize_authoring_git(destination)
    return SetupScaffoldResult(
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        output=str(destination),
        files_written=len(files),
        git_initialized=git.initialized,
        git_commit=git.commit,
        git_reason=git.reason,
    )


def setup_scaffold_files(descriptor: SetupTemplateDescriptor) -> dict[str, bytes]:
    """Return the planned regular files for one setup wrapper, without git."""
    name = descriptor.setup_name
    harness = descriptor.harness_id
    member_files: dict[str, bytes] = {}
    compose_members: list[dict[str, JsonValue]] = []
    passport_members: list[dict[str, JsonValue]] = []
    types: list[ComponentType] = []
    for member in descriptor.members:
        component = ComponentTemplateDescriptor(
            component_type=member.component_type,
            language=member.language,
            harness_variant=harness,
            executable=member.component_type not in DECLARATIVE_COMPONENT_TYPES,
        )
        nested = component_scaffold_files(member.name, component)
        member_files.update(
            {f"components/{member.name}/{path}": payload for path, payload in nested.items()}
        )
        types.append(member.component_type)
        projection_prefix = f"projections/{harness}/"
        native_paths = tuple(
            sorted(
                path.removeprefix(projection_prefix)
                for path in nested
                if path.startswith(projection_prefix) and path.rsplit("/", 1)[-1] != "GENERATED.md"
            )
        )
        compose_members.append(
            {
                "source": {
                    "kind": "path",
                    "relative_path": f"components/{member.name}/projections/{harness}",
                },
                "component_type": member.component_type,
                "name": member.name,
                "description": f"{DRAFT} replace with the component purpose.",
                "license_spdx": "NOASSERTION",
                "redistribution_allowed": False,
                "version": "0.1",
                "managed_paths": list(native_paths),
            }
        )
        passport_members.append(
            {
                "component_type": member.component_type,
                "name": member.name,
                "relative_path": f"components/{member.name}",
            }
        )
    setup_json = {
        "schema_version": 1,
        "name": name,
        "description": f"{DRAFT} replace with a one-sentence setup purpose.",
        "harness_id": harness,
        "version": "0.1",
        "tags": [],
        "components": compose_members,
    }
    setup_passport = {
        "schema_version": 1,
        "draft": True,
        "name": name,
        "harness_id": harness,
        "version": "0.1",
        "license": {"spdx_id": "NOASSERTION", "redistribution_allowed": False},
        "components": passport_members,
    }
    profile = reference_profile(tuple(types) if types else None)
    files: dict[str, bytes] = {
        ".ai-stp-template.json": canonize(cast(JsonValue, descriptor.model_dump(mode="json"))),
        ".gitignore": GITIGNORE,
        "README.md": _setup_readme(name, harness, descriptor),
        "eval-profile.json": canonize(cast(JsonValue, profile.model_dump(mode="json"))),
        "setup-passport.json": canonize(cast(JsonValue, setup_passport)),
        "setup.json": canonize(cast(JsonValue, setup_json)),
        "projections/README.md": (
            f"{DRAFT} this directory stays empty until a later export command writes "
            "a physical harness tree. Scaffold does not export. "
            "`setup compose` records a local SQLite version and is not install.\n"
        ).encode(),
    }
    files.update(member_files)
    return files


def _parse_members(raw: str | None) -> tuple[SetupMemberDescriptor, ...]:
    if raw is None or not raw.strip():
        return ()
    members: list[SetupMemberDescriptor] = []
    seen: set[str] = set()
    for item in raw.split(","):
        token = item.strip()
        if not token:
            raise _fail("a setup member must be type:name or type:name:language")
        parts = token.split(":")
        if len(parts) == 2:
            component_type, name = parts
            language = "none"
        elif len(parts) == 3:
            component_type, name, language = parts
        else:
            raise _fail("a setup member must be type:name or type:name:language")
        if component_type not in TYPES or not _NAME.fullmatch(name):
            raise _fail("the component type or lowercase bounded name is invalid")
        allowed = TYPE_LANGUAGE_MATRIX[cast(ComponentType, component_type)]
        if language not in allowed:
            raise _fail(
                "declarative components require language=none; "
                "executable components require a language"
            )
        if name in seen:
            raise _fail("setup member names must be unique")
        seen.add(name)
        members.append(
            SetupMemberDescriptor(
                component_type=component_type,  # pyright: ignore[reportArgumentType]
                name=name,
                language=language,  # pyright: ignore[reportArgumentType]
            )
        )
    return tuple(members)


def _setup_readme(name: str, harness: str, descriptor: SetupTemplateDescriptor) -> bytes:
    member_lines = "".join(
        f"- `components/{item.name}/` — `{item.component_type}`\n" for item in descriptor.members
    ) or (
        "- No members yet. Add them with `--components type:name` or by hand under `components/`.\n"
    )
    return (
        f"# {name}\n\n"
        f"{DRAFT} replace this README with a consumer description of the setup.\n\n"
        f"This directory is a draft setup for `{harness}` (`{descriptor.template_version}`).\n\n"
        "## Layout\n\n"
        "- `setup.json` is this repository's compose-manifest shape. It is a draft until "
        "members, tags, and a real description exist.\n"
        "- `setup-passport.json` is a draft graph, not a frozen SetupVersion.\n"
        f"- `projections/{harness}/` stays empty until a later export command. "
        "Scaffold does not export.\n"
        "- Nested components live under `components/` and share this git root.\n\n"
        "## Members\n\n"
        f"{member_lines}\n"
        "## Boundaries\n\n"
        "`setup compose` records an immutable local SQLite version from a complete "
        "manifest. Compose is not install. Only a public provider writes harness state.\n\n"
        "## Replace before publication\n\n"
        f"- Every `{DRAFT}` marker.\n"
        "- License `NOASSERTION` after a reviewed license decision.\n"
        "- An exact public GitHub commit for every published member.\n\n"
        "## Publication checklist\n\n"
        "- [ ] Replace draft markers with real behavior.\n"
        "- [ ] Give `setup.json` a real description and at least one member.\n"
        "- [ ] Pin exact public GitHub source for published members.\n"
        "- [ ] Replace NOASSERTION with a reviewed redistributable license.\n"
        "- [ ] Run `setup compose plan` only after the manifest is complete. That is not install.\n"
    ).encode()


def _require_unused(destination: Path) -> None:
    if destination.is_symlink() or destination.exists():
        raise _fail("the scaffold destination must not already exist")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise _fail("the scaffold destination parent must be an existing regular directory")


def _fail(message: str) -> CliFailure:
    return CliFailure("AI_STP_VALIDATION_ERROR", message)
