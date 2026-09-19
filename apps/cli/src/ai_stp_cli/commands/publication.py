"""Publication plans. Effects live in `application.publication`."""

from ai_stp_cli.application import publication as _service
from ai_stp_cli.application.publication import confirm, plan, show, validated_attestations


def __getattr__(name: str) -> object:
    return getattr(_service, name)


__all__ = ["confirm", "plan", "show", "validated_attestations"]
