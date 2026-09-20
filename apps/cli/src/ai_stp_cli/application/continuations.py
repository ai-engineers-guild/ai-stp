"""Bind continuation ``argv`` from the registry's declared parameters.

Foundation's ``bound_continuation`` is deliberately declaration-free — it
cannot tell a valued option from a flag, so an empty string collapses into
a bare flag and an explicit ``False`` on a valued option disappears from the
argv entirely. The registry already declares every parameter's kind, value
type and repeatability, and the Click parser enforces the same declaration,
so the executable form is derived from that one source instead of guessed.

Foundation stays independent of the CLI: this adapter lives at the
application boundary and ``bind_continuation`` is what the envelope builders
call. A continuation that names no registered command — or an argument the
descriptor does not declare — keeps the foundation's derivation rather than
failing the envelope that carries it.
"""

from ai_stp_contracts.machine_help import CommandDescriptor, CommandParameter
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.envelope import Continuation, bound_continuation

_descriptors: dict[tuple[str, ...], CommandDescriptor] | None = None


def bind_continuation(item: Continuation) -> Continuation:
    """Fill ``argv`` from the command descriptor; fall back when undeclared."""
    tokens = _declared_argv(item)
    if tokens is None:
        return bound_continuation(item)
    if list(item.argv) == tokens:
        return item
    return item.model_copy(update={"argv": tokens})


def _declared_argv(item: Continuation) -> list[str] | None:
    if item.missing:
        return None
    descriptor = _registry().get(tuple(item.path))
    if descriptor is None:
        return None
    declared = {parameter.name: parameter for parameter in descriptor.parameters}
    tokens = list(item.path)
    for name, value in item.arguments.items():
        parameter = declared.get(name)
        if parameter is None:
            return None
        tokens.extend(_parameter_tokens(parameter, value))
    if "json" not in item.arguments:
        tokens.append("--json")
    return tokens


def _registry() -> dict[tuple[str, ...], CommandDescriptor]:
    """Lazily — ``registry`` is a heavy import and itself imports ``output``."""
    global _descriptors
    if _descriptors is None:
        from ai_stp_cli.registry import descriptors

        _descriptors = {tuple(descriptor.path): descriptor for descriptor in descriptors()}
    return _descriptors


def _parameter_tokens(parameter: CommandParameter, value: JsonValue) -> list[str]:
    flag = f"--{parameter.name}"
    if parameter.kind == "argument":
        values = value if isinstance(value, list) else [value]
        return [str(item) for item in values]
    if parameter.value_type == "boolean":
        if value is True:
            return [flag]
        if value is False:
            return []
        return _flag_value(flag, str(value))
    values = value if isinstance(value, list) else [value]
    tokens: list[str] = []
    for item in values:
        tokens.extend(_flag_value(flag, _text(item)))
    return tokens


def _text(value: JsonValue) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _flag_value(flag: str, text: str) -> list[str]:
    """Dash-prefixed values need ``--flag=value`` so the parser cannot split them."""
    if text.startswith("-"):
        return [f"{flag}={text}"]
    return [flag, text]
