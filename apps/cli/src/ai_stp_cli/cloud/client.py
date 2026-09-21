"""The typed `/v1` client (issue #75).

One place decides timeouts, headers, which failures are worth retrying and how a
server answer becomes a registered `AI_STP_*` code. Callers get models, never
raw responses, so no route can invent its own error vocabulary. The one
exception is ``call_document``: a passport digest is over the published JSON
object, and a model dump is not those bytes.

The mock from `#71` and a real server are the same to this module: both are an
`httpx` transport, and the serializers are the models themselves. That is what
makes "tested against the mock" mean something — there is no second code path
for the real thing to diverge into.

Nothing here writes a token, a URL with a query, or a response body into an
error. `SPEC-011` REQ-1108 keeps secrets out of output, and a callback URL is
exactly the kind of thing that carries one.
"""

import ipaddress
import json
import time
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final, cast
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ValidationError

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.runtime import DISTRIBUTION, cli_version
from ai_stp_contracts.http import (
    API_BASE_PATH,
    REQUEST_ID_HEADER,
    SCHEMA_VERSION,
    SCHEMA_VERSION_HEADER,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.envelope import Continuation
from ai_stp_foundation.errors import is_registered_code

#: Bounded on purpose. An agent waiting on a hung connection cannot tell the
#: difference between slow and broken, and neither can the person waiting on it.
CONNECT_TIMEOUT: Final[float] = 5.0
READ_TIMEOUT: Final[float] = 30.0

#: Total attempts, including the first. Bounded so a retry loop cannot become an
#: outage amplifier, and small because every retried call here is a read or a
#: poll the user is waiting on.
MAX_ATTEMPTS: Final[int] = 3
BACKOFF_SECONDS: Final[float] = 0.5

#: Statuses worth trying again. A 429 is included because the contract pairs it
#: with `Retry-After`; the 5xx family because the request never reached a
#: decision. Everything else is a decision the server made, and repeating it
#: produces the same decision.
RETRYABLE_STATUSES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})

#: Codes that describe the state of the account or the device rather than a
#: transient condition. Retrying one of these cannot change the answer, and
#: doing so would turn a declined sign-in into a hammering loop.
NEVER_RETRIED: Final[frozenset[str]] = frozenset(
    {
        "AI_STP_AUTH_REQUIRED",
        "AI_STP_AUTHORIZATION_DECLINED",
        "AI_STP_AUTHORIZATION_EXPIRED",
        "AI_STP_AUTHORIZATION_PENDING",
        "AI_STP_DEVICE_REVOKED",
        "AI_STP_PERMISSION_DENIED",
        "AI_STP_SCHEMA_UNSUPPORTED",
        "AI_STP_VALIDATION_ERROR",
        "AI_STP_NOT_FOUND",
        "AI_STP_CONFLICT",
        "AI_STP_PRECONDITION_FAILED",
        # Carries HTTP 500, which is otherwise retryable, but the stored bytes
        # will not become valid between two attempts half a second apart. The
        # server already recorded the integrity event; repeating the call only
        # multiplies it.
        "AI_STP_CATALOG_INTEGRITY",
    }
)


@dataclass(frozen=True)
class Endpoint:
    """Where the platform is, how to reach it, and how patient to be.

    The transport belongs here because "the platform" and "a deterministic mock
    of the platform" are the same thing to every caller — `#75` requires the CLI
    to be fully exercisable before a server exists, and that only means
    something if there is no second code path for the real one to diverge into.
    """

    base_url: str
    max_attempts: int = MAX_ATTEMPTS
    transport: httpx.BaseTransport | None = None


def as_query(
    request: BaseModel, *, omit: frozenset[str] = frozenset({"schema_version"})
) -> dict[str, str]:
    """Render a typed request as query parameters.

    Search is a `GET` in the frozen contract, so its parameters travel in the
    query string. The model is still the serializer — that is what keeps the
    mock and a real server on one code path — but the wire form is different
    from a body, and treating them as interchangeable is how a client ends up
    sending a body no route reads.

    An absent optional is omitted rather than sent empty: a filter the caller
    did not ask for must not narrow the result.
    """
    rendered: dict[str, str] = {}
    for name, value in request.model_dump(mode="json").items():
        if name in omit or value is None or value == []:
            continue
        rendered[name] = "true" if value is True else "false" if value is False else str(value)
    return rendered


