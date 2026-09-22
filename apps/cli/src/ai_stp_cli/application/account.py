"""Account intent: device-code login, logout, and explicit sync. Login never uploads."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from ai_stp_cli.application.auth import begin as start_login
from ai_stp_cli.application.auth import complete as complete_login
from ai_stp_cli.application.auth import logout as logout_session
from ai_stp_cli.cloud import session
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import project_passport
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.auth import OAUTH_PROVIDERS
from ai_stp_contracts.machine_help import (
    AuthStatus,
    DeviceApproval,
    TaskAccountOutcome,
    TaskQuestion,
)
from ai_stp_foundation.canonical import JsonValue

_ACTIONS = ("login", "logout", "sync")
_SCOPES = ("push", "pull")
_PENDING = "AI_STP_AUTHORIZATION_PENDING"


@dataclass(frozen=True)
class DrainResult:
    outcome: TaskAccountOutcome | None = None
    questions: tuple[TaskQuestion, ...] = ()
    child_operation_ids: tuple[str, ...] = ()
    facts: dict[str, JsonValue] | None = None


def begin(provider: str) -> DeviceApproval:
    """Start device-code login. Tests may stub this."""
    return start_login({"provider": provider}).payload


def complete_once() -> AuthStatus:
    """One exchange, not a poll loop. Tests may stub this."""
    return complete_login({}).payload


def logout() -> AuthStatus:
    """Drop the local session; revoke remotely when reachable. Tests may stub this."""
    return logout_session({}).payload


def sync_now(*, scope: str, project_root: str) -> object:
    """Explicit private-registry sync. Never implied by login. Tests may stub this."""
    from ai_stp_cli.application import sync as sync_commands

    if scope == "pull":
        return sync_commands.pull({}).payload
    root = Path(project_root).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve()
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = project_passport.stable_id_for(connection, root)
    if stable_id is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no local project passport for this root",
            details={"project_root": str(root)},
        )
    return sync_commands.push({"id": stable_id, "confirm": True}).payload


def ensure_session(facts: Mapping[str, JsonValue]) -> DrainResult | AuthStatus:
    """Live session, or a login question. Never uploads."""
    report, _warning = session.status()
    if report.state == "authenticated":
        return report
    provider = facts.get("provider")
    if not isinstance(provider, str) or provider not in OAUTH_PROVIDERS:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="provider",
                    prompt="Which identity provider should sign this device in?",
                    value_type="string",
                    choices=list(OAUTH_PROVIDERS),
                    why="The platform brokers Google or GitHub. The CLI never sees a password.",
                    actor="human",
                ),
            )
        )
    store, _store_warning = open_store()
    pending = session.load_pending(store)
    if pending is not None and not pending.user_code:
        # Records written before the display fields were kept carry no code —
        # and a code nobody can see is a pending approval nobody can give.
        # Drop it and start one that can be completed (#359).
        session.clear_pending(store)
        pending = None
    # Facts carry the code after the first authorization block so a re-run
    # drain does not begin a second flow while the first still pends.
    already_begun = pending is not None or bool(_text(facts.get("user_code")))
    if not already_begun:
        approval = begin(provider)
        return _authorization_block(facts, approval)
    try:
        return complete_once()
    except CliFailure as failure:
        if failure.code == _PENDING:
            return _authorization_block(facts, approval=None, pending=pending)
        raise


def drain(facts: Mapping[str, JsonValue]) -> DrainResult:
    """Advance account until a boundary. Never shells out to `ai-stp`. Never polls."""
    action = facts.get("action")
    if not isinstance(action, str) or action not in _ACTIONS:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="action",
                    prompt="Sign in, sign out, or explicitly sync?",
                    value_type="string",
                    choices=list(_ACTIONS),
                    why="Login never uploads. Sync is a separate scoped step.",
                    actor="human",
                ),
            )
        )
    if action == "logout":
        report = logout()
        return DrainResult(
            outcome=TaskAccountOutcome(
                action="logout",
                authenticated=False,
                session_state=report.state,
            )
        )
    gate = ensure_session(facts)
    if isinstance(gate, DrainResult):
        return gate
    if action == "login":
        provider = facts.get("provider")
        return DrainResult(
            outcome=TaskAccountOutcome(
                action="login",
                authenticated=gate.state == "authenticated",
                provider=provider if isinstance(provider, str) else "",
                session_state=gate.state,
            )
        )
    scope = facts.get("scope")
    if not isinstance(scope, str) or scope not in _SCOPES:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="scope",
                    prompt="Push local revision heads, or pull the account ledger?",
                    value_type="string",
                    choices=list(_SCOPES),
                    why="Explicit sync is never implied by login.",
                    actor="human",
                ),
            )
        )
    project_root = facts.get("project_root")
    if scope == "push" and (
        not isinstance(project_root, str) or not Path(project_root).is_absolute()
    ):
        cwd = Path.cwd()
        recommended = str(cwd) if cwd.is_absolute() and (cwd / ".git").is_dir() else ""
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="project-root",
                    prompt="Which absolute project root should this sync push?",
                    value_type="string",
                    choices=[],
                    recommended=recommended,
                    why="Push sends the local project passport head, not a catalog object.",
                    actor="human",
                ),
            )
        )
    sync_now(scope=scope, project_root=project_root if isinstance(project_root, str) else "")
    provider = facts.get("provider")
    return DrainResult(
        outcome=TaskAccountOutcome(
            action="sync",
            authenticated=True,
            provider=provider if isinstance(provider, str) else "",
            session_state=gate.state,
            synced=True,
            scope=scope,
        )
    )


def _authorization_block(
    facts: Mapping[str, JsonValue],
    approval: DeviceApproval | None,
    pending: session.Pending | None = None,
) -> DrainResult:
    held: dict[str, JsonValue] = dict(facts)
    if approval is not None:
        user_code = approval.user_code
        verification_uri = approval.verification_uri
    elif pending is not None and pending.user_code:
        # `auth login` keeps the code in the pending record so a task opened
        # afterwards can still show it (#359).
        user_code = pending.user_code
        verification_uri = pending.verification_uri
    else:
        user_code = _text(facts.get("user_code"))
        verification_uri = _text(facts.get("verification_uri"))
    if approval is not None:
        held["provider"] = approval.provider
        held["user_code"] = approval.user_code
        held["verification_uri"] = approval.verification_uri
    elif pending is not None and pending.user_code:
        held["user_code"] = pending.user_code
        held["verification_uri"] = pending.verification_uri
    prompt = "Approve the user code at the verification URI, then continue this task."
    if user_code and verification_uri:
        prompt = f"Approve {user_code} at {verification_uri}, then continue this task."
    return DrainResult(
        questions=(
            TaskQuestion(
                question_id="authorization",
                prompt=prompt,
                value_type="string",
                choices=["continue"],
                recommended=user_code,
                why="Login never uploads. Show the code once. Do not poll in a tight loop.",
                actor="external",
            ),
        ),
        facts=held,
    )


def _text(value: JsonValue | None) -> str:
    return value if isinstance(value, str) else ""
