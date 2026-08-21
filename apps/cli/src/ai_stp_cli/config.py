"""Reading the global configuration (docs/contracts/cli-config.md, issue #72).

Read-only here on purpose: `#73` owns creating the file, writing it, the secure
credential store and the device identity. What this module must get right is the
*truth* of what is in effect — `SPEC-011` REQ-1116 asks for the effective value
**and** its source, because "20 because that is the default" and "20 because you
wrote 20" lead a caller to different next actions.

So an existing file is read even though none is written. Reporting `default` for
a value the user set would be a confident lie, which is worse than not having
the command.

The field list is closed (`cli-config.md`): an unknown key is a typed error with
its path, never a silent ignore. No secret is representable — cloud credentials
live in the system store, not here.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import yaml

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import config_home, data_home, redact_home, write_private
from ai_stp_contracts.machine_help import ConfigReport, ConfigValue

type ConfigScalar = str | int | bool | list[str] | None


@dataclass(frozen=True)
class Field:
    """One declared configuration field."""

    path: str
    default: ConfigScalar
    summary: str

    #: Whether the value names a filesystem location. Declared rather than
    #: guessed from the field name: rendering folds the home directory away for
    #: exactly these, and a heuristic would silently start or stop covering a
    #: field when someone renamed one.
    is_path: bool = False


def config_path() -> Path:
    """Where the single user configuration file lives, whether or not it exists."""
    return config_home() / "ai-stp" / "config.yaml"


def default_registry_path() -> str:
    """The default local registry location, as a path that can be opened.

    Real, not redacted. Redaction belongs to rendering: a value that has been
    shortened to `~/...` cannot be passed to `Path.exists`, and treating the two
    as one is how `doctor` came to check for a directory literally named `~`.
    """
    return str(data_home() / "ai-stp" / "registry.sqlite")


def declared_fields() -> tuple[Field, ...]:
    """The closed field list, in the order `cli-config.md` states it."""
    return (
        Field("catalog.enabled", True, "Whether the public catalogue is consulted."),
        Field(
            "catalog.url",
            "https://ai-stp.example",
            "Base address of the platform, without the /v1 prefix. HTTPS,"
            " or cleartext to a loopback host for local development.",
        ),
        Field("sync.enabled", False, "Whether cloud synchronisation is on; needs sign-in."),
        Field("registry.path", default_registry_path(), "Where the local registry lives.", True),
        Field("search.result_limit", 20, "Upper bound on candidates in a result."),
        Field("projects.discovery_roots", [], "Explicit roots searched for projects.", True),
        # `ADR-0112`. Off by default and staying off until a consent command
        # says otherwise: writing `true` here directly is refused, because
        # consent is an event and a value edited into a file has no provenance.
        Field("telemetry.enabled", False, "Whether the anonymous install ping is sent."),
        Field(
            "telemetry.url",
            "https://telemetry.ai-stp.example",
            "Where the anonymous install ping goes. HTTPS, or cleartext to a"
            " loopback host for local development, as for the catalogue.",
        ),
    )


def _read_file(path: Path) -> Mapping[str, object]:
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the configuration file is not valid YAML",
            details={"path": str(path), "reason": type(error).__name__},
        ) from error
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the configuration file must contain a mapping",
            details={"path": str(path)},
        )
    document = cast(dict[object, object], loaded)
    return {str(key): value for key, value in document.items()}


def _dotted(document: Mapping[str, object]) -> dict[str, object]:
    """Flatten one level of nesting into the dotted paths the contract names."""
    flat: dict[str, object] = {}
    for key, value in document.items():
        if isinstance(value, dict):
            for inner, item in cast(dict[object, object], value).items():
                flat[f"{key}.{inner}"] = item
        else:
            flat[key] = value
    return flat


ALLOWED_TOP_LEVEL: Final[frozenset[str]] = frozenset(
    {"schema_version", "catalog", "sync", "registry", "search", "projects"}
)

#: The one shape of this file that this build understands. A file claiming
#: another number is refused rather than read optimistically: it was written by a
#: build with different fields, and guessing which ones still mean the same thing
#: is how a setting silently stops applying.
CONFIG_SCHEMA_VERSION: Final[int] = 1

#: Words that must never name a configuration field. Credentials live in the
#: system store (`ADR-0058`), and a field inviting one here would be the first
#: step away from that — including one a user invents.
SECRET_WORDS: Final[tuple[str, ...]] = ("token", "secret", "password", "key", "credential")


def _validate_document(document: Mapping[str, object], path: Path) -> None:
    """Refuse anything the declared fields cannot hold, naming where it is.

    Whole-shape, not just the top level. Checking only the outermost keys let
    `catalog.urll` through — the section is declared, the key inside it is not,
    and after flattening nothing compared the result against the field list. The
    value was then dropped and the default reported as if the file had asked for
    it, which for an agent is a successful-looking write that did nothing.
    """
    declared = {field.path for field in declared_fields()}
    sections: dict[str, set[str]] = {}
    for name in declared:
        section, _, leaf = name.partition(".")
        sections.setdefault(section, set()).add(leaf)

    for key, value in document.items():
        if key == "schema_version":
            if isinstance(value, bool) or not isinstance(value, int):
                raise _refused("schema_version must be a whole number", path, key)
            if value != CONFIG_SCHEMA_VERSION:
                raise _refused(
                    f"this build reads configuration schema {CONFIG_SCHEMA_VERSION}", path, key
                )
            continue
        if key not in sections:
            raise _refused(f"unknown configuration key: {key}", path, key)
        if not isinstance(value, dict):
            raise _refused(f"configuration section {key} must be a mapping", path, key)
        for inner, held in cast(dict[object, object], value).items():
            dotted = f"{key}.{inner}"
            if dotted not in declared:
                raise _refused(f"unknown configuration key: {dotted}", path, dotted)
            if isinstance(held, dict):
                raise _refused(f"configuration value {dotted} must not be a mapping", path, dotted)


def _refused(message: str, path: Path, at: str) -> CliFailure:
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        message,
        details={"path": redact_home(path), "at": at},
        next_actions=["config validate --json"],
    )


def effective_config(overrides: Mapping[str, str] | None = None) -> ConfigReport:
    """The effective configuration, each value with where it came from.

    Precedence is the one `cli-config.md` fixes: default, then the global
    configuration file, then an explicit command argument. The third tier acts
    on this invocation only and never rewrites the file — that is what makes it
    an override rather than a write, and it is why no command in this issue
    writes configuration.
    """
    path = config_path()
    document = _read_file(path)
    supplied = dict(overrides or {})

    _validate_document(document, path)

    declared = {field.path: field for field in declared_fields()}
    unknown_override = sorted(set(supplied) - set(declared))
    if unknown_override:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"unknown configuration key: {unknown_override[0]}",
            details={"allowed": ", ".join(sorted(declared))},
        )

    written = _dotted(document)
    values: list[ConfigValue] = []
    for field in declared.values():
        if field.path in supplied:
            values.append(
                ConfigValue(
                    path=field.path,
                    value=_parse_scalar(supplied[field.path], field),
                    source="command_argument",
                )
            )
        elif field.path in written:
            values.append(
                ConfigValue(
                    path=field.path,
                    value=_as_scalar(written[field.path], field),
                    source="config_file",
                )
            )
        else:
            values.append(ConfigValue(path=field.path, value=field.default, source="default"))

    return ConfigReport(values=values, config_path=str(path) if path.exists() else None)


def for_display(report: ConfigReport) -> ConfigReport:
    """The same configuration with home-path material folded to `~`.

    Applied when rendering, never when reading: `#73` keeps the account name out
    of output, and `doctor` still needs a path it can open. Keeping one value for
    both jobs produced a registry check that could be satisfied by a directory
    named `~` in the working directory.
    """
    paths_by_name = {item.path for item in declared_fields() if item.is_path}
    return report.model_copy(
        update={
            "values": [
                value.model_copy(update={"value": _redacted(value.value)})
                if value.path in paths_by_name
                else value
                for value in report.values
            ],
            "config_path": redact_home(report.config_path) if report.config_path else None,
        }
    )


def _redacted(value: ConfigScalar) -> ConfigScalar:
    if isinstance(value, str):
        return redact_home(value)
    if isinstance(value, list):
        return [redact_home(item) for item in value]
    return value


def _parse_scalar(text: str, field: Field) -> ConfigScalar:
    """Coerce a command-line string into the declared type of `field`.

    A command argument arrives as text; the declared field decides what it
    means. An unparseable value is refused rather than coerced to something
    plausible: `--set search.result_limit=many` must not silently become the
    default.
    """
    if isinstance(field.default, bool):
        lowered = text.strip().lower()
        if lowered in ("true", "yes", "1", "on"):
            return True
        if lowered in ("false", "no", "0", "off"):
            return False
        raise _wrong_type(field, "a true/false value")
    if isinstance(field.default, int):
        try:
            return int(text)
        except ValueError as error:
            raise _wrong_type(field, "a whole number") from error
    if isinstance(field.default, list):
        return [item for item in (part.strip() for part in text.split(",")) if item]
    return text


def _as_scalar(value: object, field: Field) -> ConfigScalar:
    """Accept only what the declared field can hold."""
    if isinstance(field.default, bool):
        if not isinstance(value, bool):
            raise _wrong_type(field, "a true/false value")
        return value
    if isinstance(field.default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            raise _wrong_type(field, "a whole number")
        return value
    if isinstance(field.default, list):
        if not isinstance(value, list):
            raise _wrong_type(field, "a list of strings")
        items = cast(list[object], value)
        if not all(isinstance(item, str) for item in items):
            raise _wrong_type(field, "a list of strings")
        return [str(item) for item in items]
    if not isinstance(value, str):
        raise _wrong_type(field, "a string")
    return value


def _wrong_type(field: Field, expected: str) -> CliFailure:
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        f"configuration value {field.path} must be {expected}",
        details={"path": field.path},
    )


def catalog_and_sync_enabled() -> tuple[bool, bool]:
    """The two switches `capabilities` reports, read through the same path."""
    report = effective_config()
    by_path = {value.path: value.value for value in report.values}
    return bool(by_path["catalog.enabled"]), bool(by_path["sync.enabled"])


def _nested(values: Mapping[str, ConfigScalar]) -> dict[str, object]:
    """Turn dotted paths back into the two-level document the contract names."""
    document: dict[str, object] = {"schema_version": CONFIG_SCHEMA_VERSION}
    for dotted in sorted(values):
        section, _, leaf = dotted.partition(".")
        held = cast(dict[str, object], document.setdefault(section, {}))
        held[leaf] = values[dotted]
    return document


def write_config(values: Mapping[str, ConfigScalar]) -> Path:
    """Replace the configuration file with exactly these declared values.

    A canonical rewrite rather than an in-place edit, and that costs the user
    their comments and ordering — deliberately. This file is written by an agent
    far more often than by a person, and a round-trip editor that preserves
    layout also preserves whatever was wrong with it. Deterministic output means
    two installations configured the same way have byte-identical files, which is
    what makes a difference between them worth looking at.

    Written through the same owner-only atomic primitive as everything else, so a
    failure leaves the previous file intact rather than a truncated one.
    """
    path = config_path()
    rendered = yaml.safe_dump(_nested(values), sort_keys=True, allow_unicode=True)
    write_private(path, rendered)
    return path


def stored_values() -> dict[str, ConfigScalar]:
    """Only what the file actually sets, validated, as dotted paths."""
    path = config_path()
    document = _read_file(path)
    _validate_document(document, path)
    declared = {field.path: field for field in declared_fields()}
    written = _dotted(document)
    return {
        name: _as_scalar(written[name], field)
        for name, field in declared.items()
        if name in written
    }


def _declared_or_refused(dotted: str) -> Field:
    declared = {field.path: field for field in declared_fields()}
    if dotted not in declared:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"unknown configuration key: {dotted}",
            details={"allowed": ", ".join(sorted(declared))},
            next_actions=["config show --json"],
        )
    return declared[dotted]


def set_values(assignments: Mapping[str, str]) -> tuple[Path, tuple[str, ...]]:
    """Write these values, and say which of them actually changed.

    Idempotent: setting a value the file already holds writes the same bytes and
    reports nothing changed, so an agent repeating itself cannot tell one run
    from another by the answer — which is what makes the answer usable.
    """
    if not assignments:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "nothing was set",
            next_actions=["config show --json"],
        )
    held = stored_values()
    changed: list[str] = []
    for dotted, text in assignments.items():
        field = _declared_or_refused(dotted)
        parsed = _parse_scalar(text, field)
        if dotted not in held or held[dotted] != parsed:
            changed.append(dotted)
        held[dotted] = parsed
    return write_config(held), tuple(sorted(changed))


def unset_values(names: tuple[str, ...]) -> tuple[Path, tuple[str, ...]]:
    """Remove these values so the default applies again."""
    if not names:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "nothing was unset",
            next_actions=["config show --json"],
        )
    held = stored_values()
    removed = [name for name in names if _declared_or_refused(name) and name in held]
    for name in removed:
        del held[name]
    return write_config(held), tuple(sorted(removed))


def initialise() -> tuple[Path, bool]:
    """Create the configuration file if it is absent. Never overwrites one.

    Overwriting would discard settings the user relies on, and there is no
    reading of this file that needs it to exist: every field has a default.
    """
    path = config_path()
    if path.exists():
        # Validated rather than assumed sound: `init` on an existing file is
        # what a caller runs when it wants to know the file is usable.
        stored_values()
        return path, False
    return write_config({}), True
