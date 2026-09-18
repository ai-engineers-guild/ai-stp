"""Isolated agy gpt-oss-120b qualify runner. Unrun cells stay not_run."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.application.initialize import ANTIGRAVITY_LIMITATION
from ai_stp_cli.application.qualify import (
    AGY_MODEL,
    HAIKU_RUNS,
    HAIKU_SCENARIOS,
    PLATFORMS,
    MeasuredStatus,
    native_config_root,
    native_marker_populated,
    native_platform,
    tree_digest,
)
from ai_stp_contracts.cli_copy import INITIALIZE_PROMPT, INITIALIZE_START
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER

ROOT: Final[Path] = Path(__file__).resolve().parents[4]
DOCKER_IMAGE_ENV: Final[str] = "AI_STP_QUALIFY_DOCKER_IMAGE"
PROVIDERS_ENV: Final[str] = "AI_STP_QUALIFY_PROVIDERS"
TOOLCHAINS_ENV: Final[str] = "AI_STP_QUALIFY_TOOLCHAINS"
_REPO_SRC: Final[tuple[str, ...]] = (
    "apps/cli/src",
    "apps/api/src",
    "packages/assurance/src",
    "packages/contracts/src",
    "packages/foundation/src",
    "packages/passports/src",
    "apps/platform/src",
    "packages/sources/src",
    "apps/worker/src",
)
NO_REINIT: Final[str] = "no-reinit-on-coding"
FRESH_INIT: Final[str] = "fresh-initialize-prompt"
INSTALL_PIN: Final[str] = "install-exact-pin"
INSTALL_OPEN: Final[str] = "install-without-pin"
CHANGE_ADD: Final[str] = "change-add-component"
SWITCH_SAVED: Final[str] = "switch-preserved-setup"
RELATIVE_ROOT: Final[str] = "unsupported-project-local"
AUTHOR_DIR: Final[str] = "author-directory"
ANTIGRAVITY: Final[str] = "antigravity-limitation"
CUSTOM_HOME: Final[str] = "custom-home-section"
RECOVER: Final[str] = "expert-recovery-no-dump"
LOGIN_SKIP: Final[str] = "login-skipped"
LOGIN_IDLE: Final[str] = "login-idle-no-upload"
PUBLISH_PRIV: Final[str] = "publish-private"
PUBLISH_PUB: Final[str] = "publish-public-filesystem"
AUTH_PUBLISH: Final[str] = "auth-required-publish"
COMPENSATED: Final[str] = "compensated-install"
KILL_AFTER: Final[str] = "kill-after-apply"
CONCURRENT: Final[str] = "concurrent-continue"
PENDING_RELOAD: Final[str] = "pending-reload-not-loaded"
STALE_VERIFIED_SCENARIOS: Final[tuple[str, ...]] = (
    FRESH_INIT,
    ANTIGRAVITY,
    INSTALL_PIN,
    INSTALL_OPEN,
    CHANGE_ADD,
    SWITCH_SAVED,
    CUSTOM_HOME,
    RELATIVE_ROOT,
    AUTHOR_DIR,
    LOGIN_IDLE,
)
DEBUG_PROVIDERS_ENV: Final[str] = "AI_STP_DEBUG_PROVIDERS"
SEEDED_SCENARIOS: Final[frozenset[str]] = frozenset({SWITCH_SAVED, CHANGE_ADD, PENDING_RELOAD})
# Valid ULID-shaped id that is not in the catalog. Docker ENFORCED would
# otherwise verify a recommended cursor pin and fail `install_unmet`.
UNMET_SETUP_ID: Final[str] = "setup_01ZZZZZZZZZZZZZZZZZZZZZZZZ"
UNMET_SETUP_VERSION: Final[str] = "1.0"
UNMET_INSTALL_LEAD: Final[str] = (
    "The named pin is absent from the catalog. A failed or compensated drain "
    "is the expected result. Do not retry with a recommended pin. "
)
UNAVAILABLE_MARKERS: Final[tuple[str, ...]] = (
    "UNAVAILABLE",
    "No capacity available",
    "(code 503)",
)
UNAVAILABLE_ATTEMPTS: Final[int] = 4
UNAVAILABLE_WAIT_SECONDS: Final[int] = 20
FILL_GAP_SECONDS: Final[int] = 90
NATIVE_FOLLOW_LIMIT: Final[int] = 16
_IDEMPOTENCY_KEY: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._~-]{16,128}$")
FORBIDDEN_LEAVES: Final[tuple[str, ...]] = (
    "install plan",
    "install approve",
    "install apply",
    "install transaction plan",
    "install transaction approve",
    "install transaction apply",
    "setup compose plan",
    "setup compose apply",
    "setup update plan",
    "setup update apply",
    "setup restore plan",
    "setup preserve plan",
    "setup scaffold plan",
    "setup scaffold apply",
    "setup import inspect",
    "setup import plan",
    "setup import register",
    "auth login",
    "auth complete",
    "auth logout",
    "sync push",
    "sync pull",
    "publication plan",
    "publication confirm",
    "publication visibility plan",
    "publication visibility confirm",
    "setup publish plan",
    "setup publish confirm",
    "help --agent",
    "help --path",
    "component adopt",
    "component discover",
    "component scaffold",
    "component publish",
    "component add",
    "select propose",
    "select confirm",
    "select eligibility",
    "select bundle",
    "registry acquire",
    "registry search",
    "registry port discover",
    "registry port inspect",
    "registry port plan",
    "registry port import",
    "config init",
    "task status",
    "task info",
    "task get",
    "--help",
    "project passport",
    "provider network",
)
UPLOAD_MARKERS: Final[tuple[str, ...]] = (
    "/publications",
    "/sync-plans",
    "/revisions",
    "sync push",
    "sync pull",
    "login.poll",
)
INSTRUCTION_NAMES: Final[frozenset[str]] = frozenset({"CLAUDE.md", "AGENTS.md"})
PROMPT: Final[str] = (
    "The user asked an unrelated coding question: what is 2+2? "
    "The ai-stp skill is installed under .agents/skills/ai-stp. Follow it. "
    "Do not start the initialize intent. Do not start the install intent. "
    "Do not type install plan, install approve, or install apply. "
    "Do not dump ai-stp help. Do not type ai-stp capabilities. "
    "Answer 2+2. Use the CLI only if the skill "
    "requires it for this question."
)
SKILL_TAIL: Final[str] = (
    " You are the coding agent. Run ai-stp yourself with your tools. Do not "
    "print commands for a human to run. The ai-stp CLI is already on PATH as "
    "ai-stp. The ai-stp skill is installed under .agents/skills/ai-stp. Follow "
    "it. Do not paste the skill into a harness file. Do not dump ai-stp help. "
    "Do not type ai-stp capabilities. "
    "Do not type install plan, install approve, or install apply. "
    "Do not type sync push or sync pull. "
    "Do not type setup publish plan or setup publish confirm. "
    "envelope.continuations[0].actor is a JSON field, not who you are. When "
    "that field is cli, execute argv. When it is human, relay the question "
    "through task answer. When it is external, show the payload once and stop. "
    "Do not task continue. Do not start account. provider-too-old is not login. "
    "Start already advanced the task. Do not insert task continue "
    "when actor is human or continuations are empty. Stop when continuations "
    "are empty. A printed command is not a completed initialize. Use your "
    "shell tool to run ai-stp. Do not invent task status, task info, or task get. "
    "Do not type component add. "
    "Do not pass an absolute path outside this workspace. "
    "The shell cwd is already the project. Do not cd. "
    "An absolute path inside --input JSON is for the CLI, not a shell cwd. "
    "Wait for each ai-stp JSON envelope on stdout. Foreground the CLI; "
    "do not background it. A backgrounded invocation is a failed turn. "
    "Do not type project passport. "
    "Do not type provider network. "
    "Do not run task answer without --value. "
    "If error.details.state is failed, stop. "
    "actor=human does not mean wait; you still run task answer with --value."
)
FOLLOW_ACTOR: Final[str] = (
    "If continuations is empty or error.details.state is failed, stop. "
    "If actor is human, you run task answer now with --value from this prompt; "
    "do not wait for a person. If actor is cli, execute argv. If actor is "
    "external, show the payload once and stop. Do not task continue. Do not "
    "start account. provider-too-old is not login."
)
VERIFIED_DRAIN: Final[str] = (
    "Pass only when the task state is completed and outcome.verified is true. "
    "A failed isolation drain is not success."
)
INPUT_CWD_HINT: Final[str] = (
    "The named --input file is already in the current directory. "
    "Execute the start argv as written. Do not cd. Do not open that file. "
    "Do not refuse because the file contains an absolute path."
)
SUPPORTED_SCENARIOS: Final[frozenset[str]] = frozenset(HAIKU_SCENARIOS)
LOADED_MARKERS: Final[tuple[str, ...]] = (
    "session loaded",
    "already loaded",
    "files are now loaded",
    "running process loaded",
)


@dataclass(frozen=True)
class Workspace:
    root: Path
    home: Path
    project: Path
    wrapper: Path


def bundled_cli() -> Path:
    """The in-venv executable. Isolated HOME must not go through `uv run`."""
    name = "ai-stp.exe" if os.name == "nt" else "ai-stp"
    held = Path(sys.executable).resolve().parent / name
    if held.is_file():
        return held
    found = shutil.which("ai-stp")
    if found:
        return Path(found)
    raise FileNotFoundError("ai-stp")


def repo_root() -> Path:
    raw = os.environ.get("AI_STP_REPO", "")
    if raw:
        return Path(raw)
    for parent in Path(__file__).resolve().parents:
        if (parent / "skills" / "canonical" / "ai-stp" / "SKILL.md").is_file():
            return parent
    return ROOT


def docker_pythonpath() -> str:
    return ":".join(f"/work/{item}" for item in _REPO_SRC)


def host_home() -> Path:
    """Login home. `uv run` rewrites HOME; Path.home() is not the host user."""
    raw = os.environ.get("AI_STP_HOST_HOME", "")
    if raw:
        return Path(raw)
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, OSError):
        return Path.home()


def optional_host_dir(env_name: str, fallback: Path) -> Path | None:
    raw = os.environ.get(env_name, "")
    held = Path(raw) if raw else fallback
    return held if held.is_dir() else None


def docker_cli_command(
    image: str,
    *,
    root: Path,
    repo: Path,
    project: Path,
    extra: str = "",
) -> str:
    """Privileged Docker so bwrap can ENFORCE. Does not weaken the host product path."""
    mounts = [
        f"-v {shlex.quote(str(repo.resolve()))}:/work:ro",
        f"-v {shlex.quote(str(root.resolve()))}:{shlex.quote(str(root.resolve()))}",
    ]
    providers = optional_host_dir(PROVIDERS_ENV, host_home() / ".local" / "bin")
    if providers is not None:
        mounts.append(f"-v {shlex.quote(str(providers.resolve()))}:/opt/providers:ro")
    toolchains = optional_host_dir(TOOLCHAINS_ENV, Path("/opt/nddev-toolchains"))
    if toolchains is not None:
        mounts.append(
            f"-v {shlex.quote(str(toolchains.resolve()))}:"
            f"{shlex.quote(str(toolchains.resolve()))}:ro"
        )
    env = [
        "--env HOME",
        "--env USERPROFILE",
        "--env XDG_CONFIG_HOME",
        "--env XDG_DATA_HOME",
        "--env AI_STP_FORCE_FILE_CREDENTIAL_STORE",
        f"-e PYTHONPATH={shlex.quote(docker_pythonpath())}",
        "-e PATH=/opt/providers:/work/.venv/bin:/usr/local/bin:/usr/bin:/bin",
    ]
    if extra:
        env.append("--env CODEX_HOME")
    uid = getattr(os, "getuid", lambda: 0)()
    gid = getattr(os, "getgid", lambda: 0)()
    inner = (
        f'/work/.venv/bin/python -m ai_stp_cli "$@"; status=$?; '
        f"chown -R {uid}:{gid} {shlex.quote(str(root.resolve()))}; exit $status"
    )
    return (
        "exec docker run --rm --privileged "
        + " ".join(mounts)
        + " "
        + " ".join(env)
        + f" -w {shlex.quote(str(project.resolve()))} "
        + f'{shlex.quote(image)} /bin/sh -c {shlex.quote(inner)} sh "$@"\n'
    )


def wrapper_script(
    *,
    home: Path,
    root: Path,
    log: Path,
    extra: str = "",
    docker_image: str | None = None,
    repo: Path | None = None,
) -> str:
    quoted_root = shlex.quote(str(root.resolve()))
    runner = (
        docker_cli_command(
            docker_image,
            root=root,
            repo=repo if repo is not None else repo_root(),
            project=root / "project",
            extra=extra,
        )
        if docker_image
        else f'exec {shlex.quote(str(bundled_cli()))} "$@"\n'
    )
    return (
        "#!/bin/sh\n"
        f"export HOME={shlex.quote(str(home))}\n"
        f"export USERPROFILE={shlex.quote(str(home))}\n"
        f"export XDG_CONFIG_HOME={shlex.quote(str(home / 'config'))}\n"
        f"export XDG_DATA_HOME={shlex.quote(str(home / 'data'))}\n"
        "export AI_STP_FORCE_FILE_CREDENTIAL_STORE=1\n"
        + extra
        + f"printf '%s\\n' \"$*\" >> {shlex.quote(str(log))}\n"
        f"root={quoted_root}\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in\n'
        "    ~*|/*)\n"
        '      case "$arg" in\n'
        '        "$root"|"$root"/*) ;;\n'
        "        *)\n"
        '          echo "ai-stp qualify wrapper refused a path outside the workspace" >&2\n'
        "          exit 78\n"
        "          ;;\n"
        "      esac\n"
        "      ;;\n"
        "  esac\n"
        "done\n" + runner
    )


def copy_qualify_skill(canonical: Path, skill: Path) -> None:
    """English SKILL.md + playbooks. Locale trees double what agy injects."""
    if skill.exists():
        shutil.rmtree(skill)
    skill.mkdir(parents=True, exist_ok=True)
    shutil.copy2(canonical / "SKILL.md", skill / "SKILL.md")
    references = canonical / "references"
    if references.is_dir():
        shutil.copytree(references, skill / "references")


def prepare_workspace(
    root: Path,
    *,
    repo: Path | None = None,
    scenario: str = NO_REINIT,
    docker_image: str | None = None,
) -> Workspace:
    """Isolated project + CLI home. Does not touch the caller's harness files."""
    root = root.expanduser().resolve()
    source = repo if repo is not None else repo_root()
    home = root / "home"
    project = root / "project"
    bin_dir = root / "bin"
    skill = project / ".agents" / "skills" / "ai-stp"
    home.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    skill.parent.mkdir(parents=True, exist_ok=True)
    copy_qualify_skill(source / "skills" / "canonical" / "ai-stp", skill)
    log = root / "cli.log"
    extra = ""
    if scenario == CUSTOM_HOME:
        codex = home / "codex-home"
        codex.mkdir(parents=True, exist_ok=True)
        extra = f"export CODEX_HOME={shlex.quote(str(codex))}\n"
    wrapper = bin_dir / "ai-stp"
    wrapper.write_text(
        wrapper_script(
            home=home,
            root=root,
            log=log,
            extra=extra,
            docker_image=docker_image,
            repo=source,
        ),
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    subprocess.run(["git", "init"], cwd=project, check=False, capture_output=True)
    workspace = Workspace(root=root, home=home, project=project, wrapper=wrapper)
    prepare_scenario(workspace, scenario)
    if scenario == CUSTOM_HOME and docker_image:
        seed_bound_codex(workspace)
    if docker_image and scenario in SEEDED_SCENARIOS:
        seed_for_scenario(workspace, scenario)
    return workspace


def prepare_scenario(workspace: Workspace, scenario: str) -> None:
    if scenario not in {AUTHOR_DIR, PUBLISH_PRIV, PUBLISH_PUB, AUTH_PUBLISH, CHANGE_ADD}:
        return
    tree = workspace.project / "demo-skill"
    tree.mkdir(parents=True, exist_ok=True)
    (tree / "SKILL.md").write_text("# Demo\n\nA local skill.\n", encoding="utf-8")


def registry_path(home: Path) -> Path:
    return home / "data" / "ai-stp" / "registry.sqlite"


def task_intents(home: Path) -> tuple[str, ...]:
    return tuple(
        str(item.get("intent") or "") for item in task_snapshots(home) if item.get("intent")
    )


def task_snapshots(home: Path) -> tuple[dict[str, object], ...]:
    """Registry task rows. A stub table with only `intent` is still readable."""
    place = registry_path(home)
    if not place.is_file():
        return ()
    with sqlite3.connect(place) as connection:
        names = {str(row[1]) for row in connection.execute("PRAGMA table_info(agent_task)")}
        if "intent" not in names:
            return ()
        selected = ["intent"]
        for name in ("state", "goal_satisfied", "outcome_json", "questions_json"):
            if name in names:
                selected.append(name)
        rows = connection.execute(f"SELECT {', '.join(selected)} FROM agent_task").fetchall()
        held: list[dict[str, object]] = []
        for row in rows:
            item: dict[str, object] = {"intent": str(row[0])}
            offset = 1
            if "state" in names:
                item["state"] = row[offset]
                offset += 1
            if "goal_satisfied" in names:
                item["goal_satisfied"] = row[offset]
                offset += 1
            if "outcome_json" in names:
                raw = row[offset]
                if isinstance(raw, str) and raw:
                    try:
                        parsed: object = json.loads(raw)
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        outcome = {
                            str(key): value
                            for key, value in cast(dict[object, object], parsed).items()
                        }
                        item["outcome"] = outcome
                        item["verified"] = outcome.get("verified")
                        item["wrote"] = outcome.get("wrote")
                        item["limitation"] = outcome.get("limitation")
                offset += 1
            if "questions_json" in names:
                raw_questions = row[offset]
                if isinstance(raw_questions, str) and raw_questions:
                    try:
                        parsed_questions: object = json.loads(raw_questions)
                    except json.JSONDecodeError:
                        parsed_questions = None
                    if isinstance(parsed_questions, list):
                        item["questions"] = [
                            {
                                str(key): value
                                for key, value in cast(dict[object, object], entry).items()
                            }
                            for entry in parsed_questions
                            if isinstance(entry, dict)
                        ]
            held.append(item)
        return tuple(held)


def mutating_verified(home: Path, intent: str) -> bool:
    """True when a drained mutating task completed with a verified native outcome."""
    for item in task_snapshots(home):
        if item.get("intent") != intent:
            continue
        if item.get("state") != "completed":
            continue
        if item.get("goal_satisfied") not in (True, 1, "1"):
            continue
        if item.get("verified") is True:
            return True
    return False


def install_unmet(home: Path) -> bool:
    """Install ran and did not verify. Compensation is not a verified success."""
    if mutating_verified(home, "install"):
        return False
    saw = False
    for item in task_snapshots(home):
        if item.get("intent") != "install":
            continue
        if item.get("state") == "completed" and item.get("goal_satisfied") in (True, 1, "1"):
            return False
        if item.get("state") in {"failed", "cancelled", "running"}:
            saw = True
    return saw


def question_ids_of(item: Mapping[str, object]) -> tuple[str, ...]:
    raw = item.get("questions")
    if not isinstance(raw, list):
        return ()
    held: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        question_id = entry.get("question_id")
        if question_id:
            held.append(str(question_id))
    return tuple(held)


def blocked_on(home: Path, intent: str, question_id: str) -> bool:
    for item in task_snapshots(home):
        if item.get("intent") != intent:
            continue
        if item.get("state") != "blocked":
            continue
        if question_id in question_ids_of(item):
            return True
    return False


def author_minted(home: Path) -> bool:
    for item in task_snapshots(home):
        if item.get("intent") != "author":
            continue
        if item.get("state") != "completed":
            continue
        if item.get("goal_satisfied") not in (True, 1, "1"):
            continue
        outcome = item.get("outcome")
        if not isinstance(outcome, dict):
            continue
        if outcome.get("minted") is not True:
            continue
        if outcome.get("setup_id") and outcome.get("component_id"):
            return True
    return False


def account_idle_honest(home: Path) -> bool:
    """Login showed an external code once. A failed drain is not idle."""
    saw_block = False
    for item in task_snapshots(home):
        if item.get("intent") != "account":
            continue
        if item.get("state") == "failed":
            return False
        if item.get("state") == "blocked" and "authorization" in question_ids_of(item):
            saw_block = True
        if item.get("state") == "completed":
            outcome = item.get("outcome")
            if (
                isinstance(outcome, dict)
                and outcome.get("action") == "login"
                and outcome.get("login_uploaded") is False
            ):
                return True
    return saw_block


def publish_honest(home: Path, *, visibility: str | None = None) -> bool:
    """Unsigned isolate blocks on authorization. Completed rows stay filesystem."""
    saw_block = False
    saw_complete = False
    for item in task_snapshots(home):
        if item.get("intent") != "publish":
            continue
        if item.get("state") == "failed":
            return False
        if item.get("state") == "blocked" and "authorization" in question_ids_of(item):
            saw_block = True
        if item.get("state") != "completed":
            continue
        outcome = item.get("outcome")
        if not isinstance(outcome, dict):
            continue
        if not outcome.get("object_id"):
            continue
        if outcome.get("source_binding_id"):
            return False
        if outcome.get("provenance") not in {"filesystem", None}:
            return False
        if visibility is not None and outcome.get("visibility") != visibility:
            return False
        saw_complete = True
    return saw_block or saw_complete


def switch_not_loaded(home: Path) -> bool:
    """Switch restored or is waiting on reload-session. Never loaded or killed."""
    saw = False
    for item in task_snapshots(home):
        if item.get("intent") != "switch":
            continue
        if item.get("state") == "failed":
            return False
        outcome = item.get("outcome") if isinstance(item.get("outcome"), dict) else {}
        if not isinstance(outcome, dict):
            outcome = {}
        if outcome.get("session_loaded") is True:
            return False
        if outcome.get("process_killed") is True:
            return False
        if item.get("state") == "blocked" and "reload-session" in question_ids_of(item):
            saw = True
        if (
            item.get("state") == "completed"
            and item.get("goal_satisfied") in (True, 1, "1")
            and item.get("verified") is True
            and outcome.get("session_loaded") is False
        ):
            saw = True
    return saw


def logged_invocations(workspace: Workspace) -> str:
    place = workspace.root / "cli.log"
    if not place.is_file():
        return ""
    return place.read_text(encoding="utf-8")


def choreographed(workspace: Workspace) -> bool:
    """Forbidden leaves in argv. A pasted --value must not score as choreography.

    Unscoped `help` / `help --json` dump the full registry without spelling
    `--agent`. `capabilities --json` lists every `command_path`, including
    `install plan`. Either dump is how a weak model learns choreography.
    """
    for line in logged_invocations(workspace).splitlines():
        head = line.split(" --value", 1)[0]
        held = head.removeprefix("ai-stp ").lstrip()
        if any(leaf in held for leaf in FORBIDDEN_LEAVES):
            return True
        if held.split()[:1] in (["help"], ["capabilities"]):
            return True
    return False


def invented_instruction_files(
    workspace: Workspace, *, allowed: frozenset[Path] = frozenset()
) -> bool:
    permitted = {path.resolve() for path in allowed}
    for path in workspace.home.rglob("*"):
        if not path.is_file():
            continue
        if path.name not in INSTRUCTION_NAMES and path.suffix != ".mdc":
            continue
        if path.resolve() in permitted:
            continue
        return True
    return False


def debug_provider(binary: str) -> Path | None:
    named = os.environ.get(DEBUG_PROVIDERS_ENV, "").strip()
    if named:
        place = Path(named) / binary
        return place if place.is_file() else None
    candidate = host_home() / "Developer" / "nddev" / "setup-systems" / "target" / "debug" / binary
    return candidate if candidate.is_file() else None


def seed_bound_codex(workspace: Workspace) -> None:
    """Configured debug codex only. Initialize must not PATH-discover a provider."""
    provider = debug_provider("codex-setup-system")
    if provider is None:
        return
    bound = workspace.root / "codex-setup-system"
    shutil.copy2(provider, bound)
    bound.chmod(bound.stat().st_mode | 0o111)
    held = subprocess.run(
        [
            str(workspace.wrapper),
            "config",
            "set",
            "--set",
            f"provider.paths.codex={bound}",
            "--json",
        ],
        cwd=workspace.project,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    (workspace.root / "seed-provider.log").write_text(
        f"exit={held.returncode}\n{held.stdout}\n{held.stderr}\n",
        encoding="utf-8",
    )


def custom_home_agents(workspace: Workspace) -> Path:
    return workspace.home / "codex-home" / "AGENTS.md"


def custom_home_section_landed(workspace: Workspace) -> bool:
    place = custom_home_agents(workspace)
    if not place.is_file():
        return False
    text = place.read_text(encoding="utf-8")
    return ":::begin-ai-stp" in text and ":::end-ai-stp" in text


def initialize_wrote_codex(home: Path) -> bool:
    for item in task_snapshots(home):
        if item.get("intent") != "initialize":
            continue
        if item.get("state") != "completed":
            continue
        if item.get("goal_satisfied") not in (True, 1, "1"):
            continue
        if item.get("wrote") is not True:
            continue
        outcome = item.get("outcome")
        harness = outcome.get("harness_id") if isinstance(outcome, dict) else None
        if harness == "codex":
            return True
    return False


def marked_instruction_files(workspace: Workspace) -> frozenset[Path]:
    found: set[Path] = set()
    for path in workspace.home.rglob("*"):
        if not path.is_file():
            continue
        if path.name not in INSTRUCTION_NAMES and path.suffix != ".mdc":
            continue
        text = path.read_text(encoding="utf-8")
        if ":::begin-ai-stp" in text and ":::end-ai-stp" in text:
            found.add(path.resolve())
    return frozenset(found)


def initialize_honest(home: Path) -> bool:
    """Completed initialize with a write or the catalogued antigravity limitation."""
    for item in task_snapshots(home):
        if item.get("intent") != "initialize":
            continue
        if item.get("state") != "completed":
            continue
        if item.get("goal_satisfied") not in (True, 1, "1"):
            continue
        if item.get("wrote") is True:
            return True
        if item.get("limitation") == ANTIGRAVITY_LIMITATION and item.get("wrote") is False:
            return True
    return False


def initialize_antigravity_limitation(home: Path) -> bool:
    for item in task_snapshots(home):
        if item.get("intent") != "initialize":
            continue
        if item.get("state") != "completed":
            continue
        if item.get("goal_satisfied") not in (True, 1, "1"):
            continue
        if item.get("wrote") is not False:
            continue
        if item.get("limitation") != ANTIGRAVITY_LIMITATION:
            continue
        outcome = item.get("outcome")
        harness = outcome.get("harness_id") if isinstance(outcome, dict) else None
        if harness == "antigravity":
            return True
    return False


def initialize_wrote(home: Path) -> bool:
    return any(
        item.get("intent") == "initialize" and item.get("wrote") is True
        for item in task_snapshots(home)
    )


def cursor_pin() -> str:
    from ai_stp_cli.application.install_task import recommend_setup

    pin = recommend_setup("cursor")
    if pin is None:
        return "cursor@baseline"
    return f"{pin.setup_id}@{pin.setup_version}"


def extra_cursor_ref() -> str:
    from ai_stp_contracts.first_party import catalog_identity

    base = catalog_identity("cursor", "baseline")
    full = catalog_identity("cursor", "full-auto")
    held = {item.stable_id for item in base.component_refs}
    extra = next(item for item in full.component_refs if item.stable_id not in held)
    return f"{extra.stable_id}@{extra.version}"


def change_component_ref(workspace: Workspace) -> str:
    """Authored additive pin when seeded; catalog extra is not composable onto baseline."""
    place = workspace.root / "seed-component.txt"
    if place.is_file():
        text = place.read_text(encoding="utf-8").strip()
        if "@" in text:
            return text
    return extra_cursor_ref()


def seed_for_scenario(workspace: Workspace, scenario: str) -> None:
    if scenario in {SWITCH_SAVED, PENDING_RELOAD}:
        seed_cursor_install(workspace)
    elif scenario == CHANGE_ADD:
        seed_authored_component(workspace)


def _seed_intent(
    workspace: Workspace, *, intent: str, key: str, facts: dict[str, str]
) -> dict[str, object]:
    input_path = workspace.root / f"seed-{intent}.json"
    input_path.write_text(json.dumps(facts), encoding="utf-8")
    result = subprocess.run(
        [
            str(workspace.wrapper),
            "task",
            "start",
            "--intent",
            intent,
            "--idempotency-key",
            key,
            "--input",
            str(input_path),
            "--json",
        ],
        cwd=workspace.project,
        check=False,
        capture_output=True,
        text=True,
    )
    (workspace.root / "seed.log").write_text(
        f"exit={result.returncode}\n{result.stdout}\n{result.stderr}\n",
        encoding="utf-8",
    )
    try:
        parsed: object = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return _mapping(cast(object, parsed))


def seed_cursor_install(workspace: Workspace) -> None:
    """Install the recommended cursor pin so switch has a user working config."""
    pin = cursor_pin()
    setup_id, separator, version = pin.partition("@")
    if not separator:
        return
    _seed_intent(
        workspace,
        intent="install",
        key="qualify-seed-install-01",
        facts={
            "harness_id": "cursor",
            "setup_id": setup_id,
            "setup_version": version,
            "project_root": str(workspace.project.resolve()),
        },
    )


def seed_authored_component(workspace: Workspace) -> None:
    """Register a unique local skill so change-add does not collide with baseline."""
    body = _seed_intent(
        workspace,
        intent="author",
        key="qualify-seed-author-01",
        facts={
            "directory": str(workspace.project / "demo-skill"),
            "harness_id": "cursor",
            "component_type": "skill",
            "name": "demo",
            "license_spdx": "MIT",
        },
    )
    outcome = _mapping(_mapping(body.get("data")).get("outcome"))
    component_id = str(outcome.get("component_id") or "")
    version = str(outcome.get("component_version") or "")
    if component_id and version:
        (workspace.root / "seed-component.txt").write_text(
            f"{component_id}@{version}",
            encoding="utf-8",
        )


def unmet_install_facts(project: str) -> dict[str, str]:
    return {
        "harness_id": "cursor",
        "project_root": project,
        "setup_id": UNMET_SETUP_ID,
        "setup_version": UNMET_SETUP_VERSION,
    }


def intent_input(workspace: Workspace, name: str, facts: Mapping[str, str]) -> Path:
    """Facts file for `--input`. Written in the project cwd and the throwaway root."""
    body = json.dumps(dict(facts))
    place = workspace.project / f"{name}-input.json"
    place.write_text(body, encoding="utf-8")
    (workspace.root / f"{name}-input.json").write_text(body, encoding="utf-8")
    return place


def start_command(intent: str, *, input_path: Path | None = None) -> str:
    """Exact first argv. Weak models follow a concrete start line, not a verb."""
    command = f"ai-stp task start --intent {intent} --idempotency-key {intent}-session-01"
    if input_path is not None:
        command += f" --input {input_path.name}"
    return command + " --json"


def prompt_for(scenario: str, workspace: Workspace) -> str:
    project = str(workspace.project.resolve())
    if scenario == NO_REINIT:
        return PROMPT
    if scenario == FRESH_INIT:
        return INITIALIZE_PROMPT + SKILL_TAIL
    if scenario == INSTALL_OPEN:
        install_in = intent_input(
            workspace,
            "install",
            {"harness_id": "cursor", "project_root": project},
        )
        return (
            f"Harness: cursor. Execute "
            f"{start_command('install', input_path=install_in)}. {INPUT_CWD_HINT} "
            f"{FOLLOW_ACTOR} {VERIFIED_DRAIN} Do not quiz the catalog. Do not type "
            "the install command family." + SKILL_TAIL
        )
    if scenario == INSTALL_PIN:
        pin = cursor_pin()
        setup_id, _, version = pin.partition("@")
        install_in = intent_input(
            workspace,
            "install",
            {
                "harness_id": "cursor",
                "setup_id": setup_id,
                "setup_version": version,
                "project_root": project,
            },
        )
        return (
            f"Harness: cursor. Exact pin {pin}. Execute "
            f"{start_command('install', input_path=install_in)}. {INPUT_CWD_HINT} "
            f"{FOLLOW_ACTOR} {VERIFIED_DRAIN} Do not type the install command "
            "family." + SKILL_TAIL
        )
    if scenario == CHANGE_ADD:
        extra = change_component_ref(workspace)
        component_id, separator, version = extra.partition("@")
        seeded = (workspace.root / "seed-component.txt").is_file() and bool(separator)
        change_start = start_command("change")
        answers = (
            "Answer harness-id with cursor. Answer component-ref with that extra "
            f"component pin. Answer project-root with {project}. "
        )
        if seeded:
            change_in = intent_input(
                workspace,
                "change",
                {
                    "harness_id": "cursor",
                    "component_id": component_id,
                    "component_version": version,
                    "project_root": project,
                },
            )
            change_start = start_command("change", input_path=change_in)
            answers = INPUT_CWD_HINT + " "
            lead = "Harness: cursor. "
        else:
            lead = f"Harness: cursor. Absolute project root: {project}. "
        return (
            f"{lead}"
            f"A saved cursor setup {cursor_pin()} must stay restorable. "
            f"The change intent must keep that setup id and include "
            f"{extra}. Do not type component add. First command: "
            f"{change_start}. {FOLLOW_ACTOR} {VERIFIED_DRAIN} {answers}"
            "Do not wait for a person." + SKILL_TAIL
        )
    if scenario == SWITCH_SAVED:
        switch_in = intent_input(
            workspace,
            "switch",
            {"harness_id": "cursor", "project_root": project},
        )
        return (
            f"Harness: cursor. Execute "
            f"{start_command('switch', input_path=switch_in)}. {INPUT_CWD_HINT} "
            f"{FOLLOW_ACTOR} {VERIFIED_DRAIN} "
            "Restore the last working user setup (preserved_setup), not the "
            "upstream default. Never kill this process. Do not claim the running "
            "session loaded new files. Answer reload-session with done. "
            "After start blocks, run the emitted task answer argv with "
            "--value done in your shell. Do not print done as the reply." + SKILL_TAIL
        )
    if scenario == RELATIVE_ROOT:
        install_in = intent_input(workspace, "install", {"harness_id": "cursor"})
        return (
            "Harness: cursor. Execute "
            f"{start_command('install', input_path=install_in)}. {INPUT_CWD_HINT} "
            f"{FOLLOW_ACTOR} Then send exactly `--value relative` for "
            "project-root and stop. A second project-root question is the expected "
            "block. Do not invent a path, --help, or task status. "
            "Do not silently install globally." + SKILL_TAIL
        )
    if scenario == AUTHOR_DIR:
        directory = workspace.project / "demo-skill"
        author_in = intent_input(
            workspace,
            "author",
            {
                "harness_id": "cursor",
                "directory": str(directory.resolve()),
                "component_type": "skill",
                "name": "demo",
                "license_spdx": "MIT",
            },
        )
        return (
            "Harness: cursor. Author demo-skill as one skill named demo, license MIT. "
            f"Do not type component scaffold. First command: "
            f"{start_command('author', input_path=author_in)}. {INPUT_CWD_HINT} "
            f"{FOLLOW_ACTOR} Do not wait for a person. Never type task get or "
            "task status." + SKILL_TAIL
        )
    if scenario == ANTIGRAVITY:
        return (
            f"Harness is antigravity. Execute {INITIALIZE_START}. {FOLLOW_ACTOR} "
            "Answer harness-id with the single token antigravity. "
            "Do not invent a global instruction file the product ignores." + SKILL_TAIL
        )
    if scenario == CUSTOM_HOME:
        init_in = intent_input(workspace, "initialize", {"harness_id": "codex"})
        return (
            "Harness is codex. CODEX_HOME is already set. Execute "
            f"{start_command('initialize', input_path=init_in)}. {INPUT_CWD_HINT} "
            f"{FOLLOW_ACTOR} The section must land in CODEX_HOME/AGENTS.md. "
            "Do not write AGENTS.md yourself. Do not wait for a person." + SKILL_TAIL
        )
    if scenario == RECOVER:
        return (
            "An install operation failed or is partial. Do not list the workspace. "
            "First command: "
            "ai-stp task intents --json. Then follow recover.md. Do not dump "
            "help --agent. install recover is allowed; install apply is not. "
            "Never type task get or task status. If details.state is failed, stop." + SKILL_TAIL
        )
    if scenario == LOGIN_SKIP:
        return (
            "The user is already signed in. Do not run ai-stp. "
            "Do not start the account intent. Do not type auth login. "
            "Do not upload. Do not publish. Confirm that no catalog PUT is required."
        )
    if scenario == LOGIN_IDLE:
        account_in = intent_input(workspace, "account", {"action": "login", "provider": "github"})
        return (
            f"Execute {start_command('account', input_path=account_in)}. {INPUT_CWD_HINT} "
            "Show an external payload once, then stop. Do not task continue. "
            "Do not upload, publish, or call sync." + SKILL_TAIL
        )
    if scenario in {PUBLISH_PRIV, PUBLISH_PUB, AUTH_PUBLISH}:
        visibility = "private" if scenario == PUBLISH_PRIV else "public"
        publish_in = intent_input(
            workspace,
            "publish",
            {
                "visibility": visibility,
                "provider": "github",
                "directory": "demo-skill",
            },
        )
        if scenario == PUBLISH_PRIV:
            lead = "Publish demo-skill as a private local object. No GitHub repo. "
        elif scenario == PUBLISH_PUB:
            lead = (
                "Publish demo-skill publicly with filesystem provenance. "
                "Do not invent a git remote. "
            )
        else:
            lead = "Publish demo-skill. Auth is required. "
        return (
            f"{lead}Execute {start_command('publish', input_path=publish_in)}. "
            f"{INPUT_CWD_HINT} {FOLLOW_ACTOR} Show an external payload once, then stop. "
            "Do not type publication plan. Do not type setup publish plan." + SKILL_TAIL
        )
    if scenario == COMPENSATED:
        install_in = intent_input(workspace, "install", unmet_install_facts(project))
        return (
            "Harness: cursor. Execute "
            f"{start_command('install', input_path=install_in)}. {INPUT_CWD_HINT} "
            f"{UNMET_INSTALL_LEAD}{FOLLOW_ACTOR} "
            "If the envelope is not ok, AI_STP_COMPENSATED, or details.state is "
            "failed, stop. Compensation is not success. Never type task get or "
            "task status. Do not type the install command family." + SKILL_TAIL
        )
    if scenario == KILL_AFTER:
        install_in = intent_input(workspace, "install", unmet_install_facts(project))
        return (
            "Harness: cursor. An apply was interrupted. Execute "
            f"{start_command('install', input_path=install_in)}. {INPUT_CWD_HINT} "
            f"{UNMET_INSTALL_LEAD}{FOLLOW_ACTOR} "
            "Do not start a second apply. If actor is cli and argv is task continue, "
            "execute it once. If details.state is failed, stop. Never type task get "
            "or task status. Do not type install apply." + SKILL_TAIL
        )
    if scenario == CONCURRENT:
        install_in = intent_input(workspace, "install", unmet_install_facts(project))
        return (
            "Harness: cursor. Execute "
            f"{start_command('install', input_path=install_in)}. {INPUT_CWD_HINT} "
            f"{UNMET_INSTALL_LEAD}{FOLLOW_ACTOR} "
            "Continue the open task once. If continue is refused as a conflict, stop. "
            "Do not fire a second parallel continue. Never type task get or "
            "task status. Do not type install apply." + SKILL_TAIL
        )
    if scenario == PENDING_RELOAD:
        switch_in = intent_input(
            workspace,
            "switch",
            {"harness_id": "cursor", "project_root": project},
        )
        return (
            "Harness: cursor. Execute "
            f"{start_command('switch', input_path=switch_in)}. {INPUT_CWD_HINT} "
            f"{FOLLOW_ACTOR} "
            "Restore the last working user setup. Never kill this process. "
            "Do not claim the running session loaded new files. "
            "After start blocks on reload-session, run the emitted task answer argv "
            "with --value done in your shell. Do not print done as the reply. "
            "outcome.session_loaded must stay false." + SKILL_TAIL
        )
    raise ValueError(scenario)


def followed_through(workspace: Workspace) -> bool:
    """Start alone is not a driven journey. Continue or answer must appear."""
    log = logged_invocations(workspace)
    return "task continue" in log or "task answer" in log


def answered_without_value(workspace: Workspace) -> bool:
    """Human argv without --value is not an answer."""
    return any(
        "task answer" in line and "--value" not in line
        for line in logged_invocations(workspace).splitlines()
    )


def answered_token(log: str, value: str) -> bool:
    """True when some argv used `--value <value>` as adjacent tokens."""
    for line in log.splitlines():
        tokens = line.split()
        for index, token in enumerate(tokens):
            if token == "--value" and index + 1 < len(tokens) and tokens[index + 1] == value:
                return True
    return False


def escaped_workspace(workspace: Workspace) -> bool:
    """True when cli.log passed an absolute path outside the throwaway root."""
    root = workspace.root.resolve()
    for line in logged_invocations(workspace).splitlines():
        for token in line.split():
            if token.startswith("~"):
                return True
            if not token.startswith("/"):
                continue
            try:
                held = Path(token).resolve()
            except OSError:
                return True
            if not held.is_relative_to(root):
                return True
    return False


def incomplete_capacity_hit(
    workspace: Workspace,
    stdout: str,
    stderr: str,
    scenario: str | None = None,
) -> bool:
    """Retry a 503 unless the log already scores or followed through."""
    if not run_was_unavailable(stdout, stderr):
        return False
    if choreographed(workspace):
        return False
    if followed_through(workspace):
        return False
    if scenario is not None and drove_cli(workspace):
        try:
            if score(scenario, workspace) == "pass":
                return False
        except ValueError:
            pass
    return True


def score_no_reinit(home: Path) -> MeasuredStatus:
    """Fail when initialize or install ran. Missing registry means the CLI was not used."""
    intents = task_intents(home)
    if "initialize" in intents or "install" in intents:
        return "fail"
    return "pass"


def score(scenario: str, workspace: Workspace) -> MeasuredStatus:
    if choreographed(workspace):
        return "fail"
    if escaped_workspace(workspace):
        return "fail"
    if answered_without_value(workspace):
        return "fail"
    intents = task_intents(workspace.home)
    log = logged_invocations(workspace)
    if scenario == NO_REINIT:
        return score_no_reinit(workspace.home)
    if scenario in {FRESH_INIT, ANTIGRAVITY}:
        if "initialize" not in intents:
            return "fail"
        if "account" in intents:
            return "fail"
        if scenario == ANTIGRAVITY:
            if not initialize_antigravity_limitation(workspace.home):
                return "fail"
            if invented_instruction_files(workspace):
                return "fail"
            return "pass"
        if not initialize_honest(workspace.home):
            return "fail"
        wrote = initialize_wrote(workspace.home)
        allowed = marked_instruction_files(workspace) if wrote else frozenset()
        if wrote and not allowed:
            return "fail"
        if invented_instruction_files(workspace, allowed=allowed):
            return "fail"
        return "pass"
    if scenario == CUSTOM_HOME:
        if "initialize" not in intents:
            return "fail"
        if "account" in intents:
            return "fail"
        if invented_instruction_files(
            workspace, allowed=frozenset({custom_home_agents(workspace)})
        ):
            return "fail"
        if not initialize_wrote_codex(workspace.home):
            return "fail"
        if not custom_home_section_landed(workspace):
            return "fail"
        return "pass"
    if scenario in {INSTALL_PIN, INSTALL_OPEN}:
        if "install" not in intents:
            return "fail"
        return "pass" if mutating_verified(workspace.home, "install") else "fail"
    if scenario == CHANGE_ADD:
        if "change" not in intents:
            return "fail"
        return "pass" if mutating_verified(workspace.home, "change") else "fail"
    if scenario == SWITCH_SAVED:
        if "switch" not in intents:
            return "fail"
        return "pass" if mutating_verified(workspace.home, "switch") else "fail"
    if scenario == RELATIVE_ROOT:
        if "install" not in intents:
            return "fail"
        if invented_instruction_files(workspace):
            return "fail"
        if not answered_token(log, "relative"):
            return "fail"
        if mutating_verified(workspace.home, "install"):
            return "fail"
        if not blocked_on(workspace.home, "install", "project-root"):
            return "fail"
        return "pass"
    if scenario == AUTHOR_DIR:
        if "author" not in intents:
            return "fail"
        return "pass" if author_minted(workspace.home) else "fail"
    if scenario == RECOVER:
        if "help --agent" in log:
            return "fail"
        if "task intents" not in log:
            return "fail"
        return "pass"
    if scenario == LOGIN_SKIP:
        if any(marker in log for marker in UPLOAD_MARKERS):
            return "fail"
        if drove_cli(workspace):
            return "fail"
        return "pass"
    if scenario == LOGIN_IDLE:
        if any(marker in log for marker in UPLOAD_MARKERS):
            return "fail"
        if "account" not in intents:
            return "fail"
        return "pass" if account_idle_honest(workspace.home) else "fail"
    if scenario in {PUBLISH_PRIV, PUBLISH_PUB, AUTH_PUBLISH}:
        if any(marker in log for marker in UPLOAD_MARKERS):
            return "fail"
        if "github.com" in log:
            return "fail"
        if "publish" not in intents:
            return "fail"
        wanted = None
        if scenario == PUBLISH_PRIV:
            wanted = "private"
        elif scenario == PUBLISH_PUB:
            wanted = "public"
        return "pass" if publish_honest(workspace.home, visibility=wanted) else "fail"
    if scenario in {COMPENSATED, KILL_AFTER, CONCURRENT}:
        if "install" not in intents:
            return "fail"
        return "pass" if install_unmet(workspace.home) else "fail"
    if scenario == PENDING_RELOAD:
        if "switch" not in intents:
            return "fail"
        blob = model_output(workspace).lower()
        if any(marker in blob for marker in LOADED_MARKERS):
            return "fail"
        return "pass" if switch_not_loaded(workspace.home) else "fail"
    raise ValueError(scenario)


def model_output(workspace: Workspace) -> str:
    place = workspace.root / "agy.stdout"
    if not place.is_file():
        return ""
    return place.read_text(encoding="utf-8")


def run_was_unavailable(stdout: str, stderr: str) -> bool:
    blob = f"{stdout}\n{stderr}"
    return any(marker in blob for marker in UNAVAILABLE_MARKERS)


def drove_cli(workspace: Workspace) -> bool:
    return bool(logged_invocations(workspace).strip())


def run_was_background_killed(stderr: str) -> bool:
    """agy SUCCESS after it SIGTERM'd a backgrounded ai-stp is not a scored fail."""
    return "terminating" in stderr and "background task" in stderr


def capacity_miss(stdout: str, stderr: str, workspace: Workspace) -> bool:
    """A 503 with an empty cli.log is unrun. Tools already invoked are scored."""
    return run_was_unavailable(stdout, stderr) and not drove_cli(workspace)


def _overlay_body(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        return {}
    items = cast(dict[object, object], parsed)
    return {str(key): value for key, value in items.items()}


def _haiku_map(body: Mapping[str, object]) -> dict[str, object]:
    haiku_raw = body.get("haiku")
    if not isinstance(haiku_raw, dict):
        return {}
    raw_items = cast(dict[object, object], haiku_raw)
    return {str(key): value for key, value in raw_items.items()}


def unrun_cells(haiku: Mapping[str, object]) -> tuple[tuple[str, int], ...]:
    """Missing and not_run only. Scored pass/fail stay put."""
    held: list[tuple[str, int]] = []
    for scenario in HAIKU_SCENARIOS:
        for run in range(HAIKU_RUNS):
            if haiku.get(f"{scenario}:{run}") not in {"pass", "fail"}:
                held.append((scenario, run))
    return tuple(held)


def next_fill_cell(
    pending: tuple[tuple[str, int], ...],
    skipped: set[tuple[str, int]],
    *,
    rotate_from: tuple[str, int] | None = None,
) -> tuple[str, int] | None:
    """Prefer an unrun cell that did not 503 in this walk. Empty-log 503 stays unrun.

    When every remaining cell already 503'd, step past `rotate_from` instead of
    retrying only `pending[0]` until max-attempts expire.
    """
    if not pending:
        return None
    for cell in pending:
        if cell not in skipped:
            return cell
    if rotate_from in pending:
        return pending[(pending.index(rotate_from) + 1) % len(pending)]
    return pending[0]


def write_cell(path: Path, scenario: str, run: int, status: MeasuredStatus) -> None:
    if scenario not in HAIKU_SCENARIOS:
        raise ValueError(scenario)
    body = _overlay_body(path)
    haiku = _haiku_map(body)
    haiku[f"{scenario}:{run}"] = status
    body["haiku"] = haiku
    body["agy_model"] = AGY_MODEL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_native_cell(path: Path, harness: str, platform: str, status: MeasuredStatus) -> None:
    if harness not in HARNESS_ID_ORDER or platform not in PLATFORMS:
        raise ValueError(f"{harness}:{platform}")
    body = _overlay_body(path)
    native_raw = body.get("native")
    native: dict[str, object] = {}
    if isinstance(native_raw, dict):
        raw_items = cast(dict[object, object], native_raw)
        native = {str(key): value for key, value in raw_items.items()}
    native[f"{harness}:{platform}"] = status
    body["native"] = native
    body["agy_model"] = AGY_MODEL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def isolation_snapshot() -> dict[str, object]:
    """Host probe. Unavailable is not a native pass."""
    from ai_stp_cli.provider.network_launcher import discover_launcher
    from ai_stp_cli.provider.protocol_v2 import NetworkEnforcement

    _launcher, capability = discover_launcher()
    if capability.enforcement is NetworkEnforcement.ENFORCED:
        status = "enforced"
    elif capability.enforcement is NetworkEnforcement.UNAVAILABLE:
        status = "unavailable"
    else:
        status = "not_run"
    held: dict[str, object] = {
        "status": status,
        "os_name": capability.os_name,
        "evidence": list(capability.evidence),
    }
    if capability.launcher_id:
        held["launcher_id"] = capability.launcher_id
    return held


def write_isolation(path: Path, snapshot: Mapping[str, object]) -> None:
    body = _overlay_body(path)
    body["isolation"] = dict(snapshot)
    body["agy_model"] = AGY_MODEL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    items = cast(dict[object, object], value)
    return {str(key): item for key, item in items.items()}


def run_cli_json(argv: list[str]) -> dict[str, object]:
    result = subprocess.run(
        [str(bundled_cli()), *argv],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        parsed: object = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError((result.stderr or result.stdout)[-2000:]) from error
    if not isinstance(parsed, dict):
        raise RuntimeError("cli envelope is not an object")
    held = _mapping(cast(object, parsed))
    held["_exit"] = result.returncode
    return held


def follow_cli_continuations(body: Mapping[str, object]) -> dict[str, object]:
    current = dict(body)
    for _ in range(NATIVE_FOLLOW_LIMIT):
        raw = current.get("continuations")
        if not isinstance(raw, list) or not raw:
            return current
        item = _mapping(cast(object, raw[0]))
        argv_raw = item.get("argv")
        if item.get("actor") != "cli" or not isinstance(argv_raw, list):
            return current
        argv = [str(token) for token in cast(list[object], argv_raw)]
        if argv[:1] == ["ai-stp"]:
            argv = argv[1:]
        if not argv:
            return current
        current = run_cli_json(argv)
    return current


def native_install_passed(report: Mapping[str, object]) -> bool:
    return (
        report.get("ok") is True
        and report.get("state") == "completed"
        and report.get("goal_satisfied") is True
        and report.get("verified") is True
        and report.get("marker_exists") is True
    )


def drive_native_install(input_path: Path, key: str) -> dict[str, object]:
    if _IDEMPOTENCY_KEY.fullmatch(key) is None:
        raise ValueError("the idempotency key is not a valid key")
    loaded: object = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("native input is not an object")
    harness = str(_mapping(cast(object, loaded)).get("harness_id") or "")
    marker = native_config_root(harness)
    body = follow_cli_continuations(
        run_cli_json(
            [
                "task",
                "start",
                "--intent",
                "install",
                "--idempotency-key",
                key,
                "--input",
                str(input_path),
                "--json",
            ]
        )
    )
    data = _mapping(body.get("data"))
    outcome = _mapping(data.get("outcome"))
    populated = native_marker_populated(marker)
    return {
        "harness": harness,
        "ok": body.get("ok"),
        "exit": body.get("_exit"),
        "state": data.get("state"),
        "goal_satisfied": data.get("goal_satisfied"),
        "verified": outcome.get("verified"),
        "setup_id": outcome.get("setup_id"),
        "marker": str(marker),
        "marker_exists": populated,
        "tree_digest": tree_digest(marker) if populated else "",
        "error": body.get("error"),
        "platform": native_platform(),
    }


def clear_cell(path: Path, scenario: str, run: int) -> None:
    """Drop an unexecuted cell. Never erase a scored pass or fail."""
    if scenario not in HAIKU_SCENARIOS:
        raise ValueError(scenario)
    if not path.is_file():
        return
    body = _overlay_body(path)
    haiku = _haiku_map(body)
    key = f"{scenario}:{run}"
    if haiku.get(key) in {"pass", "fail"}:
        return
    haiku.pop(key, None)
    body["haiku"] = haiku
    body["agy_model"] = AGY_MODEL
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def invalidate_scenario(path: Path, scenario: str) -> int:
    """Drop scored cells so fill can re-run them. Explicit; clear_cell will not."""
    if scenario not in HAIKU_SCENARIOS:
        raise ValueError(scenario)
    if not path.is_file():
        return 0
    body = _overlay_body(path)
    haiku = _haiku_map(body)
    dropped = 0
    for run in range(HAIKU_RUNS):
        key = f"{scenario}:{run}"
        if key in haiku:
            haiku.pop(key)
            dropped += 1
    body["haiku"] = haiku
    body["agy_model"] = AGY_MODEL
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return dropped


def invalidate_cell(path: Path, scenario: str, run: int) -> int:
    """Drop one scored overlay cell. `clear_cell` will not erase pass/fail."""
    if scenario not in HAIKU_SCENARIOS:
        raise ValueError(scenario)
    if run < 0 or run >= HAIKU_RUNS:
        raise ValueError(run)
    if not path.is_file():
        return 0
    body = _overlay_body(path)
    haiku = _haiku_map(body)
    key = f"{scenario}:{run}"
    if key not in haiku:
        return 0
    haiku.pop(key)
    body["haiku"] = haiku
    body["agy_model"] = AGY_MODEL
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 1


def invalidate_target(token: str) -> tuple[str, int | None]:
    """`install-without-pin` drops five cells; `install-without-pin:0` drops one."""
    name, separator, rest = token.partition(":")
    if separator and rest.isdigit() and name in HAIKU_SCENARIOS:
        run = int(rest)
        if 0 <= run < HAIKU_RUNS:
            return name, run
        raise ValueError(token)
    if token in HAIKU_SCENARIOS:
        return token, None
    raise ValueError(token)


def agy_argv(
    agy: Path,
    *,
    model: str = AGY_MODEL,
    prompt: str | None = None,
    print_timeout: str = "5m",
    add_dirs: Sequence[Path] | None = None,
) -> list[str]:
    text = PROMPT if prompt is None else prompt
    held = [
        str(agy),
        "--output-format",
        "json",
        "--model",
        model,
        "--mode",
        "accept-edits",
        "--dangerously-skip-permissions",
        "--print-timeout",
        print_timeout,
    ]
    seen: set[str] = set()
    for directory in add_dirs or ():
        resolved = str(Path(directory).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        held.extend(["--add-dir", resolved])
    held.append(f"--print={text}")
    return held


PROBE_PRINT: Final[str] = "Reply with the single word pong and nothing else."


def capacity_probe(agy: Path, *, model: str = AGY_MODEL) -> bool:
    """Cheap ping. A 503 here must not burn qualify retries."""
    try:
        result = subprocess.run(
            agy_argv(agy, model=model, prompt=PROBE_PRINT, print_timeout="20s"),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return not run_was_unavailable(result.stdout, result.stderr)


def run_agy(
    workspace: Workspace,
    *,
    agy: Path,
    model: str = AGY_MODEL,
    timeout: int = 300,
    prompt: str | None = None,
    scenario: str | None = None,
) -> int:
    env = os.environ.copy()
    env["PATH"] = f"{workspace.wrapper.parent}{os.pathsep}{env.get('PATH', '')}"
    log = workspace.root / "cli.log"
    code = 1
    for attempt in range(UNAVAILABLE_ATTEMPTS):
        if log.is_file():
            log.write_text("", encoding="utf-8")
        result = subprocess.run(
            agy_argv(
                agy,
                model=model,
                prompt=prompt,
                add_dirs=(workspace.root, workspace.project),
            ),
            cwd=workspace.project,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        (workspace.root / "agy.stdout").write_text(result.stdout, encoding="utf-8")
        (workspace.root / "agy.stderr").write_text(result.stderr, encoding="utf-8")
        code = result.returncode
        if not run_was_unavailable(result.stdout, result.stderr):
            return code
        if not incomplete_capacity_hit(workspace, result.stdout, result.stderr, scenario):
            return code
        if not drove_cli(workspace):
            return code
        if attempt + 1 < UNAVAILABLE_ATTEMPTS:
            time.sleep(UNAVAILABLE_WAIT_SECONDS)
    return code


def qualify_one(
    *,
    root: Path,
    scenario: str,
    run: int,
    measured: Path | None,
    agy: Path,
    timeout: int,
    probe: bool,
    docker_image: str | None = None,
) -> int:
    if probe and not capacity_probe(agy):
        print(
            json.dumps(
                {
                    "scenario": scenario,
                    "run": run,
                    "status": "not_run",
                    "agy": 1,
                    "reason": "unavailable",
                }
            )
        )
        return 1
    workspace = prepare_workspace(root, scenario=scenario, docker_image=docker_image)
    prompt = prompt_for(scenario, workspace)
    code = run_agy(workspace, agy=agy, timeout=timeout, prompt=prompt, scenario=scenario)
    stdout = (workspace.root / "agy.stdout").read_text(encoding="utf-8")
    stderr = (workspace.root / "agy.stderr").read_text(encoding="utf-8")
    if incomplete_capacity_hit(workspace, stdout, stderr, scenario):
        if measured is not None:
            clear_cell(measured, scenario, run)
        print(
            json.dumps(
                {
                    "scenario": scenario,
                    "run": run,
                    "status": "not_run",
                    "agy": code,
                    "reason": "unavailable",
                }
            ),
            flush=True,
        )
        return 1
    if code != 0 and not drove_cli(workspace):
        status: MeasuredStatus = "fail"
    else:
        status = score(scenario, workspace)
    if run_was_background_killed(stderr) and status == "fail":
        if measured is not None:
            clear_cell(measured, scenario, run)
        print(
            json.dumps(
                {
                    "scenario": scenario,
                    "run": run,
                    "status": "not_run",
                    "agy": code,
                    "reason": "backgrounded",
                }
            ),
            flush=True,
        )
        return 1
    if measured is not None:
        write_cell(measured, scenario, run, status)
    print(json.dumps({"scenario": scenario, "run": run, "status": status, "agy": code}), flush=True)
    return 0 if status == "pass" else 1


def fill_unrun(
    parent: Path,
    *,
    measured: Path,
    agy: Path,
    timeout: int,
    max_attempts: int,
    gap_seconds: int,
    docker_image: str | None = None,
) -> int:
    """One cell at a time. 503 stays unrun; the next attempt may take a different cell."""
    passed = 0
    skipped: set[tuple[str, int]] = set()
    last: tuple[str, int] | None = None
    for attempt in range(max_attempts):
        pending = unrun_cells(_haiku_map(_overlay_body(measured)))
        chosen = next_fill_cell(pending, skipped, rotate_from=last)
        if chosen is None:
            break
        last = chosen
        scenario, run = chosen
        cell_root = parent / f"{scenario}-{run}-{attempt}"
        if cell_root.exists():
            shutil.rmtree(cell_root)
        code = qualify_one(
            root=cell_root,
            scenario=scenario,
            run=run,
            measured=measured,
            agy=agy,
            timeout=timeout,
            probe=False,
            docker_image=docker_image,
        )
        after = _haiku_map(_overlay_body(measured))
        key = f"{scenario}:{run}"
        if code == 0:
            passed += 1
            skipped.discard((scenario, run))
        elif after.get(key) not in {"pass", "fail"}:
            skipped.add((scenario, run))
        if attempt + 1 < max_attempts and unrun_cells(_haiku_map(_overlay_body(measured))):
            time.sleep(gap_seconds)
    return 0 if passed else 1


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--scenario", default=NO_REINIT)
    parser.add_argument("--run", type=int, default=0)
    parser.add_argument("--measured", type=Path)
    parser.add_argument("--native-cell")
    parser.add_argument("--native-status", choices=("pass", "fail"), default="pass")
    parser.add_argument(
        "--native-drive",
        type=Path,
        help="Drive one exact-pin install to verified catalogued native bytes.",
    )
    parser.add_argument("--idempotency-key")
    parser.add_argument("--record-isolation", action="store_true")
    parser.add_argument("--agy", type=Path, default=Path(shutil.which("agy") or "agy"))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--fill",
        action="store_true",
        help="Walk unrun Haiku cells one at a time. Scored pass/fail stay put.",
    )
    parser.add_argument("--max-attempts", type=int, default=8)
    parser.add_argument("--gap-seconds", type=int, default=FILL_GAP_SECONDS)
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Ping agy first. Default is off: a pong can consume the only live slot.",
    )
    parser.add_argument(
        "--docker-image",
        help="Opt-in: exec ai-stp inside privileged Docker so bwrap can ENFORCE. "
        f"Also {DOCKER_IMAGE_ENV}. Host isolation stays unavailable.",
    )
    parser.add_argument(
        "--invalidate",
        action="append",
        default=[],
        metavar="SCENARIO",
        help="Drop scored overlay cells for one Haiku scenario so --fill can re-run them.",
    )
    parser.add_argument(
        "--invalidate-stale-verified",
        action="store_true",
        help=(
            "Drop initialize/install/change/switch/custom-home/author/relative/login-idle "
            "overlay cells recorded under follow-through scoring."
        ),
    )
    options = parser.parse_args(arguments)
    docker_image = options.docker_image or os.environ.get(DOCKER_IMAGE_ENV) or None
    if options.invalidate_stale_verified:
        options.invalidate.extend(STALE_VERIFIED_SCENARIOS)
    if options.invalidate:
        if options.measured is None:
            print("measured overlay is required to invalidate cells", file=sys.stderr)
            return 2
        dropped: dict[str, int] = {}
        for name in options.invalidate:
            try:
                scenario, run = invalidate_target(name)
            except ValueError:
                print(f"unsupported scenario: {name}", file=sys.stderr)
                return 2
            dropped[name] = (
                invalidate_scenario(options.measured, scenario)
                if run is None
                else invalidate_cell(options.measured, scenario, run)
            )
        print(json.dumps({"invalidated": dropped}))
        if not options.fill and options.root is None:
            return 0
    if options.record_isolation:
        if options.measured is None:
            print("measured overlay is required for isolation", file=sys.stderr)
            return 2
        snapshot = isolation_snapshot()
        write_isolation(options.measured, snapshot)
        print(json.dumps({"isolation": snapshot}))
        return 0 if snapshot.get("status") == "enforced" else 1
    if options.native_cell is not None:
        if options.measured is None:
            print("measured overlay is required for a native cell", file=sys.stderr)
            return 2
        harness, separator, platform = options.native_cell.partition(":")
        if not separator:
            print(f"native cell is not harness:platform: {options.native_cell}", file=sys.stderr)
            return 2
        native_status: MeasuredStatus = "fail" if options.native_status == "fail" else "pass"
        try:
            write_native_cell(options.measured, harness, platform, native_status)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
        print(json.dumps({"native": options.native_cell, "status": native_status}))
        return 0 if native_status == "pass" else 1
    if options.native_drive is not None:
        if options.idempotency_key is None:
            print("--native-drive requires --idempotency-key", file=sys.stderr)
            return 2
        try:
            driven = drive_native_install(options.native_drive, options.idempotency_key)
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            print(str(error), file=sys.stderr)
            return 2
        passed = native_install_passed(driven)
        platform_name = native_platform()
        harness = str(driven.get("harness") or "")
        if options.measured is not None and platform_name is not None and harness:
            write_native_cell(
                options.measured,
                harness,
                platform_name,
                "pass" if passed else "fail",
            )
        print(json.dumps(driven, indent=2))
        return 0 if passed else 1
    if options.fill:
        if options.root is None or options.measured is None:
            print("--fill requires --root and --measured", file=sys.stderr)
            return 2
        return fill_unrun(
            options.root,
            measured=options.measured,
            agy=options.agy,
            timeout=options.timeout,
            max_attempts=options.max_attempts,
            gap_seconds=options.gap_seconds,
            docker_image=docker_image,
        )
    if options.root is None:
        print("--root is required", file=sys.stderr)
        return 2
    if options.scenario not in SUPPORTED_SCENARIOS:
        print(f"unsupported scenario: {options.scenario}", file=sys.stderr)
        return 2
    return qualify_one(
        root=options.root,
        scenario=options.scenario,
        run=options.run,
        measured=options.measured,
        agy=options.agy,
        timeout=options.timeout,
        probe=options.probe,
        docker_image=docker_image,
    )


if __name__ == "__main__":
    raise SystemExit(main())
