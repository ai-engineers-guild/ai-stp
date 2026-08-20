"""Wire conventions shared by every ``/v1`` route (docs/contracts/http-api.md).

One place owns the things every route repeats: the base path, the correlation
and precondition headers, the opaque cursor, the page envelope and the mapping
from a stable ``AI_STP_*`` code to an HTTP status. Routes declare payloads;
they never restate a convention.

The error body is deliberately the foundation ``ErrorEnvelope`` rather than a
second shape: the CLI then parses cloud failures and local failures through one
reader (docs/contracts/cli-json.md). HTTP status carries success, so a success
body is the resource itself and never a redundant ``ok``/``data`` wrapper.
"""

from typing import Annotated, Final, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic.json_schema import JsonSchemaValue

from ai_stp_foundation.errors import (
    ERROR_CODES,
    EXIT_AUTH,
    EXIT_CONFLICT_OR_DECISION,
    EXIT_INTERNAL,
    EXIT_INVALID_INPUT,
    EXIT_PARTIAL,
    EXIT_UNAVAILABLE,
    exit_class_for,
)
from ai_stp_foundation.timestamps import TIMESTAMP_PATTERN, is_valid_timestamp

API_VERSION: Final[str] = "v1"
API_BASE_PATH: Final[str] = "/v1"

#: Supported wire major. An unknown major fails typed rather than degrading
#: (docs/engineering/schema-evolution.md).
SCHEMA_VERSION: Final[int] = 1

REQUEST_ID_HEADER: Final[str] = "X-Request-Id"
OPERATION_ID_HEADER: Final[str] = "X-Operation-Id"
SCHEMA_VERSION_HEADER: Final[str] = "X-AI-STP-Schema-Version"
IDEMPOTENCY_KEY_HEADER: Final[str] = "Idempotency-Key"
IF_MATCH_HEADER: Final[str] = "If-Match"
ETAG_HEADER: Final[str] = "ETag"

#: Opaque to the client: an ordering token, never a decodable offset or ID.
#: The server owns its interior; the client may only echo it back verbatim.
#:
#: Known engine divergence, deliberately left in place: `$` matches before a
#: trailing newline in Python's `re` — which is what a JSON Schema validator
#: runs — but not in the Rust regex pydantic runs, so `"abc\n"` is schema-valid
#: and model-invalid. It cannot be closed in one pattern string: `\Z`/`\z` are
#: not ECMA-262, and a `(?![\s\S])` lookahead makes pydantic fail to build the
#: validator at all, because Rust's regex crate has no lookaround. The
#: divergence is in the safe direction — the model is the stricter of the two —
#: and a test pins it so a later "fix" cannot silently pick the other side.
CURSOR_PATTERN: Final[str] = r"^[A-Za-z0-9_-]{1,512}$"

#: An idempotency key is client-chosen and opaque to us; bounded so it cannot
#: become an unbounded storage key. Same anchoring note as the cursor.
IDEMPOTENCY_KEY_PATTERN: Final[str] = r"^[A-Za-z0-9._~-]{16,128}$"

PAGE_SIZE_DEFAULT: Final[int] = 20
PAGE_SIZE_MAX: Final[int] = 100

type Cursor = Annotated[str, Field(pattern=CURSOR_PATTERN)]
type IdempotencyKey = Annotated[str, Field(pattern=IDEMPOTENCY_KEY_PATTERN)]
type PageSize = Annotated[int, Field(ge=1, le=PAGE_SIZE_MAX)]


def _real_moment(value: str) -> str:
    """Reject a well-formed string that is not a moment that exists."""
    if not is_valid_timestamp(value):
        raise ValueError(f"not a real calendar moment: {value!r}")
    return value


#: Declared once for the whole package: every `/v1` payload spells a moment the
#: same way, and a second alias per module would be one more place to drift.
#:
#: The pattern alone accepts `2026-13-40T25:61:61.999Z`, and every consumer that
#: later calls `parse_timestamp` on it crashes *after* validation reported
#: success. So the alias also parses. JSON Schema cannot express "is a real
#: date", so the emitted schema keeps only the pattern and the model is the
#: stricter of the two — the safe direction for a boundary check.
type Timestamp = Annotated[str, Field(pattern=TIMESTAMP_PATTERN), AfterValidator(_real_moment)]

#: Exit class to HTTP status. The registry in ``ai_stp_foundation.errors`` maps
#: a code to its exit class, so the status of any code is derived, never
#: restated per route. ``EXIT_PARTIAL`` is 500-class on the wire: a partial
#: mutation is not a client error and the caller must recover, not retry.
_STATUS_BY_EXIT_CLASS: Final[dict[int, int]] = {
    EXIT_INVALID_INPUT: 400,
    EXIT_AUTH: 401,
    EXIT_CONFLICT_OR_DECISION: 409,
    EXIT_UNAVAILABLE: 503,
    EXIT_PARTIAL: 500,
    EXIT_INTERNAL: 500,
}