def check_base_url(value: str) -> str:
    """Parse the configured address and refuse anything unfit to send secrets to.

    `cli-config.md` requires HTTPS, and this is the connection a device key and a
    refresh token travel over, so the check is made here rather than trusted.

    Parsed rather than prefix-matched. `value.startswith("https://")` accepted
    `https://@elsewhere.test`, `https:///v1` and an address with a fragment, then
    handed the string to whichever parser looked at it next — and what that
    parser considers the authority is not something this module got to decide.
    Normalising here means every later caller sees one interpretation.

    Cleartext is allowed for loopback and nowhere else (`#194`). A development
    stack runs the API on `http://localhost:8000` with no TLS, and refusing it
    made the CLI unable to reach a healthy local backend at all. The exception is
    as narrow as the reason for it: the host must *be* the loopback interface, so
    packets never leave the machine and there is no network to intercept them on.
    A LAN address or a public name over `http` is still refused — that is the
    case the rule exists for.
    """
    text = value.strip()
    # Surrounding whitespace is a copy-and-paste artefact and is stripped;
    # whitespace inside the address is not something to guess about.
    if any(character.isspace() for character in text):
        raise _address_refused("the catalogue address must contain no whitespace")
    parsed = urlsplit(text)
    if parsed.scheme not in {"https", "http"}:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the catalogue address must use HTTPS",
            details={"scheme": parsed.scheme or "none"},
            next_actions=["config show --json"],
        )
    if parsed.scheme == "http" and not is_loopback(parsed.hostname):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the catalogue address must use HTTPS unless it is loopback",
            details={"scheme": parsed.scheme, "host": parsed.hostname or "none"},
            next_actions=["config show --json"],
        )
    # `hostname` is the parsed authority, so `https://@elsewhere.test` and
    # `https:///v1` are both caught here. A prefix check accepted both and left
    # the interpretation to whatever parser saw the string next.
    if not parsed.hostname:
        raise _address_refused("the catalogue address names no host")
    if parsed.username is not None or parsed.password is not None:
        # Credentials in the authority are a way to make a URL look like it
        # points somewhere it does not, and nothing here would ever need them.
        raise _address_refused("the catalogue address must carry no credentials")
    if parsed.query or parsed.fragment:
        raise _address_refused("the catalogue address must carry no query or fragment")
    # The scheme is carried through rather than rewritten: it was validated
    # above, and forcing `https` here would silently point a development stack
    # at a port that is not listening for TLS.
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def is_loopback(host: str | None) -> bool:
    """Whether this host is the machine itself, and therefore off the network.

    Exact matches only. `localhost.evil.test` is not localhost, and a numeric
    form `ipaddress` does not recognise — `2130706433`, `0177.0.0.1`, `127.1` —
    is not accepted either, even though a resolver might well send it to the
    loopback interface. Failing closed on a spelling we cannot read is the safe
    direction when the answer decides whether cleartext is allowed.
    """
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _address_refused(message: str) -> CliFailure:
    # The value is not echoed: it comes from configuration, and this is the
    # address a device key and a refresh token would have travelled to.
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        message,
        next_actions=["config show --json"],
    )


@contextmanager
def open_client(
    endpoint: Endpoint,
    *,
    transport: httpx.BaseTransport | None = None,
    access_token: str | None = None,
) -> Generator[httpx.Client]:
    """A client with the contract's headers already on it."""
    # Name the caller. Left to `httpx` this reads `python-httpx/0.28.1`, which
    # says which library was linked and nothing about who is calling — the same
    # request an arbitrary script sends, indistinguishable in anybody's logs.
    #
    # The provider side measured what that costs in the general case: their
    # evidence job fetched pinned artifacts with `urllib`, and a vendor CDN
    # answered `403 Forbidden` to `Python-urllib/3.x` while serving the same URL
    # to `curl`. Nothing refuses us today because the origin is one we operate,
    # but `catalog.url` is configurable and a deployment may sit behind
    # something that declines generic agents.
    headers = {
        SCHEMA_VERSION_HEADER: str(SCHEMA_VERSION),
        "Accept": "application/json",
        "User-Agent": f"{DISTRIBUTION}/{cli_version()}",
    }
    if access_token is not None:
        headers["Authorization"] = f"Bearer {access_token}"
    client = httpx.Client(
        base_url=check_base_url(endpoint.base_url),
        timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
        headers=headers,
        transport=transport or endpoint.transport,
        # A redirect on an authenticated call would resend the bearer token to
        # wherever the redirect points.
        follow_redirects=False,
    )
    try:
        yield client
    finally:
        client.close()


