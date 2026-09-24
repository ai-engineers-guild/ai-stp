"""Setup publication commands delegate to the application service."""

from ai_stp_cli.application import setup_publication as _service
from ai_stp_cli.application.setup_publication import confirm, plan


def __getattr__(name: str) -> object:
    return getattr(_service, name)


__all__ = ["confirm", "plan"]
