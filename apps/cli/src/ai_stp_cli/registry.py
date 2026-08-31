"""The command registry: the one place a command exists (issues #72, #73).

`#72` requires machine help to be generated from the actual registry, and the
canonical Skill is told not to guess flags. Both hold only if there is exactly
one declaration and the parser is built from it — a hand-written parser beside a
hand-written description would agree at first and drift by the second change.

So this module declares descriptors, `app.py` builds the parser from them, and
`help --agent` renders them. A command that is not here does not exist in any of
the three.

A command is declared here only once it can run. The local registry, cloud
clients and bounded external evidence adapters all joined through that rule.
Declaring one early with a "not implemented" answer would put something in
machine help that cannot run, and the Skill would plan a step around it.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib import import_module
from typing import Final, cast

from pydantic import BaseModel

from ai_stp_cli.answer import Answer
from ai_stp_cli.output import JSON_FLAG
from ai_stp_contracts.auth import OAUTH_PROVIDERS
from ai_stp_contracts.machine_help import (
    CommandDescriptor,
    CommandParameter,
    CommandParameterRule,
    ConfirmationKind,
    MutabilityClass,
)
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER, HARNESS_IDS

type Handler = Callable[[Mapping[str, object]], Answer[BaseModel]]


@dataclass(frozen=True)
class Command:
    """One declared command and the callable that answers it.

    The callable is named rather than referenced. Importing thirty command
    modules to answer `version` cost 0.36s of a 1.0s run, measured 2026-08-29:
    `import ai_stp_cli.registry` was 0.818s against 0.461s for the descriptors
    alone, and every invocation paid it whichever command was typed.

    Only the handler is deferred. Descriptors stay declared here, so the
    property this module exists for — one declaration, and the parser and
    machine help built from it — is untouched: a command that is not here still
    does not exist in any of the three.
    """

    descriptor: CommandDescriptor
    #: `module:function`, relative to `ai_stp_cli.commands`.
    handler_ref: str

    @property
    def name(self) -> str:
        return " ".join(self.descriptor.path)

    @property
    def handler(self) -> Handler:
        """Import the command module on dispatch and return its entry point."""
        module_name, _, attribute = self.handler_ref.partition(":")
        module = import_module(f"ai_stp_cli.commands.{module_name}")
        return cast(Handler, getattr(module, attribute))


def option(
    name: str,
    value_type: str,
    summary: str,
    *,
    required: bool = False,
    repeatable: bool = False,
    choices: tuple[str, ...] = (),
) -> CommandParameter:
    """One declared option, spelled once."""
    return CommandParameter(
        name=name,
        kind="option",
        value_type=value_type,  # pyright: ignore[reportArgumentType]
        required=required,
        repeatable=repeatable,
        summary=summary,
        choices=list(choices),
    )


#: Accepted by every command. Declared once here and once in machine help, never
#: repeated per descriptor: `--json` is not a property of any single command.
GLOBAL_OPTIONS: Final[tuple[CommandParameter, ...]] = (
    option("json", "boolean", "Emit exactly one JSON envelope on stdout and nothing else."),
)


@dataclass(frozen=True)
class Declaration:
    """A command as it is written here, before it becomes a descriptor."""

    path: list[str]
    summary: str
    result_schema: str | None
    #: `module:function`, relative to `ai_stp_cli.commands`. Resolved on
    #: dispatch; `test_every_declared_handler_resolves` proves every one.
    handler: str
    mutability: MutabilityClass = "read"
    confirmation: ConfirmationKind = "none"
    parameters: tuple[CommandParameter, ...] = ()
    parameter_rules: tuple[CommandParameterRule, ...] = ()
    next_actions: tuple[str, ...] = field(default_factory=tuple)


#: Options both replacement commands take. Spelled once: two copies of a
#: plan/confirm pair are two chances for one of them to quietly lose a guard.
_REPLACEMENT_OPTIONS: Final[tuple[CommandParameter, ...]] = (
    option(
        "harness",
        "string",
        "Harness whose provider is replaced.",
        required=True,
        choices=tuple(sorted(HARNESS_IDS)),
    ),
    option(
        "executable",
        "string",
        "The provider to replace. Required when more than one is installed.",
    ),
    option(
        "adopt",
        "boolean",
        "Replace a provider ai-stp did not install. Nothing else overwrites one.",
    ),
)

#: What `apply` adds: the plan's exact digest and an explicit confirmation. Both
#: required, so a confirmation can only ever be of something already described.
_CONFIRMED_OPTIONS: Final[tuple[CommandParameter, ...]] = (
    *_REPLACEMENT_OPTIONS,
    option("expected-plan-digest", "string", "Exact digest returned by the plan.", required=True),
    option(
        "confirm", "boolean", "Confirm the exact replacement the plan described.", required=True
    ),
)

_VERSION_OPTION: Final[CommandParameter] = option(
    "version",
    "string",
    "Exact release tag. Omit to reinstall the version already there; moving to"
    " the newest is provider update.",
)

DECLARATIONS: Final[tuple[Declaration, ...]] = (
    Declaration(
        path=["eval", "profile"],
        summary="Show the versioned reference evaluation profile for all or one component type.",
        result_schema="urn:ai-stp:schema:v1:cli-setup-eval-profile",
        handler="evaluation:profile",
        parameters=(
            option(
                "type",
                "string",
                "Limit the reference profile to one component type.",
                choices=(
                    "instruction",
                    "skill",
                    "mcp",
                    "hook",
                    "command",
                    "agent",
                    "plugin",
                    "setting",
                ),
            ),
        ),
        next_actions=("eval plan",),
    ),
    Declaration(
        path=["eval", "plan"],
        summary="Bind a reference evaluation profile to one exact local setup graph.",
        result_schema="urn:ai-stp:schema:v1:cli-setup-eval-plan",
        handler="evaluation:plan",
        mutability="plan",
        parameters=(
            option("setup-id", "string", "Exact local setup identifier.", required=True),
            option("setup-version", "string", "Exact local setup X.Y version.", required=True),
            option(
                "component-id",
                "string",
                "Optional exact component subset from the setup graph.",
                repeatable=True,
            ),
            option("harness-version", "string", "Exact evaluated harness version.", required=True),
            option(
                "provider-version", "string", "Exact evaluated provider version.", required=True
            ),
            option("runner-version", "string", "Exact evaluation runner version.", required=True),
        ),
        next_actions=("eval run",),
    ),
    Declaration(
        path=["eval", "run"],
        summary="Run local deterministic checks for one confirmed exact evaluation plan.",
        result_schema="urn:ai-stp:schema:v1:cli-setup-eval-result",
        handler="evaluation:run",
        mutability="apply",
        confirmation="plan_digest",
        parameters=(
            option("plan-id", "string", "Stored evaluation plan identifier.", required=True),
            option(
                "expected-plan-digest",
                "string",
                "Exact content digest shown by eval plan.",
                required=True,
            ),
        ),
        next_actions=("eval status", "eval show"),
    ),
    Declaration(
        path=["eval", "status"],
        summary="Read the immutable status of one local evaluation run.",
        result_schema="urn:ai-stp:schema:v1:cli-setup-eval-result",
        handler="evaluation:status",
        parameters=(option("run-id", "string", "Evaluation run identifier.", required=True),),
        next_actions=("eval show",),
    ),
    Declaration(
        path=["eval", "show"],
        summary="Show full immutable local evidence for one evaluation run.",
        result_schema="urn:ai-stp:schema:v1:cli-setup-eval-result",
        handler="evaluation:show",
        parameters=(option("run-id", "string", "Evaluation run identifier.", required=True),),
    ),
    Declaration(
        path=["publication", "plan"],
        summary="Create an immutable server plan for one exact released component version.",
        result_schema="urn:ai-stp:schema:v1:cli-publication-plan",
        handler="publication:plan",
        mutability="plan",
        parameters=(
            option("id", "string", "Stable identifier of the released component.", required=True),
            option("version", "string", "Exact local X.Y version to publish.", required=True),
            option(
                "attestation-file",
                "string",
                "Full locally signed attestation bound to this exact version.",
                repeatable=True,
            ),
        ),
        next_actions=("publication confirm", "publication status"),
    ),
    Declaration(
        path=["attestation", "sign"],
        summary="Sign exact credential-dependent test evidence with the active device key.",
        result_schema="urn:ai-stp:schema:v1:cli-signed-attestation",
        handler="attestations:sign",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("id", "string", "Released component stable identifier.", required=True),
            option("version", "string", "Exact released X.Y version.", required=True),
            option("check-id", "string", "Executed policy check identifier.", required=True),
            option("policy-version", "string", "Exact validation policy version.", required=True),
            option("tool-version", "string", "Executed tool as name=version.", repeatable=True),
            option("harness-id", "string", "Harness used for the check.", required=True),
            option("harness-version", "string", "Exact harness version.", required=True),
            option("provider-version", "string", "Exact provider version.", required=True),
            option(
                "test-case-id",
                "string",
                "Executed test-case identifier.",
                required=True,
                repeatable=True,
            ),
            option(
                "result", "string", "Observed result.", required=True, choices=("passed", "failed")
            ),
            option("output", "string", "New owner-only JSON attestation file.", required=True),
            option(
                "confirm", "boolean", "Confirm signing these exact observed facts.", required=True
            ),
        ),
        next_actions=("publication plan",),
    ),
    Declaration(
        path=["publication", "status"],
        summary="Read the current server state of one publication plan.",
        result_schema="urn:ai-stp:schema:v1:cli-publication-plan",
        handler="publication:show",
        parameters=(option("plan-id", "string", "Publication plan identifier.", required=True),),
        next_actions=("publication confirm",),
    ),
    Declaration(
        path=["publication", "confirm"],
        summary="Confirm one exact unexpired publication plan hash.",
        result_schema="urn:ai-stp:schema:v1:cli-publication-plan",
        handler="publication:confirm",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("plan-id", "string", "Publication plan identifier.", required=True),
            option(
                "plan-hash",
                "string",
                "Exact immutable hash returned by publication plan.",
                required=True,
            ),
            option("confirm", "boolean", "Confirm the exact plan and its listed effects."),
        ),
        next_actions=("publication status",),
    ),
    Declaration(
        path=["grant", "list"],
        summary="List invitations and major-line grants owned by the current account.",
        result_schema="urn:ai-stp:schema:v1:cli-grant-list",
        handler="grants:list_all",
        next_actions=("grant invite", "grant direct"),
    ),
    Declaration(
        path=["grant", "invite"],
        summary="Create an email invitation for one exact object major line.",
        result_schema="urn:ai-stp:schema:v1:cli-grant-invitation",
        handler="grants:invite",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("kind", "string", "Object kind.", required=True, choices=("component", "setup")),
            option("id", "string", "Stable object identifier.", required=True),
            option("major", "integer", "Exact major line to grant.", required=True),
            option("email", "string", "Verified recipient email address.", required=True),
            option("ttl-seconds", "integer", "Invitation lifetime; defaults to seven days."),
            option("idempotency-key", "string", "Stable key for this exact intent.", required=True),
            option("confirm", "boolean", "Confirm creating this exact invitation.", required=True),
        ),
        next_actions=("grant list",),
    ),
    Declaration(
        path=["grant", "direct"],
        summary="Grant one exact object major line to an explicit account identifier.",
        result_schema="urn:ai-stp:schema:v1:cli-grant-access",
        handler="grants:direct",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("kind", "string", "Object kind.", required=True, choices=("component", "setup")),
            option("id", "string", "Stable object identifier.", required=True),
            option("major", "integer", "Exact major line to grant.", required=True),
            option(
                "recipient-kind",
                "string",
                "How the recipient is identified.",
                required=True,
                choices=("github_username", "user_id"),
            ),
            option(
                "recipient", "string", "Recipient value in the selected namespace.", required=True
            ),
            option("idempotency-key", "string", "Stable key for this exact intent.", required=True),
            option("confirm", "boolean", "Confirm creating this exact grant.", required=True),
        ),
        next_actions=("grant list",),
    ),
    Declaration(
        path=["grant", "accept"],
        summary="Accept an invitation using a token read from a named environment variable.",
        result_schema="urn:ai-stp:schema:v1:cli-grant-access",
        handler="grants:accept",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("invitation-id", "string", "Invitation identifier.", required=True),
            option(
                "token-env",
                "string",
                "Environment variable holding the invitation token.",
                required=True,
            ),
            option("idempotency-key", "string", "Stable key for this exact intent.", required=True),
            option("confirm", "boolean", "Confirm accepting this exact invitation.", required=True),
        ),
        next_actions=("grant list",),
    ),
    Declaration(
        path=["grant", "invitation", "revoke"],
        summary="Revoke one pending invitation without deleting local bytes.",
        result_schema="urn:ai-stp:schema:v1:cli-grant-revoke",
        handler="grants:revoke_invitation",
        mutability="destructive",
        confirmation="explicit_flag",
        parameters=(
            option("invitation-id", "string", "Invitation identifier.", required=True),
            option("reason", "string", "Bounded reason recorded with the revocation."),
            option("idempotency-key", "string", "Stable key for this exact intent.", required=True),
            option("confirm", "boolean", "Confirm revoking this exact invitation.", required=True),
        ),
        next_actions=("grant list",),
    ),
    Declaration(
        path=["grant", "revoke"],
        summary="Revoke one active grant forward-only while retaining local bytes.",
        result_schema="urn:ai-stp:schema:v1:cli-grant-revoke",
        handler="grants:revoke",
        mutability="destructive",
        confirmation="explicit_flag",
        parameters=(
            option("grant-id", "string", "Access grant identifier.", required=True),
            option("reason", "string", "Bounded reason recorded with the revocation."),
            option("idempotency-key", "string", "Stable key for this exact intent.", required=True),
            option("confirm", "boolean", "Confirm revoking this exact grant.", required=True),
        ),
        next_actions=("grant list",),
    ),
    Declaration(
        path=["report", "preview"],
        summary="Prepare and show the exact bounded report payload without sending it.",
        result_schema="urn:ai-stp:schema:v1:cli-report-preview",
        handler="reports:preview",
        mutability="plan",
        parameters=(
            option("kind", "string", "Object kind.", required=True, choices=("component", "setup")),
            option("id", "string", "Stable object identifier.", required=True),
            option("version", "string", "Exact object version.", required=True),
            option("content-digest", "string", "Exact reported content digest.", required=True),
            option("harness-id", "string", "Harness identifier, when relevant."),
            option("harness-version", "string", "Harness version, when known."),
            option("provider-version", "string", "Provider version, when known."),
            option("operation-id", "string", "Related local operation identifier."),
            option("error-code", "string", "Related registered error code."),
            option(
                "validation-snapshot-id",
                "string",
                "Validation snapshot identifier.",
                repeatable=True,
            ),
            option("diagnostics-file", "string", "Bounded pre-reviewed UTF-8 diagnostics file."),
            option("vulnerability", "boolean", "Mark a possible security vulnerability."),
            option("idempotency-key", "string", "Stable key for this exact report.", required=True),
        ),
        next_actions=("report confirm",),
    ),
    Declaration(
        path=["report", "confirm"],
        summary="Submit one exact durable report preview after explicit confirmation.",
        result_schema="urn:ai-stp:schema:v1:cli-report-case",
        handler="reports:confirm",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("plan-id", "string", "Prepared local report plan identifier.", required=True),
            option(
                "plan-digest", "string", "Exact digest returned by report preview.", required=True
            ),
            option(
                "confirm", "boolean", "Confirm sending the exact previewed payload.", required=True
            ),
        ),
        next_actions=("report list",),
    ),
    Declaration(
        path=["report", "list"],
        summary="List the current account's closed report cases.",
        result_schema="urn:ai-stp:schema:v1:cli-report-list",
        handler="reports:list_all",
        next_actions=("report preview",),
    ),
    Declaration(
        path=["owner", "objects"],
        summary="List objects owned by the authenticated account.",
        result_schema="urn:ai-stp:schema:v1:cli-owner-object-list",
        handler="owner:list_objects",
        parameters=(
            option(
                "kind", "string", "Optional object-kind filter.", choices=("component", "setup")
            ),
            option("cursor", "string", "Opaque cursor returned by the previous page."),
            option("page-size", "integer", "Requested bounded page size; defaults to 20."),
        ),
        next_actions=("owner object show",),
    ),
    Declaration(
        path=["owner", "object", "show"],
        summary="Read one server-authorized owned object and its exact versions.",
        result_schema="urn:ai-stp:schema:v1:cli-owner-object-detail",
        handler="owner:show_object",
        parameters=(
            option("kind", "string", "Object kind.", required=True, choices=("component", "setup")),
            option("id", "string", "Stable object identifier.", required=True),
        ),
        next_actions=("owner version show",),
    ),
    Declaration(
        path=["owner", "version", "show"],
        summary="Read one exact owned version and its server lifecycle evidence.",
        result_schema="urn:ai-stp:schema:v1:cli-owner-version-detail",
        handler="owner:show_version",
        parameters=(
            option("kind", "string", "Object kind.", required=True, choices=("component", "setup")),
            option("id", "string", "Stable object identifier.", required=True),
            option("version", "string", "Exact object version.", required=True),
        ),
        next_actions=("publication plan",),
    ),
    Declaration(
        path=["auth", "complete"],
        summary="Finish the pending sign-in once the user has approved it.",
        result_schema="urn:ai-stp:schema:v1:cli-auth-status",
        handler="auth:complete",
        parameters=(
            option(
                "wait",
                "boolean",
                "Keep asking until the sign-in is approved, declined or expires. "
                "Bounded. For a person at a terminal; a machine caller asks again itself.",
            ),
        ),
        # It stores credentials and re-owns local passports. No confirmation
        # flag: the decision is the user's approval in the browser, which is the
        # whole point of the flow.
        mutability="apply",
        next_actions=("auth status",),
    ),
    Declaration(
        path=["auth", "login"],
        summary="Start a sign-in and report the code the user must approve.",
        result_schema="urn:ai-stp:schema:v1:cli-device-approval",
        handler="auth:begin",
        # It records a pending authorization, which is durable state.
        mutability="apply",
        parameters=(
            option(
                "provider",
                "string",
                "Which identity provider to sign in with: google or github.",
                required=True,
                choices=OAUTH_PROVIDERS,
            ),
            option(
                "open-browser",
                "boolean",
                "Also open the approval page in the desktop default browser.",
            ),
        ),
        next_actions=("auth complete", "auth status"),
    ),
    Declaration(
        path=["auth", "logout"],
        summary="End the cloud session on the server and here, keeping all local data.",
        result_schema="urn:ai-stp:schema:v1:cli-auth-status",
        handler="auth:logout",
        mutability="apply",
        next_actions=("auth status",),
    ),
    Declaration(
        path=["auth", "status"],
        summary="Report the platform relationship: local-only, authenticated, expired or revoked.",
        result_schema="urn:ai-stp:schema:v1:cli-auth-status",
        handler="auth_status:run",
        next_actions=("device show",),
    ),
    Declaration(
        path=["capabilities"],
        summary="Report what this installation can do right now.",
        result_schema="urn:ai-stp:schema:v1:cli-capabilities",
        handler="machine_help:capabilities",
        next_actions=("doctor", "help --agent"),
    ),
    Declaration(
        path=["component", "discover"],
        summary="List native components in the harness roots and one project. Changes nothing.",
        result_schema="urn:ai-stp:schema:v1:cli-native-components",
        handler="component:discover",
        parameters=(option("root", "string", "Project root to look inside, beside the roots."),),
        next_actions=("component adopt",),
    ),
    Declaration(
        path=["component", "scaffold", "plan"],
        summary="Preview exact files and digests for one versioned component scaffold.",
        result_schema="urn:ai-stp:schema:v1:cli-component-scaffold-plan",
        handler="component:scaffold_plan",
        mutability="plan",
        parameters=(
            option(
                "type",
                "string",
                "One closed-vocabulary component type.",
                required=True,
                choices=(
                    "instruction",
                    "skill",
                    "mcp",
                    "hook",
                    "command",
                    "agent",
                    "plugin",
                    "setting",
                ),
            ),
            option(
                "language",
                "string",
                "None for declarative types or one executable language.",
                required=True,
                choices=(
                    "none",
                    "python",
                    "typescript",
                    "javascript",
                    "rust",
                    "go",
                    "dart-flutter",
                ),
            ),
            option(
                "harness",
                "string",
                "Portable base or one concrete harness variant.",
                required=True,
                choices=("portable", *HARNESS_ID_ORDER),
            ),
            option("name", "string", "Lowercase component slug.", required=True),
            option("output", "string", "New scaffold directory to preview.", required=True),
        ),
        next_actions=("component scaffold apply",),
    ),
    Declaration(
        path=["component", "scaffold", "apply"],
        summary="Create exactly the confirmed component scaffold without overwriting a path.",
        result_schema="urn:ai-stp:schema:v1:cli-component-scaffold-result",
        handler="component:scaffold_apply",
        mutability="apply",
        confirmation="plan_digest",
        parameters=(
            option(
                "type",
                "string",
                "One closed-vocabulary component type.",
                required=True,
                choices=(
                    "instruction",
                    "skill",
                    "mcp",
                    "hook",
                    "command",
                    "agent",
                    "plugin",
                    "setting",
                ),
            ),
            option(
                "language",
                "string",
                "None for declarative types or one executable language.",
                required=True,
                choices=(
                    "none",
                    "python",
                    "typescript",
                    "javascript",
                    "rust",
                    "go",
                    "dart-flutter",
                ),
            ),
            option(
                "harness",
                "string",
                "Portable base or one concrete harness variant.",
                required=True,
                choices=("portable", *HARNESS_ID_ORDER),
            ),
            option("name", "string", "Lowercase component slug.", required=True),
            option("output", "string", "New scaffold directory to create.", required=True),
            option(
                "expected-plan-digest",
                "string",
                "Exact digest returned by scaffold plan.",
                required=True,
            ),
        ),
        next_actions=("component passport validate", "component adopt"),
    ),
    Declaration(
        path=["component", "template", "render"],
        summary="Render and validate a portable template for one concrete harness.",
        result_schema="urn:ai-stp:schema:v1:cli-component-template",
        handler="component:template_render",
        parameters=(
            option("template", "string", "Existing UTF-8 authoring template.", required=True),
            option(
                "harness",
                "string",
                "Concrete target from the closed harness registry.",
                required=True,
                choices=HARNESS_ID_ORDER,
            ),
            option("name", "string", "Lowercase component slug.", required=True),
            option(
                "component-root",
                "string",
                "Bounded relative POSIX path for the native component.",
                required=True,
            ),
        ),
        next_actions=("component adopt", "component scaffold plan"),
    ),
    Declaration(
        path=["component", "source", "parse"],
        summary="Parse an external component source as untrusted structured intent.",
        result_schema="urn:ai-stp:schema:v1:cli-external-source-identity",
        handler="component:source_parse",
        parameters=(
            option(
                "source",
                "string",
                "Published slug, GitHub identity, local path or collection.",
                required=True,
            ),
            option(
                "root", "string", "Base directory used only to normalize a relative local path."
            ),
        ),
        next_actions=("component source resolve", "component discover"),
    ),
    Declaration(
        path=["component", "source", "resolve"],
        summary="Bind a GitHub source intent to one exact full commit SHA.",
        result_schema="urn:ai-stp:schema:v1:cli-external-source-identity",
        handler="component:source_resolve",
        parameters=(
            option(
                "source",
                "string",
                "GitHub shorthand or credential-free HTTPS URL.",
                required=True,
            ),
            option("commit", "string", "Exact lowercase 40-character Git commit SHA."),
            option(
                "root", "string", "Base directory used only to normalize a relative local path."
            ),
        ),
        next_actions=("component discover", "component adopt"),
    ),
    Declaration(
        path=["component", "source", "evidence", "refresh"],
        summary="Refresh official GitHub archived evidence for one exact local version.",
        result_schema="urn:ai-stp:schema:v1:cli-github-archive-evidence",
        handler="component:source_evidence_refresh",
        mutability="apply",
        parameters=(
            option("id", "string", "Stable identifier of a local object.", required=True),
            option("version", "string", "Exact recorded X.Y version.", required=True),
        ),
        next_actions=("component source evidence show", "component source evidence history"),
    ),
    Declaration(
        path=["component", "source", "evidence", "show"],
        summary="Show the latest local GitHub archived evidence and freshness.",
        result_schema="urn:ai-stp:schema:v1:cli-github-archive-evidence",
        handler="component:source_evidence_show",
        parameters=(
            option("id", "string", "Stable identifier of a local object.", required=True),
            option("version", "string", "Exact recorded X.Y version.", required=True),
        ),
        next_actions=("component source evidence refresh", "component source evidence history"),
    ),
    Declaration(
        path=["component", "source", "evidence", "history"],
        summary="Show bounded append-only GitHub archived evidence history.",
        result_schema="urn:ai-stp:schema:v1:cli-github-archive-history",
        handler="component:source_evidence_history",
        parameters=(
            option("id", "string", "Stable identifier of a local object.", required=True),
            option("version", "string", "Exact recorded X.Y version.", required=True),
            option("limit", "integer", "Newest observations to return, from 1 to 100."),
        ),
        next_actions=("component source evidence show",),
    ),
    Declaration(
        path=["component", "adopt"],
        summary="Register one discovered component in the local registry.",
        result_schema="urn:ai-stp:schema:v1:cli-passport-view",
        handler="component:adopt",
        # It writes a passport and stores bytes. `SPEC-005` REQ-518 makes taking
        # something into the registry an explicit act, not a side effect.
        mutability="apply",
        parameters=(
            option("path", "string", "Exact path discovery reported.", required=True),
            option("root", "string", "Project root the component was discovered under."),
        ),
        next_actions=("component passport show", "component discover"),
    ),
    Declaration(
        path=["component", "passport", "show"],
        summary="Show the current local passport draft for one adopted component.",
        result_schema="urn:ai-stp:schema:v1:cli-passport-view",
        handler="component:passport_show",
        parameters=(
            option("id", "string", "Stable identifier of an adopted component.", required=True),
        ),
        next_actions=("component passport suggest", "component passport update"),
    ),
    Declaration(
        path=["component", "passport", "suggest"],
        summary="Suggest exact manifest facts for confirmation without changing the draft.",
        result_schema="urn:ai-stp:schema:v1:cli-component-passport-suggestions",
        handler="component:passport_suggest",
        parameters=(
            option("id", "string", "Stable identifier of an adopted component.", required=True),
        ),
        next_actions=("component passport update", "component passport validate"),
    ),
    Declaration(
        path=["component", "passport", "update"],
        summary="Add confirmed declared facts as a new content-addressed passport revision.",
        result_schema="urn:ai-stp:schema:v1:cli-passport-view",
        handler="component:passport_update",
        mutability="apply",
        confirmation="plan_digest",
        parameters=(
            option("id", "string", "Stable identifier of an adopted component.", required=True),
            option(
                "expected-revision",
                "string",
                "Exact current revision this patch was prepared against.",
                required=True,
            ),
            option("from", "string", "Path to a bounded closed-schema JSON patch.", required=True),
        ),
        next_actions=("component passport validate", "component passport show"),
    ),
    Declaration(
        path=["component", "passport", "validate"],
        summary="Report every structural blocker to publishing the current passport revision.",
        result_schema="urn:ai-stp:schema:v1:cli-component-passport-validation",
        handler="component:passport_validate",
        parameters=(
            option("id", "string", "Stable identifier of an adopted component.", required=True),
            option(
                "for-publication",
                "boolean",
                "Select the strict public-publication readiness profile.",
                required=True,
            ),
        ),
        next_actions=("component passport update", "component version release"),
    ),
    Declaration(
        path=["component", "passport", "quality"],
        summary="Show optional mechanical authoring hints without changing trust or readiness.",
        result_schema="urn:ai-stp:schema:v1:cli-component-quality-report",
        handler="component:passport_quality",
        parameters=(
            option("id", "string", "Stable identifier of an adopted component.", required=True),
        ),
        next_actions=("component passport update", "component passport validate"),
    ),
    Declaration(
        path=["component", "forget"],
        summary="Mark a registered component deleted, keeping its history.",
        result_schema="urn:ai-stp:schema:v1:cli-passport-view",
        handler="component:forget",
        mutability="apply",
        parameters=(
            option(
                "id",
                "string",
                "Stable identifier of a registered component.",
                required=True,
            ),
            option("reason", "string", "Why it is being removed."),
        ),
        next_actions=("component discover",),
    ),
    Declaration(
        path=["consent", "allow"],
        summary="Record consent to unverified objects of one publisher or major line.",
        result_schema="urn:ai-stp:schema:v1:cli-consent-record",
        handler="component:consent_allow",
        mutability="apply",
        parameters=(
            option("scope", "string", "publisher or object_major. No wider form exists."),
            option("target", "string", "The publisher or object major line it covers."),
        ),
        next_actions=("consent list",),
    ),
    Declaration(
        path=["consent", "revoke"],
        summary="Withdraw a consent. Takes effect immediately for later requests.",
        result_schema="urn:ai-stp:schema:v1:cli-consent-record",
        handler="component:consent_revoke",
        mutability="apply",
        parameters=(
            option("scope", "string", "publisher or object_major."),
            option("target", "string", "The publisher or object major line it covers."),
        ),
        next_actions=("consent list",),
    ),
    Declaration(
        path=["consent", "list"],
        summary="Every consent still in force, and what each covered when given.",
        result_schema="urn:ai-stp:schema:v1:cli-consent-summary",
        handler="component:consent_list",
        next_actions=("consent allow",),
    ),
    Declaration(
        path=["component", "version", "list"],
        summary="Every recorded version of one object, and the next minor number.",
        result_schema="urn:ai-stp:schema:v1:cli-version-line",
        handler="component:version_list",
        parameters=(
            option("id", "string", "Stable identifier of a registered object.", required=True),
        ),
        next_actions=("component version release",),
    ),
    Declaration(
        path=["component", "version", "release"],
        summary="Give the current head an immutable X.Y number. Minor unless told otherwise.",
        result_schema="urn:ai-stp:schema:v1:cli-version-line",
        handler="component:version_release",
        mutability="apply",
        # A major line is a separate access boundary, so asking for one needs a
        # decision rather than a flag that defaults to yes.
        parameters=(
            option("id", "string", "Stable identifier of a registered object.", required=True),
            option("major", "boolean", "Open the next major line instead of the next minor."),
            option("confirm", "boolean", "The explicit decision a major line requires."),
        ),
        next_actions=("component version list",),
    ),
    Declaration(
        path=["component", "fork"],
        summary="Copy one recorded version under a new identity. The original is untouched.",
        result_schema="urn:ai-stp:schema:v1:cli-version-line",
        handler="component:fork",
        mutability="apply",
        parameters=(
            option("id", "string", "Stable identifier of the object being forked.", required=True),
            option("version", "string", "The exact X.Y being forked.", required=True),
        ),
        next_actions=("component version list",),
    ),
    Declaration(
        path=["component", "find"],
        summary="Search the local registry by prefix, phrase, tag or field. No model, no network.",
        result_schema="urn:ai-stp:schema:v1:cli-local-search",
        handler="component:find",
        parameters=(
            option("prefix", "string", "Match the start of a name."),
            option("phrase", "string", "Match inside a name or description."),
            option(
                "tag",
                "string",
                "Require this tag. Repeat to require several.",
                repeatable=True,
            ),
            option("field", "string", "One declared field to match exactly."),
            option("value", "string", "The value that field must equal."),
            option(
                "include-unverified",
                "boolean",
                "Show unverified candidates for this command only. Never stored.",
            ),
        ),
        next_actions=("component version list",),
    ),
    Declaration(
        path=["config", "init"],
        summary="Create the configuration file if it is absent, and validate it either way.",
        result_schema="urn:ai-stp:schema:v1:cli-config-report",
        handler="config_show:init",
        # Idempotent and never destructive: an existing file is validated rather
        # than replaced, so there is nothing for the user to decide.
        mutability="apply",
        next_actions=("config show",),
    ),
    Declaration(
        path=["config", "set"],
        summary="Write declared values to the configuration file.",
        result_schema="urn:ai-stp:schema:v1:cli-config-report",
        handler="config_show:set_",
        mutability="apply",
        parameters=(
            option(
                "set",
                "string",
                "One declared field to write, as path=value. Repeat for several.",
                repeatable=True,
            ),
        ),
        next_actions=("config show",),
    ),
    Declaration(
        path=["config", "unset"],
        summary="Remove declared values so their defaults apply again.",
        result_schema="urn:ai-stp:schema:v1:cli-config-report",
        handler="config_show:unset",
        mutability="apply",
        parameters=(
            option(
                "field",
                "string",
                "One declared field to remove. Repeat for several.",
                repeatable=True,
            ),
        ),
        next_actions=("config show",),
    ),
    Declaration(
        path=["config", "validate"],
        summary="Read the configuration file and refuse it if it cannot be honoured.",
        result_schema="urn:ai-stp:schema:v1:cli-config-report",
        handler="config_show:validate",
        next_actions=("config show",),
    ),
    Declaration(
        path=["config", "show"],
        summary="Show the effective configuration and where each value came from.",
        result_schema="urn:ai-stp:schema:v1:cli-config-report",
        handler="config_show:run",
        parameters=(
            option(
                "set",
                "string",
                "Override one declared field for this call only, as path=value. "
                "Never writes the file.",
                repeatable=True,
            ),
        ),
        next_actions=("doctor",),
    ),
    Declaration(
        path=["device", "reset"],
        summary="Retire this device identity and create a new one.",
        result_schema="urn:ai-stp:schema:v1:cli-device-identity",
        handler="device:reset",
        # Destructive: the retired private key is discarded and cannot be
        # recovered, and any cloud account that trusted it must approve the new
        # one. Local data is untouched, but that does not make it reversible.
        mutability="destructive",
        confirmation="explicit_flag",
        parameters=(
            option(
                "confirm",
                "boolean",
                "Required. Confirms discarding the current device key.",
                required=True,
            ),
        ),
        next_actions=("device show",),
    ),
    Declaration(
        path=["device", "init"],
        summary="Create the identity of this installation, or return the existing one.",
        result_schema="urn:ai-stp:schema:v1:cli-device-identity",
        handler="device:init",
        # Idempotent, so there is nothing for the user to decide: a second run
        # returns the identity the first one made.
        mutability="apply",
        next_actions=("device show",),
    ),
    Declaration(
        path=["device", "show"],
        summary="Show this device identity and where its key is kept.",
        result_schema="urn:ai-stp:schema:v1:cli-device-identity",
        handler="device:show",
        next_actions=("auth status",),
    ),
    Declaration(
        path=["doctor"],
        summary="Report the setup state of this installation without changing it.",
        result_schema="urn:ai-stp:schema:v1:cli-doctor-report",
        handler="doctor:run",
        next_actions=("config show",),
    ),
    Declaration(
        path=["help"],
        summary="Emit the full command registry for an agent.",
        result_schema="urn:ai-stp:schema:v1:cli-machine-help",
        handler="machine_help:registry",
        parameters=(
            option(
                "agent",
                "boolean",
                "Required. Selects the machine registry rather than usage text.",
                required=True,
            ),
        ),
        next_actions=("capabilities",),
    ),
    Declaration(
        path=["link", "web"],
        summary="Print a canonical web URL and round-trippable CLI reference.",
        result_schema="urn:ai-stp:schema:v1:cli-deep-link",
        handler="link:web",
        parameters=(
            option(
                "kind",
                "string",
                "Target kind: component, setup or publisher.",
                required=True,
            ),
            option("id", "string", "Canonical stable identifier of the target.", required=True),
            option("version", "string", "Optional exact X.Y for a component or setup."),
            option("locale", "string", "Canonical web locale: ru or en. Defaults to ru."),
            option(
                "report",
                "boolean",
                "Link to the report action for an exact component or setup version.",
            ),
        ),
    ),
    Declaration(
        path=["passport", "developer", "init"],
        summary="Create the developer passport of this installation.",
        result_schema="urn:ai-stp:schema:v1:cli-passport-view",
        handler="passport:developer_init",
        # It creates durable state, and running it twice is a no-op rather than
        # a second passport, so it needs no decision from the user.
        mutability="apply",
        next_actions=("passport developer show",),
    ),
    Declaration(
        path=["passport", "developer", "show"],
        summary="Show the developer passport at its current head.",
        result_schema="urn:ai-stp:schema:v1:cli-passport-view",
        handler="passport:developer_show",
        next_actions=("passport device show",),
    ),
    Declaration(
        path=["passport", "developer", "update"],
        summary="Declare developer facts, adding one revision.",
        result_schema="urn:ai-stp:schema:v1:cli-passport-view",
        handler="passport:developer_update",
        mutability="apply",
        parameters=(
            option(
                "set",
                "string",
                "Declare one field as name=value; a comma-separated value becomes a list.",
                required=True,
                repeatable=True,
            ),
        ),
        next_actions=("passport developer show",),
    ),
    Declaration(
        path=["passport", "device", "refresh"],
        summary="Create this device passport, or bring it up to what is observable now.",
        result_schema="urn:ai-stp:schema:v1:cli-passport-view",
        handler="passport:device_refresh",
        # Observing writes a revision only when something actually changed, but
        # it can add history, so the class is the honest one.
        mutability="apply",
        next_actions=("passport device show",),
    ),
    Declaration(
        path=["passport", "device", "show"],
        summary="Show this device passport at its current head.",
        result_schema="urn:ai-stp:schema:v1:cli-passport-view",
        handler="passport:device_show",
        next_actions=("passport developer show",),
    ),
    Declaration(
        path=["project", "discover"],
        summary="List the projects inside a directory you name. Scans nothing else.",
        result_schema="urn:ai-stp:schema:v1:cli-project-candidates",
        handler="project:discover",
        parameters=(
            option(
                "root",
                "string",
                "Directory to look inside. The home directory is refused.",
                required=True,
            ),
        ),
        next_actions=("doctor",),
    ),
    Declaration(
        path=["project", "index"],
        summary="Index one project root, bounded, skipping secrets and binary content.",
        result_schema="urn:ai-stp:schema:v1:cli-project-index",
        handler="project:index",
        parameters=(option("root", "string", "Exact project root to index.", required=True),),
        next_actions=("project discover",),
    ),
    Declaration(
        path=["project", "symbols"],
        summary="Read a project's public symbols, entry points and tests. No call graph.",
        result_schema="urn:ai-stp:schema:v1:cli-project-symbols",
        handler="project:symbol_index",
        parameters=(option("root", "string", "Exact project root to read.", required=True),),
        next_actions=("project index",),
    ),
    Declaration(
        path=["harness", "install"],
        summary="Install the harness program itself under an exact prefix.",
        result_schema="urn:ai-stp:schema:v1:cli-harness-program",
        handler="harness:install",
        mutability="apply",
        parameters=(
            option("harness", "string", "Harness whose program this is.", required=True),
            option("provider", "string", "Exact provider executable to invoke.", required=True),
            option(
                "provider-release-digest",
                "string",
                "Assert the release digest of the provider that will run. Derived "
                "from the verified manifest, or from the executable's own bytes "
                "when it is explicitly unverified; a different value is refused.",
            ),
            option(
                "prefix",
                "string",
                "Absolute directory the program lives under. Not the target.",
                required=True,
            ),
            option("target", "string", "Absolute harness configuration target.", required=True),
            option(
                "provider-manifest",
                "string",
                "Signed provider release manifest proving these exact bytes.",
            ),
            option(
                "provider-build-attestation",
                "boolean",
                "Require a GitHub build attestation for the provider artifact.",
            ),
            option(
                "unverified-provider",
                "boolean",
                "Run a provider no signed release covers, such as one you built "
                "yourself. Every supported system has a launcher that denies the "
                "network by the device: Bubblewrap on Linux, AppContainer on "
                "Windows, sandbox-exec on macOS.",
            ),
        ),
        next_actions=("toolchain harnesses",),
    ),
    Declaration(
        path=["harness", "update"],
        summary="Move the exposed harness program to the version its provider pins.",
        result_schema="urn:ai-stp:schema:v1:cli-harness-program",
        handler="harness:update",
        mutability="apply",
        parameters=(
            option("harness", "string", "Harness whose program this is.", required=True),
            option("provider", "string", "Exact provider executable to invoke.", required=True),
            option(
                "provider-release-digest",
                "string",
                "Assert the release digest of the provider that will run. Derived "
                "from the verified manifest, or from the executable's own bytes "
                "when it is explicitly unverified; a different value is refused.",
            ),
            option(
                "prefix",
                "string",
                "Absolute directory the program lives under. Not the target.",
                required=True,
            ),
            option("target", "string", "Absolute harness configuration target.", required=True),
            option(
                "provider-manifest",
                "string",
                "Signed provider release manifest proving these exact bytes.",
            ),
            option(
                "provider-build-attestation",
                "boolean",
                "Require a GitHub build attestation for the provider artifact.",
            ),
            option(
                "unverified-provider",
                "boolean",
                "Run a provider no signed release covers, such as one you built "
                "yourself. Every supported system has a launcher that denies the "
                "network by the device: Bubblewrap on Linux, AppContainer on "
                "Windows, sandbox-exec on macOS.",
            ),
        ),
        next_actions=("toolchain harnesses",),
    ),
    Declaration(
        path=["harness", "remove"],
        summary="Remove the harness program this CLI installed, and nothing else.",
        result_schema="urn:ai-stp:schema:v1:cli-harness-program",
        handler="harness:remove",
        mutability="destructive",
        confirmation="explicit_flag",
        parameters=(
            option("harness", "string", "Harness whose program this is.", required=True),
            option("provider", "string", "Exact provider executable to invoke.", required=True),
            option(
                "provider-release-digest",
                "string",
                "Assert the release digest of the provider that will run. Derived "
                "from the verified manifest, or from the executable's own bytes "
                "when it is explicitly unverified; a different value is refused.",
            ),
            option(
                "prefix",
                "string",
                "Absolute directory the program lives under. Not the target.",
                required=True,
            ),
            option("target", "string", "Absolute harness configuration target.", required=True),
            option(
                "provider-manifest",
                "string",
                "Signed provider release manifest proving these exact bytes.",
            ),
            option(
                "provider-build-attestation",
                "boolean",
                "Require a GitHub build attestation for the provider artifact.",
            ),
            option(
                "unverified-provider",
                "boolean",
                "Run a provider no signed release covers, such as one you built "
                "yourself. Every supported system has a launcher that denies the "
                "network by the device: Bubblewrap on Linux, AppContainer on "
                "Windows, sandbox-exec on macOS.",
            ),
            option(
                "confirm",
                "boolean",
                "Confirm removing the program this CLI installed under the prefix.",
                required=True,
            ),
        ),
        next_actions=("harness status",),
    ),
    Declaration(
        path=["harness", "resume"],
        summary="Settle a stopped program operation by looking, never by applying again.",
        result_schema="urn:ai-stp:schema:v1:cli-harness-program",
        handler="harness:resume",
        mutability="apply",
        parameters=(
            option("operation", "string", "The operation that stopped.", required=True),
            option("provider", "string", "Exact provider executable to invoke.", required=True),
            option(
                "harness",
                "string",
                "Assert which harness this operation was planned for. Taken from "
                "the operation when omitted; a different value is refused.",
            ),
            option(
                "prefix",
                "string",
                "Assert the prefix this operation was planned against. Taken from "
                "the operation when omitted; a different value is refused.",
            ),
            option(
                "target",
                "string",
                "Assert the target this operation was planned against. Taken from "
                "the operation when omitted; a different value is refused.",
            ),
            option(
                "provider-manifest",
                "string",
                "Signed provider release manifest proving these exact bytes. Taken "
                "from the operation when omitted.",
            ),
            option(
                "provider-build-attestation",
                "boolean",
                "Require a GitHub build attestation for the provider artifact.",
            ),
            option(
                "unverified-provider",
                "boolean",
                "Run a provider no signed release covers, such as one you built "
                "yourself. Every supported system has a launcher that denies the "
                "network by the device: Bubblewrap on Linux, AppContainer on "
                "Windows, sandbox-exec on macOS.",
            ),
        ),
        next_actions=("harness status",),
    ),
    Declaration(
        path=["harness", "status"],
        summary="What program stands under one prefix, from the journal and the disk.",
        result_schema="urn:ai-stp:schema:v1:cli-harness-program-status",
        handler="harness:status",
        parameters=(
            option("harness", "string", "Harness whose program this is.", required=True),
            option(
                "prefix",
                "string",
                "Absolute directory the program lives under. Not the target.",
                required=True,
            ),
        ),
        next_actions=("harness install", "install recover"),
    ),
    Declaration(
        path=["toolchain", "install"],
        summary="Install one pinned tool into the managed directory. Runs nothing from it.",
        result_schema="urn:ai-stp:schema:v1:cli-toolchain-installation",
        handler="toolchain:install_tool",
        mutability="apply",
        parameters=(
            option("tool", "string", "Identifier of a tool the profile pins.", required=True),
            option("offline", "boolean", "Use only the verified cache; never the network."),
        ),
        next_actions=("toolchain profile",),
    ),
    Declaration(
        path=["toolchain", "remove"],
        summary="Remove one managed tool, touching only paths this CLI created.",
        result_schema="urn:ai-stp:schema:v1:cli-toolchain-installation",
        handler="toolchain:remove_tool",
        mutability="destructive",
        confirmation="explicit_flag",
        parameters=(
            option("tool", "string", "Identifier of an installed tool.", required=True),
            option(
                "confirm",
                "boolean",
                "Confirm removing the paths this CLI created for that tool.",
                required=True,
            ),
        ),
        next_actions=("toolchain profile",),
    ),
    Declaration(
        path=["project", "passport"],
        summary="Record a project passport revision pinning the index, toolchain and config.",
        result_schema="urn:ai-stp:schema:v1:cli-passport-view",
        handler="project:passport",
        # It stores a revision in the local registry. Idempotent — an unchanged
        # project adds nothing — but idempotent is not read-only.
        mutability="apply",
        parameters=(option("root", "string", "Exact project root to record.", required=True),),
        next_actions=("project symbols",),
    ),
    Declaration(
        path=["registry", "acquire"],
        summary="Acquire one exact published setup graph for local offline compilation.",
        result_schema="urn:ai-stp:schema:v1:cli-catalog-setup-acquisition",
        handler="registry:acquire",
        mutability="apply",
        parameters=(
            option("id", "string", "Stable identifier of the published setup.", required=True),
            option("version", "string", "Exact two-integer setup version.", required=True),
            option("offline", "boolean", "Use only verified cached passports and artifacts."),
        ),
        next_actions=("install plan",),
    ),
    Declaration(
        path=["registry", "port", "discover"],
        summary="Find compatible SX and APM snapshots under one explicit local root.",
        result_schema="urn:ai-stp:schema:v1:cli-store-port-discovery",
        handler="registry:port_discover",
        parameters=(option("root", "string", "Exact local directory to inspect.", required=True),),
        next_actions=("registry port inspect",),
    ),
    Declaration(
        path=["registry", "port", "inspect"],
        summary="Inspect one setup-store mapping without importing or running its CLI.",
        result_schema="urn:ai-stp:schema:v1:cli-store-port-inspection",
        handler="registry:port_inspect",
        parameters=(
            option("root", "string", "Exact local directory to inspect.", required=True),
            option("adapter", "string", "Store contract.", required=True, choices=("sx", "apm")),
        ),
        next_actions=("registry port plan",),
    ),
    Declaration(
        path=["registry", "port", "plan"],
        summary="Preview a local-only setup-store import and bind it to exact manifest bytes.",
        result_schema="urn:ai-stp:schema:v1:cli-store-port-import-plan",
        handler="registry:port_plan",
        mutability="plan",
        parameters=(
            option("root", "string", "Exact local directory to inspect.", required=True),
            option("adapter", "string", "Store contract.", required=True, choices=("sx", "apm")),
        ),
        next_actions=("registry port import",),
    ),
    Declaration(
        path=["registry", "port", "import"],
        summary="Import a confirmed exact SX or APM snapshot into the local registry only.",
        result_schema="urn:ai-stp:schema:v1:cli-store-port-import-result",
        handler="registry:port_import",
        mutability="apply",
        confirmation="plan_digest",
        parameters=(
            option("root", "string", "Exact local directory named by the plan.", required=True),
            option("adapter", "string", "Store contract.", required=True, choices=("sx", "apm")),
            option(
                "expected-plan-digest", "string", "Exact digest returned by plan.", required=True
            ),
        ),
        next_actions=("component passport validate",),
    ),
    Declaration(
        path=["registry", "fetch"],
        summary="Fetch the exact bytes of one published version into the local cache.",
        result_schema="urn:ai-stp:schema:v1:cli-catalog-artifact",
        handler="registry:fetch",
        # Writes to the local cache and nothing else; the bytes are immutable and
        # addressed by content, so a second call is a no-op.
        mutability="apply",
        parameters=(
            option("kind", "string", "Object kind.", required=True, choices=("component", "setup")),
            option("id", "string", "Typed stable identifier of the object.", required=True),
            option(
                "version",
                "string",
                "Exact two-integer version. A range is not a reference.",
                required=True,
            ),
        ),
        next_actions=("registry version",),
    ),
    Declaration(
        path=["registry", "search"],
        summary="Search the public catalogue without an account.",
        result_schema="urn:ai-stp:schema:v1:cli-catalog-search",
        handler="registry:search",
        parameters=(
            option(
                "kind",
                "string",
                "Which half of the catalogue.",
                required=True,
                choices=("component", "setup"),
            ),
            option("query", "string", "Free text to match."),
            option("cursor", "string", "Opaque cursor from a previous page."),
            option("limit", "integer", "Results per page, within the contract's bound."),
            option(
                "include-experimental",
                "boolean",
                "Also return the experimental lane, in its own section.",
            ),
        ),
        next_actions=("registry show",),
    ),
    Declaration(
        path=["registry", "version"],
        summary="Show one exact published version and its verified passport.",
        result_schema="urn:ai-stp:schema:v1:cli-catalog-version",
        handler="registry:version",
        parameters=(
            option(
                "kind",
                "string",
                "Which half of the catalogue.",
                required=True,
                choices=("component", "setup"),
            ),
            option("id", "string", "The object's stable identifier.", required=True),
            option("version", "string", "The exact version, as X.Y.", required=True),
        ),
        next_actions=("registry show",),
    ),
    Declaration(
        path=["registry", "show"],
        summary="Show one catalogue object and its published versions.",
        result_schema="urn:ai-stp:schema:v1:cli-catalog-object",
        handler="registry:show",
        parameters=(
            option(
                "kind",
                "string",
                "Which half of the catalogue.",
                required=True,
                choices=("component", "setup"),
            ),
            option("id", "string", "The object's stable identifier.", required=True),
        ),
        next_actions=("registry search",),
    ),
    Declaration(
        path=["select", "eligibility"],
        summary="Which candidates a harness may be composed from, and why each refusal happened.",
        result_schema="urn:ai-stp:schema:v1:cli-eligibility-report",
        handler="select:eligible",
        parameters=(
            option("harness", "string", "The harness being composed for.", required=True),
            option("project", "string", "Project root whose facts the target is built from."),
            option(
                "include-unverified",
                "boolean",
                "Consent to consider unverified candidates for this command only. Never stored, "
                "and never enough to select one automatically.",
            ),
            option(
                "for-redistribution",
                "boolean",
                "The composition is meant to be redistributed, so redistribution rights apply.",
            ),
        ),
        next_actions=("component find",),
    ),
    Declaration(
        path=["select", "eligibility-matrix"],
        summary="Where one object may be composed, answered for every supported harness.",
        result_schema="urn:ai-stp:schema:v1:cli-eligibility-matrix",
        handler="select:eligible_everywhere",
        parameters=(
            option(
                "harness",
                "string",
                "Narrow the answer to these harnesses. Repeat to name several; "
                "omit to cover every supported one.",
                repeatable=True,
            ),
            option("project", "string", "Project root whose facts the target is built from."),
            option(
                "include-unverified",
                "boolean",
                "Consent to consider unverified candidates for this command only. Never stored, "
                "and never enough to select one automatically.",
            ),
            option(
                "for-redistribution",
                "boolean",
                "The composition is meant to be redistributed, so redistribution rights apply.",
            ),
        ),
        next_actions=("select eligibility",),
    ),
    Declaration(
        path=["select", "impact"],
        summary="Compare context, token cost and capabilities of exact local setup versions.",
        result_schema="urn:ai-stp:schema:v1:cli-selection-impact-report",
        handler="select:impact_report",
        parameters=(
            option("setup-id", "string", "Candidate setup stable identifier.", required=True),
            option("setup-version", "string", "Candidate exact X.Y version.", required=True),
            option("against-setup-id", "string", "Optional baseline setup stable identifier."),
            option("against-setup-version", "string", "Optional baseline exact X.Y version."),
            option(
                "project-id",
                "string",
                "Use that project's installed or selected setup as the baseline when "
                "explicit baseline is absent.",
            ),
            option(
                "tokenizer-profile",
                "string",
                "Versioned deterministic local estimator.",
                choices=("ai-stp:utf8-bytes/1", "ai-stp:unicode-chars-div4/1"),
            ),
            option("price-profile", "string", "Explicit local token-price profile JSON file."),
        ),
        next_actions=("select blast-radius",),
    ),
    Declaration(
        path=["select", "blast-radius"],
        summary="Show local setup, project, device and installed-target references to a component.",
        result_schema="urn:ai-stp:schema:v1:cli-blast-radius-report",
        handler="select:blast_radius",
        parameters=(
            option("component-id", "string", "Component stable identifier.", required=True),
            option("component-version", "string", "Component exact X.Y version.", required=True),
            option(
                "scenario",
                "string",
                "Read-only impact scenario.",
                choices=("update", "deprecation", "blocked", "expired_evidence", "advisory"),
            ),
        ),
        next_actions=("select impact",),
    ),
    Declaration(
        path=["select", "propose"],
        summary="Record one composition proposal. Creates no version and no target.",
        result_schema="urn:ai-stp:schema:v1:cli-proposal-session",
        handler="select:propose",
        # Persists only the exact, expiring session proposal that confirmation
        # names. It is a plan, not an apply: no version or target exists yet.
        mutability="plan",
        parameters=(
            option("harness", "string", "The harness being composed for.", required=True),
            option("project", "string", "Project root whose passport anchors the session."),
            option(
                "member",
                "string",
                "One exact member as <stable_id>@<X.Y>. Repeat for each.",
                repeatable=True,
            ),
            option(
                "empty",
                "boolean",
                "Compose a setup that projects no files. Refuses alongside --member.",
            ),
        ),
        next_actions=("select confirm",),
    ),
    Declaration(
        path=["select", "confirm"],
        summary="Freeze one proposal as a private setup version, its trace and its pin.",
        result_schema="urn:ai-stp:schema:v1:cli-confirmation",
        handler="select:confirm",
        # The only path from a shown composition to a stored object, and the
        # user's decision is what authorises it.
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("proposal", "string", "The proposal being confirmed.", required=True),
            option(
                "confirm",
                "boolean",
                "Confirm freezing this exact proposal as a setup version.",
                required=True,
            ),
        ),
        next_actions=("select session",),
    ),
    Declaration(
        path=["select", "cancel"],
        summary="Close one proposal without creating a version or changing a target.",
        result_schema="urn:ai-stp:schema:v1:cli-proposal-session",
        handler="select:cancel",
        mutability="apply",
        parameters=(option("proposal", "string", "The proposal being cancelled.", required=True),),
        next_actions=("select session",),
    ),
    Declaration(
        path=["select", "graph"],
        summary="Resolve the exact dependency closure, or name every reason it cannot be.",
        result_schema="urn:ai-stp:schema:v1:cli-setup-graph",
        handler="select:dependency_graph",
        parameters=(
            option("proposal", "string", "Resolve the closure of this proposal's members."),
            option(
                "member",
                "string",
                "One exact root as <stable_id>@<X.Y>. Repeat for each. Use instead of --proposal.",
                repeatable=True,
            ),
        ),
        next_actions=("select propose",),
    ),
    Declaration(
        path=["select", "reports"],
        summary="Composition and conversion reports: what is chosen, what conflicts, what is lost.",
        result_schema="urn:ai-stp:schema:v1:cli-composition-reports",
        handler="select:reports",
        parameters=(
            option("harness", "string", "The harness being composed for.", required=True),
            option("proposal", "string", "The composition being reported on.", required=True),
            option("project", "string", "Project root whose facts the target is built from."),
        ),
        next_actions=("select confirm",),
    ),
    Declaration(
        path=["select", "bundle"],
        summary="Compile the deterministic package for one composition. Writes to no target.",
        result_schema="urn:ai-stp:schema:v1:cli-harness-bundle",
        handler="select:harness_bundle",
        # Compiles bytes and a manifest. `ADR-0012` gives the write to the
        # provider, so this is a read even though it produces a package.
        parameters=(
            option("harness", "string", "The harness being composed for.", required=True),
            option("proposal", "string", "The composition being bundled.", required=True),
            option("project", "string", "Project root whose facts the target is built from."),
        ),
        next_actions=("select reports",),
    ),
    Declaration(
        path=["install", "plan"],
        summary="Compute an immutable installation plan. Has no effect of its own.",
        result_schema="urn:ai-stp:schema:v1:cli-installation",
        handler="install:plan",
        # A plan is recorded, so it writes; it changes no target, so the
        # decision it needs is the approval that follows, not one of its own.
        mutability="plan",
        parameters=(
            option(
                "proposal",
                "string",
                "The newly confirmed composition to install.",
            ),
            option(
                "setup",
                "string",
                "An immutable prepared SetupVersion as <stable_id>@<X.Y>.",
            ),
            option(
                "project",
                "string",
                "Local project root that binds a catalogue setup to the current context.",
            ),
            option(
                "harness",
                "string",
                "The harness of the pair, when no proposal or setup names it.",
                choices=tuple(sorted(HARNESS_IDS)),
            ),
            option(
                "provider", "string", "The provider executable that owns the target.", required=True
            ),
            option(
                "provider-manifest",
                "string",
                "Release manifest whose exact artifact is the provider executable. "
                "Required by protocol v3 unless unverified-provider is given. "
                "A repository pinned for build attestation is verified that way.",
            ),
            option(
                "provider-build-attestation",
                "boolean",
                "Verify exact provider bytes through the repository, source commit and "
                "signer workflow pinned by the local policy. Implied when the "
                "manifest repository already has a pinned build-attestation rule.",
            ),
            option(
                "provider-attestation-bundle",
                "string",
                "Optional local GitHub attestation bundle for offline verification.",
            ),
            option(
                "unverified-provider",
                "boolean",
                "Install from a provider executable no signed or attested "
                "release covers, such as one you built yourself. The pinned "
                "trust policy checks nothing here, and the plan records "
                "provider_release_trusted false.",
            ),
            option(
                "provider-release-recovery",
                "boolean",
                "Explicitly recover an older exact provider release verified on this machine.",
            ),
            option(
                "action",
                "string",
                "Provider lifecycle action.",
                choices=("install", "update", "backup", "remove", "rollback"),
            ),
            option(
                "protocol-version",
                "integer",
                "Provider protocol selected before invocation. A trusted "
                "release manifest selects it; without one this defaults to "
                "frozen v1.",
            ),
            option(
                "target",
                "string",
                "Existing absolute provider target directory. Required by protocol v2/v3.",
            ),
            option(
                "backup-ref",
                "string",
                "Exact provider-owned BackupRef required by a protocol-v3 rollback.",
            ),
            option(
                "permission-profile",
                "string",
                "Provider-declared execution posture, separate from setup identity.",
            ),
        ),
        parameter_rules=(
            CommandParameterRule(kind="exactly_one", parameters=["proposal", "setup"]),
            CommandParameterRule(
                kind="required_when",
                parameters=["project"],
                when_parameter="setup",
                when_values=["present"],
            ),
            CommandParameterRule(
                kind="required_when",
                parameters=["target"],
                when_parameter="protocol-version",
                when_values=["2", "3"],
            ),
        ),
        next_actions=("install approve",),
    ),
    Declaration(
        path=["install", "approve"],
        summary="Approve one plan by its exact digest. Nothing else approves it.",
        result_schema="urn:ai-stp:schema:v1:cli-installation",
        handler="install:approve",
        mutability="apply",
        confirmation="plan_digest",
        parameters=(
            option("operation", "string", "The operation whose plan is approved.", required=True),
            option("plan-digest", "string", "The exact plan digest the user saw.", required=True),
        ),
        next_actions=("install apply",),
    ),
    Declaration(
        path=["install", "apply"],
        summary="Carry out one approved plan through its provider and record what happened.",
        result_schema="urn:ai-stp:schema:v1:cli-installation",
        handler="install:apply",
        mutability="apply",
        confirmation="plan_digest",
        parameters=(
            option("operation", "string", "The approved operation to apply.", required=True),
            option(
                "provider", "string", "The provider executable that owns the target.", required=True
            ),
        ),
        next_actions=("install status",),
    ),
    Declaration(
        path=["install", "cancel"],
        summary="Abandon a plan before anything is applied. Refused once applying began.",
        result_schema="urn:ai-stp:schema:v1:cli-installation",
        handler="install:cancel",
        mutability="apply",
        parameters=(
            option("operation", "string", "The operation being abandoned.", required=True),
            option("reason", "string", "Why it is being abandoned."),
        ),
        next_actions=("install status",),
    ),
    Declaration(
        path=["target", "status"],
        summary="The daily state of one project and harness. Reads; never updates anything.",
        result_schema="urn:ai-stp:schema:v1:cli-target-survey",
        handler="install:target_status",
        parameters=(
            option("project", "string", "The project passport's stable id.", required=True),
            option(
                "harness",
                "string",
                "The harness of the pair.",
                required=True,
                choices=tuple(sorted(HARNESS_IDS)),
            ),
            option("provider", "string", "Provider executable, to read the target as it is now."),
            option(
                "protocol-version",
                "integer",
                "Provider protocol selected before invocation. A trusted "
                "release manifest selects it; without one this defaults to "
                "frozen v1.",
            ),
            option(
                "unverified-provider",
                "boolean",
                "Read the target through an executable no signed or attested "
                "release covers. It does not relax isolation: the read still "
                "runs under the launcher its system proved.",
            ),
            option(
                "target",
                "string",
                "Existing absolute provider target directory. Required by protocol v2 and v3.",
            ),
            option(
                "requires-env",
                "string",
                "An additional uppercase variable this target needs beyond its setup passport. "
                "Never NAME=value.",
                repeatable=True,
            ),
            option("catalog-version", "string", "Newest known version, to report catalog drift."),
        ),
        next_actions=("install plan", "target rollback"),
    ),
    Declaration(
        path=["sync", "preview"],
        summary="Preview local fast-forward, merge or conflict without changing a head.",
        result_schema="urn:ai-stp:schema:v1:cli-sync-preview",
        handler="sync:preview",
        parameters=(
            option(
                "id",
                "string",
                "Stable identifier whose local heads are compared.",
                required=True,
            ),
        ),
        next_actions=("passport developer show",),
    ),
    Declaration(
        path=["sync", "push"],
        summary="Push one exact local head with a durable replay-safe event.",
        result_schema="urn:ai-stp:schema:v1:cli-sync-push",
        handler="sync:push",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("id", "string", "Stable identifier whose head is pushed.", required=True),
            option("confirm", "boolean", "Confirm the exact cloud write.", required=True),
        ),
        next_actions=("sync pull", "sync preview"),
    ),
    Declaration(
        path=["sync", "merge"],
        summary="Commit a mechanically clean merge of two developer-passport heads.",
        result_schema="urn:ai-stp:schema:v1:cli-sync-preview",
        handler="sync:merge",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("id", "string", "Stable identifier with two local heads.", required=True),
            option("confirm", "boolean", "Confirm the exact merge candidate.", required=True),
        ),
        next_actions=("sync push", "sync preview"),
    ),
    Declaration(
        path=["sync", "pull"],
        summary="Pull and atomically apply one bounded page from the account stream.",
        result_schema="urn:ai-stp:schema:v1:cli-sync-pull",
        handler="sync:pull",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("page-size", "integer", "Maximum events in this page."),
            option(
                "skip-event",
                "string",
                "Exact id of a refused event to walk past, abandoning its revision. "
                "Repeat to name several.",
                repeatable=True,
            ),
            option("confirm", "boolean", "Confirm the local registry update.", required=True),
        ),
        next_actions=("sync pull", "sync preview"),
    ),
    Declaration(
        path=["target", "diff"],
        summary="What installing the selected version would change. Changes nothing.",
        result_schema="urn:ai-stp:schema:v1:cli-target-diff",
        handler="install:target_diff",
        parameters=(
            option("project", "string", "The project passport's stable id.", required=True),
            option(
                "harness",
                "string",
                "The harness of the pair.",
                required=True,
                choices=tuple(sorted(HARNESS_IDS)),
            ),
            option("provider", "string", "Provider executable, to read the target as it is now."),
            option(
                "protocol-version",
                "integer",
                "Provider protocol selected before invocation. A trusted "
                "release manifest selects it; without one this defaults to "
                "frozen v1.",
            ),
            option(
                "unverified-provider",
                "boolean",
                "Read the target through an executable no signed or attested "
                "release covers. It does not relax isolation: the read still "
                "runs under the launcher its system proved.",
            ),
            option(
                "target",
                "string",
                "Existing absolute provider target directory. Required by protocol v2 and v3.",
            ),
            option(
                "requires-env",
                "string",
                "An additional uppercase variable this target needs beyond its setup passport. "
                "Never NAME=value.",
                repeatable=True,
            ),
            option("catalog-version", "string", "Newest known version, to report catalog drift."),
        ),
        next_actions=("install plan",),
    ),
    Declaration(
        path=["telemetry", "show"],
        summary="What the anonymous install ping would carry, and whether it is on.",
        result_schema="urn:ai-stp:schema:v1:cli-telemetry-status",
        handler="telemetry:show",
        next_actions=("telemetry consent",),
    ),
    Declaration(
        path=["telemetry", "consent"],
        summary="Answer the telemetry screen. Sends nothing itself.",
        result_schema="urn:ai-stp:schema:v1:cli-telemetry-status",
        handler="telemetry:consent",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option("accept", "boolean", "Agree to the anonymous install ping."),
            option("decline", "boolean", "Refuse it. Nothing asks again."),
            option("confirm", "boolean", "Required by both answers.", required=True),
        ),
        next_actions=("telemetry show",),
    ),
    Declaration(
        path=["target", "backups"],
        summary="Provider-owned copies this pair can restore from. Restores nothing itself.",
        result_schema="urn:ai-stp:schema:v1:cli-target-backups",
        handler="install:target_backups",
        parameters=(
            option("project", "string", "The project passport's stable id.", required=True),
            option(
                "harness",
                "string",
                "The harness of the pair.",
                required=True,
                choices=tuple(sorted(HARNESS_IDS)),
            ),
            # Optional, and the answer without it is exactly the answer this
            # command gave before: the journal's own record. With it the same
            # rows also carry what the provider says now, which is the only way
            # to see a copy the journal still offers and the provider no longer
            # has.
            option(
                "provider",
                "string",
                "Provider executable, to also report which copies still exist and are held.",
            ),
            option(
                "protocol-version",
                "integer",
                "Provider protocol selected before invocation. A trusted "
                "release manifest selects it; without one this defaults to "
                "frozen v1.",
            ),
            option(
                "unverified-provider",
                "boolean",
                "Read through an executable no signed or attested release covers. "
                "On Windows this is also what lets the read run at all, since no "
                "launcher there can deny the network. Elsewhere it changes nothing.",
            ),
            option(
                "target",
                "string",
                "Existing absolute provider target directory. Required by protocol v2 and v3.",
            ),
        ),
        next_actions=("install plan",),
    ),
    Declaration(
        path=["target", "rollback"],
        summary="Name the exact previous verified version. Rolls nothing back itself.",
        result_schema="urn:ai-stp:schema:v1:cli-rollback-target",
        handler="install:target_rollback",
        parameters=(
            option("project", "string", "The project passport's stable id.", required=True),
            option(
                "harness",
                "string",
                "The harness of the pair.",
                required=True,
                choices=tuple(sorted(HARNESS_IDS)),
            ),
        ),
        # Both, because they answer different questions and the difference is
        # exactly what `REQ-814` protects: this names a previous *version*,
        # `target backups` names copies. Reaching a restore from here goes
        # through the copy list, not through this answer.
        next_actions=("target backups", "install plan"),
    ),
    Declaration(
        path=["install", "status"],
        summary="Operations that stopped without a settled outcome. Changes nothing.",
        result_schema="urn:ai-stp:schema:v1:cli-installation-status",
        handler="install:status",
        next_actions=("install recover",),
    ),
    Declaration(
        path=["install", "recover"],
        summary="What one stopped operation left, and what may be done. Recovers nothing itself.",
        result_schema="urn:ai-stp:schema:v1:cli-recovery-report",
        handler="install:recover",
        parameters=(option("operation", "string", "The stopped operation.", required=True),),
        next_actions=("install resume", "install plan"),
    ),
    Declaration(
        path=["install", "resume"],
        summary="Finish the result check an interrupted apply never made. Applies nothing.",
        result_schema="urn:ai-stp:schema:v1:cli-installation",
        mutability="apply",
        handler="install:resume",
        parameters=(
            option("operation", "string", "The interrupted operation.", required=True),
            option("provider", "string", "The provider executable to ask.", required=True),
        ),
        next_actions=("target status",),
    ),
    Declaration(
        path=["setup", "import", "inspect"],
        summary="Read one native configuration and report what it holds. Writes nothing.",
        result_schema="urn:ai-stp:schema:v1:cli-import-inspection",
        handler="project:import_inspect",
        parameters=(
            option("root", "string", "The native configuration directory to read.", required=True),
            option(
                "harness", "string", "Which harness this configuration belongs to.", required=True
            ),
        ),
        next_actions=("setup import plan",),
    ),
    Declaration(
        path=["setup", "import", "plan"],
        summary="Plan exact component and setup drafts from one native configuration.",
        result_schema="urn:ai-stp:schema:v1:cli-setup-import-plan",
        handler="project:import_plan",
        mutability="plan",
        parameters=(
            option(
                "root", "string", "The native configuration directory to inspect.", required=True
            ),
            option(
                "harness", "string", "Which harness this configuration belongs to.", required=True
            ),
        ),
        next_actions=("setup import register",),
    ),
    Declaration(
        path=["setup", "publish", "plan"],
        summary=(
            "Plan the publication of one released setup together with every component it pins."
        ),
        result_schema="urn:ai-stp:schema:v1:cli-publication-set",
        handler="setup_publication:plan",
        # Creates server plans and writes the reviewed set locally. It publishes
        # nothing: the whole point of the set is that one confirmation follows.
        mutability="plan",
        parameters=(
            option("id", "string", "Stable identifier of the released setup.", required=True),
            option("version", "string", "Exact local X.Y version to publish.", required=True),
        ),
        next_actions=("setup publish confirm", "publication status"),
    ),
    Declaration(
        path=["setup", "publish", "confirm"],
        summary="Confirm one exact reviewed publication set: pinned components, then the setup.",
        result_schema="urn:ai-stp:schema:v1:cli-publication-set",
        handler="setup_publication:confirm",
        mutability="apply",
        confirmation="explicit_flag",
        parameters=(
            option(
                "set-digest",
                "string",
                "The exact digest returned by setup publish plan.",
                required=True,
            ),
            option(
                "confirm",
                "boolean",
                "Confirm making this exact graph public.",
                required=True,
            ),
        ),
        next_actions=("publication status", "owner objects"),
    ),
    Declaration(
        path=["setup", "import", "register"],
        summary="Register an inspected configuration as your own setup. No secret value is stored.",
        result_schema="urn:ai-stp:schema:v1:cli-imported-setup",
        handler="project:import_register",
        # It writes a passport and a backup reference. The target is untouched:
        # the provider made the backup and this only records where it is.
        mutability="apply",
        confirmation="plan_digest",
        parameters=(
            option("root", "string", "The native configuration directory to read.", required=True),
            option(
                "harness", "string", "Which harness this configuration belongs to.", required=True
            ),
            option(
                "backup-ref",
                "string",
                "The provider's reference to the backup it already made.",
                required=True,
            ),
            option(
                "plan-digest",
                "string",
                "The exact digest returned by setup import plan.",
                required=True,
            ),
            option("target", "string", "Which target the backup was taken from."),
        ),
        next_actions=("component find",),
    ),
    Declaration(
        path=["provider", "conformance"],
        summary="Check one provider against an explicitly selected protocol. Changes nothing.",
        result_schema="urn:ai-stp:schema:v1:cli-conformance-report",
        handler="select:provider_conformance",
        parameters=(
            option("harness", "string", "The harness this provider claims.", required=True),
            option("executable", "string", "The provider executable to check.", required=True),
            option("target", "string", "Directory passed to the provider as its target."),
            option(
                "protocol-version",
                "integer",
                "Protocol version to check explicitly. Defaults to frozen v1.",
            ),
            option(
                "unverified-provider",
                "boolean",
                "Check an executable no signed or attested release covers, such "
                "as one you built yourself. It does not relax isolation: the "
                "check still runs under the launcher its system proved.",
            ),
        ),
        next_actions=("toolchain harnesses",),
    ),
    Declaration(
        path=["component", "skill", "validate"],
        summary=(
            "Check a skill package against the Agent Skills Specification and "
            "name every deviation. Changes nothing."
        ),
        result_schema="urn:ai-stp:schema:v1:cli-skill-package",
        handler="component:skill_validate",
        parameters=(option("path", "string", "The skill package directory.", required=True),),
        next_actions=("component adopt", "component passport validate"),
    ),
    Declaration(
        path=["provider", "check"],
        summary=(
            "Report each harness's installed setup-system provider and whether "
            "a newer release exists. Changes nothing."
        ),
        result_schema="urn:ai-stp:schema:v1:cli-provider-installations",
        handler="provider:check",
        parameters=(
            option(
                "harness",
                "string",
                "Harness to ask about. Repeatable. Omit for every supported one.",
                repeatable=True,
                choices=tuple(sorted(HARNESS_IDS)),
            ),
            option(
                "offline",
                "boolean",
                "Read what is installed without asking the release source. A "
                "failed request is not reported as 'no update'.",
            ),
        ),
        next_actions=("provider fetch", "provider trust"),
    ),
    Declaration(
        path=["provider", "update", "plan"],
        summary=(
            "Describe replacing one harness's provider with the newest released "
            "version, in the same path. Changes nothing."
        ),
        result_schema="urn:ai-stp:schema:v1:cli-provider-replacement-plan",
        handler="provider:update_plan",
        parameters=_REPLACEMENT_OPTIONS,
        next_actions=("provider update apply", "provider trust"),
    ),
    Declaration(
        path=["provider", "update", "apply"],
        summary="Carry out exactly the provider replacement a plan described.",
        result_schema="urn:ai-stp:schema:v1:cli-provider-replacement-result",
        handler="provider:update_apply",
        mutability="apply",
        parameters=_CONFIRMED_OPTIONS,
        next_actions=("provider check", "provider conformance"),
    ),
    Declaration(
        path=["provider", "reinstall", "plan"],
        summary=(
            "Describe re-installing one exact provider version into the same path. Changes nothing."
        ),
        result_schema="urn:ai-stp:schema:v1:cli-provider-replacement-plan",
        handler="provider:reinstall_plan",
        parameters=(*_REPLACEMENT_OPTIONS, _VERSION_OPTION),
        next_actions=("provider reinstall apply", "provider trust"),
    ),
    Declaration(
        path=["provider", "reinstall", "apply"],
        summary="Carry out exactly the provider reinstallation a plan described.",
        result_schema="urn:ai-stp:schema:v1:cli-provider-replacement-result",
        handler="provider:reinstall_apply",
        mutability="apply",
        parameters=(*_CONFIRMED_OPTIONS, _VERSION_OPTION),
        next_actions=("provider check", "provider conformance"),
    ),
    Declaration(
        path=["provider", "forget"],
        summary=("Drop the recorded provider choice so configuration and discovery decide again."),
        result_schema="urn:ai-stp:schema:v1:cli-provider-installations",
        handler="provider:forget",
        mutability="apply",
        parameters=(
            option(
                "harness",
                "string",
                "Harness to forget. Repeatable. Omit for every supported one.",
                repeatable=True,
                choices=tuple(sorted(HARNESS_IDS)),
            ),
        ),
        next_actions=("provider check",),
    ),
    Declaration(
        path=["provider", "fetch"],
        summary=("Download an attested OpenNetwork provider and bind a closed release manifest."),
        result_schema="urn:ai-stp:schema:v1:cli-provider-bound-release",
        handler="select:provider_fetch",
        mutability="apply",
        parameters=(
            option(
                "harness",
                "string",
                "Harness whose pinned OpenNetwork setup-system to fetch.",
                required=True,
                choices=tuple(sorted(HARNESS_IDS)),
            ),
            option(
                "tag",
                "string",
                (
                    "Exact release tag. Omit to bind the current GitHub release "
                    "after resolving its tag."
                ),
            ),
            option(
                "directory",
                "string",
                "Directory that receives the artifact and bound manifest.",
            ),
            option(
                "artifact",
                "string",
                "Existing provider artifact to bind instead of downloading.",
            ),
            option(
                "attestation-bundle",
                "string",
                "Optional local GitHub attestation bundle for offline verification.",
            ),
        ),
        next_actions=("install plan", "provider trust"),
    ),
    Declaration(
        path=["provider", "network"],
        summary="Report observed protocol-v2 network isolation on this machine.",
        result_schema="urn:ai-stp:schema:v1:cli-provider-network-capability",
        handler="select:provider_network",
        next_actions=("provider conformance",),
    ),
    Declaration(
        path=["provider", "trust"],
        summary="Report the pinned provider trust policy, and check one release against it.",
        result_schema="urn:ai-stp:schema:v1:cli-provider-trust",
        handler="select:provider_trust",
        parameters=(
            option("manifest", "string", "Release manifest to check. Omit to report the policy."),
        ),
        next_actions=("provider conformance",),
    ),
    Declaration(
        path=["select", "session"],
        summary="Open proposals for one project and harness, and the version selected.",
        result_schema="urn:ai-stp:schema:v1:cli-proposal-session",
        handler="select:session",
        parameters=(
            option("harness", "string", "The harness being composed for.", required=True),
            option("project", "string", "Project root whose passport anchors the session."),
        ),
        next_actions=("select propose",),
    ),
    Declaration(
        path=["skill", "install"],
        summary="Install the canonical Agent Skill at a named destination.",
        result_schema="urn:ai-stp:schema:v1:cli-skill-delivery",
        handler="skill:install",
        # Writes one file and its ownership record, and refuses to replace a
        # skill this installation did not write.
        mutability="apply",
        parameters=(
            option("target", "string", "Directory the harness reads its native skill from."),
            option(
                "harness",
                "string",
                "Install the native projection for this harness instead of the canonical skill.",
            ),
        ),
        next_actions=("skill status",),
    ),
    Declaration(
        path=["skill", "remove"],
        summary="Remove the Agent Skill this installation put at a destination.",
        result_schema="urn:ai-stp:schema:v1:cli-skill-delivery",
        handler="skill:remove",
        mutability="apply",
        parameters=(
            option("target", "string", "Directory the harness reads its native skill from."),
        ),
        next_actions=("skill status",),
    ),
    Declaration(
        path=["skill", "status"],
        summary="Report what Agent Skill is at a destination and who owns it.",
        result_schema="urn:ai-stp:schema:v1:cli-skill-delivery",
        handler="skill:status",
        parameters=(
            option("target", "string", "Directory the harness reads its native skill from."),
        ),
        next_actions=("capabilities",),
    ),
    Declaration(
        path=["toolchain", "harness-capabilities"],
        # `#462` item 5 asked for this to be renamed *or* clarified so the
        # result cannot be read as effective provider support. Clarified: the
        # payload now answers both questions per kind — what the product reads
        # and what this build routes — so the ambiguity is gone from the data
        # rather than from the name. A path change costs every caller that has
        # this in machine help, and buys nothing the payload does not already
        # say.
        summary=(
            "Per harness and kind: what the product natively reads, what this build "
            "can project, and why any gap is a gap. Not a claim that a component "
            "is active — ask the provider for that."
        ),
        result_schema="urn:ai-stp:schema:v1:cli-harness-capability-table",
        handler="toolchain:harness_capabilities",
        # The third column is the provider's own declaration, which needs a
        # fetched provider and so is a different command rather than a field
        # this one could fill offline.
        next_actions=("provider conformance", "toolchain harnesses", "component discover"),
    ),
    Declaration(
        path=["toolchain", "harnesses"],
        summary="Report every supported harness and whether it is on this machine.",
        result_schema="urn:ai-stp:schema:v1:cli-harness-survey",
        handler="toolchain:harnesses",
        next_actions=("toolchain profile",),
    ),
    Declaration(
        path=["toolchain", "profile"],
        summary="Show the managed toolchain profile as it resolves on this machine.",
        result_schema="urn:ai-stp:schema:v1:cli-toolchain-profile",
        handler="toolchain:profile",
        next_actions=("doctor",),
    ),
    Declaration(
        path=["version"],
        summary="Report the running build and the contract versions it speaks.",
        result_schema="urn:ai-stp:schema:v1:cli-version-report",
        handler="version:run",
        next_actions=("doctor",),
    ),
)


def _command(declaration: Declaration) -> Command:
    return Command(
        descriptor=CommandDescriptor(
            path=declaration.path,
            summary=declaration.summary,
            mutability=declaration.mutability,
            confirmation=declaration.confirmation,
            parameters=list(declaration.parameters),
            parameter_rules=list(declaration.parameter_rules),
            result_schema=declaration.result_schema,
            next_actions=list(declaration.next_actions),
        ),
        handler_ref=declaration.handler,
    )


COMMANDS: Final[tuple[Command, ...]] = tuple(_command(item) for item in DECLARATIONS)


def command_paths() -> list[str]:
    """Every command, as the strings a caller types."""
    return sorted(command.name for command in COMMANDS)


def descriptors() -> list[CommandDescriptor]:
    """Every descriptor, ordered so the rendering is deterministic."""
    return [command.descriptor for command in sorted(COMMANDS, key=lambda item: item.name)]


def reserved_option_names() -> frozenset[str]:
    """Option names a command may not redeclare.

    `--json` belongs to every command; a command declaring it again would put
    the same flag in machine help twice and let the two descriptions diverge.
    """
    return frozenset({item.name for item in GLOBAL_OPTIONS}) | {JSON_FLAG.removeprefix("--")}