def call[T: BaseModel](
    client: httpx.Client,
    method: str,
    path: str,
    model: type[T],
    *,
    body: BaseModel | None = None,
    query: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
    attempts: int = MAX_ATTEMPTS,
    pause: Callable[[float], None] = time.sleep,
) -> T:
    """Make one call and return the payload it promises, or raise a typed failure.

    Retries are bounded and only cover conditions where the answer can change:
    a transport error, a 5xx, or a rate limit the server asked us to wait out.
    A refusal is never retried — see `NEVER_RETRIED`.
    """
    response = _exchange(
        client,
        method,
        path,
        body=body,
        query=query,
        headers=headers,
        attempts=attempts,
        pause=pause,
    )
    return _decode(response, model)


def call_document(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    body: BaseModel | None = None,
    query: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
    attempts: int = MAX_ATTEMPTS,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, JsonValue]:
    """Make one call and return the JSON object as received.

    Used where a digest is over published bytes: a model dump injects later
    default fields and is not what the catalogue hashed.
    """
    response = _exchange(
        client,
        method,
        path,
        body=body,
        query=query,
        headers=headers,
        attempts=attempts,
        pause=pause,
    )
    return _decode_document(response)


def _exchange(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    body: BaseModel | None,
    query: Mapping[str, str] | None,
    headers: Mapping[str, str] | None,
    attempts: int,
    pause: Callable[[float], None],
) -> httpx.Response:
    total = max(1, attempts)
    delay = BACKOFF_SECONDS
    last: CliFailure | None = None

    for attempt in range(1, total + 1):
        response: httpx.Response | None = None
        try:
            response = client.request(
                method,
                f"{API_BASE_PATH}{path}",
                params=None if query is None else dict(query),
                content=None if body is None else body.model_dump_json(),
                headers={
                    **({} if body is None else {"Content-Type": "application/json"}),
                    **(dict(headers) if headers else {}),
                },
            )
        except httpx.HTTPError as error:
            # The message can carry a full URL with a query, so only the type is
            # published.
            last = CliFailure(
                "AI_STP_DEPENDENCY_UNAVAILABLE",
                "the platform could not be reached",
                retryable=True,
                details={"exception": type(error).__name__},
                next_actions=["doctor --json"],
            )
        else:
            if response.status_code < 400:
                return response
            last = failure_from(response)
            if not _worth_retrying(response.status_code, last.code):
                raise last

        if attempt >= total:
            break
        pause(_retry_after(response) or delay)
        delay *= 2

    assert last is not None
    raise last


def _worth_retrying(status: int, code: str) -> bool:
    if code in NEVER_RETRIED:
        return False
    return status in RETRYABLE_STATUSES


def _retry_after(response: httpx.Response | None) -> float | None:
    """Honour the server's own pacing when it gives one."""
    if response is None:
        return None
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        return None
    # Bounded: a server asking for an hour must not hang the caller silently.
    return min(max(seconds, 0.0), 60.0)


def _decode[T: BaseModel](response: httpx.Response, model: type[T]) -> T:
    try:
        return model.model_validate(_decode_document(response))
    except ValidationError as error:
        raise _malformed(response, error) from error


def _decode_document(response: httpx.Response) -> dict[str, JsonValue]:
    try:
        document = json.loads(response.text)
    except ValueError as error:
        raise _malformed(response, error) from error
    _check_schema_version(response, document)
    if not isinstance(document, dict):
        raise _malformed(response, TypeError("response body is not an object"))
    return cast(dict[str, JsonValue], document)