#: Codes whose HTTP status is narrower than their exit class implies. The
#: stable ``code`` stays the machine identifier, so a shared status never
#: collapses two distinct outcomes. The device-flow codes keep RFC 8628's
#: ``400`` on the wire while carrying our own exit class locally.
_STATUS_OVERRIDES: Final[dict[str, int]] = {
    "AI_STP_NOT_FOUND": 404,
    "AI_STP_PERMISSION_DENIED": 403,
    "AI_STP_DEVICE_REVOKED": 403,
    "AI_STP_RATE_LIMITED": 429,
    "AI_STP_TIMEOUT_UNCONFIRMED": 504,
    # A failed `If-Match` is a precondition failure, not a generic conflict:
    # the caller sent a version and it no longer holds. Answering 409 would make
    # it indistinguishable from a concurrent-change conflict the caller can
    # retry differently.
    "AI_STP_PRECONDITION_FAILED": 412,
    "AI_STP_AUTHORIZATION_PENDING": 400,
    "AI_STP_AUTHORIZATION_EXPIRED": 400,
    "AI_STP_AUTHORIZATION_DECLINED": 400,
}


_UNKNOWN_OVERRIDES: Final[list[str]] = sorted(set(_STATUS_OVERRIDES) - set(ERROR_CODES))
if _UNKNOWN_OVERRIDES:  # pragma: no cover - import-time guard, cannot be reached in a valid build
    # A renamed or mistyped key would leave a dead override that never fires,
    # silently answering with the exit class instead. Failing at import makes
    # that unbuildable rather than something a test has to remember to notice.
    raise RuntimeError(f"status override for unregistered codes: {', '.join(_UNKNOWN_OVERRIDES)}")


def http_status_for(code: str) -> int:
    """Return the HTTP status of one registered stable error code."""
    override = _STATUS_OVERRIDES.get(code)
    if override is not None:
        return override
    return _STATUS_BY_EXIT_CLASS[exit_class_for(code)]


def open_wire_object(schema: JsonSchemaValue) -> None:
    """Wire policy for every ``/v1`` payload in this package.

    Two halves of one contract ship from here — this generated schema and the
    Python model it came from — so they must permit the same documents. That
    imposes two rules on every class that uses this hook, and breaking either
    makes the published artifact disagree with the shipped code:

    - **``extra="allow"``, never ``extra="forbid"``.** The schema says
      ``additionalProperties: true`` so a newer server may add an optional field
      inside the supported major; a model that forbade extras would hard-fail on
      exactly the additive evolution `docs/engineering/schema-evolution.md`
      prescribes, and an already-installed CLI could only be rescued by a forced
      upgrade. `schema-evolution.md` also says a reader *preserves* an unknown
      optional value rather than dropping it, which is why this is ``allow`` and
      not ``ignore``.
    - **No Python default on a field that carries server state.** ``required``
      below is every declared field, so a default would let the model accept a
      document the schema rejects — and for a field like ``next_cursor`` the
      default silently invents the very answer the caller needed. A default is
      allowed only on a constant discriminant such as ``schema_version``, whose
      ``Literal`` admits exactly one value, so absence cannot mask a server
      error.
    """
    properties = schema.get("properties", {})
    schema["required"] = sorted(properties)
    schema["additionalProperties"] = True


def strict_request_object(schema: JsonSchemaValue) -> None:
    """Wire policy for every ``/v1`` request payload — the mirror of the above.

    A response is a *description* and tolerates additions; a request is an
    *instruction* and does not. An unknown query parameter is not forward
    compatibility, it is a silently dropped filter: the caller asked to narrow
    the result, the server ignored it, and the answer looks like a complete one.
    A mistyped `--tag` must fail loudly rather than return the unfiltered
    catalogue.

    Version skew is carried by ``X-AI-STP-Schema-Version``, which fails typed,
    rather than by pretending an instruction was understood.
    """
    schema["additionalProperties"] = False


class PageInfo(BaseModel):
    """Cursor pagination state (docs/contracts/http-api.md).

    No total is exposed. Reporting one would let a caller detect objects it is
    not allowed to read, so a hidden or deleted object leaks through neither a
    count nor a cursor.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Always present. Catalog and object-list last pages use ``null``. Sync
    #: pull returns a resumable cursor on every non-empty page (ADR-0091).
    #: There is no Python default: a dropped field on a non-final catalog page
    #: would otherwise read as "last page" and hide remaining objects.
    next_cursor: Cursor | None

    #: The size the server actually applied, which is not necessarily the size
    #: requested: a request above `PAGE_SIZE_MAX` is clamped rather than
    #: rejected. It is not the number of items in this page — read `len(items)`
    #: for that, since a page may be short without being the last one.
    page_size: PageSize
