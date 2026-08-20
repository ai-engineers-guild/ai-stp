"""Canonical CLI/web deep links (SPEC-030, ADR-0064).

The link is a pure projection of typed identity.  It deliberately performs no
catalogue lookup: checking existence here would make an offline orientation
command network-dependent and turn it into an enumeration oracle for private
objects.
"""

from typing import Annotated, Final, Literal, Self, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_foundation.ids import is_valid_id, stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN, VersionError, parse_version

type DeepLinkKind = Literal["component", "setup", "publisher"]
type DeepLinkLocale = Literal["ru", "en"]
type DeepLinkIntent = Literal["view", "report"]

GRAMMAR_VERSION: Final[int] = 1
DEFAULT_LOCALE: Final[DeepLinkLocale] = "ru"

_PREFIX_BY_KIND: Final[dict[str, str]] = {
    "component": "component",
    "setup": "setup",
    "publisher": "account",
}
_COLLECTION_BY_KIND: Final[dict[str, str]] = {
    "component": "components",
    "setup": "setups",
}
_TARGET_ID_PATTERN: Final[str] = (
    "(?:" + "|".join(stable_id_pattern(prefix)[1:-1] for prefix in _PREFIX_BY_KIND.values()) + ")"
)


class DeepLinkTarget(BaseModel):
    """One normalized identity and navigation intent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    grammar_version: Literal[1] = 1
    kind: DeepLinkKind
    stable_id: Annotated[str, Field(pattern=_TARGET_ID_PATTERN)]
    version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    locale: DeepLinkLocale = DEFAULT_LOCALE
    intent: DeepLinkIntent = "view"

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        prefix = _PREFIX_BY_KIND[self.kind]
        if not is_valid_id(self.stable_id, prefix):
            raise ValueError(f"stable_id must use the {prefix}_ canonical form")

        if self.kind == "publisher":
            if self.version is not None:
                raise ValueError("publisher links do not have a version")
            if self.intent != "view":
                raise ValueError("publisher links support only the view intent")
            return self

        if self.version is not None:
            try:
                parse_version(self.version)
            except VersionError as error:
                raise ValueError("version must use canonical X.Y notation") from error
        if self.intent == "report" and self.version is None:
            raise ValueError("report intent requires an exact version")
        return self


class DeepLinkView(BaseModel):
    """A target projected into the web and agent-facing CLI forms."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    target: DeepLinkTarget
    web_url: Annotated[str, Field(min_length=1)]
    cli_argv: Annotated[list[str], Field(min_length=1)]
    cli_command: Annotated[str, Field(min_length=1)]


def build_deep_link(platform_base: str, target: DeepLinkTarget) -> DeepLinkView:
    """Project ``target`` into its canonical URL and CLI reference."""
    base = _base(platform_base)
    route = _route(target)
    path = f"{base.path.rstrip('/')}/{route}" if base.path else f"/{route}"
    fragment = "report" if target.intent == "report" else ""
    web_url = urlunsplit((base.scheme, base.netloc, path, "", fragment))
    argv = canonical_argv(target)
    return DeepLinkView(
        target=target,
        web_url=web_url,
        cli_argv=argv,
        cli_command=" ".join(argv),
    )


def parse_deep_link(platform_base: str, web_url: str) -> DeepLinkTarget:
    """Parse one canonical URL, refusing another origin or non-canonical form."""
    base = _base(platform_base)
    candidate = urlsplit(web_url)
    if candidate.username is not None or candidate.password is not None:
        raise ValueError("deep-link URL must carry no credentials")
    if candidate.query:
        raise ValueError("deep-link URL must carry no query")
    if (candidate.scheme, candidate.netloc) != (base.scheme, base.netloc):
        raise ValueError("deep-link URL must use the configured platform origin")

    path = _relative_path(base.path, candidate.path)
    if "%" in path or "\\" in path:
        raise ValueError("deep-link URL must use canonical unescaped path segments")
    segments = path.split("/") if path else []
    if len(segments) < 3:
        raise ValueError("deep-link URL does not match the canonical grammar")

    locale = segments[0]
    if locale not in {"ru", "en"}:
        raise ValueError("deep-link URL uses an unsupported locale")
    parsed_locale = cast(DeepLinkLocale, locale)

    kind: DeepLinkKind
    stable_id: str
    version: str | None = None
    if len(segments) == 3 and segments[1] == "publishers":
        kind, stable_id = "publisher", segments[2]
    elif len(segments) in {4, 6} and segments[1] == "catalog":
        collection = segments[2]
        if collection == "components":
            kind = "component"
        elif collection == "setups":
            kind = "setup"
        else:
            raise ValueError("deep-link URL uses an unsupported catalog collection")
        stable_id = segments[3]
        if len(segments) == 6:
            if segments[4] != "versions":
                raise ValueError("deep-link URL has a non-canonical version route")
            version = segments[5]
    else:
        raise ValueError("deep-link URL does not match the canonical grammar")

    intent: DeepLinkIntent = "view"
    if candidate.fragment:
        if candidate.fragment != "report" or kind == "publisher" or version is None:
            raise ValueError("deep-link URL uses an unsupported fragment")
        intent = "report"

    return DeepLinkTarget(
        kind=kind,
        stable_id=stable_id,
        version=version,
        locale=parsed_locale,
        intent=intent,
    )


def canonical_argv(target: DeepLinkTarget) -> list[str]:
    """Return a shell-independent, round-trippable CLI reference."""
    argv = [
        "ai-stp",
        "link",
        "web",
        "--kind",
        target.kind,
        "--id",
        target.stable_id,
    ]
    if target.version is not None:
        argv.extend(("--version", target.version))
    argv.extend(("--locale", target.locale))
    if target.intent == "report":
        argv.append("--report")
    argv.append("--json")
    return argv


def _route(target: DeepLinkTarget) -> str:
    if target.kind == "publisher":
        return f"{target.locale}/publishers/{target.stable_id}"
    collection = _COLLECTION_BY_KIND[target.kind]
    route = f"{target.locale}/catalog/{collection}/{target.stable_id}"
    if target.version is not None:
        route = f"{route}/versions/{target.version}"
    return route


def _base(value: str) -> SplitResult:
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("platform base must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("platform base must carry no credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("platform base must carry no query or fragment")
    if "%" in parsed.path or "\\" in parsed.path:
        raise ValueError("platform base path must use canonical path segments")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if any(segment in {".", ".."} for segment in segments):
        raise ValueError("platform base path must contain no traversal segments")
    return SplitResult(parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")


def _relative_path(base_path: str, candidate_path: str) -> str:
    prefix = base_path.rstrip("/")
    if prefix:
        expected = f"{prefix}/"
        if not candidate_path.startswith(expected):
            raise ValueError("deep-link URL is outside the configured platform base path")
        relative = candidate_path.removeprefix(expected)
    else:
        relative = candidate_path.removeprefix("/")
    if not relative or relative.startswith("/") or relative.endswith("/"):
        raise ValueError("deep-link URL path is not canonical")
    return relative