def _check_schema_version(response: httpx.Response, document: object) -> None:
    """Refuse a newer wire major with the code that names the problem.

    `cli-json.md`: an unknown major version is rejected. Without this it would
    still be rejected — the models pin `schema_version` — but as a generic
    "malformed body", and an agent reads those differently: one says "upgrade
    this CLI", the other says "the server is broken". Unknown *optional* fields
    within the supported major stay accepted and preserved, which is the other
    half of the same rule.
    """
    if not isinstance(document, dict):
        return
    reported = cast(dict[str, object], document).get("schema_version")
    if isinstance(reported, int) and not isinstance(reported, bool) and reported > SCHEMA_VERSION:
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "the platform answered with a newer contract version than this build understands",
            details={
                "found": str(reported),
                "supported": str(SCHEMA_VERSION),
                "request_id": response.headers.get(REQUEST_ID_HEADER, ""),
            },
            next_actions=["version --json"],
        )


def _malformed(response: httpx.Response, error: BaseException) -> CliFailure:
    """A conforming server did not answer.

    This is a client-side refusal, not a server error: what arrived does not
    match the published contract, and acting on it would mean acting on
    something nobody agreed to.

    It used to be `AI_STP_VALIDATION_ERROR`, whose handling is
    `correct_request`. That names the caller as the author of the problem, so an
    agent given a perfectly valid request went and edited it — and for a
    mutation it is worse than useless: the server answered, so the request may
    well have taken effect, and the one thing that matters is finding out.
    """
    return CliFailure(
        "AI_STP_PROTOCOL_VIOLATION",
        "the platform answered with a body that does not match the published contract",
        details={
            "status": str(response.status_code),
            "exception": type(error).__name__,
            "request_id": response.headers.get(REQUEST_ID_HEADER, ""),
        },
        next_actions=["version --json", "doctor --json"],
    )


#: Everyday sign-in is the account intent. Naming `auth login --provider …`
#: here is how a weak model learned the expert leaf (`SPEC-080` REQ-8022).
#: Which provider this installation uses is a blocked question on that intent,
#: not a pair of guessed argv lines.
_ACCOUNT_START: Final = "task start --intent account --idempotency-key account-session-01 --json"
_LOGIN_ACTIONS: Final[tuple[str, ...]] = (_ACCOUNT_START,)
_ACCOUNT_RESTART: Final[frozenset[str]] = frozenset(
    {
        "AI_STP_AUTH_REQUIRED",
        "AI_STP_AUTHORIZATION_EXPIRED",
        "AI_STP_AUTHORIZATION_PENDING",
    }
)

#: How to get out of a refusal the server reported. A code raised locally
#: already names its way back; the same code arriving over the wire named
#: nothing, because the response body carries no next actions.
#:
#: Keyed by the exact code rather than by the registry's handling class, which
#: is a coarser thing than a recovery: one `restart_authorization` covers an
#: expired authorization, a declined one and a revoked device. The recipe that
#: fits the third — retiring the device key — discards a healthy identity in
#: the first and overrides the user's own answer in the second. Codes whose
#: recovery depends on the command that failed are absent on purpose: inventing
#: a step for `correct_request` or `reconcile_state` would be worse than
#: silence.
_WAY_BACK: Final[Mapping[str, tuple[str, ...]]] = {
    "AI_STP_AUTH_REQUIRED": _LOGIN_ACTIONS,
    # Pending is not a decision. The device-code is already in the secret
    # store; the account intent finishes it. Naming `auth complete` taught
    # the expert leaf.
    "AI_STP_AUTHORIZATION_PENDING": _LOGIN_ACTIONS,
    # The request aged out; the identity behind it did not. Ask again.
    "AI_STP_AUTHORIZATION_EXPIRED": _LOGIN_ACTIONS,
    # The user said no. No command here turns that into approval, and offering
    # one asks the same person the same question until they stop reading it.
    # Reading the resulting state is the only honest next step.
    "AI_STP_AUTHORIZATION_DECLINED": ("auth status --json",),
    # Revocation is the one case where the key itself is the problem, and
    # `SPEC-002` REQ-207 is explicit that resuming needs a new key *and* a new
    # sign-in. This is the only entry that retires anything, and it is reached
    # only when the server says the device is revoked — which is the same
    # recovery `cloud/login.py` gives when this device notices it first.
    "AI_STP_DEVICE_REVOKED": ("device reset --confirm --json", *_LOGIN_ACTIONS),
}


def login_actions() -> list[str]:
    """Everyday sign-in, for callers that refuse before any request."""
    return list(_LOGIN_ACTIONS)


def login_continuations() -> list[Continuation]:
    """`actor=cli` start so FOLLOW_ACTOR does not copy `auth login` or `auth complete`."""
    from ai_stp_cli.application.outcome import intent_start_continuation

    return [intent_start_continuation("account")]


def _way_back(code: str) -> list[str]:
    return list(_WAY_BACK.get(code, ()))


#: Recovery that applies only when the server qualified the code with a
#: `reason` detail — a generic PERMISSION_DENIED is not a device problem.
_WAY_BACK_REASON: Final[Mapping[tuple[str, str], tuple[str, ...]]] = {
    # The device key is bound to a different account: only a new identity
    # (`device reset`) followed by a fresh sign-in unbinds it (#359).
    ("AI_STP_PERMISSION_DENIED", "device_key_foreign"): (
        "device reset --confirm --json",
        *_LOGIN_ACTIONS,
    ),
}


def _way_back_for(code: str, details: Mapping[str, str]) -> list[str]:
    """Reason-qualified recovery first, then the plain code map."""
    qualified = _WAY_BACK_REASON.get((code, details.get("reason", "")))
    if qualified is not None:
        return list(qualified)
    return _way_back(code)


#: Detail keys a server refusal may carry through to the caller. An allowlist
#: rather than the whole mapping: the details are the server's own text, and a
#: field nobody designed for a reader is how a path, a token or another
#: account's identifier ends up in output that `SPEC-011` REQ-1108 keeps clean.
#: Each of these is a machine-readable binding a caller acts on — which
#: precondition failed, which field was rejected, which revision it expected.
FORWARDED_DETAILS: Final[frozenset[str]] = frozenset(
    {
        "reason",
        "fields",
        "expected",
        "found",
        "supported",
        "capability",
        "authorization_revision",
        "revision",
        "state",
        "allowed",
        "retry_after",
    }
)

#: Bounded, because the length of a server string is not something this process
#: decides. Long enough for a revision or a field list, short enough that a
#: detail cannot become a payload.
DETAIL_LIMIT: Final[int] = 256


def _forwarded(error: Mapping[str, object]) -> dict[str, str]:
    """The server's own bindings, narrowed to the ones a caller can act on.

    The API answers a stale capability with `reason=capability_stale` and a
    rejected body with the exact field paths. None of that used to survive the
    client: the caller was told something failed and had to guess which
    precondition it was.
    """
    details = error.get("details")
    if not isinstance(details, dict):
        return {}
    kept: dict[str, str] = {}
    for name, value in cast(dict[str, object], details).items():
        if name not in FORWARDED_DETAILS:
            continue
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in cast(list[object], value))
        else:
            rendered = str(value)
        kept[str(name)] = rendered[:DETAIL_LIMIT]
    return kept


def failure_from(response: httpx.Response) -> CliFailure:
    """Turn an error response into a registered code.

    The body is the foundation `ErrorEnvelope` by contract, so the code comes
    from the server. An unregistered code is not passed through: the registry is
    closed, and a caller matching on codes must never see one that is not in it.
    """
    code = "AI_STP_DEPENDENCY_UNAVAILABLE"
    message = "the platform reported a failure"
    retryable = response.status_code in RETRYABLE_STATUSES
    reported_details: dict[str, str] = {}
    try:
        envelope = cast(dict[str, object], json.loads(response.text))
        error = cast(dict[str, object], envelope.get("error", {}))
        reported = str(error.get("code", ""))
        if is_registered_code(reported):
            code = reported
            message = str(error.get("message", message))
            retryable = bool(error.get("retryable", retryable))
            reported_details = _forwarded(error)
    except (ValueError, AttributeError, TypeError):
        pass
    return CliFailure(
        code,
        message,
        retryable=retryable,
        details={
            **reported_details,
            "status": str(response.status_code),
            "request_id": response.headers.get(REQUEST_ID_HEADER, ""),
        },
        next_actions=_way_back_for(code, reported_details),
        continuations=login_continuations()
        if code in _ACCOUNT_RESTART
        or (code, reported_details.get("reason", "")) in _WAY_BACK_REASON
        else [],
    )
